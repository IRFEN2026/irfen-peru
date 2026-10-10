import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADJ = ROOT / "config/phase2_zorritos_child_adjudication_v0_1.json"
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_zorritos_bocapan_coastal_ravines.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_zorritos_child_adjudication_fails_closed():
    data = load(ADJ)
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None

def test_el_grillo_point_is_not_outlet_or_child_geometry():
    data = load(ADJ)
    point = data["adjudications"]["el_grillo"]["field_control"]
    assert point["easting_m"] == 534001
    assert point["northing_m"] == 9592175
    assert point["counts_as_outlet"] is False
    assert point["counts_as_catchment_geometry"] is False
    assert point["counts_as_event_footprint"] is False
    assert point["map_publishable_as_child_geometry"] is False

def test_casitas_named_ravines_are_not_silently_merged_into_bocapan():
    data = load(ADJ)
    row = data["adjudications"]["casitas_2023_named_activations"]
    assert set(row["named_ravines"]) == {"Pena Blanca", "Carrizal", "Gramadal", "Corralitos", "Panales"}
    assert row["activation_documented"] is True
    assert row["hydrologic_parentage_resolved"] is False
    assert row["assign_to_bocapan_casitas_child"] is False
    assert row["geometry_status"] == "MISSING_NO_APPROXIMATION_ALLOWED"
    assert row["outlet_status"] == "UNRESOLVED"

def test_el_rubio_homonym_stays_quarantined():
    data = load(ADJ)
    package = load(PACKAGE)
    row = data["adjudications"]["el_rubio"]
    assert "HOMONYM_QUARANTINED" in row["identity_status"]
    assert row["event_attribution_allowed"] is False
    assert row["map_publishable"] is False
    assert package["hydrologic_components"]["el_rubio"]["activation_verified"] is False

def test_unarchived_sources_are_not_promoted():
    data = load(ADJ)
    assert data["provenance"]["external_source_bytes_archived"] is False
    assert data["provenance"]["external_source_sha256"] is None
    regional = data["regional_priority_context"]
    assert regional["critical_zone_is_child_event"] is False
    assert regional["critical_zone_is_catchment_geometry"] is False
    assert regional["critical_zone_is_event_footprint"] is False
