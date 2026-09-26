import json
from pathlib import Path

def test_arequipa_endpoint_provenance():
    p = json.loads(Path("config/phase2_arequipa_cerro_colorado_ana_channel_endpoints_provenance_v0_1.json").read_text(encoding="utf-8"))
    assert p["source_id"] == "ANA-RD-1176-2024-AAA.CO"
    assert p["official"] is True
    assert p["parent_unit_code"] == "132"
    assert p["source_content_sha256"] is None
    assert len(p["evidence_table_sha256"]) == 64
