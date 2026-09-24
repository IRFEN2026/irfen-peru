import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFLICT = ROOT / "config/phase2_jicamarca_rio_seco_colca_nomenclature_conflict_v0_1.json"
IDENTITY = ROOT / "config/phase2_jicamarca_rio_seco_ana_faja_identity_v0_1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_colca_and_rio_seco_are_fail_closed_as_distinct_children():
    c = load(CONFLICT)
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["test_mode"] == "TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"] == "BLOCKED"
    assert c["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    assert c["finding"]["adjudication"].startswith("COLCA_AND_RIO_SECO_MUST_REMAIN_DISTINCT")
    assert c["finding"]["absence_of_crosswalk_is_not_equivalence"] is True


def test_quarantined_geometry_cannot_be_consumed_as_rio_seco():
    c = load(CONFLICT)
    row = c["quarantined_artifacts"][0]
    assert row["path"] == "site/data/phase2/geometries/jicamarca_rio_seco_ana_faja_context.geojson"
    assert row["source_geometry_valid"] is True
    assert row["rio_seco_semantic_binding_valid"] is False
    assert row["map_eligible_as_rio_seco"] is False
    assert row["may_define_rio_seco_channel"] is False
    assert row["may_define_rio_seco_catchment"] is False
    assert row["may_define_rio_seco_outlet"] is False
    assert row["may_define_rio_seco_confluence"] is False
    identity = load(IDENTITY)
    assert identity["regulatory_geometry_evidence"]["map_eligible_now"] is False


def test_spatial_probe_cannot_promote_qda_colca_to_rio_seco():
    c = load(CONFLICT)["igp_spatial_probe_effect"]
    assert c["q_colca_objectids_observed"] == [3364, 11542]
    assert c["q_colca_duplicate_geometry_across_admin_records"] is True
    assert c["same_name_rio_seco_objectid_3338_inside_ana_colca_envelope"] is False
    assert c["q_colca_may_replace_rio_seco"] is False


def test_collector_coupling_remains_unknown():
    c = load(CONFLICT)["collector_coupling"]
    assert c["connectivity"] == "UNRESOLVED_NOT_ASSUMED"
    assert c["outlet_or_confluence"] is None
    assert c["Q_i_t"] is None
    assert c["travel_time"] is None
    assert c["attenuation"] is None
    assert c["quality"] == "UNKNOWN"
    assert c["tributary_activation_implies_receiver_overflow"] is False
