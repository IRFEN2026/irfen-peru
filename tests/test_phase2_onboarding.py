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
        cls.analog_contract = json.loads(phase2.ANALOG_CONTRACT_PATH.read_text(encoding="utf-8"))

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
        catalog = phase2.build_catalog(self.inventory, contracts, self.analog_contract)
        self.assertEqual(catalog["summary"]["registered_candidates"], 18)
        self.assertEqual(catalog["summary"]["operational_candidates"], 0)
        self.assertTrue(catalog["guardrails"]["activation_requires_zone_specific_validation"])
        self.assertTrue(all(z["deployment_status"] == "RESEARCH_ONLY" for z in catalog["zones"]))
        self.assertTrue(all(z["activation_gate"] == "BLOCKED" for z in catalog["zones"]))
        self.assertTrue(all(z["priority_score"] is None for z in catalog["zones"]))
        self.assertEqual(catalog["analog_transfer"]["mode"], "ANALOG_TRANSFER_TEST_ONLY")
        self.assertFalse(catalog["analog_transfer"]["local_validation"])

    def test_analog_transfer_contract_is_fail_closed(self):
        phase2.validate_analog_transfer_contract(self.analog_contract)
        unsafe_mutations = (
            (("production_use",), True),
            (("decision_use", "local_validation"), True),
            (("decision_use", "threshold_promotion"), True),
            (("donor_selection", "geographic_proximity_alone_is_sufficient"), True),
            (("normalization", "raw_millimetres_may_be_copied_as_validated_threshold"), True),
            (("mechanism_guards", "cross_mechanism_validation_allowed"), True),
            (("outcome_guards", "absence_of_report_is_none"), True),
        )
        for path, value in unsafe_mutations:
            contract = json.loads(json.dumps(self.analog_contract))
            target = contract
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(phase2.ContractError):
                phase2.validate_analog_transfer_contract(contract)

    def test_contracts_live_inside_existing_validation_trigger(self):
        self.assertEqual(
            phase2.CONTRACTS_DIR.relative_to(ROOT).as_posix(),
            "site/data/validation/phase2_zone_contracts",
        )
        workflow = (ROOT / ".github" / "workflows" / "update-and-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("site/data/validation/**", workflow)

    def test_public_generator_is_fail_closed_and_writable(self):
        catalog = phase2.generate_public_catalog(write=False)
        self.assertEqual(catalog["summary"]["registered_candidates"], 18)
        self.assertEqual(catalog["summary"]["operational_candidates"], 0)

    def test_user_named_lima_corridors_have_individual_fail_closed_contracts(self):
        required_ids = {
            "lima_norte_chillon_bajo",
            "lima_norte_chancay_huaral",
            "lima_norte_huaura_huacho_sayan",
            "lima_este_lurin_cieneguilla",
            "lima_sur_mala",
            "lima_sur_asia_omas",
            "lima_sur_canete",
        }
        candidates = {row["candidate_id"]: row for row in self.inventory["candidates"]}
        self.assertTrue(required_ids.issubset(candidates))
        for candidate_id in required_ids:
            path = phase2.CONTRACTS_DIR / f"{candidate_id}.json"
            self.assertTrue(path.is_file(), candidate_id)
            contract = json.loads(path.read_text(encoding="utf-8"))
            phase2.validate_contract(contract, candidates[candidate_id], path)
            self.assertEqual(contract["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(contract["validation"]["activation_gate"], "BLOCKED")
            self.assertFalse(contract["alerting_enabled"])
            self.assertIsNone(contract["decision_thresholds"])
            self.assertIsNone(contract["hydraulic_factors"])
            self.assertEqual(contract["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")

    def test_santa_eulalia_rimac_contract_is_compound_and_fail_closed(self):
        candidate = next(
            c for c in self.inventory["candidates"]
            if c["candidate_id"] == "lima_este_santa_eulalia_rimac"
        )
        contract = json.loads(
            (phase2.CONTRACTS_DIR / "lima_este_santa_eulalia_rimac.json").read_text(encoding="utf-8")
        )
        phase2.validate_contract(contract, candidate)
        self.assertIn("compound", contract["hazard_model"]["mechanism_preliminary"])
        self.assertEqual(contract["validation"]["activation_gate"], "BLOCKED")
        self.assertFalse(contract["alerting_enabled"])
        self.assertIsNone(contract["decision_thresholds"])
        self.assertIsNone(contract["hydraulic_factors"])
        self.assertEqual(contract["assets"]["observations"]["status"], "MISSING")
        self.assertIn("compound_hazard", contract["validation"]["required_reviews"])

    def test_geogps_mirror_is_secondary_research_only_and_fail_closed(self):
        scope = json.loads(
            (ROOT / "config" / "phase2_expansion_scope.json").read_text(encoding="utf-8")
        )
        source = next(
            row for row in scope["secondary_source_catalog"]
            if row["source_id"] == "GEOGPSPERU-HYDROGRAPHY-2023-MIRROR"
        )
        assessment_path = ROOT / source["assessment_path"]
        self.assertTrue(assessment_path.is_file())
        assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
        self.assertFalse(source["official_source"])
        self.assertFalse(source["counts_toward_validation"])
        self.assertEqual(assessment["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(assessment["production_use"])
        self.assertFalse(assessment["alerting_enabled"])
        self.assertFalse(assessment["counts_toward_v08_closeout"])
        self.assertFalse(assessment["counts_toward_zone_validation"])
        self.assertEqual(assessment["verification_gate"]["status"], "BLOCKED")
        self.assertEqual(
            assessment["verification_gate"]["missing_data_rule"],
            "UNKNOWN_NOT_LOW_RISK",
        )
        self.assertIn(
            "replace a DEM-delimited watershed",
            assessment["assessment"]["forbidden_uses"],
        )
        all_contract_source_ids = {
            source_id
            for path in phase2.CONTRACTS_DIR.glob("*.json")
            for source_id in json.loads(path.read_text(encoding="utf-8"))["official_source_ids"]
        }
        self.assertNotIn(source["source_id"], all_contract_source_ids)

    def test_committed_catalog_matches_contracts(self):
        generated = phase2.generate_public_catalog(write=False)
        committed = json.loads(phase2.OUT_PATH.read_text(encoding="utf-8"))
        generated.pop("generated_at", None)
        committed.pop("generated_at", None)
        self.assertEqual(committed, generated)


if __name__ == "__main__":
    unittest.main()
