import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADJ = ROOT / "site/data/validation/phase2_discovery_evidence/zorritos_2017_direct_child_adjudication_v0_1.json"


def load():
    return json.loads(ADJ.read_text(encoding="utf-8"))


def test_direct_primary_adjudications_are_three_and_bounded():
    x = load()
    assert x["status"] == "DIRECT_PRIMARY_CHILD_EVENT_EVIDENCE_FROZEN_PENDING_PACKAGE_BIND"
    assert x["target_discovery_id"] == "tumbes_zorritos_bocapan_coastal_ravines"
    assert x["primary_source_id"] == "INGEMMET-A6764-TUMBES-2017"
    assert set(x["adjudications"]) == {"san_andres", "la_paja", "marinero"}
    for row in x["adjudications"].values():
        assert row["event_year"] == 2017
        assert row["status"] == "POSITIVE_COMPONENT_EVENT_CONTEXT"
        assert row["source_pages"] == [32, 35]


def test_adjudication_does_not_create_geometry_thresholds_or_negatives():
    x = load()
    assert x["exact_event_footprints_frozen"] is False
    assert x["catchment_geometry_inferred"] is False
    assert x["outlets_inferred"] is False
    assert x["hydraulic_capacity_inferred"] is False
    assert x["threshold_inferred"] is False
    assert x["negative_controls_created"] is False
    assert x["transfer_to_other_children_allowed"] is False
    assert x["package_bind_required"] is True


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
