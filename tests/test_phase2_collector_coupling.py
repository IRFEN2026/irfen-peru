import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_phase2_collector_coupling as coupling


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def docs():
    return (
        load(coupling.ARCH_PATH),
        load(coupling.HIERARCHY_PATH),
        load(coupling.SPATIAL_PATH),
        load(coupling.DEMO_PATH),
    )


class CollectorCouplingTests(unittest.TestCase):
    def test_baseline_passes_without_promoting_any_collector_effect(self):
        report = coupling.build_report()
        self.assertEqual(report["status"], "PASS_PHASE2_COLLECTOR_COUPLING_FAIL_CLOSED")
        self.assertEqual(report["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(report["test_mode"], "TEST_ONLY")
        self.assertFalse(report["production_use"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["operational_alerting_enabled"])
        self.assertEqual(report["activation_gate"], "BLOCKED")
        self.assertEqual(report["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(report["decision_thresholds"])
        self.assertIsNone(report["hydraulic_factors"])
        summary = report["summary"]
        self.assertEqual(summary["tributary_count"], 2)
        self.assertEqual(summary["collector_target_count"], 1)
        self.assertEqual(summary["matrix_cell_count"], 2)
        self.assertEqual(summary["effect_state_counts"]["NO_EVIDENCE"], 2)
        self.assertEqual(summary["routing_models_run"], 0)
        self.assertEqual(summary["hydraulic_models_run"], 0)
        self.assertEqual(summary["new_map_geometries"], 0)

    def test_research_outlets_are_replayed_from_spatial_registry_not_promoted_to_confluences(self):
        arch, hierarchy, spatial, demo = docs()
        by_id = coupling.spatial_subunits(spatial, demo["parent_id"])
        for tributary in demo["tributaries"]:
            with self.subTest(local_unit_id=tributary["local_unit_id"]):
                source = tributary["source_outlet_or_explicit_missing_status"]
                expected = by_id[tributary["local_unit_id"]]["outlet_status"]
                self.assertEqual(source["lon"], expected["lon"])
                self.assertEqual(source["lat"], expected["lat"])
                self.assertEqual(source["official_confirmation"], expected["official_confirmation"])
                self.assertFalse(source["is_receiver_confluence"])
                self.assertIsNone(tributary["receiver_confluence_or_explicit_missing_status"]["location"])
                self.assertEqual(tributary["collector_effect_state"], "NO_EVIDENCE")
                self.assertEqual(tributary["connectivity"], "UNRESOLVED_NOT_ASSUMED")

    def test_parent_activation_is_rejected(self):
        arch, hierarchy, spatial, demo = docs()
        broken = copy.deepcopy(demo)
        broken["parent_activation_state"] = "DIRECT_FLOW_EVIDENCE"
        with self.assertRaisesRegex(coupling.CouplingError, "PARENT_ACTIVATION"):
            coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_no_evidence_rejects_invented_travel_time_or_discharge(self):
        arch, hierarchy, spatial, demo = docs()
        for field, value in (("travel_time_tau", {"minutes": 20}), ("q_i_t", [{"t": "x", "q": 10.0}])):
            with self.subTest(field=field):
                broken = copy.deepcopy(demo)
                broken["tributaries"][0][field] = value
                with self.assertRaisesRegex(coupling.CouplingError, "NO_EVIDENCE_HAS_UNSUPPORTED"):
                    coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_connected_state_requires_reproducible_confluence(self):
        arch, hierarchy, spatial, demo = docs()
        broken = copy.deepcopy(demo)
        broken["tributaries"][0]["collector_effect_state"] = "HYDROLOGICALLY_CONNECTED"
        broken["collector_coupling_matrix"][0]["collector_effect_state"] = "HYDROLOGICALLY_CONNECTED"
        with self.assertRaisesRegex(coupling.CouplingError, "WITHOUT_REPRODUCIBLE_CONFLUENCE"):
            coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_arbitrary_coupling_weight_or_probability_is_rejected(self):
        arch, hierarchy, spatial, demo = docs()
        broken = copy.deepcopy(demo)
        broken["collector_coupling_matrix"][0]["coupling_weight"] = 0.7
        with self.assertRaisesRegex(coupling.CouplingError, "ARBITRARY_WEIGHT_OR_PROBABILITY_FIELD"):
            coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_source_blob_sha_is_pinned_and_replayed(self):
        arch, hierarchy, spatial, demo = docs()
        self.assertEqual(demo["input_sources"][0]["git_blob_sha"], coupling.git_blob_sha(coupling.SPATIAL_PATH))
        broken = copy.deepcopy(demo)
        broken["input_sources"][0]["git_blob_sha"] = "0" * 40
        with self.assertRaisesRegex(coupling.CouplingError, "GIT_BLOB_SHA_DRIFT"):
            coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_capacity_defaults_unknown_and_cannot_be_promoted_without_validation_evidence(self):
        arch, hierarchy, spatial, demo = docs()
        broken = copy.deepcopy(demo)
        broken["collector_targets"][0]["capacity_status"] = "ADEQUATE"
        with self.assertRaisesRegex(coupling.CouplingError, "CAPACITY_WITHOUT_VALIDATION"):
            coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_hec_hms_or_ras_claim_requires_reproducible_input_bundle(self):
        for model, family in (
            ({"method": "HEC_HMS", "status": "ROUTING_CONFIGURED", "reproducible_input_bundle": None}, "HEC_HMS"),
            ({"method": "HEC_RAS", "status": "HYDRAULICALLY_REPRODUCED", "reproducible_input_bundle": None}, "HEC_RAS"),
        ):
            with self.subTest(family=family):
                with self.assertRaisesRegex(coupling.CouplingError, family):
                    coupling.validate_model_gate(model, family)

    def test_matrix_must_cover_every_registered_tributary_collector_pair_exactly_once(self):
        arch, hierarchy, spatial, demo = docs()
        broken = copy.deepcopy(demo)
        broken["collector_coupling_matrix"] = broken["collector_coupling_matrix"][:1]
        with self.assertRaisesRegex(coupling.CouplingError, "MATRIX_NOT_COMPLETE"):
            coupling.validate_demonstrator(broken, arch, hierarchy, spatial)

    def test_forbidden_contaminated_or_outcome_sources_fail_closed(self):
        arch, hierarchy, spatial, demo = docs()
        for path in (
            "site/data/validation/official_outcome_evidence.json",
            "site/data/validation/CONTAMINATED_DO_NOT_USE.json",
            "docs/A6680_numeric_reference.json",
        ):
            with self.subTest(path=path):
                broken = copy.deepcopy(demo)
                broken["input_sources"][0]["path"] = path
                with self.assertRaisesRegex(coupling.CouplingError, "FORBIDDEN_SOURCE_REFERENCE"):
                    coupling.validate_demonstrator(broken, arch, hierarchy, spatial)


if __name__ == "__main__":
    unittest.main()
