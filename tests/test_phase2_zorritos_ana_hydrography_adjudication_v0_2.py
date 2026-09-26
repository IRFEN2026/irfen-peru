import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_adjudication_matrix_v0_2.json"

def load():
    return json.loads(MATRIX.read_text(encoding="utf-8"))

def test_fail_closed():
    x = load()
    assert x["deployment_status"] == "RESEARCH_ONLY"
    assert x["test_mode"] == "TEST_ONLY"
    assert x["production_use"] is False
    assert x["production_ready"] is False
    assert x["operational_alerting_enabled"] is False
    assert x["activation_gate"] == "BLOCKED"
    assert x["missing_data_rule"] == "UNKNOWN_NOT_LOW_RISK"
    assert x["decision_thresholds"] is None
    assert x["hydraulic_factors"] is None

def test_all_targets_unmapped():
    x = load()
    assert len(x["targets"]) == 14
    for row in x["targets"].values():
        assert row["map_publishable"] is False
        assert row["outlet_status"] == "UNRESOLVED"

def test_ambiguous_names_quarantined():
    x = load()
    for key in ("san_pedro", "pena_negra", "nueva_esperanza"):
        assert "HOMONYM_QUARANTINE" in x["targets"][key]["geometry_status"]
    for key in ("mal_paso_01", "mal_paso_02"):
        assert "SAME_NAME_SUBUNIT_QUARANTINE" in x["targets"][key]["geometry_status"]
