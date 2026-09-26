import json
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "site/data/phase2/sources/ancash_santa_lower_reach_source_recovery_v0_1.json"

def test_guard():
    d = json.loads(P.read_text(encoding="utf-8"))
    assert d["activation_gate"] == "BLOCKED"
    assert d["production_use"] is False
    assert d["map_publication_enabled"] is False if "map_publication_enabled" in d else all(not v for v in d["scientific_effect"].values())
