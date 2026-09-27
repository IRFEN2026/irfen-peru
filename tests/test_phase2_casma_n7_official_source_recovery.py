import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "config/phase2_casma_n7_official_source_recovery_v0_1.json"

def load():
    return json.loads(DOC.read_text(encoding="utf-8"))

def test_casma_official_dataset_identity_is_bounded_and_fail_closed():
    d = load()
    assert d["status"] == "OFFICIAL_PUBLIC_DOWNLOAD_PATH_IDENTIFIED_EXACT_N7_BYTES_NOT_YET_FROZEN"
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_mode"] == "TEST_ONLY"
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["activation_gate"] == "BLOCKED"
    assert d["decision_thresholds"] is None
    assert d["hydraulic_factors"] is None
    assert d["official_dataset_identity"]["documented_dataset_basename"] == "Uh_pfas100"
    assert d["official_dataset_identity"]["source_scale"] == "1:100000"
    assert d["official_dataset_identity"]["reference_system"] == "WGS84"

def test_casma_n7_recovery_requires_exact_bytes_and_all_nine_codes():
    d = load()
    rows = d["casma_n7_expected"]
    assert [r["code"] for r in rows] == ["1375961","1375962","1375963","1375964","1375965","1375966","1375967","1375968","1375969"]
    assert d["exact_byte_gate"]["retrieved"] is False
    assert d["exact_byte_gate"]["source_archive_sha256"] is None
    assert d["scientific_effect"]["child_geometry_created"] is False
    assert d["scientific_effect"]["map_publication_enabled"] is False

def test_casma_recovery_contract_forbids_pdf_and_n6_substitution():
    d = load()
    forbidden = " ".join(d["forbidden"]).lower()
    assert "pdf" in forbidden
    assert "n6" in forbidden
    assert "event outcomes" in forbidden
