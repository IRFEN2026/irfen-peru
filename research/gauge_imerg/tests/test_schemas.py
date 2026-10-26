"""Contratos de datos versionados: el registro real y los ejemplos SINTÉTICOS cumplen sus esquemas."""
import importlib
import json
import os
import unittest
from pathlib import Path

import _synth

assert _synth.T0  # importar _synth fija la ruta del paquete y bloquea la red

HERE = Path(__file__).resolve().parents[1]
REQUIRE = os.environ.get("IRFEN_REQUIRE_JSONSCHEMA") == "1"
CASES = [
    ("observation_ledger", "evidence/north_gauge_reports_2026-10-22_25_v1.json"),
    ("observation_ledger", "evidence/tumbes_2026-10/north_gauge_reports_2026-10-21_26_v2.json"),
    ("observation_ledger", "examples/SYNTHETIC_observation_ledger.json"),
    ("cell_series", "examples/SYNTHETIC_cell_series.json"),
    ("pairs", "examples/SYNTHETIC_pairs.json"),
    ("station_validation_feed", "examples/SYNTHETIC_station_validation_feed.json"),
]


class Schemas(unittest.TestCase):
    def setUp(self):
        try:
            importlib.import_module("jsonschema")
        except ImportError:
            if REQUIRE:
                raise
            self.skipTest("jsonschema no instalado (en CI es obligatorio: IRFEN_REQUIRE_JSONSCHEMA=1)")

    def test_documents_conform(self):
        import jsonschema
        for schema, doc in CASES:
            with self.subTest(doc=doc):
                s = json.loads((HERE / f"schemas/{schema}.v1.schema.json").read_text(encoding="utf-8"))
                jsonschema.Draft202012Validator.check_schema(s)
                jsonschema.validate(json.loads((HERE / doc).read_text(encoding="utf-8")), s)

    def test_feed_contract_forbids_risk_fields(self):
        import jsonschema
        s = json.loads((HERE / "schemas/station_validation_feed.v1.schema.json").read_text(encoding="utf-8"))
        doc = json.loads((HERE / "examples/SYNTHETIC_station_validation_feed.json").read_text(encoding="utf-8"))
        doc["records"][0]["risk_level"] = "ALTO"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(doc, s)
        doc["records"][0].pop("risk_level")
        doc["guards"]["operational_alerting_enabled"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(doc, s)

    def test_examples_are_marked_synthetic(self):
        for _, doc in CASES[2:]:
            d = json.loads((HERE / doc).read_text(encoding="utf-8"))
            self.assertTrue(d.get("SYNTHETIC"), doc)
            self.assertIn("SINTÉTICO", d.get("_SYNTHETIC_NOTICE", ""))


if __name__ == "__main__":
    unittest.main()
