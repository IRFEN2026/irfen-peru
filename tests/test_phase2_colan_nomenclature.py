import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/"config/phase2_colan_nomenclature_resolution_v0_1.json"
SRC=ROOT/"site/data/phase2/sources/piura_colan_official_evidence_v0_1.json"

def load(p): return json.loads(p.read_text(encoding="utf-8"))

def test_colan_nomenclature_is_fail_closed():
    q=load(QA)
    assert q["status"]=="RESEARCH_ONLY_NOMENCLATURE_QA"
    assert "9 de Diciembre" in q["confirmed_names"]
    assert q["qa"]["parenthetical_alias_is_hydrologic_merge"] is False
    assert q["qa"]["route_map_title_is_geometry"] is False
    assert q["qa"]["map_materialization_allowed"] is False

def test_colan_alias_pairs_remain_unmerged():
    q=load(QA)
    pairs={tuple(r["labels"]):r for r in q["alias_signals"]}
    assert pairs[("Libertad","Centenario")]["resolution"]=="UNRESOLVED_DO_NOT_MERGE"
    assert pairs[("9 de Diciembre","Salaverry")]["resolution"]=="UNRESOLVED_DO_NOT_MERGE"
    assert pairs[("Bolognesi","Grau")]["resolution"]=="UNRESOLVED_DO_NOT_MERGE"

def test_colan_alias_sources_are_registered():
    q=load(QA); s=load(SRC)
    ids={r["source_id"] for r in s["sources"]}
    assert all(r["source_id"] in ids for r in q["alias_signals"])
    assert s["qa"]["parenthetical_alias_is_hydrologic_merge"] is False
    assert s["qa"]["vulnerability_inventory_is_event"] is False
