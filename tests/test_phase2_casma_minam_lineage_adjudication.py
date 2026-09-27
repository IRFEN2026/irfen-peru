import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "site/data/phase2/source_assessments/casma_minam_n7_live_lineage_adjudication_v0_1.json"


def test_casma_minam_lineage_result_remains_fail_closed():
    d = json.loads(DOC.read_text(encoding="utf-8"))
    assert d["status"] == "PARTIAL_DESCENDANT_NOT_EQUIVALENT_TO_2007_SOURCE"
    assert d["raw_source_bytes_frozen"] is False
    assert d["map_publication_authorized"] is False
    assert d["findings"]["exact_codes_exposed"] is True
    assert d["findings"]["strict_2007_attribute_equivalence"] is False
    assert d["findings"]["observed_area_drift"] is True
    assert d["findings"]["observed_generic_name_designator_drift"] is True
    assert d["findings"]["area_tolerance_authorized"] is False
    assert d["findings"]["bounded_name_normalization_authorized"] is False
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
