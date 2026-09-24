import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "config/phase2_north_coast_discovery_inventory_v0_1.json"
SCOPE = ROOT / "config/phase2_expansion_scope.json"
CLIMATE = ROOT / "config/phase2_climate_conditioned_research_priority_v0_1.json"


class Phase2NorthCoastDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = json.loads(PATH.read_text(encoding="utf-8"))
        cls.scope = json.loads(SCOPE.read_text(encoding="utf-8"))
        cls.climate = json.loads(CLIMATE.read_text(encoding="utf-8"))

    @staticmethod
    def source_registry_ids(discovery_id):
        """Resolve source IDs from an explicit per-package source registry when present.

        The original north-coast inventory keeps a compact shared source_catalog. Newer
        bounded discovery packages may instead carry a source_registry_path so their
        evidence can stay independently versioned and fail-closed without duplicating
        URLs into the shared inventory.
        """
        package_path = ROOT / "site/data/validation/phase2_discovery_packages" / f"{discovery_id}.json"
        if not package_path.is_file():
            return set()
        package = json.loads(package_path.read_text(encoding="utf-8"))
        registry_path = package.get("source_registry_path")
        if not registry_path:
            return set()
        full_path = ROOT / registry_path
        if not full_path.is_file():
            return set()
        registry = json.loads(full_path.read_text(encoding="utf-8"))
        return {
            row.get("source_id")
            for row in registry.get("sources", [])
            if isinstance(row, dict) and row.get("source_id")
        }

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
        self.assertEqual(rel["discovery_units_count"], 18)
        self.assertEqual(rel["discovery_units_count"], len(c["discovery_units"]))

    def test_user_requested_corridors_are_explicit(self):
        ids = {r["discovery_id"] for r in self.cfg["discovery_units"]}
        required = {
            "lima_norte_supe_caleta_vidal",
            "lima_norte_pativilca",
            "lima_norte_fortaleza_paramonga",
            "ancash_huarmey_culebras",
            "ancash_casma_sechin_yautan",
            "ancash_chimbote_lacramarca_santa_bajo",
            "lalibertad_viru",
            "lalibertad_chao_huamanzaña_chorobal",
            "lalibertad_moche",
            "lalibertad_jequetepeque",
            "lalibertad_chicama",
            "tumbes_rio_tumbes",
            "tumbes_zorritos_bocapan_coastal_ravines",
            "piura_mancora_los_organos_coastal_ravines",
            "lalibertad_chepen_chaman_morana_avispero",
            "piura_colan_bajo_chira_local_ravines",
            "piura_talara_parinas_local_ravines",
            "piura_paita_urban_local_ravines",
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

    def test_jequetepeque_is_separate_and_regulation_is_explicit(self):
        rows = {r["discovery_id"]: r for r in self.cfg["discovery_units"]}
        row = rows["lalibertad_jequetepeque"]
        self.assertIn("Rio Zaña", row["must_not_merge_with"])
        self.assertIn("Rio Chicama", row["must_not_merge_with"])
        self.assertTrue(any("Gallito Ciego" in item for item in row["first_work_package"]))

    def test_chepen_and_far_north_components_are_fail_closed(self):
        rows = {r["discovery_id"]: r for r in self.cfg["discovery_units"]}
        chepen = rows["lalibertad_chepen_chaman_morana_avispero"]
        self.assertIn("Rio Jequetepeque", chepen["must_not_merge_with"])
        mancora = rows["piura_mancora_los_organos_coastal_ravines"]
        self.assertIn("Quebrada Fernandez", mancora["hydrologic_components"])
        zorritos = rows["tumbes_zorritos_bocapan_coastal_ravines"]
        self.assertIn("Quebrada Bocapan-Casitas", zorritos["hydrologic_components"])
        tumbes = rows["tumbes_rio_tumbes"]
        self.assertIn("Rio Zarumilla", tumbes["must_not_merge_with"])

    def test_every_discovery_unit_has_sources_and_a_work_package(self):
        source_catalog = self.cfg["source_catalog"]
        inventory_registry = self.cfg.get("source_registry", {})
        self.assertIsInstance(inventory_registry, dict)
        for row in self.cfg["discovery_units"]:
            self.assertGreaterEqual(len(row["official_source_ids"]), 2, row["discovery_id"])
            self.assertGreaterEqual(len(row["first_work_package"]), 4, row["discovery_id"])
            registry_ids = self.source_registry_ids(row["discovery_id"])
            for source_id in row["official_source_ids"]:
                self.assertTrue(
                    source_id in source_catalog
                    or source_id in inventory_registry
                    or source_id in registry_ids,
                    f"{row['discovery_id']}: unresolved official source id {source_id}",
                )

    def test_extension_is_referenced_by_scope_and_climate_overlay(self):
        ext = self.scope["north_coast_discovery_extension"]
        self.assertEqual(ext["inventory"], "config/phase2_north_coast_discovery_inventory_v0_1.json")
        self.assertEqual(ext["registered_candidate_count_unchanged"], 18)
        self.assertIn("Jequetepeque", ext["requested_corridors"])
        north = next(r for r in self.climate["scenario_corridors"]
                     if r["corridor_id"] == "PACIFIC_NORTH_CENTRAL_WARM_EVENT")
        self.assertEqual(north["discovery_inventory"], ext["inventory"])
        self.assertTrue(any(gap.startswith("Jequetepeque:") for gap in north["discovery_gaps"]))


if __name__ == "__main__":
    unittest.main()
