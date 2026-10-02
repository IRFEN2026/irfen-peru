import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/phase2/sources/zorritos_ingemmet_2017_direct_child_evidence_v0_1.json"


def load():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_safe_research_guards():
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


def test_three_direct_children_are_bounded_to_primary_source_pages():
    x = load()
    assert x["source_id"] == "INGEMMET-A6764-TUMBES-2017"
    assert set(x["direct_component_evidence"]) == {"san_andres", "la_paja", "marinero"}
    for row in x["direct_component_evidence"].values():
        assert row["pages"] == [32, 35]
        assert row["status"] == "POSITIVE_2017_FLOW_DAMAGE_CONTEXT"
        assert row["exact_event_footprint_frozen"] is False


def test_no_geometry_capacity_threshold_or_sibling_transfer_is_inferred():
    x = load()
    assert x["geometry_inferred"] is False
    assert x["hydraulic_capacity_inferred"] is False
    assert x["threshold_inferred"] is False
    assert x["transfer_to_other_ravines_allowed"] is False
