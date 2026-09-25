import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / "config/phase2_santa_lower_reach_2011_source_freeze_v0_1.json"
S = ROOT / "site/data/phase2/sources/ancash_santa_lower_reach_2011_official_evidence_v0_1.json"

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def test_santa_2011_freeze_stays_research_only():
    c = load(C)
    s = load(S)
    for x in (c, s):
        assert x["deployment_status"] == "RESEARCH_ONLY"
        assert x["test_mode"] == "TEST_ONLY"
        assert x["production_use"] is False
        assert x["production_ready"] is False
        assert x["operational_alerting_enabled"] is False
        assert x["activation_gate"] == "BLOCKED"
        assert x["decision_thresholds"] is None
        assert x["hydraulic_factors"] is None

def test_santa_2011_documentary_controls_do_not_publish_geometry():
    c = load(C)
    assert c["source_provenance"]["original_pdf_md5"] == "b920108b7054aa77f164b979ea618ec0"
    assert c["study_scope"]["coordinate_reference_status"] == "UTM_DATUM_AND_ZONE_UNRESOLVED"
    assert c["chainage_qa"]["map_eligible"] is False
    assert c["critical_point_context"]["documented_count"] == 24
    assert c["hydraulic_model_context"]["values_are_current_hydraulic_capacity"] is False
    assert c["hydraulic_model_context"]["values_are_irfen_thresholds"] is False
    assert c["scientific_effect"]["map_publication_enabled"] is False
