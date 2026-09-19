"""Tests for the Phase-2 asset_readiness / promotion_gate projections (PR-C).

These tests exercise the fix for the READY/gate-semantics problem flagged for
`lima_este_santa_eulalia_rimac`: `historical_events.status == "READY"` means
only "an asset file is registered", never "the minimum verified-sample
requirement is scientifically demonstrated" nor "this research contract is
eligible for promotion". `asset_readiness` and `promotion_gate` are additive,
derived projections; they never rename, remove, or replace `asset_status`,
`readiness_stage`, or `blocking_items`, and they never touch scientific
cases, historical evidence, or Phase-2 contract files.
"""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase2_ready_gate", ROOT / "scripts" / "build_phase2_catalog.py"
)
phase2 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(phase2)


class DataPresenceTests(unittest.TestCase):
    """data_presence must be derived strictly from path + real file existence."""

    def test_nonexistent_file_cannot_give_present(self):
        # Required test: a path that does not resolve to a real file on disk
        # can never be reported PRESENT, no matter what an asset's `status`
        # field claims.
        self.assertEqual(
            phase2.data_presence("site/data/validation/phase2_zone_contracts/does_not_exist_xyz.json"),
            "MISSING",
        )

    def test_none_or_empty_path_is_missing(self):
        self.assertEqual(phase2.data_presence(None), "MISSING")
        self.assertEqual(phase2.data_presence(""), "MISSING")

    def test_absolute_path_is_not_treated_as_repository_presence(self):
        absolute = str(ROOT / "config" / "phase2_candidate_inventory_v0_2.json")
        self.assertEqual(phase2.data_presence(absolute), "UNKNOWN")

    def test_real_committed_file_is_present(self):
        self.assertEqual(
            phase2.data_presence("site/data/validation/phase2_zone_contracts/lima_sur_malanche.json"),
            "PRESENT",
        )


class NegativeControlLegTests(unittest.TestCase):
    """Only the single unambiguous literal signal is ever treated as False."""

    def test_exact_literal_is_false(self):
        case = {"negative_control_status": {"status": "NO_CONFIRMED_NEGATIVE_CONTROL"}}
        self.assertIs(phase2.evaluate_negative_control_leg(case), False)

    def test_differently_worded_synonym_is_null_not_false(self):
        # catacaos_bajo_piura_2002_2021.json uses this different literal
        # ("INSUFFICIENT_CONFIRMED_NEGATIVES"); it must not be silently
        # treated as equivalent to the recognized signal.
        case = {"negative_control_status": {"status": "INSUFFICIENT_CONFIRMED_NEGATIVES"}}
        self.assertIsNone(phase2.evaluate_negative_control_leg(case))

    def test_absent_field_is_null(self):
        self.assertIsNone(phase2.evaluate_negative_control_leg({}))
        self.assertIsNone(phase2.evaluate_negative_control_leg({"negative_control_status": None}))


class HistoricalEventsGateTests(unittest.TestCase):
    def test_no_minimum_declared_is_not_applicable(self):
        gate_met, status, basis = phase2.compute_historical_events_gate(
            "synthetic_zone", {"path": None}, {}, {}
        )
        self.assertIsNone(gate_met)
        self.assertEqual(status, "NOT_APPLICABLE")
        self.assertIsNone(basis)

    def test_no_linkable_case_is_null_not_false(self):
        # Required test: an undeterminable minimum (no case can be
        # mechanically linked) must resolve to null, never False.
        asset = {"path": None, "minimum_verified_event_days": 1, "minimum_verified_none_days": 10}
        gate_met, status, basis = phase2.compute_historical_events_gate(
            "zone_with_no_linked_case", asset, {}, {}
        )
        self.assertIsNone(gate_met)
        self.assertEqual(status, "NO_LINKED_CASE_EVIDENCE")

    def test_inconclusive_linked_case_is_null_not_false(self):
        # A case is linked but carries no recognizable negative_control_status
        # shape: undeterminable minimum must be null, not a fabricated False.
        by_zone_id = {"synthetic_zone": {"case_id": "synthetic_case", "negative_control_status": None}}
        asset = {"path": None, "minimum_verified_event_days": 1, "minimum_verified_none_days": 10}
        gate_met, status, basis = phase2.compute_historical_events_gate(
            "synthetic_zone", asset, by_zone_id, {}
        )
        self.assertIsNone(gate_met)
        self.assertEqual(status, "CASE_EVIDENCE_INCONCLUSIVE")
        self.assertEqual(basis["linked_case_validation"], "synthetic_case")

    def test_contradicting_linked_case_is_false(self):
        by_zone_id = {
            "synthetic_zone": {
                "case_id": "synthetic_case",
                "negative_control_status": {"status": "NO_CONFIRMED_NEGATIVE_CONTROL"},
            }
        }
        asset = {"path": None, "minimum_verified_event_days": 1, "minimum_verified_none_days": 10}
        gate_met, status, basis = phase2.compute_historical_events_gate(
            "synthetic_zone", asset, by_zone_id, {}
        )
        self.assertFalse(gate_met)
        self.assertEqual(status, "CASE_EVIDENCE_CONTRADICTS_MINIMUM")

    def test_path_based_linkage_when_zone_id_absent(self):
        by_relpath = {
            "site/data/validation/phase2_case_validations/synthetic.json": {
                "case_id": "synthetic_case",
                "negative_control_status": {"status": "NO_CONFIRMED_NEGATIVE_CONTROL"},
            }
        }
        asset = {
            "path": "site/data/validation/phase2_case_validations/synthetic.json",
            "minimum_verified_event_days": 1, "minimum_verified_none_days": 10,
        }
        gate_met, status, basis = phase2.compute_historical_events_gate(
            "candidate_with_no_zone_id_match", asset, {}, by_relpath
        )
        self.assertFalse(gate_met)
        self.assertEqual(basis["link_method"], "asset_path_exact_match")


