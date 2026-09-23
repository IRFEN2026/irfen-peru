import copy
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


class ChancayHuaralLocalActivationTests(unittest.TestCase):
    def setUp(self):
        self.zone = load(ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_chancay_huaral.json")
        self.package = load(ROOT / "site/data/validation/phase2_registered_unit_packages/lima_norte_chancay_huaral_local_activation_v0_1.json")
        self.sources = load(ROOT / "site/data/phase2/sources/lima_norte_chancay_huaral_official_evidence_v0_1.json")

    def test_linked_package_passes_universal_fail_closed_validator(self):
        result = local_packages.validate_all()
        row = next(x for x in result["packages"] if x["candidate_id"] == "lima_norte_chancay_huaral")
        self.assertEqual(row["child_count"], 4)
        self.assertEqual(row["subunits_with_historical_evidence"], 2)
        self.assertEqual(row["map_eligible_child_count"], 0)
        self.assertIsNone(row["parent_activation_state"])
        self.assertEqual(row["activation_gate"], "BLOCKED")

    def test_parent_is_context_only_and_child_evidence_does_not_promote(self):
        parent = self.package["parent"]
        self.assertEqual(parent["role"], "CONTEXT_CONTAINER_NON_ACTIVATABLE")
        self.assertIsNone(parent["research_evidence_state"])
        self.assertIsNone(parent["activation_state"])
        self.assertFalse(parent["child_evidence_promotes_parent_activation"])
        self.assertTrue(parent["whole_basin_activation_statement_forbidden"])
        self.assertEqual(parent["parent_summary"]["statement"], "2 subunits with evidence")
        self.assertIsNone(parent["parent_summary"]["activation_statement"])

    def test_huerequeque_2017_state_is_local_direct_flow_evidence_only(self):
        children = {x["local_unit_id"]: x for x in self.package["children"]}
        q = children["quebrada_huerequeque"]
        self.assertEqual(q["historical_event_states"]["2017"]["state"], "DIRECT_FLOW_EVIDENCE")
        self.assertEqual(q["identity_source_ids"], ["ANA-CHANCAY-HUARAL-2017-HUAYAN-HUEREQUEQUE"])
        self.assertIsNone(q["geometry_path"])
        self.assertFalse(q["map_eligible"])
        self.assertFalse(q["state_is_operational_alert"])
        self.assertFalse(q["state_is_risk_class"])
        self.assertFalse(q["imerg_alone_can_select_activation"])
        self.assertFalse(q["absence_of_report_is_negative_control"])

    def test_huerequeque_state_is_supported_by_existing_admissible_official_claim(self):
        sources = {x["source_id"]: x for x in self.sources["sources"]}
        s = sources["ANA-CHANCAY-HUARAL-2017-HUAYAN-HUEREQUEQUE"]
        self.assertIn(
            "ANA attributed flooding at Huayan to activation of Quebrada Huerequeque",
            s["admissible_claims"],
        )
        self.assertIn("Quebrada Huerequeque geometry is resolved by the territorial report", s["forbidden_inferences"])

    def test_mainstem_flow_evidence_does_not_infer_receiver_overflow_or_threshold(self):
        children = {x["local_unit_id"]: x for x in self.package["children"]}
        mainstem = children["chancay_huaral_mainstem_observation"]
        rec = mainstem["historical_event_states"]["2017"]
        self.assertEqual(rec["state"], "DIRECT_FLOW_EVIDENCE")
        self.assertEqual(rec["source_reported_discharge_values_m3s"], [270, 277])
        self.assertEqual(rec["discrepancy_status"], "RETAINED_NOT_SILENTLY_RECONCILED")
        self.assertFalse(rec["receiver_overflow_inferred"])
        self.assertFalse(mainstem["provider_values_are_irfen_thresholds"])
        self.assertFalse(mainstem["tributary_activation_implies_mainstem_overflow"])
        self.assertFalse(mainstem["station_to_tributary_transfer_allowed_without_routing_qa"])

    def test_unresolved_children_remain_unmapped_and_unlabelled(self):
        children = {x["local_unit_id"]: x for x in self.package["children"]}
        for cid in ("subcuenca_huataya", "subcuenca_anasmayo"):
            child = children[cid]
            self.assertTrue(child["geometry_status"].startswith("MISSING"))
            self.assertIsNone(child["geometry_path"])
            self.assertFalse(child["map_eligible"])
            self.assertIsNone(child["current_research_evidence_state"])
            self.assertEqual(child["historical_event_states"], {})
            self.assertFalse(child["critical_point_context_is_event_evidence"])
            self.assertFalse(child["absence_of_report_is_negative_control"])

    def test_all_strict_phase2_guards_remain_exact(self):
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

    def test_validator_rejects_parent_promotion(self):
        unsafe_zone = copy.deepcopy(self.zone)
        unsafe_zone["local_activation_hierarchy"]["child_evidence_promotes_parent_activation"] = True
        with self.assertRaisesRegex(local_packages.LocalPackageError, "CHILD_TO_PARENT_PROMOTION"):
            local_packages.validate_one(
                "lima_norte_chancay_huaral",
                unsafe_zone,
                unsafe_zone["local_activation_hierarchy"],
            )


if __name__ == "__main__":
    unittest.main()
