import json
from pathlib import Path

PATH = Path("config/phase2_ica_official_course_hierarchy_v0_1.json")

def test_ica_course_hierarchy_research_guards():
    doc=json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["deployment_status"]=="RESEARCH_ONLY"
    assert doc["test_mode"]=="TEST_ONLY"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["activation_gate"]=="BLOCKED"
    assert doc["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert doc["decision_thresholds"] is None
    assert doc["hydraulic_factors"] is None
    assert doc["geometry_assets_published"]==0
    assert doc["new_operational_zones"]==0

def test_ica_course_hierarchy_identity_and_no_promotion():
    doc=json.loads(PATH.read_text(encoding="utf-8"))
    collectors={x["id"]:x for x in doc["collector_identities"]}
    assert collectors["ica_ica_river_collector"]["uh_code"]=="1374"
    assert collectors["ica_pisco_river_collector"]["uh_code"]=="13752"
    assert collectors["ica_san_juan_river_collector"]["uh_code"]=="137532"
    assert collectors["ica_topara_collector"]["uh_code"]=="137534"
    assert all(x["map_publishable"] is False for x in doc["collector_identities"])
    targets={(x["name"],x["uh_code"],x["course_code"]) for x in doc["local_targets"]}
    assert ("Quebrada Gramonal","1374","13742") in targets
    assert ("Quebrada Tingue","1374","13744") in targets
    assert ("Quebrada Veladero","13752","137522") in targets
    assert ("Quebrada Incachaca","13752","137528") in targets
    assert ("Quebrada Almacén","137532","1375322") in targets
    assert ("Quebrada Ayoque","137532","1375324") in targets
    assert all(x["map_publishable"] is False for x in doc["local_targets"])
    assert doc["geometry_status"].endswith("GEOMETRY_NOT_FROZEN")
    guards=doc["guards"]
    assert guards["course_identity_is_not_geometry"] is True
    assert guards["course_identity_is_not_outlet_proof"] is True
    assert guards["eca_category_is_not_activation_classification"] is True
    assert guards["reported_length_is_not_travel_time"] is True
    assert guards["matagente_alias_not_asserted"] is True
    assert guards["event_transfer_forbidden"] is True
