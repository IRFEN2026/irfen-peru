import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_jicamarca_discovery_v0_1.json"

def load():
    return json.loads(CFG.read_text(encoding="utf-8"))

def test_fail_closed():
    c=load()
    assert c["deployment_status"]=="RESEARCH_ONLY"
    assert c["test_mode"]=="TEST_ONLY"
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["activation_gate"]=="BLOCKED"
    assert c["missing_data_rule"]=="UNKNOWN_NOT_LOW_RISK"
    assert c["decision_thresholds"] is None
    assert c["hydraulic_factors"] is None

def test_jicamarca_is_not_one_synthetic_ravine():
    c=load()
    assert c["territorial_identity"]["jicamarca_is_single_hydrologic_unit"] is False
    ids={x["child_id"] for x in c["hydrologic_components"]}
    assert {"huaycoloro","rio_seco","canto_grande_media_luna","jicamarca_named_channel"} <= ids
    assert c["map_policy"]["publish_parent_polygon"] is False

def test_huaycoloro_is_referenced_not_duplicated():
    c=load()
    h=next(x for x in c["hydrologic_components"] if x["child_id"]=="huaycoloro")
    assert h["existing_irfen_reference"]=="chosica_huaycoloro"
    assert h["duplicate_new_parent_geometry_forbidden"] is True

def test_historical_evidence_preserves_component_attribution():
    c=load()
    ev={x["event_id"]:x for x in c["historical_evidence"]}
    assert ev["JICAMARCA-MEDIA-LUNA-2002"]["component_id"]=="canto_grande_media_luna"
    assert ev["JICAMARCA-HUAYCOLORO2-2023-03-15"]["component_id"]=="huaycoloro"
    assert ev["JICAMARCA-VALLE-SAGRADO-2023-03-15"]["status"].endswith("MECHANISM_PARTIAL")

def test_monitoring_does_not_import_operational_thresholds():
    c=load()
    cen=next(x for x in c["monitoring_assets"] if x["source_id"]=="IGP-CENDEHUA")
    assert cen["operational_alert_thresholds_imported_to_irfen"] is False
