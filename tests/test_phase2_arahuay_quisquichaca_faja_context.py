import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/arahuay_quisquichaca_faja_context/ana_quisquichaca_faja_hitos_v0_1.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_arahuay_quisquichaca_faja_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_arahuay_quisquichaca_geometry_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_arahuay_chillon.json"


class ArahuayQuisquichacaFajaContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))
        cls.geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_source_uses_final_post_field_verification_table(self):
        right = self.source["right_margin"]
        left = self.source["left_margin"]
        self.assertEqual([x["id"] for x in right], [f"HD-{i}" for i in range(1, 46)])
        self.assertEqual([x["id"] for x in left], [f"HI-{i}" for i in range(1, 44)])
        self.assertEqual(len(right), 45)
        self.assertEqual(len(left), 43)
        self.assertEqual(right[0], {"id":"HD-1","easting_m":304646,"northing_m":8710120})
        self.assertEqual(right[1], {"id":"HD-2","easting_m":304763,"northing_m":8710029})
        self.assertEqual(right[-1], {"id":"HD-45","easting_m":310024,"northing_m":8710596})
        self.assertEqual(left[0], {"id":"HI-1","easting_m":304587,"northing_m":8710077})
        self.assertEqual(left[-1], {"id":"HI-43","easting_m":310005,"northing_m":8710551})
        self.assertEqual(self.source["source_interpretation"]["approved_hito_counts"], {"right_margin":45,"left_margin":43,"total":88})
        self.assertIn("item 2.7", self.source["source_interpretation"]["final_table_rule"])

    def test_normalized_geometry_is_two_lines_not_a_polygon(self):
        self.assertEqual(self.geometry["type"], "FeatureCollection")
        features = self.geometry["features"]
        self.assertEqual(len(features), 2)
        self.assertEqual({f["geometry"]["type"] for f in features}, {"LineString"})
        by_margin = {f["properties"]["margin"]: f for f in features}
        self.assertEqual(len(by_margin["RIGHT"]["geometry"]["coordinates"]), 45)
        self.assertEqual(len(by_margin["LEFT"]["geometry"]["coordinates"]), 43)
        self.assertEqual(by_margin["RIGHT"]["properties"]["unit_id"], "quisquichaca_faja_right_margin")
        self.assertEqual(by_margin["LEFT"]["properties"]["unit_id"], "quisquichaca_faja_left_margin")

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
            self.assertEqual(props["hydrologic_unit"], "Rio Quisquichaca")
            self.assertEqual(props["parent_system"], "Chillon")

    def test_contract_links_only_partial_quisquichaca_context(self):
        self.assertEqual(self.contract["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(self.contract["test_mode"], "TEST_ONLY")
        self.assertFalse(self.contract["production_use"])
        self.assertFalse(self.contract["production_ready"])
        self.assertFalse(self.contract["operational_alerting_enabled"])
        self.assertEqual(self.contract["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(self.contract["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(self.contract["decision_thresholds"])
        self.assertIsNone(self.contract["hydraulic_factors"])
        g = self.contract["assets"]["geometry"]
        self.assertEqual(g["status"], "PARTIAL")
        self.assertEqual(g["path"], "site/data/phase2/geometries/lima_norte_arahuay_quisquichaca_faja_context.geojson")
        self.assertEqual(set(g["source_ids"]), {"ANA-RD-0709-2025-AAACF", "ANA-IT-024-2024-P_ALACHRL_39-JEAC"})
        self.assertEqual(self.contract["assets"]["historical_events"]["status"], "MISSING")
        self.assertEqual(self.contract["assets"]["observations"]["status"], "MISSING")
        self.assertEqual(self.contract["assets"]["hydraulic_context"]["status"], "MISSING")

    def test_validation_keeps_compound_candidate_unresolved(self):
        v = self.validation
        self.assertEqual(v["status"], "PASS_PARTIAL_OFFICIAL_QUISQUICHACA_FAJA_CONTEXT_GEOMETRY")
        self.assertEqual(v["feature_count"], 2)
        self.assertEqual(v["geometry_types"], ["LineString"])
        self.assertEqual(v["field_verified_modified_right_hitos"], ["HD-1", "HD-2"])
        self.assertFalse(v["counts_as_complete_candidate_geometry"])
        self.assertFalse(v["candidate_wide_sampling_ready"])
        self.assertFalse(v["artificial_polygon_or_connector_used"])
        self.assertFalse(v["design_or_model_discharge_imported_as_capacity_or_threshold"])
        self.assertEqual(v["component_resolution"]["quisquichaca_catchment"], "UNRESOLVED_NOT_DERIVED_FROM_FAJA")
        self.assertEqual(v["component_resolution"]["other_arahuay_ravines"], "UNRESOLVED_NOT_CONNECTED_ARTIFICIALLY")
        self.assertEqual(v["component_resolution"]["chillon_river_reach"], "NOT_REPRESENTED_BY_THIS_ASSET")

    def test_builder_replays_exact_committed_bytes(self):
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/build_arahuay_quisquichaca_faja_context.py"), "--check-only"],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
