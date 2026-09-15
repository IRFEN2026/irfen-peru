import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "site/data/map_layers.json"


class MapLayerCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    def test_catalog_is_fail_closed(self):
        self.assertEqual(self.catalog["version"], "phase2-map-layer-catalog-v0.2")
        self.assertEqual(self.catalog["summary"]["research_candidates_registered"], 18)
        self.assertEqual(self.catalog["summary"]["new_operational_zones"], 0)
        self.assertTrue(self.catalog["guardrails"]["research_layers_non_operational"])
        self.assertTrue(self.catalog["guardrails"]["missing_geometry_not_approximated"])
        self.assertTrue(self.catalog["guardrails"]["reference_points_for_missing_geometry_forbidden"])

    def test_technical_layers_are_non_operational_and_traceable(self):
        self.assertEqual(self.catalog["summary"]["technical_layers_registered"], 5)
        for layer in self.catalog["technical_layers"]:
            self.assertIn(layer["deployment_status"], {"TEST_ONLY", "RESEARCH_ONLY"})
            self.assertFalse(layer["production_use"])
            self.assertFalse(layer["alerting_enabled"])
            self.assertIn("source", layer)
            self.assertIn("confidence", layer)

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
        eligible = {
            "lima_este_santa_eulalia_rimac",
            "lima_este_lurin_cieneguilla",
        }
        self.assertEqual(self.catalog["summary"]["research_candidates_map_eligible"], len(eligible))
        for zone in zones:
            if zone["candidate_id"] in eligible:
                self.assertTrue(zone["geometry"]["map_eligible"])
                self.assertEqual(zone["geometry"]["representation"], "REPRODUCIBLE_FILE")
            else:
                self.assertFalse(zone["geometry"]["map_eligible"])
                self.assertEqual(zone["geometry"]["representation"], "NOT_MAPPED_NO_REPRODUCIBLE_FILE")
        self.assertTrue(self.catalog["guardrails"]["reference_points_for_missing_geometry_forbidden"])

    def test_w1_santa_eulalia_geometry_is_review_only_and_traceable(self):
        zone = next(row for row in self.catalog["research_zones"]
                    if row["candidate_id"] == "lima_este_santa_eulalia_rimac")
        self.assertTrue(zone["geometry"]["map_eligible"])
        self.assertEqual(zone["geometry"]["representation"], "REPRODUCIBLE_FILE")
        self.assertEqual(zone["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(zone["production_use"])
        self.assertFalse(zone["alerting_enabled"])

    def test_existing_geometry_files_have_hash_and_supported_geometry(self):
        for zone in self.catalog["research_zones"]:
            geometry = zone["geometry"]
            if not geometry["map_eligible"]:
                continue
            self.assertIsNotNone(geometry["sha256"])
            self.assertIn(geometry["geometry_type"], {"Polygon", "MultiPolygon", "LineString", "MultiLineString", "FeatureCollection"})

    def test_development_queue_is_complete_and_not_a_risk_score(self):
        queue = self.catalog["development_queue"]
        self.assertEqual(len(queue), 18)
        self.assertFalse(self.catalog["guardrails"]["development_priority_is_risk_score"])
        self.assertTrue(all(not row["is_risk_or_operational_priority"] for row in queue))

    def test_web_layers_use_manifest_and_expose_research_tab(self):
        js = (ROOT / "site/app.js").read_text(encoding="utf-8")
        html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        self.assertIn("map_layers.json", js)
        self.assertIn("research", html.lower())

    def test_publishers_and_smoke_test_include_new_assets(self):
        workflow = (ROOT / ".github/workflows/update-and-deploy.yml").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts/live_smoke.py").read_text(encoding="utf-8")
        self.assertIn("build_map_layer_catalog.py", workflow)
        self.assertIn("map_layers.json", smoke)

    def test_geometry_builders_refresh_the_map_catalog(self):
        builders = [
            ROOT / "scripts/build_w1_santa_eulalia_rimac.py",
            ROOT / "scripts/build_w1_remaining_geometries.py",
            ROOT / "scripts/build_lambayeque_hydrologic_units.py",
        ]
        for path in builders:
            if path.exists():
                self.assertIn("build_map_layer_catalog", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
