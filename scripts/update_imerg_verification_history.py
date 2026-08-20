#!/usr/bin/env python3
"""Añade observaciones IMERG nuevas al histórico científico inmutable.

La ventana móvil es solo una entrada de adquisición. Los valores ya archivados
nunca se reemplazan: una discrepancia para la misma clave hace fallar la corrida.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "site/data/latest.json"
DEFAULT_HISTORY = ROOT / "site/data/forecast/imerg_verification_history.json"
PILOT_METHODS = {
    "san_ildefonso": "validated_dem_polygon",
    "chosica": "validated_dem_polygon",
    "catacaos": "provisional_weighted_operational_sampling_areas",
}


class HistoryUpdateError(ValueError):
    pass


def validate_source_window(window):
    """Reject non-scientific, static, or DEMO windows before any mutation."""
    source = str(window.get("source") or "")
    warning = str(window.get("warning") or "")
    acquisition_mode = str(window.get("acquisition_mode") or "")
    markers = " ".join((source, warning, acquisition_mode)).upper()
    if "DEMO" in markers:
        raise HistoryUpdateError("latest.json DEMO no puede incorporarse al histórico científico")
    if "STATIC_FALLBACK" in markers or "FALLBACK ESTÁTICO" in markers:
        raise HistoryUpdateError("latest.json con fallback estático no puede incorporarse")
    if window.get("fallback_used") is True:
        raise HistoryUpdateError("latest.json marcado fallback_used=true no puede incorporarse")
    if window.get("product") != "GPM_3IMERGDL":
        raise HistoryUpdateError("latest.json no declara el producto científico GPM_3IMERGDL")
    if not source or "NASA" not in source.upper() or "IMERG" not in source.upper():
        raise HistoryUpdateError("latest.json no acredita adquisición NASA IMERG directa")
    if not window.get("generated_at"):
        raise HistoryUpdateError("latest.json no declara generated_at trazable")


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit():
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "UNKNOWN"


def relative(path: Path):
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def observed_series(zone, sampling_method):
    if sampling_method == "validated_dem_polygon":
        polygon = zone.get("experimental_polygon") or {}
        if polygon.get("production_use") is not False:
            return []
        return polygon.get("series") or []
    return zone.get("series") or []


def candidates_from_window(window):
    validate_source_window(window)
    zones = {row.get("id"): row for row in window.get("zones") or []}
    if set(zones) != set(PILOT_METHODS):
        raise HistoryUpdateError(f"La ventana no contiene exactamente los tres pilotos: {sorted(zones)}")
    candidates = []
    for zone_id, method in PILOT_METHODS.items():
        for row in observed_series(zones[zone_id], method):
            if row.get("date") and row.get("rain_mm") is not None:
                candidates.append({
                    "zone_id": zone_id,
                    "sampling_method": method,
                    "valid_date_utc": row["date"],
                    "observed_imerg_mm": round(float(row["rain_mm"]), 3),
                })
    return candidates


def append_observations(history, candidates, source_evidence, recorded_at=None):
    recorded_at = recorded_at or datetime.now(timezone.utc).isoformat()
    retention = history.get("retention_policy") or {}
    if history.get("production_use") is not False or retention.get("mode") != "APPEND_ONLY":
        raise HistoryUpdateError("El histórico no satisface la guarda APPEND_ONLY/TEST_ONLY")
    if source_evidence.get("fallback_used") is not False:
        raise HistoryUpdateError("Un fallback no puede incorporarse como evidencia científica")
    evidence_id = source_evidence.get("evidence_id")
    if not evidence_id:
        raise HistoryUpdateError("La procedencia requiere evidence_id")

    # Runtime acquisition is append-only for observations and evidence. It has
    # no code path capable of creating, editing, or deleting tombstones.
    withdrawals_before = copy.deepcopy(history.get("withdrawals") or [])
    existing = {}
    for row in history.get("observations") or []:
        key = (row.get("zone_id"), row.get("sampling_method"), row.get("valid_date_utc"))
        if key in existing:
            raise HistoryUpdateError(f"Histórico duplicado antes de actualizar: {key}")
        existing[key] = row

    incoming = {}
    for row in candidates:
        key = (row.get("zone_id"), row.get("sampling_method"), row.get("valid_date_utc"))
        if PILOT_METHODS.get(key[0]) != key[1]:
            raise HistoryUpdateError(f"Contrato espacial inesperado: {key}")
        value = round(float(row["observed_imerg_mm"]), 3)
        if key in incoming and incoming[key] != value:
            raise HistoryUpdateError(f"Conflicto dentro de la ventana: {key}")
        incoming[key] = value

    additions = []
    identical = 0
    for key, value in sorted(incoming.items()):
        prior = existing.get(key)
        if prior is not None:
            if round(float(prior["observed_imerg_mm"]), 3) != value:
                raise HistoryUpdateError(
                    f"Conflicto append-only para {key}: {prior['observed_imerg_mm']} != {value}"
                )
            identical += 1
            continue
        additions.append({
            "zone_id": key[0],
            "sampling_method": key[1],
            "valid_date_utc": key[2],
            "observed_imerg_mm": value,
            "provenance_evidence_id": evidence_id,
        })

    before = len(existing)
    history.setdefault("source_evidence", [])
    if not any(row.get("evidence_id") == evidence_id for row in history["source_evidence"]):
        history["source_evidence"].append(source_evidence)
    history.setdefault("observations", []).extend(additions)
    history["observations"].sort(
        key=lambda row: (row["valid_date_utc"], row["zone_id"], row["sampling_method"])
    )
    after = len(history["observations"])
    dates = sorted(row["valid_date_utc"] for row in history["observations"])
    event = {
        "event_id": f"append-{evidence_id}",
        "event_type": "APPEND_FROM_DIRECT_IMERG_ACQUISITION",
        "recorded_at": recorded_at,
        "evidence_id": evidence_id,
        "observations_before": before,
        "candidate_observations": len(incoming),
        "identical_observations_deduplicated": identical,
        "observations_added": len(additions),
        "observations_after": after,
        "minimum_valid_date_utc": dates[0] if dates else None,
        "maximum_valid_date_utc": dates[-1] if dates else None,
        "fallback_used": False,
    }
    history.setdefault("change_log", []).append(event)
    history["last_updated_at"] = recorded_at
    history["summary"] = {
        "observation_count": after,
        "pilot_count": len(PILOT_METHODS),
        "withdrawal_count": len(history.get("withdrawals") or []),
        "minimum_valid_date_utc": dates[0] if dates else None,
        "maximum_valid_date_utc": dates[-1] if dates else None,
    }
    if (history.get("withdrawals") or []) != withdrawals_before:
        raise HistoryUpdateError("La adquisición automática no puede modificar tombstones")
    return event


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    return parser.parse_args()


def main():
    args = parse_args()
    window = json.loads(args.source.read_text(encoding="utf-8"))
    history = json.loads(args.history.read_text(encoding="utf-8"))
    source_hash = sha256_file(args.source)
    run_id = os.environ.get("GITHUB_RUN_ID") or f"local-{source_hash[:12]}"
    source_evidence = {
        "evidence_id": f"direct-imerg-{run_id}",
        "source_kind": "DIRECT_NASA_IMERG_LATE_ACQUISITION",
        "input_path": relative(args.source),
        "input_sha256": source_hash,
        "dataset": window.get("product") or "GPM_3IMERGDL",
        "source_generated_at": window.get("generated_at"),
        "workflow_name": os.environ.get("GITHUB_WORKFLOW", "LOCAL_REPRODUCIBLE_BUILD"),
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_run_number": os.environ.get("GITHUB_RUN_NUMBER"),
        "main_commit": current_commit(),
        "acquisition_mode": "DIRECT_NASA_EARTHDATA",
        "fallback_used": False,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    event = append_observations(
        history, candidates_from_window(window), source_evidence,
        recorded_at=source_evidence["recorded_at"],
    )
    args.history.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(event, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
