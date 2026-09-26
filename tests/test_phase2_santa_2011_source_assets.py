import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/ancash_santa_2011_lower_reach_model_context_v0_1.json"
AXIS = ROOT / "site/data/phase2/sources/ancash_santa_2011_axis_native_v0_1.json"
MODEL = ROOT / "site/data/phase2/sources/ancash_santa_2011_hydraulic_model_context_v0_1.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_santa_2011_assets_stay_fail_closed():
    for path in (SOURCE, AXIS, MODEL):
        data = load(path)
        assert data["deployment_status"] == "RESEARCH_ONLY"
        assert data["test_mode"] == "TEST_ONLY"
        assert data["production_use"] is False
        assert data["production_ready"] is False
        assert data["operational_alerting_enabled"] is False
        assert data["activation_gate"] == "BLOCKED"

def test_santa_2011_axis_preserves_unresolved_reference_and_duplicate_end_rows():
    axis = load(AXIS)
    assert len(axis["rows"]) == 51
    assert axis["narrative_endpoint_claims"]["start"]["chainage"] == "0+000"
    assert axis["rows"][0]["chainage"] == "1+000"
    assert (axis["rows"][0]["x"], axis["rows"][0]["y"]) == (758969, 9007565)
    end_rows = [row for row in axis["rows"] if row["chainage"] == "50+000"]
    assert len(end_rows) == 2
    assert {(row["x"], row["y"]) for row in end_rows} == {(788372, 9037490), (788881, 9038309)}
    assert axis["silent_correction_forbidden"] is True
    assert axis["coordinate_reference"]["status"] == "UNRESOLVED_DATUM_AND_UTM_ZONE_NOT_EXPLICITLY_VERIFIED"
    assert axis["coordinate_reference"]["transform_to_irfen_map_authorized"] is False
    assert axis["map_eligible"] is False

def test_santa_2011_model_values_remain_context_only():
    model = load(MODEL)
    scenarios = model["model_scenarios"]
    assert [(row["return_period_years"], row["discharge_m3_s"]) for row in scenarios] == [(10, 976), (25, 1177), (50, 1327)]
    assert [(row["return_period_years"], row["modeled_area_ha"]) for row in scenarios] == [(10, 2588), (25, 2700), (50, 2816)]
    assert model["simulation"]["flow_type"] == "STEADY"
    assert model["simulation"]["routing_or_wave_attenuation_modeled"] is False
    assert model["study_sector_count"] == 24
    assert model["study_era_defense_count"] == 16
    assert model["study_era_inappropriately_aligned_defense_count"] == 3
    policy = model["interpretation_policy"]
    assert policy["model_scenarios_are_current_capacity"] is False
    assert policy["model_scenarios_are_irfen_thresholds"] is False
    assert policy["modeled_area_is_observed_event_footprint"] is False
    assert policy["study_sector_rows_are_observed_event_labels"] is False
    assert policy["study_era_defenses_are_current_capacity"] is False
