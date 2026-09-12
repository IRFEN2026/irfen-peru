from __future__ import annotations

from episode_continuity_test_support import *


class EpisodeContinuityReplayAndGuardTests(unittest.TestCase):
    def test_extreme_replay_reports_concurrency_persistence_and_deduplication(self):
        times = [f"2026-09-05T{hour:02d}:00:00+00:00" for hour in range(1, 10)]
        signals = [
            {},
            {"san": True},
            {"san": True, "cat": True},
            {"san": True, "cat": True},
            {"san": True, "cat": True},
            {"cat": True},
            {},
            {},
            {},
        ]
        frames = [
            {"potential": potential_frame(at, suffix=chr(65 + i), **signal), "experimental": experimental(), "generated_at": at}
            for i, (at, signal) in enumerate(zip(times, signals))
        ]
        report = module.replay_sequence({"frames": frames}, contract())
        metrics = report["metrics"]
        self.assertEqual(metrics["cycles"], 9)
        self.assertEqual(metrics["events_opened"], 2)
        self.assertGreaterEqual(metrics["persistent_transitions"], 2)
        self.assertGreaterEqual(metrics["upstream_candidate_id_churn_absorbed"], 4)
        self.assertEqual(metrics["maximum_concurrent_open_zones"], 2)
        self.assertGreaterEqual(metrics["regional_saturation_cycles"], 4)
        self.assertEqual(metrics["alerts_created"], 0)
        self.assertEqual(metrics["publications_created"], 0)


    def test_first_cycle_global_blocker_fails_closed_with_guarded_normal_rows(self):
        bad = potential_frame("2026-09-05T01:00:00+00:00", san=True, suffix="A")
        bad["production_use"] = True
        out = module.build_output(bad, experimental(), contract(), None, "2026-09-05T01:00:00+00:00")
        self.assertEqual(out["status"], "BLOCKED_FAIL_CLOSED")
        row = by_zone(out, "san_ildefonso")
        self.assertEqual(row["lifecycle_state"], "NORMAL")
        self.assertEqual(row["transition"], "BLOCKED_RETAIN_PREVIOUS")
        self.assertFalse(row["production_use"])
        self.assertFalse(row["operational_alerting_enabled"])

    def test_same_source_hash_with_changed_timestamp_is_blocked(self):
        first_frame = potential_frame("2026-09-05T01:00:00+00:00", san=True, suffix="A")
        first = module.build_output(first_frame, experimental(), contract(), None, "2026-09-05T01:00:00+00:00")
        contradictory = potential_frame("2026-09-05T02:00:00+00:00", suffix="A")
        out = module.build_output(contradictory, experimental(), contract(), first, "2026-09-05T02:00:00+00:00")
        self.assertEqual(out["status"], "BLOCKED_RETAINED_PREVIOUS")
        self.assertIn("same_source_hash_different_timestamp", out["global_blockers"])
        self.assertEqual(
            by_zone(out, "san_ildefonso")["continuity_episode_id"],
            by_zone(first, "san_ildefonso")["continuity_episode_id"],
        )

    def test_invalid_contract_hysteresis_fails_before_evaluation(self):
        cfg = contract()
        cfg["temporal_control"]["close_after_consecutive_clear"] = 2
        with self.assertRaisesRegex(ValueError, "same-event reactivation window"):
            module.build_output(
                potential_frame("2026-09-05T01:00:00+00:00", suffix="A"),
                experimental(),
                cfg,
                None,
                "2026-09-05T01:00:00+00:00",
            )

    def test_contract_invariants_match_hysteresis_parameters(self):
        cfg = contract()
        temporal = cfg["temporal_control"]
        self.assertEqual(
            temporal["same_event_reactivation_max_clear_cycles"],
            temporal["close_after_consecutive_clear"] - 1,
        )
        self.assertTrue(temporal["parameters_are_test_mechanics_not_scientific_thresholds"])
        self.assertFalse(cfg["scientific_candidate_forwarding_enabled"])



if __name__ == "__main__":
    unittest.main()
