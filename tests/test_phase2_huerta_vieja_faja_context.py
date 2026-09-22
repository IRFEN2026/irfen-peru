import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/huerta_vieja_faja_context/ana_huerta_vieja_faja_hitos_v0_1.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_huerta_vieja_faja_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_huerta_vieja_geometry_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_huerta_vieja.json"


class HuertaViejaFajaContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_source_freezes_exact_official_hito_tables(self):
        self.assertEqual([x["id"] for x in self.source["left_margin"]], [f"HI-{i}" for i in range(1, 19)])
        self.assertEqual([x["id"] for x in self.source["right_margin"]], [f"HD-{i}" for i in range(1, 22)])
        self.assertEqual(self.source["left_margin"][0], {"id":"HI-1","easting_m":300596,"northing_m":8706636})
        self.assertEqual(self.source["left_margin"][-1], {"id":"HI-18","easting_m":300361,"northing_m":8705198})
        self.assertEqual(self.source["right_margin"][0], {"id":"HD-1","easting_m":300615,"northing_m":8706645})
        self.assertEqual(self.source["right_margin"][-1], {"id":"HD-21","easting_m":300445,"northing_m":8705185})
        self.assertTrue(self.source["source_interpretation"]["document_text_count_inconsistency"]["present"])

    def test_normalized_geometry_is_two_lines_never_a_polygon(self):
        self.assertEqual(self.geometry["type"], "FeatureCollection")
        features = self.geometry["features"]
        self.assertEqual(len(features), 2)
        self.assertEqual({f["geometry"]["type"] for f in features}, {"LineString"})
        by_margin = {f["properties"]["margin"]: f for f in features}
        self.assertEqual(len(by_margin["LEFT"]["geometry"]["coordinates"]), 18)
        self.assertEqual(len(by_margin["RIGHT"]["geometry"]["coordinates"]), 21)
        self.assertEqual(by_margin["LEFT"]["properties"]["unit_id"], "huerta_vieja_faja_left_margin")
        self.assertEqual(by_margin["RIGHT"]["properties"]["unit_id"], "huerta_vieja_faja_right_margin")

    def test_every_feature_preserves_fail_closed_semantics(self):
        for feature in self.geometry["features"]:
            props = feature["properties"]
            self.assertEqual(props["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(props["test_mode"], "TEST_ONLY")
            self.assertFalse(props["production_use"])
            self.assertFalse(props["production_ready"])
            self.assertFalse(props["alerting_enabled"])
            self.assertEqual(props["activation_gate"], "BLOCKED")
            self.assertEqual(props["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(props["decision_thresholds"])
            self.assertIsNone(props["hydraulic_factors"])
            self.assertTrue(props["not_catchment"])
            self.assertTrue(props["not_event_footprint"])
            self.assertTrue(props["not_historical_hydraulic_capacity"])
            self.assertFalse(props["candidate_wide_sampling_ready"])
            self.assertFalse(props["counts_as_complete_candidate_geometry"])

    def test_contract_links_partial_context_without_promotion(self):
        self.assertEqual(self.contract["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(self.contract["test_mode"], "TEST_ONLY")
        self.assertFalse(self.contract["production_use"])
        self.assertFalse(self.contract["production_ready"])
        self.assertFalse(self.contract["operational_alerting_enabled"])
        self.assertEqual(self.contract["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(self.contract["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(self.contract["decision_thresholds"])
        self.assertIsNone(self.contract["hydraulic_factors"])
        geometry = self.contract["assets"]["geometry"]
        self.assertEqual(geometry["status"], "PARTIAL")
        self.assertEqual(geometry["path"], "site/data/phase2/geometries/lima_norte_huerta_vieja_faja_context.geojson")
        self.assertEqual(set(geometry["source_ids"]), {"ANA-RD-0690-2025-AAACF", "ANA-IT-0112-2024-AAA-CF-MCFS"})
        self.assertEqual(self.contract["assets"]["historical_events"]["status"], "MISSING")
        self.assertEqual(self.contract["assets"]["observations"]["status"], "MISSING")
        self.assertEqual(self.contract["assets"]["hydraulic_context"]["status"], "MISSING")

    def test_validation_records_non_catchment_role(self):
        self.assertEqual(self.validation["status"], "PASS_PARTIAL_OFFICIAL_FAJA_CONTEXT_GEOMETRY")
        self.assertEqual(self.validation["feature_count"], 2)
        self.assertEqual(self.validation["geometry_types"], ["LineString"])
        self.assertFalse(self.validation["counts_as_complete_candidate_geometry"])
        self.assertFalse(self.validation["candidate_wide_sampling_ready"])
        self.assertFalse(self.validation["artificial_polygon_or_connector_used"])
        self.assertEqual(self.validation["component_resolution"]["catchment"], "UNRESOLVED_NOT_DERIVED_FROM_FAJA")
        self.assertEqual(self.validation["component_resolution"]["historical_hydraulic_capacity"], "UNKNOWN_NOT_INFERRED")

    def test_builder_replays_exact_committed_bytes(self):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_huerta_vieja_faja_context.py"), "--check-only"],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
