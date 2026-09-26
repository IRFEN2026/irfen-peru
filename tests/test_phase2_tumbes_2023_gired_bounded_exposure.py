import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_2023_gired_bounded_exposure_v0_1.json"


def load():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_research_guards_stay_closed():
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


def test_reported_rio_tumbes_exposure_is_bounded_and_not_geometry():
    x = load()
    r = x["rio_tumbes_context"]
    assert r["urban_tumbes_affected_area_reported"] is True
    assert r["malecón_mariscal_benavides_parque_del_beso_reference"] is True
    assert r["overflow_monitoring_sectors"] == ["Limon", "Cabuya", "Naranjo", "Cerro Blanco"]
    assert r["cerro_blanco_agricultural_inundation_reported"] is True
    assert r["exact_event_footprint_frozen"] is False
    assert x["event_footprint_inferred"] is False
    assert x["basin_geometry_inferred"] is False


def test_bounded_quebrada_statement_never_becomes_negative_control():
    x = load()
    q = x["same_report_quebrada_statement"]
    assert q["bounded_report_statement_present"] is True
    assert q["may_be_used_as_basin_wide_negative"] is False
    assert q["may_be_used_as_zorritos_child_negative"] is False
    assert q["may_be_used_as_negative_control"] is False


def test_no_hydraulic_or_cross_system_inference():
    x = load()
    assert x["discharge_inferred"] is False
    assert x["hydraulic_capacity_inferred"] is False
    assert x["travel_time_inferred"] is False
    assert x["threshold_inferred"] is False
    assert x["outcome_transferred_to_zarumilla"] is False
    assert x["outcome_transferred_to_zorritos"] is False
