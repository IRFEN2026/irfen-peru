"""Ejecución reproducible y offline: registro de lecturas + serie de celdas IMERG → pares, evaluación y calibración.

    python -m irfen_gauge_imerg.run_pipeline --ledger L.json [--cells C.json] --use metrics --out-dir salida/

Sin ``--cells`` se evalúa solo la elegibilidad (útil cuando aún no hay HDF5): todo par queda rechazado y la
calibración BLOQUEADA, con el motivo exacto. El manifiesto de ejecución guarda el SHA-256 de cada entrada y de cada
módulo del paquete, para reproducir el resultado byte a byte con ``--fixed-time``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from . import GUARDS, SCHEMA_VERSION
from .calibrate import calibrate
from .evaluate import evaluate
from .observations import check_ledger
from .pairing import build_pairs

PKG = Path(__file__).resolve().parent


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _dump(obj, path: Path):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str, sort_keys=False) + "\n",
                    encoding="utf-8")


def empty_series() -> dict:
    return {"schema": "irfen.gauge_imerg.cell_series", "schema_version": SCHEMA_VERSION, "stations": {},
            "granules": [], "read_errors": [], "provenance": {"tool": "none", "note": "SIN_HDF5_LOCALES"}}


def run(ledger_path: Path, cells_path: Path | None, use: str, family: str, out_dir: Path,
        fixed_time: str | None = None) -> dict:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    series = json.loads(cells_path.read_text(encoding="utf-8")) if cells_path else empty_series()
    out_dir.mkdir(parents=True, exist_ok=True)
    elig = check_ledger(ledger)
    elig_doc = {"schema": "irfen.gauge_imerg.eligibility", "schema_version": SCHEMA_VERSION,
                "observations": {k: {**v, "window_start_utc": v["window_start_utc"] and v["window_start_utc"].isoformat(),
                                     "window_end_utc": v["window_end_utc"] and v["window_end_utc"].isoformat()}
                                 for k, v in elig.items()},
                "counts": {u: sum(1 for v in elig.values() if v[u]) for u in ("exploratory", "metrics", "calibration")}}
    pairs = build_pairs(ledger, series, {"use": use, "family": family})
    ev = evaluate(pairs)
    cal = calibrate(pairs)
    _dump(elig_doc, out_dir / "eligibility.json")
    _dump(pairs, out_dir / "pairs.json")
    _dump(ev, out_dir / "evaluation.json")
    _dump(cal, out_dir / "calibration.json")
    manifest = {
        "schema": "irfen.gauge_imerg.run_manifest", "schema_version": SCHEMA_VERSION, "guards": GUARDS,
        "generated_at_utc": fixed_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": platform.python_version(), "use": use, "family": family,
        "inputs": {"ledger": {"path": ledger_path.name, "sha256": _sha_file(ledger_path)},
                   "cells": ({"path": cells_path.name, "sha256": _sha_file(cells_path)} if cells_path else None)},
        "code_sha256": {p.name: _sha_file(p) for p in sorted(PKG.glob("*.py"))},
        "outputs": {n: _sha_file(out_dir / n) for n in ("eligibility.json", "pairs.json", "evaluation.json",
                                                         "calibration.json")},
        "summary": {**pairs["summary"], "eligibility": elig_doc["counts"], "calibration_status": cal["status"]},
    }
    _dump(manifest, out_dir / "run_manifest.json")
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--cells", type=Path)
    ap.add_argument("--use", default="metrics", choices=("exploratory", "metrics", "calibration"))
    ap.add_argument("--family", default="EARLY:V07")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--fixed-time", default=None, help="sello de tiempo fijo para salidas reproducibles")
    a = ap.parse_args(argv)
    m = run(a.ledger, a.cells, a.use, a.family, a.out_dir, a.fixed_time)
    print(json.dumps(m["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
