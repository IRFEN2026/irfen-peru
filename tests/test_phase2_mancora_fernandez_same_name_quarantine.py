import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARANTINE = ROOT / "config/phase2_mancora_fernandez_same_name_quarantine_v0_1.json"
SOURCES = ROOT / "site/data/phase2/sources/piura_mancora_organos_official_evidence_v0_1.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/piura_mancora_los_organos_coastal_ravines.json"

SAFE = {
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


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_quarantine_is_fail_closed_and_bound_to_mancora_discovery():
    q = load(QUARANTINE)
    p = load(PACKAGE)
    for key, expected in SAFE.items():
        assert q[key] == expected
        assert p[key] == expected
    assert q["discovery_id"] == p["discovery_id"] == "piura_mancora_los_organos_coastal_ravines"
    assert q["status"] == "CROSS_REGION_SAME_NAME_GEOMETRY_CROSSWALK_REQUIRED"


def test_tumbes_same_name_faja_cannot_fill_mancora_geometry_gap_without_crosswalk():
    q = load(QUARANTINE)
    x = q["cross_region_same_name_source"]
    assert x["source_region_context"] == "Tumbes"
    assert x["faja_length_km_reported"] == 7.0
    assert x["relationship_to_mancora_fernandez"] == "UNRESOLVED_REQUIRES_COORDINATE_LEVEL_CROSSWALK"
    assert x["may_be_used_as_mancora_catchment_without_crosswalk"] is False
    assert x["may_be_used_as_mancora_channel_without_crosswalk"] is False
    assert x["may_be_used_as_mancora_outlet_without_crosswalk"] is False
    assert x["may_be_used_as_mancora_event_footprint"] is False
    a = q["adjudication"]
    assert a["same_name_is_sufficient_for_cross_region_geometry_binding"] is False
    assert a["tumbes_faja_may_fill_mancora_missing_geometry_without_crosswalk"] is False
    assert a["tumbes_and_mancora_features_proven_distinct"] is False
    assert a["tumbes_and_mancora_features_proven_same"] is False
    assert a["mancora_fernandez_geometry_status_after_review"] == "MISSING_NO_APPROXIMATION_ALLOWED"
    assert a["map_geometry_created"] is False


def test_mancora_groundwater_context_does_not_become_surface_geometry():
    q = load(QUARANTINE)
    m = q["mancora_identity_anchor"]
    assert m["source_id"] == "ANA-RD-0173-2025-AAA-JZ"
    assert m["surface_catchment_geometry_supplied"] is False
    assert m["event_geometry_supplied"] is False
    assert m["outlet_supplied"] is False


def test_quarantine_does_not_downgrade_verified_2026_activation_or_create_negative_control():
    q = load(QUARANTINE)
    p = load(PACKAGE)
    fernandez = p["hydrologic_components"]["quebrada_fernandez"]
    assert fernandez["activation_verified"] is True
    assert fernandez["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
    assert q["adjudication"]["mancora_fernandez_activation_evidence_status"].startswith("UNCHANGED_VERIFIED")
    assert q["adjudication"]["negative_control_created"] is False


def test_source_registry_references_quarantine_and_forbids_name_only_binding():
    s = load(SOURCES)
    for key, expected in SAFE.items():
        assert s[key] == expected
    row = next(item for item in s["qa_artifacts"] if item["path"] == "config/phase2_mancora_fernandez_same_name_quarantine_v0_1.json")
    assert row["may_supply_mancora_geometry"] is False
    assert row["may_bind_same_name_source_without_coordinate_crosswalk"] is False
    assert s["qa"]["same_name_cross_region_geometry_binding_allowed"] is False
