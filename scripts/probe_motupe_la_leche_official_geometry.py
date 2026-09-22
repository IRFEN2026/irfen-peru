#!/usr/bin/env python3
"""Fetch bounded official ANA geometry for the Motupe/La Leche research split.

This is a source-discovery/provenance probe only. It does not create an event
footprint, infer an outlet, estimate hydraulic capacity, or open activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://geosnirh.ana.gob.pe/server/rest/services/Mapas_ALA/Capas_ALA_Motupe_Olmos_LaLeche/MapServer"
BASIN_URL = BASE + "/9/query?" + urlencode({
    "where": "CODIGO='137772'",
    "outFields": "*",
    "returnGeometry": "true",
    "outSR": "4326",
    "geometryPrecision": "7",
    "f": "geojson",
})
NETWORK_URL = BASE + "/4/query?" + urlencode({
    "where": "CODIGO_CA LIKE '137772%'",
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
    with urlopen(request, timeout=90) as response:
        payload = response.read()
    data = json.loads(payload.decode("utf-8"))
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("ANA response is not a GeoJSON FeatureCollection")
    return data, payload


def normalized_text(value: object) -> str:
    return str(value or "").strip().lower().replace("í", "i").replace("ó", "o").replace("á", "a").replace("é", "e").replace("ú", "u")


def named_features(features: list[dict], needle: str) -> list[dict]:
    target = normalized_text(needle)
    rows = []
    for feature in features:
        values = [normalized_text(value) for value in (feature.get("properties") or {}).values()]
        if target in values:
            rows.append(feature)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    basin, basin_raw = fetch_geojson(BASIN_URL)
    network, network_raw = fetch_geojson(NETWORK_URL)

    if len(basin["features"]) != 1:
        raise ValueError(f"expected exactly one ANA Cuenca Motupe feature, got {len(basin['features'])}")
    basin_feature = basin["features"][0]
    bp = basin_feature.get("properties") or {}
    if str(bp.get("CODIGO")) != "137772" or normalized_text(bp.get("NOMBRE")) != "cuenca motupe":
        raise ValueError(f"unexpected basin identity: {bp}")
    if (basin_feature.get("geometry") or {}).get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Cuenca Motupe official feature is not polygonal")

    la_leche = named_features(network["features"], "Rio La Leche")
    motupe = named_features(network["features"], "Rio Motupe")
    if not la_leche:
        raise ValueError("official ANA network query returned no Rio La Leche feature")
    if not motupe:
        raise ValueError("official ANA network query returned no Rio Motupe feature")
    for feature in la_leche + motupe:
        if (feature.get("geometry") or {}).get("type") not in {"LineString", "MultiLineString"}:
            raise ValueError("selected official watercourse feature is not linear")

    basin_path = args.out_dir / "ana_cuenca_motupe_137772.geojson"
    network_path = args.out_dir / "ana_motupe_unit_watercourses_137772.geojson"
    basin_path.write_bytes(canonical(basin))
    network_path.write_bytes(canonical(network))

    def compact(feature: dict) -> dict:
        p = feature.get("properties") or {}
        return {
            "geometry_type": (feature.get("geometry") or {}).get("type"),
            "properties": p,
        }

    report = {
        "version": "phase2-motupe-la-leche-official-geometry-probe-v1",
        **GUARDS,
        "status": "PASS_OFFICIAL_GEOMETRY_IDENTITY_PROBE",
        "interpretation": {
            "hydrologic_unit": "ANA unit 137772 is Cuenca Motupe.",
            "la_leche": "Rio La Leche is an official named watercourse within unit 137772; no separate La Leche basin polygon is asserted by this probe.",
            "motupe": "Rio Motupe is an official named watercourse within unit 137772.",
            "pitipo": "Pitipo remains a territorial reference; this probe does not invent a Pitipo hydrologic polygon.",
        },
        "sources": {
            "basin_query_url": BASIN_URL,
            "watercourse_query_url": NETWORK_URL,
            "basin_response_sha256_raw": sha(basin_raw),
            "watercourse_response_sha256_raw": sha(network_raw),
            "basin_canonical_sha256": hashlib.sha256(basin_path.read_bytes()).hexdigest(),
            "watercourse_canonical_sha256": hashlib.sha256(network_path.read_bytes()).hexdigest(),
        },
        "basin": compact(basin_feature),
        "network_feature_count": len(network["features"]),
        "la_leche_feature_count": len(la_leche),
        "motupe_feature_count": len(motupe),
        "la_leche_features": [compact(row) for row in la_leche],
        "motupe_features": [compact(row) for row in motupe],
        "forbidden_inferences": [
            "official basin boundary as event footprint",
            "watercourse line as inundation footprint",
            "faja marginal as event footprint",
            "hydraulic capacity from map geometry",
            "negative control from documentary silence",
            "separate La Leche or Pitipo basin without reproducible official hydrologic boundary",
        ],
    }
    (args.out_dir / "motupe_la_leche_official_geometry_probe.json").write_bytes(canonical(report))
    print(json.dumps({
        "status": report["status"],
        "network_feature_count": report["network_feature_count"],
        "la_leche_feature_count": report["la_leche_feature_count"],
        "motupe_feature_count": report["motupe_feature_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
