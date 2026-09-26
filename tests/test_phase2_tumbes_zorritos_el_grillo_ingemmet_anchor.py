import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/tumbes_zorritos_el_grillo_ingemmet_anchor_v0_1.json"


def load():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_anchor_is_exact_but_not_geometry():
    x = load()
    p = x["control_point"]
    assert p["crs"] == "WGS84_UTM_ZONE_17S"
    assert p["easting_m"] == 534001
    assert p["northing_m"] == 9592175
    assert p["territorial_reference"] == "sector Los Pinos, Zorritos"
    assert p["counts_as_channel_geometry"] is False
    assert p["counts_as_catchment_geometry"] is False
    assert p["counts_as_outlet"] is False
    assert p["counts_as_event_footprint"] is False
    assert p["counts_as_activation_point"] is False
    assert p["map_publishable_as_child_geometry"] is False


def test_source_is_bounded_to_el_grillo():
    x = load()
    assert x["parent_discovery_id"] == "tumbes_zorritos_bocapan_coastal_ravines"
    assert x["component_id"] == "el_grillo"
    assert x["source_id"] == "INGEMMET-A7454-TUMBES-2023"
    g = x["scientific_guards"]
    assert g["transfer_to_other_zorritos_children_allowed"] is False
    assert g["transfer_to_rio_tumbes_or_zarumilla_allowed"] is False


def test_fail_closed_guards():
    x = load()
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None
    g = x["scientific_guards"]
    assert g["critical_sector_point_is_threshold"] is False
    assert g["critical_sector_point_is_capacity"] is False
