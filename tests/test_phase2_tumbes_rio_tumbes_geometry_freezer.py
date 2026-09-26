import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "site/data/phase2/sources/tumbes_rio_tumbes_geometry_freeze_plan_v0_2.json"


def load():
    return json.loads(PLAN.read_text(encoding="utf-8"))


def test_freeze_plan_keeps_roles_separate():
    x = load()
    rows = {row["layer_id"]: row for row in x["layers"]}
    assert set(rows) == {2, 66, 67}
    assert rows[2]["role"] == "OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT"
    assert rows[66]["role"] == "OBSERVED_EVENT_FOOTPRINT_ONLY"
    assert rows[66]["event_date"] == "2023-04-28"
    assert rows[67]["role"] == "OBSERVED_EVENT_FOOTPRINT_ONLY"
    assert rows[67]["event_date"] == "2023-05-04"


def test_freeze_plan_is_fail_closed():
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


def test_freeze_contract_requires_exact_bytes_and_hashes():
    x = load()["freeze_contract"]
    assert x["preserve_raw_metadata_bytes"] is True
    assert x["preserve_raw_geojson_bytes"] is True
    assert x["write_canonical_geojson"] is True
    assert x["sha256_raw_and_canonical"] is True
    assert x["out_sr"] == 4326
    assert x["geometry_precision"] == 7
    assert x["query_where"] == "1=1"
    assert x["query_out_fields"] == "*"
    assert x["query_return_geometry"] is True


def test_freeze_guards_forbid_cross_role_promotion():
    g = load()["guards"]
    assert g["basin_geometry_is_event_footprint"] is False
    assert g["event_footprints_are_basin_geometry"] is False
    assert g["provider_alert_bands_are_irfen_thresholds"] is False
    assert g["observed_discharge_is_hydraulic_capacity"] is False
    assert g["transfer_to_zarumilla_or_zorritos_allowed"] is False
    assert g["event_footprint_implies_basin_activation"] is False
    assert g["absence_of_event_footprint_is_negative"] is False
