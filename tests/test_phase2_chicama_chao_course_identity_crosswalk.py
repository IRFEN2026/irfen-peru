import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site/data/phase2/sources/ana_rj056_2018_chicama_chao_course_classification_v0_1.json"
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_chao_course_identity_crosswalk_20260926.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_ana_course_classification_keeps_scientific_guards_closed():
    src = load(SRC)
    ev = load(EVID)
    for obj in (src, ev):
        assert obj["deployment_status"] == "RESEARCH_ONLY"
        assert obj["test_mode"] == "TEST_ONLY"
        assert obj["production_use"] is False
        assert obj["production_ready"] is False
        assert obj["operational_alerting_enabled"] is False
        assert obj["activation_gate"] == "BLOCKED"
        assert obj["decision_thresholds"] is None
        assert obj["hydraulic_factors"] is None
    assert src["counts_as_channel_geometry"] is False
    assert src["counts_as_subcatchment_geometry"] is False
    assert src["counts_as_event_footprint"] is False
    assert src["proves_confluence_or_outlet"] is False
    assert ev["map_eligible"] is False
    assert ev["map_changed"] is False


def test_chicama_named_courses_are_official_identity_context_only():
    src = load(SRC)
    rows = {(x["course_code"], x["name"]) for x in src["chicama"]["courses"]}
    assert ("137722", "Río Quirripano") in rows
    assert ("137724", "Río Santanero") in rows
    assert ("137726", "Río Ochape") in rows
    assert ("137728", "Río Chuquillanqui") in rows
    assert ("137729", "Río Huancay") in rows
    assert src["chicama"]["parent_uh"]["code"] == "13772"


def test_chao_course_table_and_chorobal_documentary_name_remain_distinct():
    src = load(SRC)
    ev = load(EVID)
    rows = {(x["course_code"], x["name"]) for x in src["chao"]["courses"]}
    assert ("1377122", "Río Chao") in rows
    assert ("1377124", "Quebrada Pampa Colorada") in rows
    assert ("1377126", "Quebrada Tucumaca") in rows
    assert ("1377128", "Río Tutumo") in rows
    assert src["chao"]["parent_uh"]["code"] == "137712"
    assert src["chao"]["chorobal_crosswalk"]["name_present_in_this_table"] is False
    assert src["chao"]["chorobal_crosswalk"]["auto_crosswalk_forbidden"] is True
    assert ev["qa"]["chorobal_alias_crosswalk_resolved"] is False
    assert ev["qa"]["chorobal_outlet_resolved"] is False


def test_no_absence_or_provider_category_is_promoted():
    src = load(SRC)
    ev = load(EVID)
    assert src["scientific_guards"]["absence_of_chorobal_name_is_negative"] is False
    assert src["scientific_guards"]["provider_category_is_irfen_threshold"] is False
    assert src["scientific_guards"]["map_publication_from_table_only"] is False
    assert ev["qa"]["threshold_created"] is False
    assert ev["qa"]["capacity_inferred"] is False
    assert ev["qa"]["absence_used_as_negative"] is False
