import json
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "site/data/phase2/sources/tumbes_zorritos_caf_1997_1998_event_context_v0_1.json"

def test_caf_zorritos_context_fail_closed():
    x = json.loads(P.read_text(encoding="utf-8"))
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["source"]["source_bytes_sha256"] is None
    assert x["adjudication"]["existing_children"]["las_delicias"]["map_publishable"] is False
    assert x["adjudication"]["existing_children"]["sechurita"]["map_publishable"] is False
    assert x["adjudication"]["existing_children"]["el_tiburon"]["map_publishable"] is False
    assert x["adjudication"]["quarantines"]["el_pozo_vs_los_pozos"]["status"] == "NAME_CROSSWALK_UNRESOLVED"
    assert x["adjudication"]["quarantines"]["los_peones_vs_los_leones"]["status"] == "SOURCE_INTERNAL_NAME_DISCREPANCY"
