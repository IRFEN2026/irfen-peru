import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "site/data/phase2/sources/ancash_casma_n7_vector_provenance_v0_1.json"

def test_casma_vector_provenance_is_fail_closed():
    d = json.loads(DOC.read_text(encoding="utf-8"))
    assert d["documented_original_vector"]["filename"] == "Uh_pfas100.shp"
    assert d["documented_original_vector"]["vector_bytes_recovered"] is False
    assert len(d["casma_target"]["exact_n7_codes"]) == 9
    assert d["casma_target"]["current_public_exact_n7_exposed"] is False
    assert d["recovery_gate"]["parent_polygon_may_substitute_child"] is False
    assert d["recovery_gate"]["pdf_map_may_supply_exact_geometry"] is False
    assert d["recovery_gate"]["map_publication_unblocked"] is False
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
