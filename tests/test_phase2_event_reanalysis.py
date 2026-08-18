import importlib.util
import json
from datetime import timedelta
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase2_event_reanalysis", ROOT / "scripts/build_phase2_event_reanalysis.py"
)
rean = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(rean)


class Phase2EventReanalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ves = json.loads(
            (ROOT / "site/data/validation/phase2_event_intake/villa-el-salvador-2026-08-16-coen.json")
            .read_text(encoding="utf-8")
        )
        cls.viru = json.loads(
            (ROOT / "site/data/validation/phase2_event_intake/viru-2026-08-17-unverified.json")
            .read_text(encoding="utf-8")
        )

    def synthetic_archive(self, sample_count=48):
        occurrence = rean.parse_time(self.ves["reported_event"]["occurrence_time_local"])
        start = occurrence - timedelta(hours=24)
        target_id = f"phase2_event:{self.ves['event_id']}"
        return {
            "source": "synthetic test",
            "granules": [
                {
                    "time_utc": (start + index * rean.STEP).isoformat(),
                    "targets": [{"target_id": target_id, "accum_30min_mm": 0.5, "rate_mm_hr": 1.0}],
                }
                for index in range(sample_count)
            ],
        }

    def test_complete_series_exposes_only_complete_accumulations(self):
        item = rean.build_event(self.ves, self.synthetic_archive())
        self.assertEqual(item["status"], "COMPLETE_SATELLITE_REANALYSIS")
        self.assertEqual(item["windows"]["3h"]["accum_mm"], 3.0)
        self.assertEqual(item["windows"]["6h"]["accum_mm"], 6.0)
        self.assertEqual(item["windows"]["24h"]["accum_mm"], 24.0)
        self.assertFalse(item["local_validation"])
        self.assertFalse(item["threshold_inference_allowed"])

    def test_partial_series_never_exposes_window_accumulation(self):
        item = rean.build_event(self.ves, self.synthetic_archive(sample_count=47))
        self.assertEqual(item["status"], "PARTIAL_SATELLITE_REANALYSIS")
        self.assertIsNone(item["windows"]["24h"]["accum_mm"])
        self.assertEqual(item["windows"]["24h"]["coverage_pct"], 97.9)
        self.assertEqual(len(item["windows"]["24h"]["missing_slots_utc"]), 1)
        self.assertEqual(item["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")

    def test_unverified_event_remains_blocked(self):
        item = rean.build_event(self.viru, self.synthetic_archive())
        self.assertEqual(item["status"], "BLOCKED_UNVERIFIED_EVENT")
        self.assertEqual(item["windows"], {})
        self.assertFalse(item["operational_zone_activation"])

    def test_committed_artifact_matches_fail_closed_generator(self):
        generated = rean.generate(write=False)
        committed = json.loads(rean.OUT_PATH.read_text(encoding="utf-8"))
        generated.pop("generated_at", None)
        committed.pop("generated_at", None)
        self.assertEqual(committed, generated)
        self.assertTrue(committed["guardrails"]["missing_data_is_not_low_risk"])
        ves = next(item for item in committed["items"] if item["event_id"] == self.ves["event_id"])
        if ves["status"] != "COMPLETE_SATELLITE_REANALYSIS":
            self.assertTrue(any(window["accum_mm"] is None for window in ves["windows"].values()))


if __name__ == "__main__":
    unittest.main()
