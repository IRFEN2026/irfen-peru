import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "map_layers", ROOT / "scripts/build_map_layer_catalog.py"
)
map_layers = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(map_layers)


class MapLayerCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = map_layers.build_catalog()
        cls.priority = json.loads(map_layers.PRIORITY_PATH.read_text(encoding="utf-8"))

    def test_catalog_is_fail_closed(self):
        self.assertFalse(self.catalog["production_use"])
        self.assertFalse(self.catalog["production_ready"])
        self.assertFalse(self.catalog["operational_alerting_enabled"])
        self.assertTrue(self.catalog["relationship_to_v07_1"]["logic_unchanged"])
        self.assertTrue(self.catalog["relationship_to_v07_1"]["thresholds_unchanged"])
        self.assertFalse(self.catalog["relationship_to_v08"]["counts_toward_closeout"])
        self.assertEqual(self.catalog["summary"]["new_operational_zones"], 0)

    def test_technical_layers_are_non_operational_and_traceable(self):
        layers = self.catalog["technical_layers"]
        self.assertEqual(len(layers), 5)
        self.assertEqual(sum(layer["default_visibility"] for layer in layers), 2)
        for layer in layers:
            self.assertIn(layer["deployment_status"], {"TEST_ONLY", "RESEARCH_ONLY"})
            self.assertFalse(layer["loaded_into_operational_calculation"])
            self.assertFalse(layer["carries_alert_values"])
            self.assertFalse(layer["carries_risk_classification"])
            self.assertTrue(layer["source_path"].endswith((".geojson", ".json")))
            self.assertTrue(layer["source_ids"])
            self.assertTrue(layer["map_disclaimer"])

    def test_existing_geometry_files_have_hash_and_supported_geometry(self):
        for layer in self.catalog["technical_layers"]:
            metadata = layer["source_metadata"]
            if layer["required_in_repository"]:
                self.assertGreater(metadata["feature_count"], 0)
                self.assertEqual(len(metadata["sha256"]), 64)
                self.assertTrue(set(metadata["geometry_types"]).issubset(map_layers.ALLOWED_GEOMETRIES))
            else:
                self.assertEqual(layer["generated_by"], "scripts/build_ana_catacaos_segments.py")
                self.assertTrue(layer["provenance_sha256"])

    def test_chosica_candidate_sets_are_registered_but_off_by_default(self):
        layer = next(
            row for row in self.catalog["technical_layers"]
            if row["layer_id"] == "chosica_local_candidate_sets"
        )
        self.assertFalse(layer["default_visibility"])
        self.assertEqual(layer["confidence"], "LOW_OUTLET_AND_OFFICIAL_AREA_NOT_VALIDATED")
        self.assertEqual(layer["deployment_status"], "TEST_ONLY")

    def test_phase2_zones_have_minimum_reproducible_model(self):
        zones = self.catalog["research_zones"]
        self.assertEqual(len(zones), 18)
        required = {"geometry", "sources", "confidence", "coverage", "variables_available", "validation"}
        for zone in zones:
            self.assertTrue(required.issubset(zone))
            self.assertEqual(zone["deployment_status"], "RESEARCH_ONLY")
            self.assertFalse(zone["production_use"])
            self.assertFalse(zone["alerting_enabled"])
            self.assertEqual(zone["validation"]["activation_gate"], "BLOCKED")
            self.assertFalse(zone["development_priority"]["is_risk_or_operational_priority"])

    def test_missing_geometry_is_not_replaced_by_reference_points(self):
        zones = self.catalog["research_zones"]
        self.assertEqual(self.catalog["summary"]["research_candidates_map_eligible"], 0)
        for zone in zones:
            self.assertFalse(zone["geometry"]["map_eligible"])
            self.assertEqual(zone["geometry"]["representation"], "NOT_MAPPED_NO_REPRODUCIBLE_FILE")
        self.assertTrue(self.catalog["guardrails"]["reference_points_for_missing_geometry_forbidden"])

    def test_development_queue_is_complete_and_not_a_risk_score(self):
        rows = [item for wave in self.priority["waves"] for item in wave["candidates"]]
        self.assertEqual(len(rows), 18)
        self.assertEqual(sorted(item["development_order"] for item in rows), list(range(1, 19)))
        self.assertFalse(self.priority["scoring"]["numeric_score_used"])
        self.assertFalse(self.priority["scoring"]["risk_score_used"])
        self.assertFalse(self.priority["guardrails"]["promotion_from_this_queue_allowed"])

    def test_committed_catalog_matches_sources(self):
        committed = json.loads(map_layers.OUT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(map_layers.comparable(committed), map_layers.comparable(self.catalog))

    def test_web_layers_use_manifest_and_expose_research_tab(self):
        experimental = (ROOT / "site/v08-experimental.js").read_text(encoding="utf-8")
        expansion = (ROOT / "site/v08-expansion.js").read_text(encoding="utf-8")
        self.assertIn("data/map_layers.json", experimental)
        self.assertIn("loaded_into_operational_calculation", json.dumps(self.catalog))
        self.assertIn("sin alerta · sin puntuación de riesgo", experimental)
        self.assertIn("no se sustituyen por puntos aproximados", experimental)
        self.assertIn("data/map_layers.json", expansion)
        self.assertIn("no es prioridad de riesgo", expansion)

    def test_publishers_and_smoke_test_include_new_assets(self):
        for path in (
            ROOT / ".github/workflows/update-and-deploy.yml",
            ROOT / ".github/workflows/publish-committed-data.yml",
        ):
            workflow = path.read_text(encoding="utf-8")
            self.assertIn("build_map_layer_catalog.py", workflow)
            self.assertIn("v08-expansion.js", workflow)
            self.assertIn("site/data/map_layers.json", workflow)
        smoke = (ROOT / ".github/workflows/live-smoke-test.yml").read_text(encoding="utf-8")
        self.assertIn('"data/map_layers.json"', smoke)
        self.assertIn('"v08-expansion.js"', smoke)

    def test_geometry_builders_refresh_the_map_catalog(self):
        for path in (
            ROOT / ".github/workflows/build-san-ildefonso-v08.yml",
            ROOT / ".github/workflows/build-huaycoloro-v08.yml",
            ROOT / ".github/workflows/chosica-local-dem-candidates.yml",
        ):
            workflow = path.read_text(encoding="utf-8")
            self.assertIn("build_map_layer_catalog.py", workflow)
            self.assertIn("site/data/map_layers.json", workflow)


if __name__ == "__main__":
    unittest.main()
