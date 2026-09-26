import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_casma_candidate_is_fail_closed():
    doc = load("site/data/phase2/sources/ancash_casma_n7_minam_vector_candidate_v0_1.json")
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["probe_status"]["geometry_retrieved"] is False
    assert doc["probe_status"]["map_publication_enabled"] is False


def test_santa_recovery_is_fail_closed():
    doc = load("site/data/phase2/sources/ancash_santa_lower_reach_source_recovery_v0_1.json")
    assert doc["activation_gate"] == "BLOCKED"
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert all(v is False for v in doc["original_assets_retrieved"].values())
    assert all(v is False for v in doc["scientific_effect"].values())
