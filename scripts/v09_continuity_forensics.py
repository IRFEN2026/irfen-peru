#!/usr/bin/env python3
"""IRFEN v0.9 — forensics of every interval > 90 min between successful runs of the two v0.9 collectors.

Read-only (GitHub API GET + local git history of main). For each interval it separates five components:

  scheduler    nominal cron slots that passed without GitHub creating a run, and how late GitHub created the run
               that closed the interval (minutes after its nominal slot)
  ejecucion    runs created inside the interval that failed or were cancelled; duration of the closing run
  captura      what the closing run's capture recorded: source check ok/errors (avisos), Earthdata contact (IMERG)
  fuente       whether the source had something new: posts first seen at the closing run (avisos), half-hours
               retrieved at the closing run and how long before that run each had ended (IMERG)
  publicacion  minutes from the closing run's creation to its commit on main (data visible in the repository)

    GH_TOKEN=... python scripts/v09_continuity_forensics.py --since 2026-10-13T02:00:00Z [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v09_continuity_report as R  # noqa: E402  (same package of read-only helpers)

COLLECTORS = {
    "v09-senamhi-avisos-capture.yml": dict(minutes=(7, 37), data="data/v09/senamhi_avisos/health_v0_1.json", subject="avisos SENAMHI via INDECI/COEN"),
    "v09-rain-north.yml": dict(minutes=(22, 52), data="data/v09/rain/imerg_early_north_v0_1.json", subject="lluvia IMERG Early zonas norte"),
}
P = R.parse


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args]).decode("utf-8")


def commits(path: str, subject: str, since: datetime) -> list[tuple[datetime, str]]:
    out = []
    # by subject, not by path: a run whose IMERG file did not change still commits (GOES, engine, dashboard)
    for line in git("log", "origin/main", f"--since={since.isoformat()}", "--format=%cI|%H|%s").splitlines():
        t, h, s = line.split("|", 2)
        if subject in s:
            out.append((P(t), h))
    return sorted(out)


def missed_slots(a: datetime, b: datetime, minutes: tuple[int, ...]) -> int:
    t, n = a.replace(second=0, microsecond=0) + timedelta(minutes=1), 0
    while t < b - timedelta(minutes=1):
        if t.minute in minutes:
            n += 1
        t += timedelta(minutes=1)
    return n


def closing_details(wf: str, run: dict, cmts: list, a: datetime) -> dict:
    created = P(run["created_at"])
    c = next(((t, h) for t, h in cmts if created <= t <= created + timedelta(minutes=30)), None)
    out = dict(run_created_utc=run["created_at"], run_minutes=round((P(run["updated_at"]) - created).total_seconds() / 60, 1),
               publication_minutes=round((c[0] - created).total_seconds() / 60, 1) if c else None,
               commit=c[1][:8] if c else None)
    slots = [created.replace(minute=m, second=0, microsecond=0) - timedelta(hours=h) for m in COLLECTORS[wf]["minutes"] for h in (0, 1)]
    out["scheduler_creation_delay_minutes"] = round((created - max(s for s in slots if s <= created)).total_seconds() / 60, 1)
    if not c:
        out["capture"] = "sin commit (sin cambios o no persistido)"
        return out
    doc = json.loads(git("show", f"{c[1]}:{COLLECTORS[wf]['data']}"))
    if wf.startswith("v09-senamhi"):
        lc = doc.get("last_check", {})
        out["capture"] = dict(ok=lc.get("ok"), errors=lc.get("errors"), requests=lc.get("requests"), source_state=doc.get("source_health", {}).get("state"))
        out["source"] = dict(new_posts=lc.get("new_posts"), new_documents=lc.get("new_documents"))
    else:
        st = doc.get("status", {})
        written = st.get("written_at_utc")
        touched = COLLECTORS[wf]["data"] in git("diff-tree", "--no-commit-id", "--name-only", "-r", c[1]).split()
        updated = (created - timedelta(minutes=5) <= P(written) <= c[0]) if written else touched  # older schema: no written_at
        out["capture"] = dict(state=st.get("state") if updated else "SIN_ESTADO_NUEVO (el archivo IMERG no lo reescribió esta ejecución)",
                              status_written_at_utc=written, earthdata_contact=[x.get("ok") for x in st.get("contact_attempts", [])] if updated else None,
                              missing_half_hours_24h=len(st.get("missing_half_hours_24h") or []) if updated else None)
        got = [g for g in doc.get("granules", []) if g.get("retrieved_at_utc") and abs((P(g["retrieved_at_utc"]) - c[0]).total_seconds()) < 1800]
        ends = sorted((created - (P(g["time_utc"]) + timedelta(minutes=30))).total_seconds() / 3600 for g in got)
        # NASA's own latency for IMERG Early is about 4 h: a half-hour that had ended more than 6 h before the run
        # would very likely have been available at an earlier (missed) slot
        out["source"] = dict(half_hours_retrieved=len(got), oldest_end_hours_before_run=round(ends[-1], 1) if ends else None,
                             newest_end_hours_before_run=round(ends[0], 1) if ends else None,
                             retrieved_late_by_missing_runs=sum(1 for h in ends if h > 6))
    return out


def forensics(runs_by_wf: dict, since: datetime, now: datetime) -> dict:
    out = {}
    for wf, runs in runs_by_wf.items():
        cmts = commits(COLLECTORS[wf]["data"], COLLECTORS[wf]["subject"], since - timedelta(hours=12))
        ok = sorted((r for r in runs if r.get("conclusion") == "success"), key=lambda r: r["created_at"])
        rows = []
        for g in R.classify_gaps(runs, since, now):
            a, b = P(g["start_utc"]), P(g["end_utc"])
            row = dict(start_utc=g["start_utc"][:16], end_utc=g["end_utc"][:16], minutes=g["minutes"], open=g["open"],
                       scheduler=dict(missed_cron_slots=missed_slots(a, b, COLLECTORS[wf]["minutes"]), cause=g["cause"]),
                       ejecucion=dict(failed_runs=g["failed_runs"], cancelled_runs=g["cancelled_runs"]))
            closing = next((r for r in ok if P(r["created_at"]) == b), None)
            if closing:
                row.update(closing_details(wf, closing, cmts, a))
            rows.append(row)
        out[wf] = rows
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--repo", default="IRFEN2026/irfen-peru")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GH_TOKEN required (read-only use)")
        return 2
    since, now = P(a.since), datetime.now(timezone.utc)
    runs = {wf: R.fetch_runs(a.repo, wf, since, token) for wf in COLLECTORS}
    rep = forensics(runs, since, now)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(dict(since_utc=since.isoformat(), now_utc=now.isoformat(), collectors=rep), fh, ensure_ascii=False, indent=1)
    for wf, rows in rep.items():
        print(f"## {wf}")
        for r in rows:
            print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
