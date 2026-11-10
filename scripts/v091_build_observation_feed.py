#!/usr/bin/env python3
"""IRFEN v0.9.1: research-only live SOURCE HEALTH feed, built from existing archives.

This script DOES NOT fetch remote endpoints, publish a site, predict hazards or
update checkpoint hazard colors. It is designed as a bounded post-capture step.
Run on an authorized research runner against a fresh checkout of the archive.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SOURCES = (
    dict(id="avisos_indeci_coen", label="Avisos oficiales vía INDECI/COEN",
         path="data/v09/senamhi_avisos/health_v0_1.json",
         time_path=("source_health", "last_successful_check_utc"),
         freshness_minutes=180, coverage="documentos oficiales capturados", mode="REPEATED"),
    dict(id="imerg_early_north", label="NASA IMERG Early · zonas norte",
         path="data/v09/rain/imerg_early_north_v0_1.json",
         time_path=("status", "latest_granule_start_utc"),
         # when the last capture failed the status block carries only the error: use the newest archived granule
         fallback_list=("granules", "time_utc"),
         freshness_minutes=720, coverage="zonas norte archivadas", mode="REPEATED"),
    dict(id="goes19_rrqpe_north", label="NOAA GOES-19 RRQPE · zonas norte",
         path="data/v09/rain/goes19_rrqpe_north_v0_1.json",
         time_path=("status", "latest_scan_end"),
         # a failed sampling run (e.g. NO_RECENT_RRQPE_OBJECTS, 02-11 20:24 UTC) leaves only the error: use the newest archived scan
         fallback_list=("scans", "scan_end"),
         freshness_minutes=90, coverage="zonas norte archivadas", mode="REPEATED"),
    dict(id="imerg_early_coast_snapshot", label="NASA IMERG Early · toda la costa",
         path="data/v09/research/coast_rain/imerg_early_coast_snapshot_v0_1.json",
         time_path=("windows_end_utc",),
         freshness_minutes=720, coverage="costa Tumbes–Tacna; solo instantánea",
         mode="SNAPSHOT_ONLY"),
)

def parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, OverflowError):
        return None

def pick(data, keys):
    obj = data
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj

def examine(spec, root, now):
    rel = spec["path"]
    row = dict(id=spec["id"], label=spec["label"], archive_path=rel,
               coverage=spec["coverage"], cadence=spec["mode"],
               status="UNKNOWN", source_time_utc=None, age_minutes=None,
               reason="Archivo no inspeccionado")
    try:
        payload = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        row["reason"] = "Archivo ausente o ilegible; nunca interpretar como ausencia de lluvia/avisos"
        return row
    if payload.get("production_use") is not False or payload.get("deployment_status", "RESEARCH_ONLY") != "RESEARCH_ONLY":
        row["status"] = "INVALID_GUARD"
        row["reason"] = "Contratos de investigación no satisfechos"
        return row
    timestamp = pick(payload, spec["time_path"])
    state = pick(payload, ("status", "state"))
    if isinstance(state, str):
        row["capture_state"] = state
    if timestamp is None and spec.get("fallback_list"):
        lst, key = spec["fallback_list"]
        items = payload.get(lst) if isinstance(payload.get(lst), list) else []
        times = [parse_time(x.get(key)) for x in items if isinstance(x, dict)]
        times = [t for t in times if t]
        if times:
            timestamp = max(times).isoformat()
            row["time_basis"] = "último dato archivado (la última captura no dejó estado)"
    # Coast snapshot stores per-window timestamps as a mapping; choose the
    # newest valid ending time solely for the SOURCE, not for each rain window.
    if isinstance(timestamp, dict):
        dt_values = [parse_time(v) for v in timestamp.values()]
        timestamp = max((v for v in dt_values if v), default=None)
    else:
        timestamp = parse_time(timestamp)
    if not timestamp:
        row["reason"] = "Marca temporal de observación/captura inexistente o inválida"
        return row
    row["source_time_utc"] = timestamp.isoformat().replace("+00:00", "Z")
    age = (now - timestamp).total_seconds() / 60
    row["age_minutes"] = round(age, 1)
    if age < -2:
        row["status"] = "INVALID_TIME"
        row["reason"] = "Fecha futura respecto al instante de evaluación"
    elif spec["mode"] == "SNAPSHOT_ONLY":
        row["status"] = "SNAPSHOT_ONLY"
        row["reason"] = "Solo captura histórica: no afirmar actualización continua"
    elif age > spec["freshness_minutes"]:
        row["status"] = "STALE"
        row["reason"] = "La observación excede su antigüedad máxima"
    else:
        row["status"] = "RECENT_ARCHIVED"
        row["reason"] = "Registro reciente archivado; NO es medición en vivo garantizada"
    return row

def build(root, now):
    rows = [examine(spec, root, now) for spec in SOURCES]
    return dict(schema_version="irfen_v091_observation_feed_v0_1",
        deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
        production_use=False, public_alerting=False, notifications_enabled=False,
        predictive=False, map_publishable=False, activation_gate="BLOCKED",
        missing_data_rule="UNKNOWN_NOT_LOW_RISK",
        assessment_time_utc=now.isoformat().replace("+00:00", "Z"),
        sources=rows,
        semaforo_policy=("El estado de fuente es independiente de los colores de peligro. "
          "No generar VERDE/AMARILLO/ROJO con este archivo; exigir evaluación "
          "local y observaciones oficiales documentadas para confirmar eventos."),
        note=("Estado de capturas archivadas: no indica condiciones actuales "
              "de crecida, desborde o activación de quebradas."))

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", type=Path, default=Path("data/v09/research/live/observation_feed_v0_1.json"))
    p.add_argument("--as-of", help="Hora de evaluación ISO-8601 con zona; para QA reproducible")
    p.add_argument("--check", action="store_true")
    ns = p.parse_args(argv)
    now = parse_time(ns.as_of) if ns.as_of else datetime.now(timezone.utc)
    if not now:
        p.error("--as-of requiere fecha ISO-8601 con zona horaria")
    out = build(ns.root, now)
    target = ns.output if ns.output.is_absolute() else ns.root / ns.output
    serialized = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if ns.check:
        return 0 if target.is_file() and target.read_text(encoding="utf-8") == serialized else 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized, encoding="utf-8")
    print(json.dumps(dict(output=str(target), statuses={x["id"]: x["status"] for x in out["sources"]}), ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
