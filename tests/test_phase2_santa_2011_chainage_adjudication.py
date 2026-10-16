import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "site/data/phase2/source_assessments/santa_2011_chainage_label_adjudication_v0_1.json"
SOURCE = ROOT / "site/data/phase2/sources/ancash_santa_lower_reach_2011_normalization_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


class Santa2011ChainageLabelAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessment = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
        cls.source = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_scientific_guards_remain_fail_closed(self):
        for key, expected in SAFE.items():
            self.assertEqual(self.assessment.get(key), expected, key)

    def test_source_contradiction_is_preserved_not_silently_corrected(self):
        rows = self.source["native_axis_points"]
        self.assertEqual(len(rows), 51)
        self.assertEqual(rows[0]["chainage"], "1+000")
        self.assertEqual(rows[0]["easting"], 758969)
        self.assertEqual(rows[0]["northing"], 9007565)
        self.assertEqual(rows[-2]["chainage"], "50+000")
        self.assertEqual(rows[-2]["easting"], 788372)
        self.assertEqual(rows[-2]["northing"], 9037490)
        self.assertEqual(rows[-1]["chainage"], "50+000")
        self.assertEqual(rows[-1]["easting"], 788881)
        self.assertEqual(rows[-1]["northing"], 9038309)

    def test_prose_endpoint_controls_are_recorded_without_relabeling(self):
        obs = self.assessment["direct_source_observations"]
        self.assertEqual(obs["prose_start"], {
            "chainage": "0+000",
            "easting": 758969,
            "northing": 9007565,
            "source_location": "printed page 68, paragraph immediately above Figure 18",
        })
        self.assertEqual(obs["prose_end"], {
            "chainage": "50+000",
            "easting": 788881,
            "northing": 9038309,
            "source_location": "printed page 68, paragraph immediately above Figure 18",
        })
        adjudication = self.assessment["adjudication"]
        self.assertTrue(adjudication["contradiction_confirmed"])
        self.assertFalse(adjudication["correction_applied"])
        self.assertTrue(adjudication["native_labels_preserved"])
        self.assertFalse(adjudication["corrected_chainages_emitted"])
        self.assertFalse(adjudication["transformed_geometry_emitted"])
        self.assertFalse(adjudication["map_publication_enabled"])

    def test_candidate_interpretation_is_not_promoted_to_geometry_or_hydraulics(self):
        policy = self.assessment["scientific_policy"]
        self.assertTrue(policy["silent_chainage_relabeling_forbidden"])
        self.assertTrue(policy["source_crs_datum_still_unresolved"])
        self.assertFalse(policy["hydraulic_capacity_inferred"])
        self.assertFalse(policy["event_footprint_created"])
        self.assertFalse(policy["threshold_created"])


if __name__ == "__main__":
    unittest.main()
