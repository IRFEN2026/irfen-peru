import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_phase2_linked_local_activation_packages as local_packages


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class HuauraLocalActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zone = load(ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_huaura_huacho_sayan.json")
        cls.package = load(ROOT / "site/data/validation/phase2_registered_unit_packages/lima_norte_huaura_huacho_sayan_local_activation_v0_1.json")
        cls.sources = load(ROOT / "site/data/phase2/sources/lima_norte_huaura_huacho_sayan_official_evidence_v0_1.json")

    def test_linked_package_passes_fail_closed_validator(self):
        result = local_packages.validate_all()
        row = next(x for x in result["packages"] if x["candidate_id"] == "lima_norte_huaura_huacho_sayan")
        self.assertEqual(row["child_count"], 2)
        self.assertEqual(row["subunits_with_historical_evidence"], 1)
        self.assertEqual(row["map_eligible_child_count"], 0)
        self.assertIsNone(row["parent_activation_state"])
        self.assertEqual(row["activation_gate"], "BLOCKED")

    def test_parent_is_context_only(self):
        parent = self.package["parent"]
        self.assertEqual(parent["role"], "CONTEXT_CONTAINER_NON_ACTIVATABLE")
        self.assertIsNone(parent["research_evidence_state"])
        self.assertIsNone(parent["activation_state"])
        self.assertFalse(parent["child_evidence_promotes_parent_activation"])
        self.assertEqual(parent["parent_summary"]["statement"], "1 subunit with evidence")
        self.assertIsNone(parent["parent_summary"]["activation_statement"])
        self.assertFalse(parent["official_basin_geometry_is_event_footprint"])

    def test_2023_impact_is_local_to_mainstem_context(self):
        children = {x["local_unit_id"]: x for x in self.package["children"]}
        mainstem = children["rio_huaura_humaya_vilcahuaura_impact_context"]
        event = mainstem["historical_event_states"]["2023"]
        self.assertEqual(event["state"], "IMPACT_CONFIRMED")
        self.assertEqual(event["source_ids"], ["ANA-HUAURA-HUMAYA-VILCAHUAURA-2023"])
        self.assertTrue(event["river_rise_reported"])
        self.assertTrue(event["named_infrastructure_impacts_reported"])
        self.assertFalse(event["event_footprint_reproducible"])
        self.assertFalse(event["local_ravine_activation_inferred"])
        self.assertFalse(event["receiver_overflow_extent_inferred"])
        self.assertIsNone(mainstem["geometry_path"])
        self.assertFalse(mainstem["map_eligible"])

    def test_alco_is_observation_control_not_threshold_or_ravine_proxy(self):
        children = {x["local_unit_id"]: x for x in self.package["children"]}
        alco = children["alco_sayan_hydrometric_control"]
        self.assertEqual(alco["unit_type"], "OUTLET_OR_CONTROL_POINT")
        self.assertEqual(alco["identity_source_ids"], ["ANA-HUAURA-ALCO-STATION-2021", "ANA-HUAURA-ALCO-STATION-2022"])
        self.assertIsNone(alco["geometry_path"])
        self.assertFalse(alco["map_eligible"])
        self.assertFalse(alco["provider_monitoring_objectives_are_irfen_thresholds"])
        self.assertFalse(alco["station_to_local_ravine_transfer_allowed_without_routing_qa"])
        self.assertFalse(alco["missing_observations_are_low_risk"])

    def test_existing_official_evidence_bounds_2023_inference(self):
        sources = {x["source_id"]: x for x in self.sources["sources"]}
        src = sources["ANA-HUAURA-HUMAYA-VILCAHUAURA-2023"]
        self.assertIn(
            "ANA reported damage at Humaya and Vilcahuaura intakes and diversion canals due to a rise of Rio Huaura",
            src["admissible_claims"],
        )
        self.assertIn("the event proves activation of unresolved local ravines", src["forbidden_inferences"])

    def test_receiver_and_meteorology_remain_separate(self):
        receiver = self.package["receiver_response"]
        self.assertFalse(receiver["tributary_activation_implies_receiver_overflow"])
        self.assertEqual(receiver["travel_time_status"], "MISSING_NOT_INFERRED")
        self.assertEqual(receiver["peak_coincidence_status"], "MISSING_NOT_INFERRED")
        self.assertIsNone(receiver["hydraulic_capacity_values"])
        met = self.package["meteorology_policy"]
        self.assertEqual(met["imerg_role"], "REGIONAL_OR_SUBBASIN_CONTEXT_ONLY")
        self.assertFalse(met["imerg_alone_selects_small_ravine_activation"])

    def test_strict_phase2_guards_remain_exact(self):
        for obj in (self.zone, self.package):
            self.assertEqual(obj["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(obj["test_mode"], "TEST_ONLY")
            self.assertFalse(obj["production_use"])
            self.assertFalse(obj["production_ready"])
            self.assertFalse(obj["operational_alerting_enabled"])
            gate = obj["activation_gate"] if "activation_gate" in obj else obj["validation"]["activation_gate"]
            self.assertEqual(gate, "BLOCKED")
            self.assertEqual(obj["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(obj["decision_thresholds"])
            self.assertIsNone(obj["hydraulic_factors"])


if __name__ == "__main__":
    unittest.main()
