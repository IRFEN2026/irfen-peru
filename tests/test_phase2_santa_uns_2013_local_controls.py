import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "site/data/phase2/source_assessments/santa_uns_2013_local_hec_ras_controls_v0_1.json"

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
    return json.loads(PATH.read_text(encoding="utf-8"))

def test_uns_local_controls_keep_fail_closed_guards():
    doc = load()
    for key, expected in SAFE.items():
        assert doc[key] == expected
    assert doc["status"].startswith("RESEARCH_ONLY_SECONDARY_LOCAL_HYDRAULIC_CONTROLS")

def test_three_local_hec_ras_studies_are_bounded_and_distinct():
    rows = load()["sources"]
    assert len(rows) == 3
    assert {r["handle"] for r in rows} == {
        "20.500.14278/2449",
        "20.500.14278/2371",
        "20.500.14278/2380",
    }
    assert all("HEC-RAS" in r["model"] for r in rows)
    assert all(r["scientific_role"] == "secondary local hydraulic-model QA only" for r in rows)

def test_secondary_studies_do_not_promote_ana_geometry_or_capacity():
    a = load()["adjudication"]
    assert a["confirms_independent_local_hec_ras_use_on_lower_santa"] is True
    assert a["proves_ana_2011_model_assets"] is False
    assert a["proves_ana_2011_datum"] is False
    assert a["proves_ana_2011_cross_sections"] is False
    assert a["supplies_reproducible_floodplain_geometry"] is False
    assert a["may_be_mosaicked_to_replace_ana_2011_0_50km_model"] is False
    assert a["map_publication_enabled"] is False
