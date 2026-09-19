"""Tests for the Phase-2 Climate-Conditioned Activation Matrix (PR-D), v0.1
corrected revision.

v0.1 establishes the reproducible *architecture* for representing rainfall,
antecedent-moisture, persistence, season, large-scale-climate and historical
evidence per Phase-2 candidate -- it does NOT assert a scientifically
calibrated combination function over those dimensions. Per the corrections
that produced this revision, `compute_physical_plausibility()` therefore
always returns `category=INSUFFICIENT_EVIDENCE` /
`physical_response_plausibility_score=None` /
`classification_method_status=NOT_YET_CALIBRATED`, regardless of any input
-- INCLUDING an extreme synthetic rainfall percentile, a VERY_WET antecedent
state, or a strong ENSO phase.

These tests therefore do NOT try to prove that any particular combination of
inputs produces VERY_LOW/VERY_HIGH/etc. -- that would validate a
hydrological model from synthetic fixtures, which is explicitly out of
scope for v0.1 ("Do NOT use synthetic fixtures to establish scientific
plausibility thresholds"). Instead they prove *software* behavior: the
function never crashes, never fabricates a score, and stays fail-closed no
matter what it is handed; and that the guardrail state authoritative
elsewhere in the repository (Phase-2 catalog, candidate inventory) is read
independently rather than trusted from the matrix's own self-declared
constants.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, relpath):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


cm = _load_module("phase2_climate_matrix_under_test", "scripts/build_phase2_climate_matrix.py")


def _rainfall_with_percentile(percentile):
    """Synthetic, extreme rainfall input -- used only to prove that no
    scoring path exists for it to influence, never to establish a
    threshold."""
    rainfall = cm.build_rainfall_block()
    rainfall["24h"] = {
        "window_id": "24h", "evidence_status": "OBSERVED_LIVE_OR_NEAR_REAL_TIME",
        "accumulated_mm": 42.0, "max_mm": 10.0, "intensity_mm_per_hr": 5.0,
        "climatological_percentile": percentile, "anomaly_mm": 12.0, "observations": [],
    }
    return rainfall


def _known(state, key="state", evidence="OBSERVED_LIVE_OR_NEAR_REAL_TIME", **extra):
    return {key: state, "evidence_status": evidence, **extra}


def _climate(enso_phase, evidence="OBSERVED_LIVE_OR_NEAR_REAL_TIME"):
    return {"enso_phase": enso_phase, "evidence_status": evidence, "source": None, "note": None, "is_trigger_alone": False}


class PlausibilityArchitectureTests(unittest.TestCase):
    """compute_physical_plausibility(): NOT_YET_CALIBRATED architecture only.

    Point 1, 2, 3, 5 of the corrections' 12-point test list.
    """

    # 1. missing meteorological evidence -> INSUFFICIENT_EVIDENCE
    def test_missing_meteorological_evidence_is_insufficient_evidence(self):
        rainfall = cm.build_rainfall_block()  # all windows INSUFFICIENT_EVIDENCE
        antecedent = cm.build_antecedent_moisture()
        persistence = cm.build_persistence()
        season = cm.build_season_context()
        climate = cm.build_large_scale_climate_context("any_candidate", {})
        result = cm.compute_physical_plausibility(rainfall, antecedent, persistence, season, climate)
        self.assertEqual(result["category"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["physical_response_plausibility_score"])
        self.assertEqual(result["classification_method_status"], "NOT_YET_CALIBRATED")

    # 2. no arbitrary numeric score is ever generated, even with extreme
    #    synthetic inputs across every dimension at once. This demonstrates
    #    software behavior (fail-closed, no crash) only -- it establishes no
    #    hydrological weight or threshold.
    def test_no_arbitrary_score_is_generated_even_with_extreme_synthetic_inputs(self):
        extreme_cases = [
            (_rainfall_with_percentile(99), _known("VERY_WET"), _known("PROLONGED"), _known("WET_SEASON"), _climate("WARM_EL_NINO_STRONG")),
            (_rainfall_with_percentile(1), _known("DRY"), _known("NONE"), _known("DRY_SEASON"), _climate("COLD_LA_NINA_STRONG")),
            (cm.build_rainfall_block(), cm.build_antecedent_moisture(), cm.build_persistence(), cm.build_season_context(), _climate("NEUTRAL")),
        ]
        for rainfall, antecedent, persistence, season, climate in extreme_cases:
            result = cm.compute_physical_plausibility(rainfall, antecedent, persistence, season, climate)
            self.assertEqual(result["category"], "INSUFFICIENT_EVIDENCE")
            self.assertIsNone(result["physical_response_plausibility_score"])
            self.assertIsNone(result["score_components"])
            self.assertEqual(result["classification_method_status"], "NOT_YET_CALIBRATED")

    # 3. ENSO alone cannot create or upgrade a plausibility category. This is
    #    now provable by construction (no scoring path exists for ENSO, or
    #    any other dimension, to influence at all), not just by a bounded
    #    score swing -- the property the previous weighted model claimed but
    #    did not actually guarantee.
    def test_enso_alone_cannot_create_or_upgrade_plausibility_category(self):
        rainfall = _rainfall_with_percentile(60)
        antecedent = _known("NORMAL")
        persistence = _known("SHORT")
        season = _known("TRANSITION")
        categories = set()
        scores = set()
        for enso_phase in ("UNKNOWN", "NEUTRAL", "WARM_EL_NINO_STRONG", "COLD_LA_NINA_STRONG"):
            result = cm.compute_physical_plausibility(rainfall, antecedent, persistence, season, _climate(enso_phase))
            categories.add(result["category"])
            scores.add(result["physical_response_plausibility_score"])
        self.assertEqual(categories, {"INSUFFICIENT_EVIDENCE"})
        self.assertEqual(scores, {None})

    # 5. unknown antecedent conditions remain unknown -- and do not get
    #    silently promoted by any other dimension being extreme.
    def test_unknown_antecedent_conditions_remain_unknown(self):
        antecedent = cm.build_antecedent_moisture()
        self.assertEqual(antecedent["state"], "UNKNOWN")
        self.assertEqual(antecedent["evidence_status"], "INSUFFICIENT_EVIDENCE")
        result = cm.compute_physical_plausibility(
            _rainfall_with_percentile(99), antecedent, _known("PROLONGED"), _known("WET_SEASON"), _climate("WARM_EL_NINO_STRONG")
        )
        self.assertEqual(result["category"], "INSUFFICIENT_EVIDENCE")

    def test_persistence_day_count_boundaries_are_unresolved(self):
        persistence = cm.build_persistence()
        self.assertEqual(persistence["state"], "UNKNOWN")
        note = persistence["definition_note"]
        self.assertIn("UNRESOLVED", note)
        # Must not assert the previously-removed specific day-count
        # boundaries as authoritative.
        for stale_claim in ("1-2", "3-5", ">5 days"):
            self.assertNotIn(stale_claim, note)


class HistoricalRealizationExtractionTests(unittest.TestCase):
    """Narrow, mechanical, non-fabricating extraction from linked cases."""

    def test_event_block_shape(self):
        case = {
            "event": {"date_local": "2015-03-23", "classification": "CONFIRMED_POSITIVE_FIELD_EVIDENCE",
                      "primary_source_id": "SRC-1"},
            "rainfall_context": {"reported_peak_daily_mm_on_event_day": 18.0},
        }
        realization = cm.extract_documented_realization(case)
        self.assertEqual(realization["event_date_local"], "2015-03-23")
        self.assertEqual(realization["classification"], "CONFIRMED_POSITIVE_FIELD_EVIDENCE")
        self.assertTrue(realization["rainfall_evidence_available"])
        self.assertEqual(realization["rainfall_evidence_field_ref"], "rainfall_context")

    def test_event_reference_block_shape(self):
        case = {
            "event_reference": {"event_date_local": "2023-03-14", "event_type": "debris_flow_huaico"},
            "rainfall_reference": {"pmax24_return_period_mm": 120},
        }
        realization = cm.extract_documented_realization(case)
        self.assertEqual(realization["event_date_local"], "2023-03-14")
        self.assertEqual(realization["classification"], "debris_flow_huaico")
        self.assertTrue(realization["rainfall_evidence_available"])
        self.assertEqual(realization["rainfall_evidence_field_ref"], "rainfall_reference")

    def test_unfamiliar_shape_is_not_guessed_at(self):
        # A case validation with neither known key shape must not be scraped
        # via generic heuristics -- required "no free-text extraction" rule.
        case = {"historical_cases": {"something": "unrelated shape"}}
        realization = cm.extract_documented_realization(case)
        self.assertIsNone(realization["event_date_local"])
        self.assertIsNone(realization["classification"])
        self.assertFalse(realization["rainfall_evidence_available"])

    def test_none_case_is_empty_realization(self):
        realization = cm.extract_documented_realization(None)
        self.assertIsNone(realization["classification"])


class GeneratedMatrixTests(unittest.TestCase):
    """Exercises the real, committed generator output end to end."""

    @classmethod
    def setUpClass(cls):
        cls.matrix = cm.generate_climate_matrix(write=False)
        cls.records_by_id = {r["candidate_id"]: r for r in cls.matrix["records"]}

    def test_candidate_count_is_18(self):
        self.assertEqual(len(self.matrix["records"]), 18)
        self.assertEqual(self.matrix["summary"]["candidate_count"], 18)

    def test_matches_phase2_inventory_ids_exactly(self):
        inventory = json.loads((ROOT / "config" / "phase2_candidate_inventory_v0_2.json").read_text(encoding="utf-8"))
        expected = {c["candidate_id"] for c in inventory["candidates"]}
        self.assertEqual(set(self.records_by_id.keys()), expected)

    def test_grouper_entity_role_preserved(self):
        grouper = self.records_by_id["lambayeque_chongoyape_oyotun_zana"]
        self.assertEqual(grouper["entity_role"], "HISTORICAL_NON_ACTIVABLE_GROUPER")
        self.assertIsNone(grouper["physical_factors"]["source_asset_ref"])
        self.assertEqual(grouper["activation_gate"], "BLOCKED")

    # 4. historical evidence is not silently converted into a general
    #    activation rule: a candidate linked to CONFIRMED_POSITIVE_FIELD_EVIDENCE
    #    still gets INSUFFICIENT_EVIDENCE / non-operational plausibility --
    #    the historical link is evidence *about the past*, not a calibrated
    #    activation trigger.
    def test_historical_evidence_is_not_silently_converted_into_activation_rule(self):
        record = self.records_by_id["lima_este_santa_eulalia_rimac"]
        summary = record["historical_evidence_summary"]
        self.assertEqual(summary["linked_case_validation"], "cashahuacra_santa_eulalia_2015")
        self.assertEqual(summary["link_method"], "zone_id_exact_match")
        self.assertEqual(summary["documented_realizations"][0]["classification"], "CONFIRMED_POSITIVE_FIELD_EVIDENCE")
        plausibility = record["physical_plausibility_assessment"]
        self.assertEqual(plausibility["category"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(plausibility["physical_response_plausibility_score"])
        self.assertFalse(plausibility["is_operational_activation"])
        self.assertEqual(plausibility["classification_method_status"], "NOT_YET_CALIBRATED")

    # 6. all eight rainfall windows remain represented, for every candidate.
    def test_all_eight_rainfall_windows_represented(self):
        expected_windows = {"1h", "3h", "6h", "12h", "24h", "48h", "72h", "7d"}
        self.assertEqual(set(cm.RAINFALL_WINDOWS), expected_windows)
        for record in self.matrix["records"]:
            self.assertEqual(set(record["rainfall"].keys()), expected_windows)

    def test_no_guardrail_field_is_altered(self):
        self.assertEqual(self.matrix["deployment_status"], "RESEARCH_ONLY")
        self.assertTrue(self.matrix["test_mode"])
        self.assertFalse(self.matrix["production_use"])
        self.assertFalse(self.matrix["production_ready"])
        self.assertFalse(self.matrix["operational_alerting_enabled"])
        self.assertIsNone(self.matrix["decision_thresholds"])
        self.assertEqual(self.matrix["activation_gate"], "BLOCKED")
        self.assertTrue(self.matrix["guardrails"]["enso_alone_is_never_a_trigger"])
        for record in self.matrix["records"]:
            self.assertEqual(record["deployment_status"], "RESEARCH_ONLY")
            self.assertFalse(record["production_use"])
            self.assertFalse(record["production_ready"])
            self.assertEqual(record["activation_gate"], "BLOCKED")
            self.assertFalse(record["physical_plausibility_assessment"]["is_operational_activation"])
            self.assertFalse(record["large_scale_climate_context"]["is_trigger_alone"])

    def test_summary_counts_are_honest_given_todays_data(self):
        # Every candidate legitimately lacks rainfall percentile data today,
        # and v0.1 has no calibrated scoring path in any case: all 18 must
        # be INSUFFICIENT_EVIDENCE.
        summary = self.matrix["summary"]
        self.assertEqual(summary["insufficient_evidence_count"], 18)
        self.assertEqual(summary["differentiated_plausibility_count"], 0)
        self.assertEqual(summary["operational_candidate_count"], 0)
        self.assertFalse(summary["any_activation_gate_open"])
        self.assertFalse(summary["any_promotion_gate_true_due_to_matrix"])
        self.assertEqual(self.matrix["methodology"]["classification_method_status"], "NOT_YET_CALIBRATED")
        for record in self.matrix["records"]:
            self.assertEqual(record["physical_plausibility_assessment"]["category"], "INSUFFICIENT_EVIDENCE")

    # 12. deterministic regeneration still passes.
    def test_check_only_generation_is_deterministic(self):
        first = cm.generate_climate_matrix(write=False)
        second = cm.generate_climate_matrix(write=False)
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        self.assertEqual(first, second)

    def test_matrix_does_not_declare_promotion_gate_or_asset_readiness_keys(self):
        def walk(node):
            if isinstance(node, dict):
                self.assertNotIn("promotion_gate_met", node)
                self.assertNotIn("asset_readiness", node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(self.matrix)


class HydrologicChildUnitsReferenceTests(unittest.TestCase):
    """build_hydrologic_child_units_reference(): correction #4."""

    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((ROOT / "config" / "phase2_candidate_inventory_v0_2.json").read_text(encoding="utf-8"))

    def test_reference_lists_both_children_outside_the_18_candidate_count(self):
        ref = cm.build_hydrologic_child_units_reference(self.inventory)
        children = {c["candidate_id"]: c for c in ref["children"]}
        self.assertEqual(set(children), {"lambayeque_chancay_lambayeque_chongoyape", "lambayeque_zana_oyotun"})
        self.assertEqual(children["lambayeque_chancay_lambayeque_chongoyape"]["official_hydrologic_unit_code"], "13776")
        self.assertEqual(children["lambayeque_zana_oyotun"]["official_hydrologic_unit_code"], "137754")
        for child in children.values():
            self.assertFalse(child["counts_as_additional_phase2_candidate"])
            self.assertFalse(child["counts_as_operational_candidate"])
        self.assertFalse(ref["children_counted_as_additional_phase2_candidates"])

    def test_parent_grouper_stays_historical_non_activable(self):
        ref = cm.build_hydrologic_child_units_reference(self.inventory)
        parent = ref["parent_grouper"]
        self.assertEqual(parent["candidate_id"], "lambayeque_chongoyape_oyotun_zana")
        self.assertEqual(parent["entity_role"], "HISTORICAL_NON_ACTIVABLE_GROUPER")
        self.assertEqual(parent["geometry_policy"], "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR")
        self.assertEqual(parent["activation_gate"], "BLOCKED")

    def test_does_not_duplicate_authoritative_contracts(self):
        ref = cm.build_hydrologic_child_units_reference(self.inventory)
        for child in ref["children"]:
            self.assertIn("authoritative_source_refs", child)
            self.assertTrue(child["authoritative_source_refs"])
            # Only pointers (paths / fragment refs), never a nested copy of
            # the child's own contract content.
            self.assertNotIn("geometry", child)
            self.assertNotIn("source_and_confidence", child)

    def test_fails_closed_if_ana_code_changes_silently(self):
        tampered = copy.deepcopy(self.inventory)
        for child in tampered["hydrologic_child_units"]:
            if child["candidate_id"] == "lambayeque_chancay_lambayeque_chongoyape":
                child["official_hydrologic_unit_code"] = "99999"
        with self.assertRaises(cm.phase2_catalog.ContractError):
            cm.build_hydrologic_child_units_reference(tampered)

    def test_fails_closed_if_grouper_entity_role_changes_silently(self):
        tampered = copy.deepcopy(self.inventory)
        for candidate in tampered["candidates"]:
            if candidate["candidate_id"] == "lambayeque_chongoyape_oyotun_zana":
                candidate["entity_role"] = "ACTIVABLE_ZONE"
        with self.assertRaises(cm.phase2_catalog.ContractError):
            cm.build_hydrologic_child_units_reference(tampered)

    def test_fails_closed_if_a_child_is_missing(self):
        tampered = copy.deepcopy(self.inventory)
        tampered["hydrologic_child_units"] = [
            c for c in tampered["hydrologic_child_units"] if c["candidate_id"] != "lambayeque_zana_oyotun"
        ]
        with self.assertRaises(cm.phase2_catalog.ContractError):
            cm.build_hydrologic_child_units_reference(tampered)


