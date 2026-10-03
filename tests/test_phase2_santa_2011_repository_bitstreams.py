import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "site/data/phase2/source_assessments/santa_2011_repository_bitstream_inventory_v0_1.json"


class Santa2011RepositoryBitstreamTests(unittest.TestCase):
    def test_repository_inventory_is_fail_closed(self):
        d = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
        self.assertEqual(d["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(d["test_mode"], "TEST_ONLY")
        self.assertFalse(d["production_use"])
        self.assertFalse(d["production_ready"])
        self.assertFalse(d["operational_alerting_enabled"])
        self.assertEqual(d["activation_gate"], "BLOCKED")
        self.assertEqual(d["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(d["decision_thresholds"])
        self.assertIsNone(d["hydraulic_factors"])

    def test_original_pdf_has_repository_checksum_metadata(self):
        d = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
        original = next(x for x in d["institutional_record"]["bitstreams"] if x["role"] == "ORIGINAL")
        self.assertEqual(original["name"], "ANA0001097.pdf")
        self.assertEqual(original["size_bytes"], 5981714)
        self.assertEqual(original["repository_checksum_algorithm"], "MD5")
        self.assertEqual(len(original["repository_checksum"]), 32)

    def test_public_record_does_not_claim_model_assets(self):
        d = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
        g = d["model_asset_search"]
        self.assertFalse(g["hec_ras_project_listed_in_repository_record"])
        self.assertFalse(g["hec_georas_project_listed_in_repository_record"])
        self.assertFalse(g["arcgis_project_or_geodatabase_listed_in_repository_record"])
        self.assertFalse(g["dem_or_tin_listed_as_separate_bitstream"])
        self.assertFalse(g["cross_section_dataset_listed_as_separate_bitstream"])
        self.assertIn("does not prove", g["inference_limit"])
        self.assertFalse(d["reproducibility_effect"]["hydraulic_model_project_is_reproducible_from_public_assets"])
        self.assertFalse(d["reproducibility_effect"]["map_geometry_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