class PromotionGateTests(unittest.TestCase):
    def _asset_readiness(self, **overrides):
        base = {
            name: {"status": "READY", "data_presence": "PRESENT",
                   "minimum_sample_gate_met": None, "gate_evidence_status": "NOT_APPLICABLE",
                   "gate_basis": None}
            for name in phase2.ASSETS
        }
        for asset_name, patch in overrides.items():
            base[asset_name].update(patch)
        return base

    def _contract(self, **overrides):
        contract = {
            "hazard_model": {"mechanism_status": "RESOLVED"},
            "validation": {
                "required_reviews": ["scientific", "hydrological_or_hydraulic", "local_outcome"],
                "review_evidence": [
                    {"review_type": "scientific"},
                    {"review_type": "hydrological_or_hydraulic"},
                    {"review_type": "local_outcome"},
                ],
                "promotion_requires_all_gates": True,
            },
        }
        contract.update(overrides)
        return contract

    def test_ready_status_alone_never_implies_promotion_gate_met(self):
        # Required test: every asset carries status "READY" (the presentation
        # label), but one asset's *data_presence* is MISSING (the file is not
        # actually resolvable) — READY the label must not be enough.
        readiness = self._asset_readiness(forecast={"data_presence": "MISSING"})
        result = phase2.compute_promotion_gate(self._contract(), readiness)
        self.assertFalse(result["promotion_gate_met"])
        self.assertIn("asset_not_present:forecast", result["promotion_blocking_items"])

    def test_present_but_partial_asset_status_still_blocks_promotion(self):
        readiness = self._asset_readiness(
            geometry={"status": "PARTIAL", "data_presence": "PRESENT"}
        )
        result = phase2.compute_promotion_gate(self._contract(), readiness)
        self.assertFalse(result["promotion_gate_met"])
        self.assertIn("asset_status_not_ready:geometry", result["promotion_blocking_items"])

    def test_undetermined_minimum_sample_gate_blocks_like_false(self):
        readiness = self._asset_readiness(
            historical_events={"minimum_sample_gate_met": None, "gate_evidence_status": "CASE_EVIDENCE_INCONCLUSIVE"}
        )
        result = phase2.compute_promotion_gate(self._contract(), readiness)
        self.assertFalse(result["promotion_gate_met"])
        self.assertIn("minimum_sample_gate_not_met:historical_events", result["promotion_blocking_items"])

    def test_all_conditions_satisfied_allows_promotion_gate_met_true(self):
        # Confirms the gate is not vacuously always False by construction;
        # it is fail-closed by requiring every condition, not unconditional.
        readiness = self._asset_readiness(
            historical_events={"minimum_sample_gate_met": True, "gate_evidence_status": "CASE_EVIDENCE_CONFIRMS_MINIMUM"}
        )
        result = phase2.compute_promotion_gate(self._contract(), readiness)
        self.assertTrue(result["promotion_gate_met"])
        self.assertEqual(result["promotion_blocking_items"], [])

    def test_non_dict_review_evidence_entries_do_not_count(self):
        # Real-world shape found in ica_pisco_san_andres.json: review_evidence
        # is a list of bare path strings, not {"review_type": ...} objects.
        readiness = self._asset_readiness(
            historical_events={"minimum_sample_gate_met": True, "gate_evidence_status": "CASE_EVIDENCE_CONFIRMS_MINIMUM"}
        )
        contract = self._contract()
        contract["validation"]["review_evidence"] = ["site/data/validation/phase2_case_validations/x.json"]
        result = phase2.compute_promotion_gate(contract, readiness)
        self.assertFalse(result["promotion_gate_met"])
        self.assertTrue(any(item.startswith("missing_required_reviews:") for item in result["promotion_blocking_items"]))


