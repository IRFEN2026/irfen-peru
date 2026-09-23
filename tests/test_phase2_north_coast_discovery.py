import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"

class Phase2NorthCoastDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(PATH.read_text(encoding="utf-8"))

    def test_extension_is_fail_closed_and_does_not_change_registered_count(self):
        c = self.cfg
        self.assertEqual(c["status"], "RESEARCH_ONLY_DISCOVERY_EXTENSION")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertEqual(c["activation_gate"], "BLOCKED")
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        rel = c["relationship_to_phase2"]
        self.assertEqual(rel["registered_candidate_count_unchanged"], 18)
        self.assertFalse(rel["changes_registered_candidate_count"])
        self.assertFalse(rel["changes_operational_scope"])
        self.assertTrue(rel["promotion_requires_explicit_versioned_migration"])

    def test_user_requested_corridors_are_explicit(self):
        ids = {r["discovery_id"] for r in self.cfg["discovery_units"]}
        required = {
            "lima_norte_pativilca",
            "lima_norte_fortaleza_paramonga",
            "ancash_huarmey_culebras",
            "ancash_casma_sechin_yautan",
            "ancash_chimbote_lacramarca_santa_bajo",
            "lalibertad_viru",
            "lalibertad_chao_huamanzaña_chorobal",
            "lalibertad_moche",
            "lalibertad_chicama",
        }
        self.assertEqual(ids, required)

    def test_huaura_and_huaral_are_strengthened_not_duplicated(self):
        ids = {r["candidate_id"] for r in self.cfg["registered_units_to_strengthen"]}
        self.assertEqual(ids, {"lima_norte_chancay_huaral", "lima_norte_huaura_huacho_sayan"})

    def test_territorial_groupers_require_hydrologic_children(self):
        rows = {r["discovery_id"]: r for r in self.cfg["discovery_units"]}
        for cid in ("ancash_chimbote_lacramarca_santa_bajo", "lalibertad_chao_huamanzaña_chorobal"):
            self.assertIn("REQUIRES_HYDROLOGIC_CHILDREN", rows[cid]["entity_role"])
            self.assertGreaterEqual(len(rows[cid]["hydrologic_components"]), 2)

    def test_paramonga_is_not_silently_merged_with_pativilca(self):
        rows = {r["discovery_id"]: r for r in self.cfg["discovery_units"]}
        self.assertIn("Rio Pativilca", rows["lima_norte_fortaleza_paramonga"]["must_not_merge_with"])
        self.assertIn("Rio Fortaleza", rows["lima_norte_pativilca"]["must_not_merge_with"])

    def test_every_discovery_unit_has_sources_and_a_work_package(self):
        source_catalog = self.cfg["source_catalog"]
        for row in self.cfg["discovery_units"]:
            self.assertGreaterEqual(len(row["official_source_ids"]), 2, row["discovery_id"])
            self.assertGreaterEqual(len(row["first_work_package"]), 4, row["discovery_id"])
            for source_id in row["official_source_ids"]:
                self.assertIn(source_id, source_catalog, source_id)

if __name__ == "__main__":
    unittest.main()
