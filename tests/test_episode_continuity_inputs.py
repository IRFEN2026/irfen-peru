from __future__ import annotations

from episode_continuity_test_support import *


class EpisodeContinuityInputGuardTests(unittest.TestCase):
    def test_duplicate_source_is_idempotent(self):
        frame = potential_frame("2026-09-05T01:00:00+00:00", san=True, suffix="A")
        first = module.build_output(frame, experimental(), contract(), None, "2026-09-05T01:01:00+00:00")
        replay = module.build_output(frame, experimental(), contract(), first, "2026-09-05T01:02:00+00:00")
        first_row = by_zone(first, "san_ildefonso")
        replay_row = by_zone(replay, "san_ildefonso")
        self.assertEqual(replay["status"], "IDEMPOTENT_REPLAY_COMPLETE")
        self.assertEqual(replay_row["candidate_streak"], first_row["candidate_streak"])
        self.assertEqual(replay_row["open_cycle_count"], first_row["open_cycle_count"])
        self.assertEqual(replay_row["continuity_episode_id"], first_row["continuity_episode_id"])

    def test_out_of_order_source_is_blocked_and_previous_open_state_is_retained(self):
        current = cycle(None, "2026-09-05T03:00:00+00:00", san=True, suffix="C")
        older = module.build_output(
            potential_frame("2026-09-05T02:00:00+00:00", suffix="B"),
            experimental(),
            contract(),
            current,
            "2026-09-05T03:01:00+00:00",
        )
        before = by_zone(current, "san_ildefonso")
        after = by_zone(older, "san_ildefonso")
        self.assertEqual(older["status"], "BLOCKED_RETAINED_PREVIOUS")
        self.assertIn("out_of_order_source", older["global_blockers"])
        self.assertEqual(after["lifecycle_state"], before["lifecycle_state"])
        self.assertEqual(after["continuity_episode_id"], before["continuity_episode_id"])

    def test_blocked_upstream_zone_is_not_interpreted_as_clear(self):
        active = cycle(None, "2026-09-05T01:00:00+00:00", san=True, suffix="A")
        blocked_frame = potential_frame("2026-09-05T02:00:00+00:00", suffix="B")
        blocked = blocked_frame["zones"][0]
        blocked["detector_status"] = "BLOCKED_INPUT_GATE"
        blocked["input_gate_blockers"] = ["explicit_stale_input"]
        out = module.build_output(blocked_frame, experimental(), contract(), active, "2026-09-05T02:00:00+00:00")
        row = by_zone(out, "san_ildefonso")
        self.assertEqual(row["lifecycle_state"], "ACTIVE")
        self.assertEqual(row["transition"], "BLOCKED_RETAIN_PREVIOUS")
        self.assertEqual(row["clear_streak"], 0)

    def test_missing_short_windows_are_unknown_not_zero(self):
        out = cycle(None, "2026-09-05T01:00:00+00:00", san=True, suffix="A")
        temporal = by_zone(out, "san_ildefonso")["temporal_evidence"]
        for key in ("rain1h", "rain3h", "rain6h"):
            self.assertIsNone(temporal["windows"][key]["value_mm"])
            self.assertEqual(temporal["windows"][key]["status"], "MISSING_NOT_INFERRED")
        self.assertEqual(temporal["availability"]["available_window_count"], 3)
        self.assertEqual(temporal["availability"]["interpretation"], "DATA_COMPLETENESS_ONLY_NOT_RISK_NOT_CONFIDENCE")

    def test_all_temporal_windows_and_context_are_preserved_without_new_thresholds(self):
        out = module.build_output(
            potential_frame("2026-09-05T01:00:00+00:00", san=True, suffix="A"),
            experimental(full_temporal=True),
            contract(),
            None,
            "2026-09-05T01:00:00+00:00",
        )
        temporal = by_zone(out, "san_ildefonso")["temporal_evidence"]
        self.assertEqual(temporal["availability"]["available_window_count"], 6)
        self.assertEqual(temporal["windows"]["rain1h"]["value_mm"], 2.0)
        self.assertEqual(temporal["context"]["wet_streak_days"]["value"], 3)
        self.assertEqual(temporal["context"]["data_confidence"]["value"], "UPSTREAM_HIGH")
        self.assertFalse(temporal["thresholds_created"])
        self.assertFalse(temporal["interpolation_applied"])

    def test_watch_state_does_not_open_episode(self):
        out = cycle(None, "2026-09-05T01:00:00+00:00", watch_san=True, suffix="A")
        row = by_zone(out, "san_ildefonso")
        self.assertEqual(row["lifecycle_state"], "WATCH")
        self.assertFalse(row["continuity_open"])
        self.assertIsNone(row["continuity_episode_id"])



if __name__ == "__main__":
    unittest.main()
