import json
from pathlib import Path

CFG=Path("config/phase2_arequipa_official_ravine_identities_provenance_v0_1.json")

def test_official_provenance_is_explicit():
    p=json.loads(CFG.read_text(encoding="utf-8"))
    assert p["verified_on"]=="2026-09-26"
    assert len(p["sources"])==5
    assert all(x["institution"]=="Autoridad Nacional del Agua" for x in p["sources"])
    assert all(x["official"] is True for x in p["sources"])
    assert all(x["source_bytes_archived"] is False for x in p["sources"])
    assert all(x["content_sha256"] is None for x in p["sources"])
    assert p["notes"]["regulatory_faja_is_not_channel_axis"] is True
    assert p["notes"]["regulatory_faja_is_not_event_footprint"] is True
