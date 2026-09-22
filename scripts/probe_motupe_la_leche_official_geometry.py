#!/usr/bin/env python3
"""Fetch bounded official ANA basin geometry for Motupe/La Leche research context.

Only the official hydrologic-unit polygon is materialized. Río La Leche and
Río Motupe remain distinct named watercourse components from existing official
evidence; no line geometry or separate La Leche/Pítipo basin is invented.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/la_leche_pacora_pitipo_official_context_1998_2025.json"
BASE = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
BASIN_URL = BASE + "?" + urlencode({
    "where": "NOMBRE='Cuenca Motupe'",
    "outFields": "*",
    "returnGeometry": "true",
    "outSR": "4326",
    "geometryPrecision": "7",
    "f": "geojson",
})

GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_geojson(url: str) -> tuple[dict, bytes]:
    request = Request(url, headers={"User-Agent": "IRFEN-research-source-probe/1.0"})
    with urlopen(request, timeout=45) as response:
        payload = response.read()
    data = json.loads(payload.decode("utf-8"))
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("ANA response is not a GeoJSON FeatureCollection")
    return data, payload


def normalized_text(value: object) -> str:
    return (str(value or "").strip().lower().replace("í", "i").replace("ó", "o")
            .replace("á", "a").replace("é", "e").replace("ú", "u"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    identity = evidence["official_hydrologic_identity"]
    if identity["ana_hydrologic_unit_code"] != "137772" or identity["ana_hydrologic_unit_name"] != "Cuenca Motupe":
        raise ValueError("committed official hydrologic identity changed unexpectedly")
    if identity["la_leche_watercourse_code"] != "1377722" or normalized_text(identity["la_leche_watercourse_name"]) != "rio la leche":
        raise ValueError("committed Rio La Leche identity changed unexpectedly")

    basin, basin_raw = fetch_geojson(BASIN_URL)
    if len(basin["features"]) != 1:
        raise ValueError(f"expected exactly one ANA Cuenca Motupe feature, got {len(basin['features'])}")
    basin_feature = basin["features"][0]
    bp = basin_feature.get("properties") or {}
    if str(bp.get("CODIGO")) != "137772" or normalized_text(bp.get("NOMBRE")) != "cuenca motupe":
        raise ValueError(f"unexpected basin identity: {bp}")
    if (basin_feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Cuenca Motupe official feature is not polygonal")

    basin_path = args.out_dir / "ana_cuenca_motupe_137772.geojson"
    basin_path.write_bytes(canonical(basin))
    report = {
        "version": "phase2-motupe-la-leche-official-geometry-probe-v2",
        **GUARDS,
        "status": "PASS_OFFICIAL_BASIN_GEOMETRY_IDENTITY_PROBE",
        "interpretation": {
            "hydrologic_unit": "ANA unit 137772 is Cuenca Motupe and is the only polygon materialized by this probe.",
            "la_leche": "Committed official evidence identifies Rio La Leche (watercourse 1377722) within unit 137772; no separate La Leche basin polygon is asserted.",
            "motupe": "Motupe remains a named river/system component inside the official Cuenca Motupe context; no river-line geometry is asserted by this probe.",
            "pitipo": "Pitipo remains a territorial reference; this probe does not invent a Pitipo hydrologic polygon.",
        },
        "sources": {
            "basin_query_url": BASIN_URL,
            "basin_response_sha256_raw": sha(basin_raw),
            "basin_canonical_sha256": hashlib.sha256(basin_path.read_bytes()).hexdigest(),
            "identity_evidence_path": EVIDENCE.relative_to(ROOT).as_posix(),
            "identity_evidence_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
        },
        "basin": {
            "geometry_type": (basin_feature.get("geometry") or {}).get("type"),
            "properties": bp,
        },
        "watercourse_geometry_materialized": False,
        "separate_la_leche_basin_geometry_materialized": False,
        "pitipo_hydrologic_geometry_materialized": False,
        "forbidden_inferences": [
            "official basin boundary as event footprint",
            "watercourse identity as an invented line geometry",
            "faja marginal as event footprint",
            "hydraulic capacity from map geometry",
            "negative control from documentary silence",
            "separate La Leche or Pitipo basin without reproducible official hydrologic boundary",
        ],
    }
    (args.out_dir / "motupe_la_leche_official_geometry_probe.json").write_bytes(canonical(report))
    print(json.dumps({
        "status": report["status"],
        "basin_code": str(bp.get("CODIGO")),
        "basin_name": bp.get("NOMBRE"),
        "watercourse_geometry_materialized": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
