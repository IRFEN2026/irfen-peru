import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/phase2_jicamarca_rio_seco_igp_spatial_probe_v0_1.json"


def load():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_scientific_guards_are_fail_closed():
    doc = load()
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_mode"] == "TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None


def test_ana_faja_is_query_context_only():
    doc = load()
    ctx = doc["ana_context"]
    assert ctx["use_as_query_envelope_only"] is True
    assert ctx["faja_is_channel_centerline"] is False
    assert ctx["faja_is_catchment_polygon"] is False
    assert ctx["faja_is_event_footprint"] is False
    assert ctx["faja_may_define_outlet"] is False
    assert doc["query"]["geometry_source"] == "EXACT_FROZEN_ANA_CONTEXT_ENVELOPE_NO_BUFFER"


def test_candidate_lines_cannot_promote_hydrology_or_operations():
    doc = load()
    policy = doc["candidate_policy"]
    assert policy["candidate_geometry_is_accepted_channel"] is False
    assert policy["candidate_geometry_is_catchment"] is False
    assert policy["candidate_endpoint_is_outlet"] is False
    assert policy["candidate_endpoint_is_confluence"] is False
    assert policy["candidate_length_may_define_travel_time"] is False
    assert policy["candidate_may_define_discharge"] is False
    assert policy["candidate_may_define_hydraulic_capacity"] is False
    assert policy["candidate_may_define_event_footprint"] is False
    assert policy["candidate_may_enable_routing"] is False
    assert policy["candidate_may_promote_parent_activation"] is False
    assert policy["candidate_may_promote_rimac_overflow"] is False
    assert policy["selection_requires_separate_frozen_identity_review"] is True


def test_collector_coupling_remains_unknown():
    coupling = load()["collector_coupling"]
    assert coupling["receiver"] == "rimac_mainstem"
    assert coupling["connectivity"] == "UNRESOLVED_NOT_ASSUMED"
    assert coupling["outlet_or_confluence"] is None
    assert coupling["Q_i_t"] is None
    assert coupling["travel_time"] is None
    assert coupling["attenuation"] is None
    assert coupling["quality"] == "UNKNOWN"
    assert coupling["tributary_activation_implies_receiver_overflow"] is False
