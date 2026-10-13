#!/usr/bin/env python3
"""IRFEN v0.9 — informe de continuidad: huecos reales entre ejecuciones correctas de cada workflow en main.

Sirve para verificar, con datos de la API de GitHub Actions y no con promesas, la cadencia efectiva del piloto
antes y después de activar el disparador externo. Solo lee (GET); no despacha nada.

  GH_TOKEN=... python scripts/v09_continuity_report.py --hours 72            # informe en Markdown
  GH_TOKEN=... python scripts/v09_continuity_report.py --hours 48 --json out.json

Para cada workflow: ejecuciones correctas en la ventana, por origen (schedule, workflow_dispatch, …), hueco máximo,
mediana y percentil 90 de los huecos, y antigüedad de la última ejecución correcta en el momento del informe (que
cuenta como hueco abierto: un dato que no llega es un hueco, no una ausencia de eventos).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

# Nominal minutes between runs (from each workflow's cron; the fallback is ticked every 10 min by the external Worker).
WORKFLOWS = {"v09-senamhi-avisos-capture.yml": 30, "v09-rain-north.yml": 30, "imerg-early-probe.yml": 30,
             "igp-cendehua-probe.yml": 60, "goes19-rrqpe-probe.yml": 60, "shadow-validation.yml": 160,
             "geos-forecast.yml": 1440, "v08-scheduler-fallback.yml": 10}
# Owner's continuity criterion, fixed 13-10-2026 before the active trial: no interval between successful runs above
# 90 min and no improper duplicate (two runs created < 10 min apart, or overlapping). Applied to the v0.9 collectors;
# the other workflows are reported against their own cadence for information.
CRITERION = dict(share_intervals_within_min=90, required_share=1.0, max_gap_min=90, max_duplicates=0, duplicate_window_min=10)
CRITERION_WORKFLOWS = ("v09-senamhi-avisos-capture.yml", "v09-rain-north.yml")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def summarize(runs: list[dict], since: datetime, now: datetime, nominal_min: int | None) -> dict:
    """Pure. runs: GitHub workflow runs (created_at, event, conclusion). Gaps between consecutive successful run
    creations inside [since, now], plus the open gap from the last success to now."""
    ok = sorted(parse(r["created_at"]) for r in runs if r.get("conclusion") == "success")
    before = [t for t in ok if t < since]
    inside = [t for t in ok if since <= t <= now]
    anchors = ([before[-1]] if before else []) + inside
    gaps = [(b - a).total_seconds() / 60 for a, b in zip(anchors, anchors[1:])]
    if not before and inside:  # nothing ran before the window: the stretch from its start to the first success is a gap
        gaps.insert(0, (inside[0] - since).total_seconds() / 60)
    open_gap = (now - anchors[-1]).total_seconds() / 60 if anchors else None
    all_gaps = sorted(gaps + ([open_gap] if open_gap is not None else []))

    def pct(p):
        if not all_gaps:
            return None
        return round(all_gaps[min(len(all_gaps) - 1, int(p * (len(all_gaps) - 1) + 0.5))], 1)

    hours = (now - since).total_seconds() / 3600
    by_event: dict[str, int] = {}
    for r in runs:
        if r.get("conclusion") == "success" and since <= parse(r["created_at"]) <= now:
            by_event[r.get("event", "?")] = by_event.get(r.get("event", "?"), 0) + 1
    within = sum(1 for g in all_gaps if g <= CRITERION["share_intervals_within_min"])
    started = sorted((parse(r["created_at"]), parse(r.get("run_started_at") or r["created_at"]), parse(r.get("updated_at") or r["created_at"]))
                     for r in runs if r.get("conclusion") not in ("cancelled", "skipped") and since <= parse(r["created_at"]) <= now)
    duplicates = sum(1 for a, b in zip(started, started[1:])
                     if (b[0] - a[0]).total_seconds() < CRITERION["duplicate_window_min"] * 60 or b[1] < a[2])
    return dict(successful_runs=len(inside), intervals=len(all_gaps),
                share_intervals_within_90_min=round(within / len(all_gaps), 4) if all_gaps else None, duplicates=duplicates, expected_at_nominal=int(hours * 60 / nominal_min) if nominal_min else None,
                by_event=by_event, max_gap_min=round(max(all_gaps), 1) if all_gaps else None, median_gap_min=pct(0.5),
                p90_gap_min=pct(0.9), open_gap_min=round(open_gap, 1) if open_gap is not None else None,
                last_success_utc=anchors[-1].isoformat() if anchors else None,
                failed_runs=sum(1 for r in runs if r.get("conclusion") == "failure" and since <= parse(r["created_at"]) <= now))


def fetch_runs(repo: str, workflow: str, since: datetime, token: str) -> list[dict]:
    out, page = [], 1
    while page <= 10:
        url = (f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?branch=main&per_page=100&page={page}"
               f"&created=>={(since - timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "irfen-v09-continuity-report"})
        try:
            with urlopen(req, timeout=30) as r:
                body = json.loads(r.read())
        except Exception as exc:  # noqa: BLE001 - a missing workflow is reported, not fatal
            return [dict(error=str(exc))]
        runs = body.get("workflow_runs", [])
        out += [dict(created_at=x["created_at"], event=x["event"], status=x["status"], conclusion=x["conclusion"],
                     run_started_at=x.get("run_started_at"), updated_at=x.get("updated_at")) for x in runs]
        if len(runs) < 100:
            break
        page += 1
    return out


def evaluate(report: dict) -> dict:
    """PASA / NO_PASA per criterion item for each v0.9 collector. Stale-data visibility cannot be measured from
    the Actions API: it is checked by tests/test_v09_dashboard_browser.py (CI) and by inspecting the panel."""
    out = {}
    for wf in CRITERION_WORKFLOWS:
        s = report["workflows"].get(wf) or {}
        if "error" in s or not s.get("intervals"):
            out[wf] = dict(result="SIN_DATOS", detail=s.get("error") or "no successful runs in the window")
            continue
        items = dict(all_intervals_within_90_min=s["share_intervals_within_90_min"] >= CRITERION["required_share"]
                     and s["max_gap_min"] <= CRITERION["max_gap_min"],
                     zero_duplicates=s["duplicates"] <= CRITERION["max_duplicates"])
        out[wf] = dict(result="PASA" if all(items.values()) else "NO_PASA", items=items)
    out["stale_data_visibility"] = dict(result="VERIFICAR", detail="tests/test_v09_dashboard_browser.py en CI + revisión del panel durante el ensayo")
    return out


def markdown(report: dict) -> str:
    f = lambda m: "—" if m is None else f"{m / 60:.1f} h" if m >= 90 else f"{m:.0f} min"
    L = [f"# Continuidad v0.9 · {report['since_utc'][:16]} → {report['now_utc'][:16]} UTC", "",
         f"Criterio (fijado por el propietario antes del ensayo): ningún intervalo entre ejecuciones correctas > "
         f"{CRITERION['max_gap_min']} min (incluidos el inicial y el abierto) y {CRITERION['max_duplicates']} duplicados "
         f"(creadas a < {CRITERION['duplicate_window_min']} min o solapadas). Se aplica a los colectores v0.9.", "",
         "| Workflow | Frecuencia esperada | Ejecuciones esperadas | Ejecuciones reales (correctas) | Por origen | Hueco máximo | Duplicados | % intervalos ≤ 90 min | Resultado |",
         "|---|---|---|---|---|---|---|---|---|"]
    crit = report.get("criterion") or {}
    for wf, s in report["workflows"].items():
        if "error" in s:
            L.append(f"| {wf} | — | — | error: {s['error'][:60]} | | | | | SIN_DATOS |")
            continue
        nominal = WORKFLOWS.get(wf)
        share = s.get("share_intervals_within_90_min")
        result = crit.get(wf, {}).get("result") if wf in CRITERION_WORKFLOWS else "informativo"
        L.append(f"| {wf} | cada {f(nominal) if nominal else '—'} | {s['expected_at_nominal'] or '—'} | {s['successful_runs']} (fallidas {s['failed_runs']}) | "
                 f"{', '.join(f'{k} {v}' for k, v in s['by_event'].items()) or '—'} | {f(s['max_gap_min'])} | {s['duplicates']} | "
                 f"{'—' if share is None else f'{share:.1%}'} | **{result}** |")
    if crit.get("stale_data_visibility"):
        L += ["", f"Visibilidad de datos desactualizados: **{crit['stale_data_visibility']['result']}** — {crit['stale_data_visibility']['detail']}"]
    trace = report.get("fallback_trace")
    if trace is not None:
        L += ["", "## Trazabilidad de los disparos del respaldo", "",
              "| Creada (UTC) | Origen | Lanzada por | Resultado | Workflows despachados |", "|---|---|---|---|---|"]
        for t in trace:
            L.append(f"| {t['created_at'][:19]} | {t['event']} | {t.get('actor') or '—'} | {t.get('conclusion') or t.get('status')} | "
                     f"{'; '.join(t['dispatched']) or '—'} |")
    return "\n".join(L) + "\n"


def fallback_trace(repo: str, since: datetime, token: str, get=None) -> list[dict]:
    """Every fallback run in the window with who started it and what it dispatched (FALLBACK_DISPATCH annotations)."""
    def _get(path):
        req = Request(f"https://api.github.com/repos/{repo}{path}", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                                                           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "irfen-v09-continuity-report"})
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    get = get or _get
    out = []
    runs = get(f"/actions/workflows/v08-scheduler-fallback.yml/runs?branch=main&per_page=100&created=>={since.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    for r in sorted(runs.get("workflow_runs", []), key=lambda x: x["created_at"]):
        dispatched = []
        for job in get(f"/actions/runs/{r['id']}/jobs").get("jobs", []):
            for a in get(f"/check-runs/{job['id']}/annotations"):
                if a.get("title") == "FALLBACK_DISPATCH":
                    dispatched.append(a.get("message", ""))
        out.append(dict(id=r["id"], created_at=r["created_at"], event=r["event"], actor=(r.get("triggering_actor") or {}).get("login"),
                        status=r.get("status"), conclusion=r.get("conclusion"), dispatched=dispatched))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=72)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "IRFEN2026/irfen-peru"))
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GH_TOKEN required (read-only use)")
        return 2
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=args.hours)
    report = dict(now_utc=now.isoformat(), since_utc=since.isoformat(), workflows={})
    for wf, nominal in WORKFLOWS.items():
        runs = fetch_runs(args.repo, wf, since, token)
        report["workflows"][wf] = runs[0] if runs and "error" in runs[0] else summarize(runs, since, now, nominal)
    report["criterion"] = evaluate(report)
    try:
        report["fallback_trace"] = fallback_trace(args.repo, since, token)
    except Exception as exc:  # noqa: BLE001 - the trace is reported as unavailable, never invented
        report["fallback_trace_error"] = f"{type(exc).__name__}: {exc}"[:200]
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    print(markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
