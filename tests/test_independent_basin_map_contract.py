import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "site" / "data" / "independent_validation" / "basins.json"


class IndependentBasinMapContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_independent_map_is_strictly_non_operational(self):
        data = self.data
        self.assertEqual(data["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(data["test_status"], "TEST_ONLY")
        self.assertIs(data["production_use"], False)
        self.assertIs(data["production_ready"], False)
        self.assertIs(data["operational_alerting_enabled"], False)
        self.assertIs(data["operational_labels_allowed"], False)
        self.assertEqual(data["blind_outcome_evidence"], "SEALED")
        self.assertIs(data["map_policy"]["never_enters_operational_calc"], True)
        for basin in data["basins"]:
            self.assertIs(basin["production_use"], False)
            self.assertIs(basin["production_ready"], False)
            self.assertIs(basin["operational_alerting_enabled"], False)

    def test_every_mapped_basin_has_reproducible_geometry_reference(self):
        data = self.data
        self.assertTrue(data["basins"])
        for basin in data["basins"]:
            geometry = basin["geometry"]
            self.assertTrue(geometry["source_path"])
            self.assertTrue(geometry["feature_property"])
            self.assertTrue(geometry["feature_value"])
            source = ROOT / "site" / geometry["source_path"]
            self.assertTrue(source.exists(), f"Missing geometry source for {basin['basin_id']}: {source}")
            fc = json.loads(source.read_text(encoding="utf-8"))
            self.assertTrue(
                any(
                    feature.get("properties", {}).get(geometry["feature_property"])
                    == geometry["feature_value"]
                    for feature in fc.get("features", [])
                ),
                f"Geometry selector did not resolve for {basin['basin_id']}",
            )

    def test_public_indicators_are_scientific_traceability_only(self):
        data = self.data
        forbidden_indicator_ids = {
            "risk",
            "risk_score",
            "threat",
            "threat_score",
            "priority",
            "priority_score",
            "alert",
            "activation",
            "operational_status",
        }
        for basin in data["basins"]:
            indicators = basin["public_indicators"]
            self.assertGreaterEqual(len(indicators), 1)
            self.assertLessEqual(len(indicators), 6)
            ids = {item["id"] for item in indicators}
            self.assertTrue(ids.isdisjoint(forbidden_indicator_ids))
            self.assertEqual(basin["blind_assessment_status"], "SEALED")

    def test_missing_is_not_recast_as_low_risk_and_smap_is_not_imputed(self):
        data = self.data
        self.assertEqual(
            data["map_policy"]["missing_data_semantics"],
            "UNKNOWN_OR_MISSING_NEVER_LOW_RISK",
        )
        cashahuacra = next(b for b in data["basins"] if b["basin_id"] == "cashahuacra")
        self.assertEqual(
            cashahuacra["sensors"]["smap"]["status"],
            "MISSING_FOR_EVENT_WINDOW",
        )
        self.assertIs(cashahuacra["sensors"]["smap"]["imputation_allowed"], False)

    def test_cashahuacra_requires_outlet_revalidation_against_ana_seed(self):
        data = self.data
        cashahuacra = next(b for b in data["basins"] if b["basin_id"] == "cashahuacra")
        geometry = cashahuacra["geometry"]
        self.assertEqual(
            geometry["status"],
            "REVIEW_ONLY_CANDIDATE_REVALIDATION_REQUIRED",
        )
        self.assertEqual(
            geometry["ana_channel_seed"]["role"],
            "SNAP_SEED_ONLY_NOT_FORCED_OUTLET",
        )
        self.assertGreater(geometry["existing_outlet_to_ana_seed_distance_m"], 0)
        self.assertIs(geometry["raw_byte_hash_independently_reverified"], False)


if __name__ == "__main__":
    unittest.main()
