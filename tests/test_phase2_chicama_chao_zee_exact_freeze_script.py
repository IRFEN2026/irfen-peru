import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/phase2_chicama_chao_zee_layer39_freeze_v0_1.json"
SCRIPT = ROOT / "scripts/freeze_phase2_chicama_chao_zee_subunits.py"


def load_script():
    spec = importlib.util.spec_from_file_location("zee_freeze", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_candidate_set_is_fixed_and_unique():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    names = m.candidate_names(cfg)
    assert len(names) == 13
    assert len(set(names)) == 13
    assert "Cuenca Quirripano" in names
    assert "Intercuenca Chicama 137727" in names
    assert "Cuenca Chao" in names
    assert "Cuenca Tucumaca" in names
    assert "Cuenca Tutumo" in names
    assert "Unidad Hidrografica 137711" in names


def test_query_is_exact_and_reproducible_not_substring_selection():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    names = m.candidate_names(cfg)
    url = m.build_query_url(cfg, names)
    q = parse_qs(urlparse(url).query)
    where = q["where"][0]
    assert "Nombre_U_1 IN (" in where
    assert "LIKE" not in where
    assert q["returnGeometry"] == ["true"]
    assert q["outSR"] == ["4326"]
    assert q["geometryPrecision"] == ["7"]
    assert q["f"] == ["geojson"]


def test_feature_validation_requires_exact_complete_name_set():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    names = m.candidate_names(cfg)
    props = {k: None for k in cfg["source"]["required_fields"]}
    props["Nombre_U_1"] = names[0]
    props["OBJECTID"] = 1
    raw = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,0]]]},
        }],
    }
    try:
        m.validate_features(raw, cfg, names)
    except m.ProbeError as e:
        assert "QUERY_COUNT_MISMATCH" in str(e)
    else:
        raise AssertionError("partial feature set must fail closed")


def test_scientific_guards_stay_blocked_before_topology_qa():
    m = load_script()
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    m.validate_guards(cfg, "CONFIG")
    assert cfg["map_publish_enabled"] is False
    assert cfg["production_use"] is False
    assert cfg["production_ready"] is False
    assert cfg["operational_alerting_enabled"] is False
    assert cfg["activation_gate"] == "BLOCKED"
    assert cfg["decision_thresholds"] is None
    assert cfg["hydraulic_factors"] is None
