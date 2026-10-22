"""Fail-closed documentary crosscheck of IGP Santa report 039-2025."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config/phase2_santa_igp_2025_geotechnical_crosscheck_v0_1.json"

class TestSantaIGP2025Crosscheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(PATH.read_text(encoding="utf-8"))

    def test_source_locator_and_unfrozen_hash_are_explicit(self):
        source = self.record["source"]
        self.assertEqual(source["report_number"], "039-2025/IGP")
        self.assertEqual(source["report_date"], "2025-11")
        self.assertIn("sigrid.cenepred.gob.pe", source["public_pdf_url"])
        self.assertIsNone(source["pdf_sha256"])
        self.assertEqual(source["pdf_sha256_status"], "UNKNOWN_BINARY_NOT_RECOVERED")

    def test_crosscheck_does_not_resolve_original_area_conflict(self):
        data = self.record["corroborated_documentary_values"]
        self.assertEqual(data["urban_dtm_area_ha"] + data["river_dtm_area_ha"], 1758)
        self.assertEqual(data["area_components_sum_ha"], 1758)
        self.assertFalse(self.record["source_relationship"]["2020_internal_1597_vs_1758_ha_conflict_resolved"])
        self.assertTrue(self.record["source_relationship"]["republication_of_prior_topographic_values_not_independent_field_survey"])

    def test_guardrails_and_missing_assets_fail_closed(self):
        r = self.record
        self.assertEqual(r["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(r["test_mode"], "TEST_ONLY")
        self.assertEqual(r["activation_gate"], "BLOCKED")
        self.assertEqual(r["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(r["decision_thresholds"])
        self.assertIsNone(r["hydraulic_factors"])
        for field in ("production_use", "production_ready", "operational_alerting_enabled",
                      "map_publication_enabled", "source_geometry_extracted",
                      "observed_event_footprint_created", "hydraulic_capacity_inferred",
                      "2011_axis_transformed"):
            with self.subTest(field=field):
                self.assertIs(r[field], False)
        for field in ("native_dtm_raster_recovered", "native_orthomosaic_recovered",
                      "native_contour_vectors_recovered", "2011_ana_hec_ras_geometry_recovered",
                      "2020_wgs84_utm17s_may_prove_2011_ana_datum"):
            with self.subTest(field=field):
                self.assertIs(r["source_relationship"][field], False)

if __name__ == "__main__":
    unittest.main()
