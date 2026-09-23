#!/usr/bin/env python3
"""Bounded official-ANA probe for Río La Leche watercourse code 1377722.

RESEARCH_ONLY / TEST_ONLY. This bootstrap probes the ANA national Ríos y
Quebradas feature layer by the already documented exact watercourse code. A
successful query is geometry discovery only: it cannot promote candidate
maturity, infer a basin polygon, outlet, event footprint, hydraulic capacity,
negative control, threshold, risk or alert.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]
LAYER = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0"
CODE = "1377722"
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/la_leche_national_watercourse_probe_20260923.json"
SOURCE = ROOT / "site/data/phase2/sources/motupe_la_leche_hydrologic_context/ana_national_rio_la_leche_1377722.geojson"

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


def get_json(url: str, params: dict[str, str], timeout: int = 60) -> tuple[dict, bytes, str]:
    last: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": "IRFEN-research-source-lock/1.0"},
                timeout=(15, timeout),
            )
            response.raise_for_status()
            raw = response.content
            return response.json(), raw, response.url
        except Exception as exc:  # bounded network boundary; result never becomes negative evidence
            last = exc
            if attempt == 1:
                raise RuntimeError(f"OFFICIAL_SOURCE_UNREACHABLE: {type(exc).__name__}: {exc}") from exc
    raise RuntimeError(str(last))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if args.check_only:
        if not EVIDENCE.is_file():
            raise ValueError("probe evidence is not frozen")
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        for key, expected in GUARDS.items():
            if evidence.get(key) != expected:
                raise ValueError(f"guard mismatch: {key}")
        if evidence.get("queried_watercourse_code") != CODE:
            raise ValueError("watercourse code drift")
        status = evidence.get("status")
        if status == "FOUND_EXACT_CODE_FEATURES_PENDING_IDENTITY_REVIEW":
            if not SOURCE.is_file():
                raise ValueError("frozen source geometry missing")
            source = json.loads(SOURCE.read_text(encoding="utf-8"))
            if sha(canonical(source)) != evidence.get("canonical_geojson_sha256"):
                raise ValueError("frozen source canonical SHA-256 mismatch")
            features = source.get("features") or []
            if len(features) != evidence.get("feature_count") or not features:
                raise ValueError("frozen feature-count mismatch")
            for feature in features:
                props = feature.get("properties") or {}
                if str(props.get("CODIGO_CA")) != CODE:
                    raise ValueError("frozen source contains a different watercourse code")
                if (feature.get("geometry") or {}).get("type") not in {"LineString", "MultiLineString"}:
                    raise ValueError("unexpected frozen watercourse geometry type")
        elif status == "ZERO_FEATURES_EXACT_CODE_NO_GEOMETRY_ASSERTED":
            if SOURCE.exists():
                raise ValueError("zero-feature probe must not materialize geometry")
        else:
            raise ValueError(f"unsupported frozen probe status: {status}")
        print(json.dumps({"status": "PASS_FROZEN_LA_LECHE_WATERCOURSE_PROBE", "probe_status": status}, sort_keys=True))
        return 0

    metadata, metadata_raw, metadata_url = get_json(LAYER, {"f": "pjson"})
    if metadata.get("type") != "Feature Layer" or metadata.get("geometryType") != "esriGeometryPolyline":
        raise ValueError("ANA source is not the expected polyline Feature Layer")
    fields = {f.get("name") for f in metadata.get("fields") or []}
    if "CODIGO_CA" not in fields:
        raise ValueError("ANA source schema no longer exposes CODIGO_CA")

    params = {
        "where": f"CODIGO_CA='{CODE}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    data, raw, query_url = get_json(f"{LAYER}/query", params)
    if data.get("type") != "FeatureCollection":
        raise ValueError("ANA query did not return GeoJSON FeatureCollection")
    features = data.get("features") or []
    names = set()
    types = set()
    for feature in features:
        props = feature.get("properties") or {}
        if str(props.get("CODIGO_CA")) != CODE:
            raise ValueError("ANA query returned a different watercourse code")
        gtype = (feature.get("geometry") or {}).get("type")
        if gtype not in {"LineString", "MultiLineString"}:
            raise ValueError(f"unexpected watercourse geometry type: {gtype}")
        for key in ("NOMBRE", "NOMBRE_CA", "NOM_CA", "NOMBRE_RIO"):
            value = props.get(key)
            if value:
                names.add(str(value).strip())
        if props.get("TIPO_CA"):
            types.add(str(props["TIPO_CA"]).strip())

    canonical_sha = sha(canonical(data))
    acquired = datetime.now(timezone.utc).isoformat()
    evidence = {
        "version": "phase2-la-leche-national-watercourse-probe-v0.1",
        "candidate_id": "lambayeque_motupe_la_leche_pitipo",
        "component_id": "la_leche_hydrologic_component",
        **GUARDS,
        "status": "FOUND_EXACT_CODE_FEATURES_PENDING_IDENTITY_REVIEW" if features else "ZERO_FEATURES_EXACT_CODE_NO_GEOMETRY_ASSERTED",
        "queried_watercourse_code": CODE,
        "feature_count": len(features),
        "observed_name_values": sorted(names),
        "observed_type_values": sorted(types),
        "source": {
            "institution": "Autoridad Nacional del Agua / GEOSNIRH ONRH",
            "service": "ONRH/Rios_Quebradas_AAVI/MapServer/0",
            "layer_name": metadata.get("name"),
            "layer_description": metadata.get("description"),
            "layer_geometry_type": metadata.get("geometryType"),
            "layer_spatial_reference": metadata.get("extent", {}).get("spatialReference"),
            "metadata_url": metadata_url,
            "query_url": query_url,
            "metadata_raw_sha256": sha(metadata_raw),
            "query_raw_sha256": sha(raw),
            "canonical_geojson_sha256": canonical_sha,
            "acquired_at_utc": acquired,
        },
        "canonical_geojson_sha256": canonical_sha,
        "geometry_materialized_for_map": False,
        "candidate_maturity_change": "NONE",
        "activation_change": "NONE",
        "interpretation": "Exact-code discovery only. If features are present, they must undergo identity/topology review before any normalized research layer is linked or mapped.",
        "forbidden": [
            "treat the watercourse polyline as a basin polygon",
            "infer an outlet or event footprint",
            "connect Río La Leche to Río Motupe or local quebradas without reproducible topology evidence",
            "infer hydraulic capacity or discharge",
            "infer a negative control from absence of records",
            "derive thresholds, risk levels or alerts",
        ],
    }

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_bytes(canonical(evidence))
    if features:
        SOURCE.parent.mkdir(parents=True, exist_ok=True)
        SOURCE.write_bytes(canonical(data))
    elif SOURCE.exists():
        SOURCE.unlink()
    print(json.dumps({"status": evidence["status"], "feature_count": len(features), "canonical_geojson_sha256": canonical_sha}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
