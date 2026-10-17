import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "site/data/validation/phase2_discovery_packages/tumbes_zorritos_bocapan_coastal_ravines.json"
CONTRACT = ROOT / "site/data/validation/phase2_discovery_contracts/tumbes_zorritos_bocapan_coastal_ravines.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_zorritos_homonyms_are_quarantined():
    package = load(PACKAGE)
    contract = load(CONTRACT)
    pena = package["hydrologic_components"]["pena_negra"]["homonym_guard"]
    assert pena["status"] == "ACTIVE_DO_NOT_MERGE_SAME_NAME_FEATURES"
    assert pena["geometry_or_event_transfer_allowed"] is False
    san_pedro = package["hydrologic_components"]["san_pedro"]["homonym_guard"]
    assert san_pedro["geometry_or_event_transfer_allowed"] is False
    assert contract["homonym_guards"]["pena_negra"]["merge_allowed"] is False
    assert contract["homonym_guards"]["san_pedro"]["merge_allowed"] is False
