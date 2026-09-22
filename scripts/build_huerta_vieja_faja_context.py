#!/usr/bin/env python3
"""Build the Phase-2 Huerta Vieja official faja-marginal context geometry.

This builder is deliberately narrow: it transforms the frozen ANA hito tables to two
separate WGS84 LineStrings. It never closes them into a polygon and never interprets the
faja marginal as a catchment, event footprint, hydraulic capacity or operational threshold.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/huerta_vieja_faja_context/ana_huerta_vieja_faja_hitos_v0_1.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_huerta_vieja_faja_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_huerta_vieja_geometry_validation.json"

EXPECTED_LEFT_IDS = [f"HI-{i}" for i in range(1, 19)]
EXPECTED_RIGHT_IDS = [f"HD-{i}" for i in range(1, 22)]


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def canonical_bytes(document: dict) -> bytes:
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def assert_guards(source: dict) -> None:
    assert source["candidate_id"] == "lima_norte_huerta_vieja"
    assert source["deployment_status"] == "RESEARCH_ONLY"
    assert source["test_mode"] == "TEST_ONLY"
    assert source["production_use"] is False
    assert source["production_ready"] is False
    assert source["operational_alerting_enabled"] is False
    assert source["activation_gate"] == "BLOCKED"
    assert source["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert source["decision_thresholds"] is None
    assert source["hydraulic_factors"] is None
    assert source["source"]["resolution_id"] == "ANA-RD-0690-2025-AAACF"
    assert source["source"]["technical_report_id"] == "ANA-IT-0112-2024-AAA-CF-MCFS"
    assert source["source"]["epsg"] == 32718
    assert source["source_interpretation"]["not_catchment"] is True
    assert source["source_interpretation"]["not_event_footprint"] is True
    assert source["source_interpretation"]["not_historical_hydraulic_capacity"] is True
    assert source["source_interpretation"]["not_operational_threshold"] is True
    assert source["source_interpretation"]["candidate_wide_sampling_ready"] is False
    assert source["source_interpretation"]["counts_as_complete_candidate_geometry"] is False


def validate_hitos(rows: list[dict], expected_ids: list[str]) -> None:
    assert [row["id"] for row in rows] == expected_ids
    assert len({(row["easting_m"], row["northing_m"]) for row in rows}) == len(rows)
    for row in rows:
        assert 290000 <= row["easting_m"] <= 310000
        assert 8690000 <= row["northing_m"] <= 8720000


def build_geometry(source: dict) -> dict:
    left = source["left_margin"]
    right = source["right_margin"]
    validate_hitos(left, EXPECTED_LEFT_IDS)
    validate_hitos(right, EXPECTED_RIGHT_IDS)
    transformer = Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True)

    def coords(rows: list[dict]) -> list[list[float]]:
        out = []
        for row in rows:
            lon, lat = transformer.transform(row["easting_m"], row["northing_m"])
            out.append([round(lon, 7), round(lat, 7)])
        return out

    common = {
        "candidate_id": "lima_norte_huerta_vieja",
        "source_ids": ["ANA-RD-0690-2025-AAACF", "ANA-IT-0112-2024-AAA-CF-MCFS"],
        "representation": "OFFICIAL_FAJA_MARGINAL_HITO_ALIGNMENT",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "not_catchment": True,
        "not_event_footprint": True,
        "not_historical_hydraulic_capacity": True,
        "candidate_wide_sampling_ready": False,
        "counts_as_complete_candidate_geometry": False,
        "map_role": "RESEARCH_CONTEXT_ONLY"
    }
    features = [
        {
            "type": "Feature",
            "properties": {**common, "unit_id": "huerta_vieja_faja_left_margin", "margin": "LEFT", "hito_count": len(left)},
            "geometry": {"type": "LineString", "coordinates": coords(left)}
        },
        {
            "type": "Feature",
            "properties": {**common, "unit_id": "huerta_vieja_faja_right_margin", "margin": "RIGHT", "hito_count": len(right)},
            "geometry": {"type": "LineString", "coordinates": coords(right)}
        }
    ]
    return {
        "type": "FeatureCollection",
        "properties": {
            "candidate_id": "lima_norte_huerta_vieja",
            "title": "Quebrada Huerta Vieja · alineamientos oficiales de faja marginal",
            "deployment_status": "RESEARCH_ONLY",
            "test_mode": "TEST_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "decision_thresholds": None,
            "hydraulic_factors": None,
            "geometry_status": "PARTIAL_NON_CATCHMENT_CONTEXT",
            "representation": "TWO_SEPARATE_OFFICIAL_FAJA_MARGIN_ALIGNMENTS",
            "not_catchment": True,
            "not_event_footprint": True,
            "not_historical_hydraulic_capacity": True,
            "candidate_wide_sampling_ready": False,
            "counts_as_complete_candidate_geometry": False,
            "default_visibility": False,
            "source_ids": ["ANA-RD-0690-2025-AAACF", "ANA-IT-0112-2024-AAA-CF-MCFS"]
        },
        "features": features
    }


def build_validation(source: dict, geometry_bytes: bytes) -> dict:
    return {
        "version": "phase2-huerta-vieja-geometry-validation-v1",
        "candidate_id": "lima_norte_huerta_vieja",
        "status": "PASS_PARTIAL_OFFICIAL_FAJA_CONTEXT_GEOMETRY",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "source_snapshot_path": str(SOURCE.relative_to(ROOT)),
        "source_snapshot_sha256": file_sha256(SOURCE),
        "normalized_geometry_path": str(GEOMETRY.relative_to(ROOT)),
        "normalized_geometry_sha256": sha256(geometry_bytes).hexdigest(),
        "source_crs": "EPSG:32718",
        "normalized_crs": "EPSG:4326",
        "left_margin_hito_count": 18,
        "right_margin_hito_count": 21,
        "feature_count": 2,
        "geometry_types": ["LineString"],
        "component_resolution": {
            "left_faja_margin_alignment": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "right_faja_margin_alignment": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "catchment": "UNRESOLVED_NOT_DERIVED_FROM_FAJA",
            "event_footprint": "NOT_ASSERTED",
            "historical_hydraulic_capacity": "UNKNOWN_NOT_INFERRED",
            "observed_event": "NOT_ASSERTED"
        },
        "counts_as_complete_candidate_geometry": False,
        "candidate_wide_sampling_ready": False,
        "artificial_polygon_or_connector_used": False,
        "document_text_count_inconsistency_preserved": source["source_interpretation"]["document_text_count_inconsistency"]["present"]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert_guards(source)
    geometry = build_geometry(source)
    geometry_bytes = canonical_bytes(geometry)
    validation = build_validation(source, geometry_bytes)
    validation_bytes = canonical_bytes(validation)

    if args.check_only:
        if not GEOMETRY.is_file() or GEOMETRY.read_bytes() != geometry_bytes:
            raise SystemExit("Huerta Vieja normalized geometry is missing or stale")
        if not VALIDATION.is_file() or VALIDATION.read_bytes() != validation_bytes:
            raise SystemExit("Huerta Vieja geometry validation record is missing or stale")
        return 0

    GEOMETRY.parent.mkdir(parents=True, exist_ok=True)
    GEOMETRY.write_bytes(geometry_bytes)
    VALIDATION.write_bytes(validation_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
