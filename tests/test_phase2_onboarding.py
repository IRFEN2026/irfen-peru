import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase2", ROOT / "scripts" / "build_phase2_catalog.py"
)
phase2 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(phase2)


class Phase2OnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(
            (ROOT / "config" / "phase2_candidate_inventory_v0_1.json").read_text(encoding="utf-8")
        )
        cls.candidate = cls.inventory["candidates"][0]

    def test_default_contract_is_blocked_and_non_operational(self):
        contract = phase2.default_contract(self.candidate)
        self.assertFalse(contract["production_use"])
        self.assertFalse(contract["alerting_enabled"])
        self.assertEqual(contract["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(contract["validation"]["activation_gate"], "BLOCKED")
        self.assertIsNone(contract["decision_thresholds"])
        self.assertIsNone(contract["hydraulic_factors"])
        phase2.validate_contract(contract, self.candidate)

    def test_threshold_or_hydraulic_factor_is_rejected(self):
        for field in ("decision_thresholds", "hydraulic_factors"):
            contract = phase2.default_contract(self.candidate)
            contract[field] = {"value": 1}
            with self.assertRaises(phase2.ContractError):
                phase2.validate_contract(contract, self.candidate)

    def test_missing_data_cannot_be_interpreted_as_low_risk(self):
        contract = phase2.default_contract(self.candidate)
        contract["missing_data_rule"] = "LOW_RISK"
        with self.assertRaises(phase2.ContractError):
            phase2.validate_contract(contract, self.candidate)

    def test_ready_asset_requires_existing_file(self):
        contract = phase2.default_contract(self.candidate)
        contract["assets"]["geometry"].update(status="READY", path="does/not/exist.geojson")
        with self.assertRaises(phase2.ContractError):
            phase2.validate_contract(contract, self.candidate)

    def test_approved_contract_requires_all_assets_and_mechanism(self):
        contract = phase2.default_contract(self.candidate)
        contract["contract_status"] = "APPROVED"
        with self.assertRaises(phase2.ContractError):
            phase2.validate_contract(contract, self.candidate)

    def test_catalog_keeps_all_candidates_research_only(self):
        contracts = {
            c["candidate_id"]: phase2.default_contract(c)
            for c in self.inventory["candidates"]
        }
        catalog = phase2.build_catalog(self.inventory, contracts)
        self.assertEqual(catalog["summary"]["registered_candidates"], 10)
        self.assertEqual(catalog["summary"]["operational_candidates"], 0)
        self.assertTrue(catalog["guardrails"]["activation_requires_zone_specific_validation"])
        self.assertTrue(all(z["deployment_status"] == "RESEARCH_ONLY" for z in catalog["zones"]))
        self.assertTrue(all(z["activation_gate"] == "BLOCKED" for z in catalog["zones"]))
        self.assertTrue(all(z["priority_score"] is None for z in catalog["zones"]))

    def test_contracts_live_inside_existing_validation_trigger(self):
        self.assertEqual(
            phase2.CONTRACTS_DIR.relative_to(ROOT).as_posix(),
            "site/data/validation/phase2_zone_contracts",
        )
        workflow = (ROOT / ".github" / "workflows" / "update-and-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("site/data/validation/**", workflow)

    def test_public_generator_is_fail_closed_and_writable(self):
        catalog = phase2.generate_public_catalog(write=False)
        self.assertEqual(catalog["summary"]["registered_candidates"], 10)
        self.assertEqual(catalog["summary"]["operational_candidates"], 0)

    def test_committed_catalog_matches_contracts(self):
        generated = phase2.generate_public_catalog(write=False)
        committed = json.loads(phase2.OUT_PATH.read_text(encoding="utf-8"))
        generated.pop("generated_at", None)
        committed.pop("generated_at", None)
        self.assertEqual(committed, generated)


if __name__ == "__main__":
    unittest.main()
