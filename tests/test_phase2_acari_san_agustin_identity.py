import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "site/data/validation/phase2_research_evidence/acari_san_agustin_identity_review_20260923.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/arequipa_acari_san_agustin.json"


class AcariSanAgustinIdentityReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_scientific_guards_remain_closed(self):
        e = self.evidence
        c = self.contract
        for obj in (e, c):
            self.assertEqual(obj["deployment_status"], "RESEARCH_ONLY")
            self.assertFalse(obj["production_use"])
            self.assertFalse(obj["production_ready"])
            self.assertFalse(obj["operational_alerting_enabled"])
            self.assertIsNone(obj["decision_thresholds"])
            self.assertIsNone(obj["hydraulic_factors"])
            self.assertEqual(obj["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertEqual(e["test_mode"], "TEST_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertEqual(e["activation_gate"], "BLOCKED")
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")

    def test_reference_is_bounded_to_official_huanuhuanu_context(self):
        e = self.evidence
        self.assertEqual(e["official_source"]["document_id"], 21388)
        self.assertEqual(e["san_agustin_reference"]["district"], "Huanuhuanu")
        self.assertEqual(e["san_agustin_reference"]["locality"], "Anexo de María")
        self.assertEqual(e["san_agustin_reference"]["reported_datum"], "WGS 1984")
        self.assertEqual(e["san_agustin_reference"]["reported_utm_zone"], "18S")
        self.assertEqual(
            e["san_agustin_reference"]["reported_start"],
            {"easting_m": 588523.40, "northing_m": 8269699.82},
        )
        self.assertEqual(
            e["san_agustin_reference"]["reported_end"],
            {"easting_m": 588707.29, "northing_m": 8269234.16},
        )
        self.assertEqual(
            e["san_agustin_reference"]["coordinate_role"],
            "PROJECT_PROTECTION_REACH_ENDPOINTS_ONLY",
        )

    def test_no_channel_geometry_or_routing_is_invented(self):
        s = self.evidence["scientific_interpretation"]
        self.assertTrue(s["named_quebrada_identity_supported"])
        self.assertTrue(s["territorial_location_supported"])
        for key in (
            "full_channel_geometry_supported",
            "catchment_geometry_supported",
            "outlet_supported",
            "routing_to_rio_acari_supported",
            "event_footprint_supported",
            "historical_hydraulic_capacity_supported",
            "negative_control_supported",
            "map_geometry_materialized",
        ):
            self.assertFalse(s[key], key)
        implication = self.evidence["candidate_implication"]
        self.assertEqual(implication["candidate_geometry_status_change"], "NONE")
        self.assertEqual(implication["candidate_maturity_change"], "NONE")
        self.assertEqual(implication["activation_change"], "NONE")
        self.assertEqual(implication["map_action"], "NO_NEW_GEOMETRY")

    def test_existing_geometry_contract_stays_canonical_and_unpromoted(self):
        c = self.contract
        self.assertEqual(c["contract_status"], "DRAFT")
        self.assertEqual(c["assets"]["geometry"]["status"], "PARTIAL")
        self.assertTrue(c["assets"]["geometry"]["path"].endswith("_acari_basin_context.geojson"))
        self.assertEqual(c["validation"]["review_evidence"], [])
        self.assertNotIn(
            "CENEPRED-PPRRD-HUANUHUANU-2025-2030-SAN-AGUSTIN",
            c["official_source_ids"],
        )
        self.assertTrue(EVIDENCE.is_file())
        self.assertEqual(self.evidence["candidate_implication"]["map_action"], "NO_NEW_GEOMETRY")


if __name__ == "__main__":
    unittest.main()
