import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"config/phase2_santa_eulalia_indeci2017_local_activation_names_v0_1.json"

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def test_registry_is_fail_closed():
    d=load()
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d["test_mode"]=="TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"]=="BLOCKED"
    assert d["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None

def test_quirio_exact_name_but_spelling_variants_not_auto_promoted():
    d=load()
    rows={x["source_name"]:x for x in d["rows"]}
    assert rows["Quebrada Quirio"]["canonical_unit_id"]=="quirio"
    assert rows["Quebrada Quirio"]["identity_status"]=="EXACT_NAME_MATCH"
    assert rows["Quebrada Casahuacra"]["canonical_unit_id"] is None
    assert rows["Quebrada Casahuacra"]["candidate_canonical_unit_id"]=="cashahuacra"
    assert rows["Quebrada Chingolay"]["canonical_unit_id"] is None
    assert rows["Quebrada Chingolay"]["candidate_canonical_unit_id"]=="shingolay"
    assert d["adjudication"]["cashahuacra_name_variant_resolved"] is False
    assert d["adjudication"]["shingolay_chingolay_name_variant_resolved"] is False

def test_no_timing_routing_or_map_geometry_inferred():
    d=load()
    assert all(row["activation_reported"] is True for row in d["rows"])
    assert all(row["event_time"] is None for row in d["rows"])
    assert d["adjudication"]["routing_enabled"] is False
    assert d["adjudication"]["travel_time_enabled"] is False
    assert d["adjudication"]["map_geometry_created"] is False
    assert d["map_updates"]=={"new_geometries_published":0,"new_nodes_published":0}
