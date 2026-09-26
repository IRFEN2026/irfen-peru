import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "site/data/phase2/sources/ancash_casma_2007_surface_water_inventory_v0_1.json"

def test_casma_2007_surface_inventory_is_fail_closed():
    data = json.loads(ASSET.read_text(encoding="utf-8"))
    assert data["deployment_status"] == "RESEARCH_ONLY"
    assert data["test_mode"] == "TEST_ONLY"
    assert data["production_use"] is False
    assert data["production_ready"] is False
    assert data["operational_alerting_enabled"] is False
    assert data["activation_gate"] == "BLOCKED"
    assert data["decision_thresholds"] is None
    assert data["hydraulic_factors"] is None
    inventory = data["inventory_summary"]
    assert inventory["total_quebradas"] == 626
    assert inventory["quebrada_count_sum"] == 626
    assert [row["code"] for row in inventory["n7_units"]] == [
        "1375961","1375962","1375963","1375964","1375965","1375966","1375967","1375968","1375969"
    ]
    assert [row["quebradas"] for row in inventory["n7_units"]] == [58,191,64,113,102,27,1,19,51]
    assert [row["annex_map"] for row in inventory["n7_units"]] == ["13.1","13.2","13.3","13.4","13.5","13.6","13.6","13.7","13.8"]\n    assert data["provenance"]["annex_map_index_qa"]["verified_sequence"][-1] == "13.8:1375969"
    assert data["recovery_value"]["exact_vector_recovered"] is False
    assert data["recovery_value"]["pdf_digitization_authorized"] is False
    assert data["map_policy"]["map_eligible"] is False