class AuthoritativeCatalogStateTests(unittest.TestCase):
    """Reads site/data/phase2/catalog.json and the candidate inventory
    directly -- never through the climate matrix -- to independently confirm
    points 7, 8, 9, 10, 11 of the corrections' 12-point test list."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "site/data/phase2/catalog.json").read_text(encoding="utf-8"))
        cls.inventory = json.loads((ROOT / "config/phase2_candidate_inventory_v0_2.json").read_text(encoding="utf-8"))
        cls.zones = cls.catalog["zones"]

    # 7. authoritative Phase-2 catalog still reports 18 / 0 / 0 / 0.
    def test_authoritative_catalog_reports_18_0_0_0(self):
        self.assertEqual(len(self.zones), 18)
        self.assertEqual(self.catalog["summary"]["registered_candidates"], 18)
        self.assertEqual(self.catalog["summary"]["contracts_approved"], 0)
        self.assertEqual(self.catalog["summary"]["operational_candidates"], 0)
        promotion_met = [z for z in self.zones if (z.get("promotion_gate") or {}).get("promotion_gate_met") is True]
        self.assertEqual(promotion_met, [])

    # 8. both Lambayeque child units remain separately represented in the
    #    authoritative state, with their correct ANA codes.
    def test_both_lambayeque_children_separately_represented(self):
        catalog_children = {c["candidate_id"]: c for c in self.catalog["hydrologic_child_units"]}
        self.assertEqual(
            set(catalog_children), {"lambayeque_chancay_lambayeque_chongoyape", "lambayeque_zana_oyotun"}
        )
        self.assertEqual(catalog_children["lambayeque_chancay_lambayeque_chongoyape"]["official_hydrologic_unit_code"], "13776")
        self.assertEqual(catalog_children["lambayeque_zana_oyotun"]["official_hydrologic_unit_code"], "137754")

        inventory_children = {c["candidate_id"]: c for c in self.inventory["hydrologic_child_units"]}
        self.assertEqual(
            set(inventory_children), {"lambayeque_chancay_lambayeque_chongoyape", "lambayeque_zana_oyotun"}
        )
        self.assertEqual(inventory_children["lambayeque_chancay_lambayeque_chongoyape"]["official_hydrologic_unit_code"], "13776")
        self.assertEqual(inventory_children["lambayeque_zana_oyotun"]["official_hydrologic_unit_code"], "137754")

    # 9. the parent remains HISTORICAL_NON_ACTIVABLE_GROUPER.
    def test_parent_remains_historical_non_activable_grouper(self):
        inventory_candidates = {c["candidate_id"]: c for c in self.inventory["candidates"]}
        grouper = inventory_candidates["lambayeque_chongoyape_oyotun_zana"]
        self.assertEqual(grouper["entity_role"], "HISTORICAL_NON_ACTIVABLE_GROUPER")
        self.assertEqual(grouper["geometry_policy"], "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR")
        zone = next(z for z in self.zones if z["candidate_id"] == "lambayeque_chongoyape_oyotun_zana")
        self.assertEqual(zone["activation_gate"], "BLOCKED")

    # 10. all activation gates remain BLOCKED.
    def test_all_activation_gates_blocked(self):
        self.assertEqual({z["activation_gate"] for z in self.zones}, {"BLOCKED"})
        for child in self.catalog["hydrologic_child_units"]:
            self.assertEqual(child["activation_gate"], "BLOCKED")

    # 11. production and alerting guardrails remain false.
    def test_production_and_alerting_guardrails_false(self):
        self.assertEqual(self.catalog["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(self.catalog["production_use"])
        self.assertFalse(self.catalog["production_ready"])
        self.assertTrue(self.catalog["guardrails"]["alerts_disabled"])
        for child in self.catalog["hydrologic_child_units"]:
            self.assertFalse(child["production_use"])
            self.assertEqual(child["deployment_status"], "RESEARCH_ONLY")


class ValidatorIndependentAuthoritativeCheckTests(unittest.TestCase):
    """The CI validator must read catalog.json/inventory independently and
    fail closed if that authoritative state changes unexpectedly -- not
    trust the matrix's own self-declared summary constants (correction #3).
    """

    @classmethod
    def setUpClass(cls):
        cls.validator = _load_module("phase2_climate_matrix_validator_under_test", "scripts/validate_phase2_climate_matrix.py")
        cls.real_matrix = cm.generate_climate_matrix(write=False)

    def setUp(self):
        self.validator.ERRORS.clear()

    def test_passes_against_real_authoritative_state(self):
        self.validator.check_authoritative_phase2_state(self.real_matrix)
        self.assertEqual(self.validator.ERRORS, [])

    def test_fails_closed_if_an_activation_gate_opens_unexpectedly(self):
        tampered_path = ROOT / "site/data/phase2/catalog.json"
        catalog = json.loads(tampered_path.read_text(encoding="utf-8"))
        catalog["zones"][0]["activation_gate"] = "OPEN"
        tmp = ROOT / "tests" / "_tmp_tampered_catalog_for_test.json"
        tmp.write_text(json.dumps(catalog), encoding="utf-8")
        original_path = self.validator.CATALOG_PATH
        try:
            self.validator.CATALOG_PATH = tmp
            self.validator.check_authoritative_phase2_state(self.real_matrix)
            self.assertTrue(any("activation_gate" in e for e in self.validator.ERRORS))
        finally:
            self.validator.CATALOG_PATH = original_path
            tmp.unlink(missing_ok=True)

    def test_fails_closed_if_promotion_gate_met_becomes_true_unexpectedly(self):
        tampered_path = ROOT / "site/data/phase2/catalog.json"
        catalog = json.loads(tampered_path.read_text(encoding="utf-8"))
        catalog["zones"][0].setdefault("promotion_gate", {})["promotion_gate_met"] = True
        tmp = ROOT / "tests" / "_tmp_tampered_catalog_for_test.json"
        tmp.write_text(json.dumps(catalog), encoding="utf-8")
        original_path = self.validator.CATALOG_PATH
        try:
            self.validator.CATALOG_PATH = tmp
            self.validator.check_authoritative_phase2_state(self.real_matrix)
            self.assertTrue(any("promotion_gate_met" in e for e in self.validator.ERRORS))
        finally:
            self.validator.CATALOG_PATH = original_path
            tmp.unlink(missing_ok=True)

    def test_fails_closed_if_a_hydrologic_child_ana_code_changes_unexpectedly(self):
        tampered_path = ROOT / "config/phase2_candidate_inventory_v0_2.json"
        inventory = json.loads(tampered_path.read_text(encoding="utf-8"))
        for child in inventory["hydrologic_child_units"]:
            if child["candidate_id"] == "lambayeque_zana_oyotun":
                child["official_hydrologic_unit_code"] = "00000"
        tmp = ROOT / "tests" / "_tmp_tampered_inventory_for_test.json"
        tmp.write_text(json.dumps(inventory), encoding="utf-8")
        original_path = self.validator.INVENTORY_PATH
        try:
            self.validator.INVENTORY_PATH = tmp
            self.validator.check_authoritative_phase2_state(self.real_matrix)
            self.assertTrue(any("lambayeque_zana_oyotun" in e for e in self.validator.ERRORS))
        finally:
            self.validator.INVENTORY_PATH = original_path
            tmp.unlink(missing_ok=True)


@unittest.skipUnless((ROOT / "config" / "phase2_climate_conditioned_activation_matrix.schema.json").is_file(), "schema missing")
class SchemaConformanceTests(unittest.TestCase):
    def test_generated_matrix_conforms_to_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed in this environment")
        schema = json.loads((ROOT / "config" / "phase2_climate_conditioned_activation_matrix.schema.json").read_text(encoding="utf-8"))
        matrix = cm.generate_climate_matrix(write=False)
        jsonschema.validate(matrix, schema)

    def test_schema_forces_insufficient_evidence_when_not_yet_calibrated(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed in this environment")
        schema = json.loads((ROOT / "config" / "phase2_climate_conditioned_activation_matrix.schema.json").read_text(encoding="utf-8"))
        matrix = cm.generate_climate_matrix(write=False)
        tampered = copy.deepcopy(matrix)
        tampered["records"][0]["physical_plausibility_assessment"]["category"] = "HIGH_PLAUSIBILITY"
        tampered["records"][0]["physical_plausibility_assessment"]["physical_response_plausibility_score"] = 0.9
        with self.assertRaises(Exception):
            jsonschema.validate(tampered, schema)


class CommittedFileAndValidatorTests(unittest.TestCase):
    def test_committed_file_matches_generator(self):
        out_path = ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"
        if not out_path.is_file():
            self.skipTest("committed matrix file not yet generated")
        committed = json.loads(out_path.read_text(encoding="utf-8"))
        fresh = cm.generate_climate_matrix(write=False)
        committed.pop("generated_at", None)
        fresh.pop("generated_at", None)
        self.assertEqual(committed, fresh)

    def test_validator_script_passes(self):
        validator = ROOT / "scripts" / "validate_phase2_climate_matrix.py"
        if not validator.is_file() or not (ROOT / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json").is_file():
            self.skipTest("validator or committed file not yet generated")
        result = subprocess.run([sys.executable, str(validator)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
