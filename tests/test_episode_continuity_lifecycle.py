from __future__ import annotations

from episode_continuity_test_support import *


class EpisodeContinuityLifecycleTests(unittest.TestCase):
    def test_candidate_opens_new_continuity_episode_without_alert(self):
        out = cycle(None, "2026-09-05T01:00:00+00:00", san=True, suffix="A")
        row = by_zone(out, "san_ildefonso")
        self.assertEqual(row["lifecycle_state"], "ACTIVE")
        self.assertEqual(row["transition"], "NEW_EVENT")
        self.assertTrue(row["continuity_open"])
        self.assertTrue(row["continuity_episode_id"].startswith("IRFEN-CONT-SAN-ILDEFONSO-"))
        self.assertEqual(out["notification_preview"]["alerts_created"], 0)
        self.assertEqual(out["notification_preview"]["publications_created"], 0)
        self.assertFalse(out["scientific_candidate_forwarding_enabled"])

    def test_upstream_candidate_id_churn_does_not_reopen_episode(self):
        first = cycle(None, "2026-09-05T01:00:00+00:00", san=True, suffix="A")
        second = cycle(first, "2026-09-05T02:00:00+00:00", san=True, suffix="B")
        first_row = by_zone(first, "san_ildefonso")
        second_row = by_zone(second, "san_ildefonso")
        self.assertNotEqual(first_row["input_candidate_id"], second_row["input_candidate_id"])
        self.assertEqual(first_row["continuity_episode_id"], second_row["continuity_episode_id"])
        self.assertEqual(second_row["transition"], "ACTIVE_CONTINUES")

    def test_three_consecutive_candidates_become_persistent(self):
        first = cycle(None, "2026-09-05T01:00:00+00:00", san=True, suffix="A")
        second = cycle(first, "2026-09-05T02:00:00+00:00", san=True, suffix="B")
        third = cycle(second, "2026-09-05T03:00:00+00:00", san=True, suffix="C")
        row = by_zone(third, "san_ildefonso")
        self.assertEqual(row["lifecycle_state"], "PERSISTENT")
        self.assertEqual(row["transition"], "BECAME_PERSISTENT")
        self.assertEqual(row["candidate_streak"], 3)
        self.assertTrue(row["persistent_reached"])

    def test_clear_cycle_enters_recovery_instead_of_closing(self):
        active = cycle(None, "2026-09-05T01:00:00+00:00", cat=True, suffix="A")
        recovering = cycle(active, "2026-09-05T02:00:00+00:00", suffix="B")
        row = by_zone(recovering, "catacaos")
        self.assertEqual(row["lifecycle_state"], "RECOVERY")
        self.assertEqual(row["transition"], "ENTERED_RECOVERY")
        self.assertTrue(row["continuity_open"])
        self.assertEqual(row["clear_streak"], 1)

    def test_three_clear_cycles_close_episode(self):
        active = cycle(None, "2026-09-05T01:00:00+00:00", cat=True, suffix="A")
        event_id = by_zone(active, "catacaos")["continuity_episode_id"]
        first_clear = cycle(active, "2026-09-05T02:00:00+00:00", suffix="B")
        second_clear = cycle(first_clear, "2026-09-05T03:00:00+00:00", suffix="C")
        closed = cycle(second_clear, "2026-09-05T04:00:00+00:00", suffix="D")
        row = by_zone(closed, "catacaos")
        self.assertEqual(row["lifecycle_state"], "NORMAL")
        self.assertEqual(row["transition"], "EVENT_CLOSED")
        self.assertFalse(row["continuity_open"])
        self.assertIsNone(row["continuity_episode_id"])
        self.assertEqual(row["last_closed_episode_id"], event_id)

    def test_reactivation_during_recovery_reuses_same_event(self):
        active = cycle(None, "2026-09-05T01:00:00+00:00", cat=True, suffix="A")
        event_id = by_zone(active, "catacaos")["continuity_episode_id"]
        recovering = cycle(active, "2026-09-05T02:00:00+00:00", suffix="B")
        reactivated = cycle(recovering, "2026-09-05T03:00:00+00:00", cat=True, suffix="C")
        row = by_zone(reactivated, "catacaos")
        self.assertEqual(row["transition"], "REACTIVATED_SAME_EVENT")
        self.assertEqual(row["continuity_episode_id"], event_id)

    def test_reactivation_after_close_gets_new_event_id(self):
        active = cycle(None, "2026-09-05T01:00:00+00:00", cat=True, suffix="A")
        old_id = by_zone(active, "catacaos")["continuity_episode_id"]
        one = cycle(active, "2026-09-05T02:00:00+00:00", suffix="B")
        two = cycle(one, "2026-09-05T03:00:00+00:00", suffix="C")
        closed = cycle(two, "2026-09-05T04:00:00+00:00", suffix="D")
        reopened = cycle(closed, "2026-09-05T05:00:00+00:00", cat=True, suffix="E")
        self.assertNotEqual(by_zone(reopened, "catacaos")["continuity_episode_id"], old_id)
        self.assertEqual(by_zone(reopened, "catacaos")["transition"], "NEW_EVENT")

    def test_two_simultaneous_north_coast_zones_enter_saturation_coordination_only(self):
        out = cycle(None, "2026-09-05T01:00:00+00:00", san=True, cat=True, suffix="A")
        self.assertEqual(out["global_saturation"]["level"], "REGIONAL_SATURATION_TEST")
        north = next(g for g in out["coordination_groups"] if g["group_id"] == "north_coast_test_coordination")
        self.assertEqual(north["concurrency_level"], "REGIONAL_SATURATION_TEST")
        self.assertFalse(north["shared_hydrologic_event"])
        self.assertEqual(north["interpretation"], "COORDINATION_ONLY_NOT_A_SHARED_HYDROLOGIC_EVENT")
        self.assertEqual(out["notification_preview"]["mode"], "ONE_REGIONAL_DIGEST_PREVIEW_NO_POINT_MESSAGES")
        self.assertEqual(out["notification_preview"]["messages_created"], 0)

    def test_recovery_counts_as_active_like_and_prevents_saturation_flicker(self):
        active = cycle(None, "2026-09-05T01:00:00+00:00", san=True, cat=True, suffix="A")
        mixed = cycle(active, "2026-09-05T02:00:00+00:00", cat=True, suffix="B")
        self.assertEqual(by_zone(mixed, "san_ildefonso")["lifecycle_state"], "RECOVERY")
        self.assertEqual(by_zone(mixed, "catacaos")["lifecycle_state"], "ACTIVE")
        self.assertEqual(mixed["global_saturation"]["level"], "REGIONAL_SATURATION_TEST")



if __name__ == "__main__":
    unittest.main()
