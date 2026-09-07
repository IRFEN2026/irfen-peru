from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_episode_continuity_pilot as pilot

PILOT_CONFIG_PATH = ROOT / "config" / "episode_continuity_pilot_v01.json"
CONTROLLER_CONTRACT_PATH = ROOT / "config" / "episode_continuity_contract_v01.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report() -> dict:
    return pilot.build_report(load(PILOT_CONFIG_PATH), load(CONTROLLER_CONTRACT_PATH))


def by_scenario(report: dict, scenario_id: str) -> dict:
    return next(item for item in report["scenarios"] if item["scenario_id"] == scenario_id)


class EpisodeContinuityPilotTests(unittest.TestCase):
    def test_all_preregistered_pilot_scenarios_pass(self):
        report = build_report()
        print("IRFEN_CONTINUITY_PILOT_SUMMARY=" + json.dumps(report["summary"], sort_keys=True))
        self.assertEqual(
            report["status"],
            "PASS",
            json.dumps(report, indent=2, ensure_ascii=False),
        )
        self.assertEqual(report["interpretation"], "CONTROL_LOGIC_PASSED_NOT_HYDROLOGICAL_VALIDATION")
        self.assertEqual(report["summary"]["scenarios_executed"], 2)
        self.assertEqual(report["summary"]["scenarios_passed"], 2)
        self.assertEqual(report["summary"]["metric_checks_passed"], report["summary"]["metric_checks_total"])
        self.assertEqual(report["summary"]["checkpoints_passed"], report["summary"]["checkpoints_total"])

    def test_ordinary_pilot_preserves_identity_through_pause_and_changes_it_after_close(self):
        scenario = by_scenario(build_report(), "ordinary_single_zone_hysteresis")
        self.assertEqual(scenario["status"], "PASS", json.dumps(scenario, indent=2, ensure_ascii=False))
        timeline = scenario["timeline"]
        first_id = timeline[1]["continuity_episode_ids"]["san_ildefonso"]
        reactivated_id = timeline[5]["continuity_episode_ids"]["san_ildefonso"]
        reopened_id = timeline[9]["continuity_episode_ids"]["san_ildefonso"]
        self.assertEqual(first_id, reactivated_id)
        self.assertNotEqual(first_id, reopened_id)
        self.assertEqual(timeline[10]["status"], "IDEMPOTENT_REPLAY_COMPLETE")
        self.assertEqual(timeline[10]["candidate_streaks"]["san_ildefonso"], 1)

    def test_extreme_pilot_sustains_regional_saturation_without_claiming_shared_hydrology(self):
        scenario = by_scenario(build_report(), "extreme_multizone_multiday_saturation")
        self.assertEqual(scenario["status"], "PASS", json.dumps(scenario, indent=2, ensure_ascii=False))
        metrics = scenario["metrics"]
        self.assertEqual(metrics["maximum_concurrent_open_zones"], 3)
        self.assertEqual(metrics["regional_saturation_cycles"], 10)
        self.assertEqual(metrics["events_opened"], metrics["events_closed"])
        self.assertEqual(scenario["final"]["global_saturation"], "NORMAL_LOAD")
        self.assertEqual(scenario["final"]["open_continuity_episode_count"], 0)

    def test_blocked_and_partial_inputs_are_not_interpreted_as_clear(self):
        scenario = by_scenario(build_report(), "extreme_multizone_multiday_saturation")
        blocked_cycle = scenario["timeline"][7]
        self.assertEqual(blocked_cycle["controller_statuses"]["san_ildefonso"], "BLOCKED_RETAINED_PREVIOUS")
        self.assertEqual(blocked_cycle["lifecycle_states"]["san_ildefonso"], "PERSISTENT")
        self.assertIn("rain1h", blocked_cycle["temporal_missing_windows"]["san_ildefonso"])
        self.assertIn("rain3h", blocked_cycle["temporal_missing_windows"]["san_ildefonso"])
        self.assertIn("rain6h", blocked_cycle["temporal_missing_windows"]["san_ildefonso"])
        self.assertEqual(blocked_cycle["clear_streaks"]["san_ildefonso"], 0)

    def test_pilot_preserves_all_non_operational_guards(self):
        report = build_report()
        for key in (
            "production_use",
            "production_ready",
            "operational_alerting_enabled",
            "public_social_publishing",
            "scientific_candidate_forwarding_enabled",
            "hydrological_skill_validated",
            "rainfall_thresholds_validated",
            "operational_readiness_validated",
        ):
            self.assertFalse(report[key], key)
        self.assertEqual(report["summary"]["alerts_created"], 0)
        self.assertEqual(report["summary"]["publications_created"], 0)
        for scenario in report["scenarios"]:
            self.assertTrue(all(scenario["guards"].values()), scenario["guards"])

    def test_pilot_report_is_deterministic(self):
        self.assertEqual(build_report(), build_report())


if __name__ == "__main__":
    unittest.main()
