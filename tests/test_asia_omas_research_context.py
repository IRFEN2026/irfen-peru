import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/asia_omas_official_spatial_exposure_context_2016_2024.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_asia_omas.json"

class AsiaOmasResearchContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_guardrails_remain_closed(self):
        e = self.evidence
        c = self.contract
        self.assertEqual(e["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(e["test_mode"], "TEST_ONLY")
        self.assertFalse(e["production_use"])
        self.assertFalse(e["production_ready"])
        self.assertFalse(e["operational_alerting_enabled"])
        self.assertIsNone(e["decision_thresholds"])
        self.assertEqual(e["activation_gate"], "BLOCKED")
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["alerting_enabled"])
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")

    def test_official_omas_identity_is_bounded(self):
        unit = self.evidence["official_hydrologic_context"]["official_unit"]
        self.assertEqual(unit["code"], "1375512")
        self.assertEqual(unit["name"], "Cuenca Omas")
        self.assertEqual(unit["area_km2"], 1111.12)
        sep = self.evidence["component_separation"]
        self.assertTrue(sep["official_omas_unit_confirmed"])
        self.assertFalse(sep["local_asia_ravines_individually_normalized"])
        self.assertFalse(sep["hydrologic_equivalence_of_all_omas_rio_chico_local_ravines_confirmed"])

    def test_faja_is_not_event_footprint(self):
        faja = self.evidence["regulatory_spatial_context"]["rd0312_2022"]
        self.assertEqual(faja["reach_length_km"], 11.35)
        self.assertEqual(faja["main_reach_markers_total"], 179)
        self.assertEqual(faja["branch_markers_total"], 61)
        self.assertIn("NOT_EVENT_FOOTPRINT", faja["role"])
        self.assertFalse(faja["normalized_machine_readable_geometry_committed"])
        self.assertFalse(self.evidence["geometry_status"]["event_specific_inundation_footprint_available"])

    def test_2024_huaico_is_not_silently_assigned(self):
        event = self.evidence["historical_hazard_context"]["asia_huaico_2024_02_06"]
        self.assertEqual(event["event_date_local"], "2024-02-06")
        self.assertEqual(event["hazard"], "HUAICO")
        self.assertFalse(event["specific_watercourse_resolved"])
        self.assertFalse(event["assigned_to_omas_or_rio_chico"])
        self.assertFalse(self.evidence["component_separation"]["event_2024_assigned_to_named_watercourse"])

    def test_only_bounded_assets_advance(self):
        assets = self.contract["assets"]
        self.assertEqual(assets["geometry"]["status"], "PARTIAL")
        self.assertEqual(assets["geometry"]["path"], "site/data/phase2/geometries/lima_sur_asia_omas_omas_basin_context.geojson")
        document = json.loads((ROOT / assets["geometry"]["path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(document["features"]), 1)
        props = document["features"][0]["properties"]
        self.assertEqual(props["official_hydrologic_unit_code"], "1375512")
        self.assertEqual(props["official_hydrologic_unit_name"], "Cuenca Omas")
        self.assertFalse(props["local_asia_ravines_geometry_resolved"])
        self.assertFalse(props["coastal_fans_geometry_resolved"])
        self.assertFalse(props["event_2024_assigned_to_named_watercourse"])
        self.assertFalse(props["counts_as_complete_candidate_geometry"])
        self.assertEqual(assets["exposure"]["status"], "PARTIAL")
        self.assertEqual(assets["historical_events"]["status"], "MISSING")
        self.assertEqual(assets["observations"]["status"], "MISSING")
        self.assertEqual(assets["forecast"]["status"], "CANDIDATE")
        self.assertEqual(assets["hydraulic_context"]["status"], "MISSING")

    def test_no_negative_or_threshold_fabrication(self):
        self.assertFalse(self.evidence["observations_status"]["verified_negative_controls_available"])
        forbidden = set(self.evidence["forbidden_uses"])
        self.assertIn("operational threshold derivation", forbidden)
        self.assertIn("negative-control inference from missing reports", forbidden)

if __name__ == "__main__":
    unittest.main()
