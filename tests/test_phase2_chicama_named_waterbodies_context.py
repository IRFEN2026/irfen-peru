import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT / "site/data/validation/phase2_research_evidence/lalibertad_chicama_named_waterbodies_context_20260926.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_named_waterbody_context_is_fail_closed():
    ev = load(EVID)
    assert ev["deployment_status"] == "RESEARCH_ONLY"
    assert ev["test_mode"] == "TEST_ONLY"
    assert ev["production_use"] is False
    assert ev["production_ready"] is False
    assert ev["operational_alerting_enabled"] is False
    assert ev["activation_gate"] == "BLOCKED"
    assert ev["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert ev["decision_thresholds"] is None
    assert ev["hydraulic_factors"] is None
    assert ev["map_eligible"] is False
    assert ev["map_changed"] is False
    assert ev["qa"]["named_waterbody_is_subcatchment_geometry"] is False
    assert ev["qa"]["monitoring_point_is_outlet"] is False
    assert ev["qa"]["project_scope_is_geometry"] is False
    assert ev["qa"]["event_created"] is False
    assert ev["qa"]["event_footprint_created"] is False
    assert ev["qa"]["threshold_created"] is False
    assert ev["qa"]["capacity_inferred"] is False
    assert ev["qa"]["absence_used_as_negative"] is False

def test_official_sources_preserve_identity_and_relationship_scope():
    ev = load(EVID)
    ana = next(x for x in ev["sources"] if x["source_id"] == "ANA-CHICAMA-WATER-QUALITY-2023-12-12")
    assert set(ana["named_waterbodies"]) == {
        "Perejil", "Negro", "Grande", "Sayapullo", "Chuquillanqui", "Cascas", "Santanero", "Chicama"
    }
    grll = next(x for x in ev["sources"] if x["source_id"] == "GRLL-CASCAS-OCHAPE-2021-12-10")
    assert grll["role"] == "OFFICIAL_HYDROGRAPHIC_RELATIONSHIP_CONTEXT_ONLY"
    assert any("Ochape" in x and "upper Chicama" in x for x in grll["relationships"])
