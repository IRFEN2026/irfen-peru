import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase2_events", ROOT / "scripts" / "build_phase2_event_catalog.py"
)
phase2_events = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(phase2_events)


class Phase2EventIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "site/data/validation/phase2_event_intake/viru-2026-08-17-unverified.json"
        cls.row = json.loads(cls.path.read_text(encoding="utf-8"))

    def test_viru_report_is_unverified_blocked_and_non_operational(self):
        phase2_events.validate_event(self.row, self.path)
        self.assertFalse(self.row["verification"]["event_confirmed"])
        self.assertEqual(self.row["analysis"]["status"], "BLOCKED_MISSING_EVENT_IDENTITY")
        self.assertFalse(self.row["counts_toward_v08_closeout"])
        self.assertFalse(self.row["operational_zone_activation"])

    def test_unverified_event_cannot_be_marked_ready(self):
        row = copy.deepcopy(self.row)
        row["analysis"]["status"] = "READY_FOR_REANALYSIS"
        with self.assertRaises(phase2_events.EventIntakeError):
            phase2_events.validate_event(row)

    def test_threshold_hydraulic_or_activation_changes_are_rejected(self):
        for field, value in (
            ("decision_thresholds", {"mm": 1}),
            ("hydraulic_factors", {"factor": 1}),
            ("operational_zone_activation", True),
            ("counts_toward_v08_closeout", True),
        ):
            row = copy.deepcopy(self.row)
            row[field] = value
            with self.assertRaises(phase2_events.EventIntakeError):
                phase2_events.validate_event(row)

    def test_context_source_cannot_claim_event_confirmation(self):
        row = copy.deepcopy(self.row)
        row["context_sources"][0]["supports_event_confirmation"] = True
        with self.assertRaises(phase2_events.EventIntakeError):
            phase2_events.validate_event(row)

    def test_verified_event_requires_complete_identity(self):
        row = copy.deepcopy(self.row)
        row["verification"]["event_confirmed"] = True
        row["status"] = "VERIFIED_EVENT_RESEARCH_ONLY"
        row["analysis"]["status"] = "READY_FOR_REANALYSIS"
        with self.assertRaises(phase2_events.EventIntakeError):
            phase2_events.validate_event(row)

    def test_official_outcome_can_be_confirmed_while_geometry_blocks_analysis(self):
        path = ROOT / "site/data/validation/phase2_event_intake/villa-el-salvador-2026-08-16-coen.json"
        row = json.loads(path.read_text(encoding="utf-8"))
        phase2_events.validate_event(row, path)
        self.assertTrue(row["verification"]["event_confirmed"])
        self.assertEqual(row["missing_required_fields"], ["coordinates"])
        self.assertEqual(row["analysis"]["status"], "BLOCKED_MISSING_ANALYSIS_GEOMETRY")
        self.assertFalse(row["analysis"]["threshold_inference_allowed"])

    def test_complete_identity_still_waits_for_official_review(self):
        row = copy.deepcopy(self.row)
        row["reported_location"]["feature_name"] = "Quebrada oficial"
        row["reported_location"]["coordinates"] = {"lat": -8.4, "lon": -78.8}
        row["reported_event"]["occurrence_time_local"] = "2026-08-17T16:00:00-05:00"
        row["verification"]["official_event_source"] = "https://www.gob.pe/evento"
        row["missing_required_fields"] = []
        row["analysis"]["status"] = "BLOCKED_PENDING_OFFICIAL_REVIEW"
        phase2_events.validate_event(row)
        self.assertFalse(row["verification"]["event_confirmed"])

    def test_public_catalog_is_fail_closed_and_committed(self):
        generated = phase2_events.generate_public_catalog(write=False)
        self.assertEqual(generated["summary"]["registered_events"], 2)
        self.assertEqual(generated["summary"]["verified_events"], 1)
        self.assertEqual(generated["summary"]["verified_pending_geometry"], 1)
        self.assertEqual(generated["summary"]["operational_activations"], 0)
        self.assertTrue(generated["guardrails"]["unverified_events_block_reanalysis"])
        committed = json.loads(phase2_events.OUT_PATH.read_text(encoding="utf-8"))
        generated.pop("generated_at", None)
        committed.pop("generated_at", None)
        self.assertEqual(committed, generated)


if __name__ == "__main__":
    unittest.main()
