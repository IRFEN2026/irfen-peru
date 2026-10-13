#!/usr/bin/env python3
"""Respaldo controlado del planificador de GitHub Actions (IRFEN v0.8 + v0.9).

No es un planificador independiente: solo se ejecuta cuando lo lanza el propietario (workflow_dispatch) o cuando
IRFEN2026 abre, edita o reabre la incidencia dedicada (ver .github/workflows/v08-scheduler-fallback.yml). En cada
activación revisa CADA workflow de la lista por separado y lo despacha en `main` solo si:

1. el archivo del workflow existe en `main` (los que aún no se han integrado se omiten, no se despachan);
2. no tiene ninguna ejecución en curso, en cola, en espera o solicitada en `main` (no duplica);
3. su última ejecución en `main`, de cualquier origen, es más antigua que su enfriamiento.

Que otro workflow distinto se haya ejecutado hace poco no impide despachar este. El script nunca cambia guardas,
umbrales, datos ni la rama: solo pide `workflow_dispatch` con ref=main.

  python scripts/scheduler_fallback.py            # runner: GH_TOKEN y GITHUB_REPOSITORY
  python scripts/scheduler_fallback.py --dry-run  # solo informa
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github/workflows"
# workflow file -> minimum seconds since its last run on main before a fallback dispatch
TARGETS = {
    # v0.8 closeout collectors (unchanged cooldowns)
    "igp-cendehua-probe.yml": 5400,
    "goes19-rrqpe-probe.yml": 5400,
    "senamhi-nacara-probe.yml": 5400,
    "imerg-early-probe.yml": 5400,
    "shadow-validation.yml": 7200,
    "official-outcome-evidence.yml": 25200,
    "piura-source-status.yml": 90000,
    "update-and-deploy.yml": 90000,
    "geos-forecast.yml": 90000,
    # v0.9 pilot (cadence 30 min; one hour without any run on main is already a gap)
    "v09-senamhi-avisos-capture.yml": 3600,
    "v09-rain-north.yml": 3600,  # dispatched only once the workflow exists on main
}
ACTIVE_STATUSES = ("queued", "in_progress", "waiting", "requested", "pending")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def decide(workflow: str, cooldown: int, exists_on_main: bool, runs: list[dict], now: datetime) -> tuple[bool, str]:
    """Pure decision for one workflow. `runs` are its most recent runs on main (any event, any status)."""
    if not exists_on_main:
        return False, "NOT_ON_MAIN: workflow file not present on main; not dispatched"
    active = [r for r in runs if r.get("status") in ACTIVE_STATUSES]
    if active:
        return False, f"ACTIVE_RUN: {len(active)} run(s) {sorted({r['status'] for r in active})}; no duplicate dispatch"
    if runs:
        latest = max(runs, key=lambda r: r["created_at"])
        age = (now - parse(latest["created_at"])).total_seconds()
        if age < cooldown:
            return False, f"COOLDOWN: last run {int(age)}s ago ({latest.get('event')}) < {cooldown}s"
        return True, f"STALE: last run {int(age)}s ago ({latest.get('event')}) >= {cooldown}s"
    return True, "NO_RUN_ON_MAIN_YET"


class GitHub:
    def __init__(self, repo: str, token: str):
        self.base = f"https://api.github.com/repos/{repo}"
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "IRFEN-scheduler-fallback"}

    def _call(self, path: str, method: str = "GET", body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method, headers=self.headers)
        with urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    def runs(self, workflow: str) -> list[dict]:
        seen = {}
        for query in ("per_page=5", *(f"status={s}&per_page=5" for s in ("queued", "in_progress", "waiting", "requested", "pending"))):
            try:
                for r in self._call(f"/actions/workflows/{workflow}/runs?branch=main&{query}").get("workflow_runs", []):
                    seen[r["id"]] = dict(status=r["status"], created_at=r["created_at"], event=r["event"])
            except HTTPError as exc:
                if exc.code != 404:
                    raise
        return list(seen.values())

    def dispatch(self, workflow: str) -> None:
        self._call(f"/actions/workflows/{workflow}/dispatches", method="POST", body={"ref": "main"})


def run(api, now: datetime, dry_run: bool, workflows_dir: Path = WORKFLOWS_DIR) -> list[dict]:
    report = []
    for workflow, cooldown in TARGETS.items():
        exists = (workflows_dir / workflow).is_file()
        runs = api.runs(workflow) if exists else []
        go, reason = decide(workflow, cooldown, exists, runs, now)
        if go and not dry_run:
            api.dispatch(workflow)
        report.append(dict(workflow=workflow, dispatched=go and not dry_run, would_dispatch=go, reason=reason))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("GH_TOKEN and GITHUB_REPOSITORY are required")
        return 1
    report = run(GitHub(repo, token), datetime.now(timezone.utc), args.dry_run)
    for row in report:
        print(f"{'DISPATCHED' if row['dispatched'] else ('WOULD_DISPATCH' if row['would_dispatch'] else 'SKIPPED'):14s} "
              f"{row['workflow']:34s} {row['reason']}")
    print(f"::notice title=SCHEDULER_FALLBACK::dispatched={sum(r['dispatched'] for r in report)} "
          f"skipped={sum(not r['would_dispatch'] for r in report)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
