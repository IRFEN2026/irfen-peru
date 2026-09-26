import json
from pathlib import Path

CFG=Path("config/phase2_ica_official_ravine_identities_provenance_v0_1.json")

def test_ica_provenance_is_bounded_and_official():
    p=json.loads(CFG.read_text(encoding="utf-8"))
    assert p["verified_on"]=="2026-09-26"
    assert len(p["sources"])==2
    assert all(x["institution"]=="Autoridad Nacional del Agua" for x in p["sources"])
    assert all(x["official"] is True for x in p["sources"])
    assert all(x["source_bytes_archived"] is False for x in p["sources"])
    assert all(x["content_sha256"] is None for x in p["sources"])
    assert p["notes"]["map_context_does_not_freeze_local_geometry"] is True
    assert p["notes"]["critical_point_is_not_activation_event"] is True
    assert p["notes"]["cansas_coordinate_extract_requires_source_table_validation_before_geometry_use"] is True
