import hashlib, json
from pathlib import Path

CFG=Path("config/phase2_arequipa_acari_parent_geometry_bridge_v0_1.json")

def load(p):
    return json.loads(p.read_text(encoding="utf-8"))

def sha(p):
    d=load(p)
    raw=(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    return hashlib.sha256(raw).hexdigest()

def test_acari_parent_geometry_bridge():
    c=load(CFG)
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None
    r=c["reused_frozen_geometry"]
    v=load(Path(r["geometry_validation_path"]))
    assert v["official_unit"]["code"]=="13718"
    assert v["official_unit"]["name"]=="Cuenca Acarí"
    assert sha(Path(r["geometry_path"]))==r["normalized_geometry_sha256"]
    assert sha(Path(r["source_snapshot_path"]))==r["source_snapshot_sha256"]
    child=c["local_children_remaining_fail_closed"][0]
    assert child["child_id"]=="arequipa_san_agustin"
    assert child["geometry_asset"] is None
    assert child["outlet"] is None
    assert child["map_publishable"] is False
    assert c["summary"]["new_operational_zones"]==0
