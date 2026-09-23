#!/usr/bin/env python3
"""Build official Jacayita faja-margin research context for Phase 2.

Transforms the ANA RD 0396-2025 official UTM hito tables into four separate WGS84
LineStrings: main-channel right/left margins and Aportante 1 right/left margins. It
never closes the lines, derives a catchment/event footprint, infers hydraulic
capacity, or connects Jacayita to Rio Canete or other tributary ravines.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/canete_jacayita_faja_context/ana_jacayita_faja_hitos_v0_1.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_sur_canete_jacayita_faja_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_sur_canete_jacayita_faja_context_validation.json"
EXPECTED = {
    "main_right": [f"HD-{i}" for i in range(1, 22)],
    "main_left": [f"HI-{i}" for i in range(1, 23)],
    "aportante_right": [f"HD-AP-{i}" for i in range(1, 11)],
    "aportante_left": [f"HI-AP-{i}" for i in range(1, 10)],
}


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def assert_guards(source: dict) -> None:
    assert source["candidate_id"] == "lima_sur_canete"
    assert source["component_id"] == "jacayita"
    assert source["deployment_status"] == "RESEARCH_ONLY"
    assert source["test_mode"] == "TEST_ONLY"
    assert source["production_use"] is False
    assert source["production_ready"] is False
    assert source["operational_alerting_enabled"] is False
    assert source["activation_gate"] == "BLOCKED"
    assert source["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert source["decision_thresholds"] is None
    assert source["hydraulic_factors"] is None
    assert source["source"]["source_id"] == "ANA-JACAYITA-FAJA-RD0396-2025"
    assert source["source"]["sigrid_document_id"] == 18856
    assert source["source"]["epsg"] == 32718
    interpretation = source["source_interpretation"]
    assert interpretation["not_catchment"] is True
    assert interpretation["not_event_footprint"] is True
    assert interpretation["not_historical_hydraulic_capacity"] is True
    assert interpretation["not_operational_threshold"] is True
    assert interpretation["not_observed_event"] is True
    assert interpretation["candidate_wide_sampling_ready"] is False
    assert interpretation["counts_as_complete_candidate_geometry"] is False
    assert interpretation["approved_hito_counts"] == {
        "main_right_margin": 21,
        "main_left_margin": 22,
        "aportante_1_right_margin": 10,
        "aportante_1_left_margin": 9,
        "total": 62,
    }


def validate_hitos(rows: list[dict], expected_ids: list[str]) -> None:
    assert [row["id"] for row in rows] == expected_ids
    assert len({(row["easting_m"], row["northing_m"]) for row in rows}) == len(rows)
    for row in rows:
        assert 375000 <= row["easting_m"] <= 385000
        assert 8568000 <= row["northing_m"] <= 8573000


def build_geometry(source: dict) -> dict:
    main_right = source["main_channel"]["right_margin"]
    main_left = source["main_channel"]["left_margin"]
    aportante_right = source["aportante_1"]["right_margin"]
    aportante_left = source["aportante_1"]["left_margin"]
    validate_hitos(main_right, EXPECTED["main_right"])
    validate_hitos(main_left, EXPECTED["main_left"])
    validate_hitos(aportante_right, EXPECTED["aportante_right"])
    validate_hitos(aportante_left, EXPECTED["aportante_left"])
    transformer = Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True)

    def coords(rows: list[dict]) -> list[list[float]]:
        output = []
        for row in rows:
            lon, lat = transformer.transform(row["easting_m"], row["northing_m"])
            output.append([round(lon, 7), round(lat, 7)])
        return output

    common = {
        "candidate_id": "lima_sur_canete",
        "hydrologic_unit": "Quebrada Jacayita",
        "parent_system": "Rio Canete y quebradas tributarias",
        "source_ids": ["ANA-JACAYITA-FAJA-RD0396-2025"],
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
        "not_observed_event": True,
        "candidate_wide_sampling_ready": False,
        "counts_as_complete_candidate_geometry": False,
        "artificial_connector_used": False,
        "map_role": "RESEARCH_CONTEXT_ONLY",
    }
    specs = [
        ("jacayita_main_faja_right_margin", "MAIN_CHANNEL", "RIGHT", main_right),
        ("jacayita_main_faja_left_margin", "MAIN_CHANNEL", "LEFT", main_left),
        ("jacayita_aportante_1_faja_right_margin", "APORTANTE_1", "RIGHT", aportante_right),
        ("jacayita_aportante_1_faja_left_margin", "APORTANTE_1", "LEFT", aportante_left),
    ]
    features = []
    for unit_id, branch, margin, rows in specs:
        features.append({
            "type": "Feature",
            "properties": {
                **common,
                "unit_id": unit_id,
                "branch": branch,
                "margin": margin,
                "hito_count": len(rows),
            },
            "geometry": {"type": "LineString", "coordinates": coords(rows)},
        })
    return {
        "type": "FeatureCollection",
        "properties": {
            "candidate_id": "lima_sur_canete",
            "component_id": "jacayita",
            "title": "Quebrada Jacayita · alineamientos oficiales de faja marginal",
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
            "representation": "FOUR_SEPARATE_OFFICIAL_FAJA_MARGIN_ALIGNMENTS",
            "hydrologic_identity": "JACAYITA_MAIN_AND_APORTANTE_1_ONLY",
            "not_catchment": True,
            "not_event_footprint": True,
            "not_historical_hydraulic_capacity": True,
            "not_observed_event": True,
            "candidate_wide_sampling_ready": False,
            "counts_as_complete_candidate_geometry": False,
            "artificial_connector_used": False,
            "default_visibility": False,
            "source_ids": ["ANA-JACAYITA-FAJA-RD0396-2025"],
        },
        "features": features,
    }


def build_validation(source: dict, geometry_bytes: bytes) -> dict:
    return {
        "version": "phase2-canete-jacayita-geometry-validation-v1",
        "candidate_id": "lima_sur_canete",
        "component_id": "jacayita",
        "status": "PASS_PARTIAL_OFFICIAL_JACAYITA_FAJA_CONTEXT_GEOMETRY",
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
        "main_right_margin_hito_count": 21,
        "main_left_margin_hito_count": 22,
        "aportante_1_right_margin_hito_count": 10,
        "aportante_1_left_margin_hito_count": 9,
        "total_hito_count": 62,
        "feature_count": 4,
        "geometry_types": ["LineString"],
        "component_resolution": {
            "jacayita_main_right_faja_alignment": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "jacayita_main_left_faja_alignment": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "jacayita_aportante_1_right_faja_alignment": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "jacayita_aportante_1_left_faja_alignment": "REPRODUCIBLE_OFFICIAL_GEOMETRY",
            "jacayita_catchment": "UNRESOLVED_NOT_DERIVED_FROM_FAJA",
            "rio_canete_connection": "NOT_ASSERTED_NO_ARTIFICIAL_CONNECTOR",
            "other_named_ravines": "UNRESOLVED_NOT_GENERALIZED_FROM_JACAYITA",
            "event_footprint": "NOT_ASSERTED",
            "historical_hydraulic_capacity": "UNKNOWN_NOT_INFERRED",
            "observed_event": "NOT_ASSERTED",
        },
        "counts_as_complete_candidate_geometry": False,
        "candidate_wide_sampling_ready": False,
        "artificial_polygon_or_connector_used": False,
        "design_or_project_values_imported_as_capacity_or_threshold": False,
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
            raise SystemExit("Canete/Jacayita normalized geometry is missing or stale")
        if not VALIDATION.is_file() or VALIDATION.read_bytes() != validation_bytes:
            raise SystemExit("Canete/Jacayita geometry validation is missing or stale")
        return 0
    GEOMETRY.parent.mkdir(parents=True, exist_ok=True)
    GEOMETRY.write_bytes(geometry_bytes)
    VALIDATION.write_bytes(validation_bytes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
