import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "config/phase2_jicamarca_evidence_index_v0_2.json"
ASSESSMENT = "config/phase2_jicamarca_canto_grande_media_luna_assessment_v0_2.json"

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


def load():
    return json.loads(INDEX.read_text(encoding="utf-8"))


def test_index_v02_preserves_fail_closed_guards_and_versions_v01():
    index = load()
    for key, expected in SAFE.items():
        assert index[key] == expected
    assert index["extends"] == "config/phase2_jicamarca_evidence_index_v0_1.json"
    assert index["status"] == "RESEARCH_ONLY_EVIDENCE_INDEX_CHILD_CHANNEL_GEOMETRY_FROZEN"


def test_index_promotes_only_official_child_channel_context_not_outlets_or_catchments():
    index = load()
    package = next(row for row in index["packages"] if row["path"] == ASSESSMENT)
    assert package["role"] == "OFFICIAL_IGP_CHILD_CHANNEL_GEOMETRY_AND_FAIL_CLOSED_OUTLET_GATE"
    assert package["may_define_channel_geometry"] is True
    assert package["may_define_catchment_geometry"] is False
    assert package["may_define_outlet"] is False
    assert package["may_use_channel_endpoint_as_outlet"] is False
    assert package["may_use_event_outcome_to_fit_geometry"] is False
    assert package["may_promote_parent_activation"] is False
    assert package["may_promote_rimac_overflow"] is False
    assert (ROOT / ASSESSMENT).is_file()


def test_index_keeps_rio_seco_colca_semantic_quarantine_and_collector_blocked():
    index = load()
    assert "QDA_COLCA_FROZEN_FAJA_DO_NOT_USE_AS_RIO_SECO" in index["semantic_quarantine_effect"]
    assert "CANTO_GRANDE_AND_MEDIA_LUNA_OFFICIAL_CHANNEL_LINES_ARE_SEPARATE_LOCAL_CHILD_CONTEXTS_AND_MUST_NOT_BE_UNIONED" in index["semantic_quarantine_effect"]
    assert index["collector_effect"] == "NO_OUTLET_PROMOTION_NO_Q_TRAVEL_TIME_ATTENUATION_PEAK_COINCIDENCE_OR_RECEIVER_RESPONSE_PROMOTION"


def test_index_map_effect_is_channel_context_only():
    effect = load()["map_effect"]
    assert effect.startswith("OFFICIAL_CANTO_GRANDE_AND_MEDIA_LUNA_CHILD_CHANNEL_LINES_MAY_BE_PUBLISHED_AS_RESEARCH_CONTEXT_ONLY")
    assert "CATCHMENT_POLYGONS_OUTLETS_EVENT_FOOTPRINTS_AND_PARENT_ACTIVATION_REMAIN_WITHHELD" in effect
