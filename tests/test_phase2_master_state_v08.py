import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "site/data/validation/phase2_master_state_v08.json"
CASE_DIR = ROOT / "site/data/validation/phase2_case_validations"
PHASE2_CATALOG = ROOT / "site/data/phase2/catalog.json"
SANTA_CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"
LURIN_CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_este_lurin_cieneguilla.json"


class Phase2MasterStateV08Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads(MASTER.read_text(encoding="utf-8"))
        cls.catalog = json.loads(PHASE2_CATALOG.read_text(encoding="utf-8"))
        cls.santa_contract = json.loads(SANTA_CONTRACT.read_text(encoding="utf-8"))
        cls.lurin_contract = json.loads(LURIN_CONTRACT.read_text(encoding="utf-8"))
        cls.case_rows = {row["case_id"]: row for row in cls.master["cases"]}

    def test_master_state_is_non_operational_and_fail_closed(self):
        m = self.master
        self.assertEqual(m["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(m["production_use"])
        self.assertFalse(m["production_ready"])
        self.assertFalse(m["operational_alerting_enabled"])
        self.assertIsNone(m["decision_thresholds"])
        self.assertEqual(m["activation_gate"], "BLOCKED")
        self.assertTrue(m["guardrails"]["all_zone_activation_gates_remain_blocked"])

    def test_v08_operational_scope_is_not_expanded(self):
        scope = self.master["v08_scope"]
        self.assertTrue(scope["scope_unchanged"])
        self.assertFalse(scope["phase2_closeouts_are_operational_promotions"])
        self.assertFalse(scope["phase2_closeouts_count_toward_v08_release_scorecard"])
        self.assertEqual(scope["operational_pilots"], [
            "san_ildefonso", "chosica_huaycoloro", "catacaos_bajo_piura"
        ])
        self.assertTrue(self.catalog["relationship_to_v08"]["v08_scope_unchanged"])
        self.assertFalse(self.catalog["relationship_to_v08"]["phase2_candidates_are_operational"])

    def test_master_case_statuses_mirror_canonical_case_files(self):
        json_files = sorted(path for path in CASE_DIR.glob("*.json"))
        self.assertEqual(len(json_files), self.master["portfolio_summary"]["case_validation_files"])
        canonical = {}
        for path in json_files:
            case = json.loads(path.read_text(encoding="utf-8"))
            canonical[case["case_id"]] = case
        self.assertEqual(set(canonical), set(self.case_rows))
        for case_id, row in self.case_rows.items():
            source = canonical[case_id]
            self.assertEqual(row["case_status"], source["case_status"])
            self.assertFalse(source["production_use"])
            self.assertFalse(source["production_ready"])
            self.assertFalse(source["operational_alerting_enabled"])
            self.assertIsNone(source.get("decision_thresholds"))
            self.assertEqual(source["activation_gate"], "BLOCKED")

    def test_portfolio_counts_are_derived_from_case_status(self):
        statuses = [row["case_status"] for row in self.case_rows.values()]
        self.assertEqual(statuses.count("CLOSED_RESEARCH_VALIDATION_CASE"), 7)
        self.assertEqual(statuses.count("IN_REVIEW_RESEARCH_VALIDATION_CASE"), 1)
        self.assertEqual(self.master["portfolio_summary"]["closed_research_validation_cases"], 7)
        self.assertEqual(self.master["portfolio_summary"]["in_review_research_validation_cases"], 1)

    def test_phase2_contracts_remain_non_operational(self):
        summary = self.catalog["summary"]
        self.assertEqual(summary["registered_candidates"], 18)
        self.assertEqual(summary["contracts_approved"], 0)
        self.assertEqual(summary["operational_candidates"], 0)
        self.assertEqual(self.master["portfolio_summary"]["phase2_registered_candidates"], 18)
        self.assertEqual(self.master["portfolio_summary"]["phase2_contracts_approved"], 0)
        self.assertEqual(self.master["portfolio_summary"]["phase2_operational_candidates"], 0)

    def test_cashahuacra_closeout_does_not_close_compound_system(self):
        case = json.loads((CASE_DIR / "cashahuacra_santa_eulalia_2015.json").read_text(encoding="utf-8"))
        sep = case["compound_system_separation"]
        self.assertTrue(sep["cashahuacra_local_component_closed_for_research"])
        self.assertFalse(sep["santa_eulalia_river_component_resolved"])
        self.assertFalse(sep["rimac_receiving_river_component_resolved"])
        self.assertFalse(sep["compound_synchronization_validated"])
        self.assertEqual(self.santa_contract["contract_status"], "DRAFT")
        self.assertEqual(self.santa_contract["validation"]["activation_gate"], "BLOCKED")

    def test_lurin_closeout_does_not_activate_zone_contract(self):
        case = json.loads((CASE_DIR / "lurin_cieneguilla_pachacamac_2017.json").read_text(encoding="utf-8"))
        self.assertEqual(case["case_status"], "CLOSED_RESEARCH_VALIDATION_CASE")
        self.assertEqual(case["negative_control_status"]["status"], "NO_CONFIRMED_NEGATIVE_CONTROL")
        self.assertEqual(self.lurin_contract["contract_status"], "DRAFT")
        self.assertEqual(self.lurin_contract["validation"]["activation_gate"], "BLOCKED")
        self.assertIsNone(self.lurin_contract["decision_thresholds"])

    def test_pedregal_remains_in_review_and_sealed(self):
        case = json.loads((CASE_DIR / "pedregal_san_antonio_2015.json").read_text(encoding="utf-8"))
        self.assertEqual(case["case_status"], "IN_REVIEW_RESEARCH_VALIDATION_CASE")
        self.assertEqual(case["activation_gate"], "BLOCKED")
        self.assertTrue(self.master["guardrails"]["pedregal_clean_room_sealed_until_safe_unblind"])

    def test_threshold_and_missing_data_guards_are_preserved(self):
        guards = self.master["guardrails"]
        self.assertEqual(guards["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertTrue(guards["no_negative_from_absence_of_report"])
        self.assertTrue(guards["no_station_transfer_without_hydraulic_validation"])
        self.assertTrue(guards["no_modelled_value_as_observed_truth"])
        self.assertTrue(guards["no_historical_or_design_value_as_irfen_operational_threshold"])


if __name__ == "__main__":
    unittest.main()