class CanonicalCatalogTests(unittest.TestCase):
    """Exercises the real, committed data end to end."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = phase2.generate_public_catalog(write=False)
        cls.zones_by_id = {z["candidate_id"]: z for z in cls.catalog["zones"]}

    def test_canonical_santa_eulalia_rimac_scenario(self):
        # Required canonical test from the PR-C brief.
        zone = self.zones_by_id["lima_este_santa_eulalia_rimac"]
        he = zone["asset_readiness"]["historical_events"]
        self.assertEqual(he["status"], "READY")
        self.assertEqual(zone["asset_status"]["historical_events"], "READY")  # unchanged, preserved
        self.assertEqual(he["data_presence"], "PRESENT")
        self.assertIs(he["minimum_sample_gate_met"], False)
        self.assertIs(zone["promotion_gate"]["promotion_gate_met"], False)

    def test_all_18_contracts_remain_unpromoted(self):
        # Required test: no Phase-2 closure alters the guardrails; every
        # current contract stays below the promotion gate.
        self.assertEqual(len(self.catalog["zones"]), 18)
        for zone in self.catalog["zones"]:
            self.assertIs(
                zone["promotion_gate"]["promotion_gate_met"], False,
                f"{zone['candidate_id']} unexpectedly reports promotion_gate_met=True",
            )
        # Activation stays BLOCKED for every zone regardless of promotion_gate.
        self.assertTrue(all(z["activation_gate"] == "BLOCKED" for z in self.catalog["zones"]))

    def test_asset_status_readiness_stage_and_blocking_items_preserved(self):
        # asset_readiness/promotion_gate are additive; the pre-existing
        # fields keep their pre-existing meaning and values.
        zone = self.zones_by_id["lima_este_santa_eulalia_rimac"]
        self.assertEqual(zone["readiness_stage"], "DATA_PACKAGE_IN_PROGRESS")
        self.assertEqual(
            sorted(zone["blocking_items"]),
            sorted(["geometry", "exposure", "observations", "forecast", "hydraulic_context", "mechanism_resolution"]),
        )

    def test_check_only_build_is_deterministic(self):
        first = phase2.generate_public_catalog(write=False)
        second = phase2.generate_public_catalog(write=False)
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        self.assertEqual(first, second)

    def test_build_catalog_backward_compatible_without_case_validations_kwarg(self):
        # The existing positional-call test suite must keep working: calling
        # build_catalog() without `case_validations` must not raise, and
        # must still attach the new additive keys (defaulting to null/empty).
        inventory = json.loads((ROOT / "config" / "phase2_candidate_inventory_v0_2.json").read_text(encoding="utf-8"))
        contracts = phase2.load_contracts(inventory)
        analog_contract = json.loads(phase2.ANALOG_CONTRACT_PATH.read_text(encoding="utf-8"))
        child_contracts = phase2.load_child_contracts(inventory)
        catalog = phase2.build_catalog(inventory, contracts, analog_contract, child_contracts)
        zone = next(z for z in catalog["zones"] if z["candidate_id"] == "lima_este_santa_eulalia_rimac")
        self.assertIn("asset_readiness", zone)
        self.assertIn("promotion_gate", zone)
        # With no case-validation lookup supplied, nothing can be linked.
        self.assertEqual(
            zone["asset_readiness"]["historical_events"]["gate_evidence_status"],
            "NO_LINKED_CASE_EVIDENCE",
        )

    def test_v08_scorecard_script_does_not_depend_on_new_phase2_fields(self):
        # Mechanical guard: no Phase-2 READY/gate-semantics closure should
        # couple the v0.8 scorecard to these new, additive fields.
        scorecard_src = (ROOT / "scripts" / "build_v08_scorecard.py").read_text(encoding="utf-8")
        self.assertNotIn("asset_readiness", scorecard_src)
        self.assertNotIn("promotion_gate", scorecard_src)


if __name__ == "__main__":
    unittest.main()
