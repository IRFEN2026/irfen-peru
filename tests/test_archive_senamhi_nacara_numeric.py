from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/senamhi-nacara-probe.yml"
SPEC = importlib.util.spec_from_file_location(
    "archive_senamhi_nacara_numeric_probe",
    ROOT / "scripts/archive_senamhi_nacara_numeric_probe.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample(generated_at, requested_at, available, value=None, reason=None):
    return {
        "generated_at": generated_at,
        "status": "OFFICIAL_NUMERIC_RIVER_STATE_CANDIDATE_AVAILABLE" if available else "NO_VALID_NUMERIC_READING",
        "numeric_river_state_available": available,
        "rejection_reason": reason,
        "query": {"requested_observation_time": requested_at},
        "http": {"status": 200 if available else None},
        "reading": ({
            "station_id": "47E0415A",
            "station_name": "PUENTE ÑACARA",
            "variable": "CAUDAL",
            "value": value,
            "unit": "m3/s",
            "trend_code": "E",
        } if available else None),
    }


class ArchiveSenamhiNacaraTests(unittest.TestCase):
    def test_workflow_retries_transient_main_push_collisions(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("for attempt in 1 2 3 4", workflow)
        self.assertIn("git fetch origin main", workflow)
        self.assertIn("git rebase origin/main", workflow)
        self.assertIn("git rebase --abort || true", workflow)
        self.assertIn("No fue posible publicar evidencia SENAMHI tras 4 intentos.", workflow)

    def test_failure_is_unknown_and_never_observation(self):
        archive = MODULE.build_archive([
            sample("2026-08-16T14:00:00+00:00", "2026-08-16T09:00:00-05:00", False, reason="URLError")
        ], datetime(2026, 8, 16, 14, 1, tzinfo=timezone.utc))
        self.assertEqual(archive["summary"]["observation_count"], 0)
        self.assertEqual(archive["probe_records"][0]["missing_data_interpretation"], "UNKNOWN_NOT_ZERO")
        self.assertIn("never zero", archive["scientific_gate"]["missing_data_rule"])

    def test_archives_success_and_preserves_test_only_guard(self):
        archive = MODULE.build_archive([
            sample("2026-08-16T14:00:00+00:00", "2026-08-16T09:00:00-05:00", True, 2.544),
            sample("2026-08-16T15:00:00+00:00", "2026-08-16T10:00:00-05:00", True, 2.6),
        ])
        self.assertEqual(archive["summary"]["successful_numeric_count"], 2)
        self.assertEqual(archive["summary"]["longest_consecutive_hours"], 2)
        self.assertEqual(archive["observations"][0]["use"], "TEST_ONLY_CHANNEL_CONTINUITY_EVIDENCE")
        self.assertFalse(archive["scientific_gate"]["official_threshold_promoted_to_irfen"])
        self.assertFalse(archive["scientific_gate"]["hydraulic_transfer_to_catacaos_validated"])

    def test_intermitent_channel_retains_last_valid_without_fabrication(self):
        archive = MODULE.build_archive([
            sample("2026-08-16T14:00:00+00:00", "2026-08-16T09:00:00-05:00", True, 2.544),
            sample("2026-08-16T15:00:00+00:00", "2026-08-16T10:00:00-05:00", False, reason="URLError"),
        ])
        self.assertEqual(archive["status"], "INTERMITTENT_OFFICIAL_NUMERIC_CHANNEL")
        self.assertEqual(archive["summary"]["observation_count"], 1)
        self.assertEqual(archive["probe_records"][-1]["value"], None)


if __name__ == "__main__":
    unittest.main()
