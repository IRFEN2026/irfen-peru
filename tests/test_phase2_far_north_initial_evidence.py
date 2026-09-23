import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "site/data/validation/phase2_discovery_evidence"

class FarNorthInitialEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chepen = json.loads((BASE / "lalibertad_chepen_initial_context_2023_2026.json").read_text(encoding="utf-8"))
        cls.mancora = json.loads((BASE / "piura_mancora_organos_initial_context_2020_2026.json").read_text(encoding="utf-8"))
        cls.zorritos = json.loads((BASE / "tumbes_zorritos_initial_context_2017_2026.json").read_text(encoding="utf-8"))
        cls.tumbes = json.loads((BASE / "tumbes_rio_tumbes_initial_context_2019_2026.json").read_text(encoding="utf-8"))

    def _closed(self, row):
        self.assertEqual(row["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(row["test_mode"], "TEST_ONLY")
        self.assertFalse(row["production_use"])
        self.assertFalse(row["production_ready"])
        self.assertFalse(row["operational_alerting_enabled"])
        self.assertEqual(row["activation_gate"], "BLOCKED")
        self.assertIsNone(row["decision_thresholds"])
        self.assertIsNone(row["hydraulic_factors"])

    def test_all_packages_fail_closed(self):
        for row in (self.chepen, self.mancora, self.zorritos, self.tumbes):
            with self.subTest(row=row["discovery_id"]):
                self._closed(row)

    def test_chepen_does_not_invent_a_river(self):
        sep = self.chepen["component_separation"]
        self.assertFalse(sep["synthetic_rio_chepen_allowed"])
        self.assertTrue(sep["rio_chaman_distinct"])
        self.assertTrue(sep["rio_la_morana_distinct"])
        self.assertTrue(sep["quebrada_avispero_distinct"])
        self.assertTrue(sep["rio_jequetepeque_separate_discovery_system"])

    def test_mancora_fernandez_is_verified_but_drain_is_separate(self):
        sep = self.mancora["component_separation"]
        self.assertTrue(sep["quebrada_fernandez_verified_activable"])
        self.assertFalse(sep["dren_primero_de_mayo_is_natural_ravine"])
        self.assertFalse(sep["quebrada_la_capilla_activation_verified"])
        self.assertFalse(sep["los_organos_local_catchments_resolved"])

    def test_zorritos_ravines_remain_separate_from_rio_tumbes(self):
        sep = self.zorritos["component_separation"]
        self.assertFalse(sep["composite_zorritos_polygon_allowed"])
        self.assertTrue(sep["rio_tumbes_is_separate"])
        self.assertTrue(sep["bocapan_casitas_requires_own_geometry"])

    def test_rio_tumbes_observed_context_is_not_threshold(self):
        obs = self.tumbes["observed_context"]
        self.assertEqual(obs["critical_points_2019_rio_tumbes"], 48)
        self.assertEqual(obs["april_2023"]["max_instantaneous_discharge_m3s"], 1833)
        self.assertFalse(obs["april_2023"]["irfen_threshold"])
        self.assertFalse(obs["february_2026"]["provider_alert_bands_are_irfen_thresholds"])
        self.assertEqual(len(obs["mapserver_2023"]), 2)

if __name__ == "__main__":
    unittest.main()
