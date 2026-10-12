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

WORKFLOWS = {"v09-senamhi-avisos-capture.yml": 30, "v09-rain-north.yml": 30, "v08-scheduler-fallback.yml": None}  # nominal minutes


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
    return dict(successful_runs=len(inside), expected_at_nominal=int(hours * 60 / nominal_min) if nominal_min else None,
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
        out += [dict(created_at=x["created_at"], event=x["event"], status=x["status"], conclusion=x["conclusion"]) for x in runs]
        if len(runs) < 100:
            break
        page += 1
    return out


def markdown(report: dict) -> str:
    L = [f"# Continuidad v0.9 · {report['since_utc']} → {report['now_utc']}", "",
         "| Workflow | Correctas | Esperadas (nominal) | Por origen | Hueco máx. | Mediana | P90 | Hueco abierto | Fallidas |",
         "|---|---|---|---|---|---|---|---|---|"]
    for wf, s in report["workflows"].items():
        if "error" in s:
            L.append(f"| {wf} | error: {s['error']} |||||||")
            continue
        f = lambda m: "—" if m is None else f"{m / 60:.1f} h" if m >= 90 else f"{m:.0f} min"
        L.append(f"| {wf} | {s['successful_runs']} | {s['expected_at_nominal'] or '—'} | {', '.join(f'{k} {v}' for k, v in s['by_event'].items()) or '—'} | "
                 f"{f(s['max_gap_min'])} | {f(s['median_gap_min'])} | {f(s['p90_gap_min'])} | {f(s['open_gap_min'])} | {s['failed_runs']} |")
    return "\n".join(L) + "\n"


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
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    print(markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
