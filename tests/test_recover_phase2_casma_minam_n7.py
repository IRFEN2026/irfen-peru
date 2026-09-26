import importlib.util
import json
import unittest
from pathlib import Path

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
                    [-78.6, -9.8], [-77.5, -9.8], [-77.5, -8.8],
                    [-78.6, -8.8], [-78.6, -9.8],
                ]],
            },
        }],
    }


class CasmaMinamRecoveryTests(unittest.TestCase):
    def test_contract_is_fail_closed_and_exactly_nine_units(self):
        data = load_contract()
        for key, expected in module.SAFE.items():
            self.assertEqual(data[key], expected)
        self.assertEqual(
            [row["code"] for row in data["units"]],
            ["1375961", "1375962", "1375963", "1375964", "1375965",
             "1375966", "1375967", "1375968", "1375969"],
        )
        self.assertFalse(data["validation"]["partial_archive_allowed"])
        self.assertFalse(data["validation"]["pdf_digitization_allowed"])
        self.assertFalse(data["validation"]["outlet_inference_allowed"])

    def test_bounded_name_normalization(self):
        self.assertEqual(module.normalize_name(" Río   Sechín "), module.normalize_name("Rio Sechin"))
        self.assertEqual(module.normalize_name("YAUTÁN"), module.normalize_name("Yautan"))

    def test_exact_identity_area_and_geometry_pass(self):
        data = load_contract()
        out = module.validate_feature(data, data["units"][0], feature_doc())
        self.assertEqual(out["actual_name"], "Bajo Casma")
        self.assertEqual(round(out["actual_area_km2"], 1), 418.7)

    def test_identity_and_area_drift_fail_closed(self):
        data = load_contract()
        for doc, message in [
            (feature_doc(code="1375962"), "CODE_MISMATCH"),
            (feature_doc(name="Otro nombre"), "NAME_MISMATCH"),
            (feature_doc(area=420.0), "AREA_MISMATCH"),
            (feature_doc(nivel=6), "LEVEL_MISMATCH"),
        ]:
            with self.subTest(message=message):
                with self.assertRaisesRegex(module.RecoveryError, message):
                    module.validate_feature(data, data["units"][0], doc)

    def test_multiple_features_are_not_silently_dissolved(self):
        data = load_contract()
        doc = feature_doc()
        doc["features"].append(doc["features"][0])
        with self.assertRaisesRegex(module.RecoveryError, "FEATURE_COUNT_MISMATCH"):
            module.validate_feature(data, data["units"][0], doc)

    def test_query_is_exact_and_requests_geojson_wgs84(self):
        data = load_contract()
        url = module.query_url(data, "1375961")
        self.assertIn("CODIGO", url)
        self.assertIn("1375961", url)
        self.assertIn("outSR=4326", url)
        self.assertIn("f=geojson", url)


if __name__ == "__main__":
    unittest.main()
