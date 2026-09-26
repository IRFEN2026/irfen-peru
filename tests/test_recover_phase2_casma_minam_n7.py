import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
CONTRACT = ROOT / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"

spec = importlib.util.spec_from_file_location("casma_recovery", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def load_contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def feature_doc(code="1375961", name="Bajo Casma", area=418.7, nivel=7):
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "OBJECTID": 1,
                "CODIGO": code,
                "NIVEL": nivel,
                "NIVEL7": code,
                "NOMB_UH_N7": name,
                "Nombre_UH": name,
                "AREA_KM2": area,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-78.6, -9.8],
                    [-77.5, -9.8],
                    [-77.5, -8.8],
                    [-78.6, -8.8],
                    [-78.6, -9.8],
                ]],
            },
        }],
    }


def test_contract_is_fail_closed_and_exactly_nine_units():
    data = load_contract()
    for key, expected in module.SAFE.items():
        assert data[key] == expected
    assert [row["code"] for row in data["units"]] == [
        "1375961", "1375962", "1375963", "1375964", "1375965",
        "1375966", "1375967", "1375968", "1375969",
    ]
    assert data["validation"]["partial_archive_allowed"] is False
    assert data["validation"]["pdf_digitization_allowed"] is False
    assert data["validation"]["outlet_inference_allowed"] is False


def test_bounded_name_normalization():
    assert module.normalize_name(" Río   Sechín ") == module.normalize_name("Rio Sechin")
    assert module.normalize_name("YAUTÁN") == module.normalize_name("Yautan")


def test_exact_identity_area_and_geometry_pass():
    data = load_contract()
    out = module.validate_feature(data, data["units"][0], feature_doc())
    assert out["actual_name"] == "Bajo Casma"
    assert round(out["actual_area_km2"], 1) == 418.7


def test_wrong_code_fails_closed():
    data = load_contract()
    with pytest.raises(module.RecoveryError, match="CODE_MISMATCH"):
        module.validate_feature(data, data["units"][0], feature_doc(code="1375962"))


def test_wrong_name_fails_closed():
    data = load_contract()
    with pytest.raises(module.RecoveryError, match="NAME_MISMATCH"):
        module.validate_feature(data, data["units"][0], feature_doc(name="Otro nombre"))


def test_wrong_area_fails_closed():
    data = load_contract()
    with pytest.raises(module.RecoveryError, match="AREA_MISMATCH"):
        module.validate_feature(data, data["units"][0], feature_doc(area=420.0))


def test_wrong_level_fails_closed():
    data = load_contract()
    with pytest.raises(module.RecoveryError, match="LEVEL_MISMATCH"):
        module.validate_feature(data, data["units"][0], feature_doc(nivel=6))


def test_multiple_features_are_not_silently_dissolved():
    data = load_contract()
    doc = feature_doc()
    doc["features"].append(doc["features"][0])
    with pytest.raises(module.RecoveryError, match="FEATURE_COUNT_MISMATCH"):
        module.validate_feature(data, data["units"][0], doc)


def test_query_is_exact_and_requests_geojson_wgs84():
    data = load_contract()
    url = module.query_url(data, "1375961")
    assert "CODIGO" in url
    assert "1375961" in url
    assert "outSR=4326" in url
    assert "f=geojson" in url
