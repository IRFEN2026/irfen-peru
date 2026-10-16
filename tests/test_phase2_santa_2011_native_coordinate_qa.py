import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "site/data/phase2/source_assessments/santa_2011_native_coordinate_qa_v0_1.json"
REG = ROOT / "site/data/phase2/sources/ancash_chimbote_lacramarca_santa_bajo_official_evidence_v0_1.json"

def test_santa_2011_native_table_stays_fail_closed():
    q = json.loads(QA.read_text(encoding="utf-8"))
    assert q["source_id"] == "ANA-SANTA-LOWER-REACH-2011"
    assert q["crs_verified"] is False
    assert q["map_eligible"] is False
    assert q["chainage_label_discrepancy"] is True
    assert q["duplicate_50k_records"] == 2
    assert q["silent_correction_forbidden"] is True
    assert q["observed_event_footprint"] is False
    assert q["production_use"] is False
    assert q["production_ready"] is False
    assert q["operational_alerting_enabled"] is False
    assert q["activation_gate"] == "BLOCKED"

def test_santa_2011_source_is_bound_with_forbidden_inferences():
    d = json.loads(REG.read_text(encoding="utf-8"))
    s = next(x for x in d["sources"] if x["source_id"] == "ANA-SANTA-LOWER-REACH-2011")
    forbidden = " ".join(s["forbidden_inferences"]).lower()
    assert "datum" in forbidden
    assert "silently correct" in forbidden
    assert "observed historical event footprints" in forbidden
    assert "irfen thresholds" in forbidden
    assert d["qa"]["lower_santa_2011_native_coordinates_are_map_ready"] is False
    assert d["qa"]["lower_santa_2011_crs_frozen"] is False
