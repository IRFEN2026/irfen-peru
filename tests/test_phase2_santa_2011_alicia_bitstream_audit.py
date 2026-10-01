import json
import re
from pathlib import Path


def test_santa_2011_alicia_bitstream_audit_is_fail_closed():
    p = Path("site/data/phase2/source_assessments/santa_2011_alicia_bitstream_audit_v0_1.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["status"] == "PUBLIC_PRIMARY_BITSTREAM_AUDIT_COMPLETE_NATIVE_HYDRAULIC_ASSETS_NOT_INDEXED"
    assert data["source"]["oai_identifier"] == "oai:repositorio.ana.gob.pe:20.500.12543/2362"
    assert re.fullmatch(r"[0-9a-f]{32}MD51", data["source"]["primary_pdf_repository_digest"])
    assets = data["native_asset_inventory"]
    assert not any(assets[k] for k in assets if k.endswith("_indexed"))
    guards = data["guards"]
    assert guards["deployment_status"] == "RESEARCH_ONLY"
    assert guards["test_mode"] == "TEST_ONLY"
    assert guards["production_use"] is False
    assert guards["production_ready"] is False
    assert guards["operational_alerting_enabled"] is False
    assert guards["activation_gate"] == "BLOCKED"
    assert guards["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert guards["decision_thresholds"] is None
    assert guards["hydraulic_factors"] is None
