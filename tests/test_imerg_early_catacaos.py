import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]

# Las pruebas son puramente geométricas y de archivo; no autentican ni llaman
# Earthdata. El workflow instala earthaccess antes de ejecutarlas, mientras que
# este sustituto permite correrlas también en entornos locales mínimos.
try:
    import earthaccess  # noqa: F401
except ModuleNotFoundError:
    sys.modules["earthaccess"] = types.ModuleType("earthaccess")


def load_script(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = load_script("probe_imerg_early_live", "scripts/probe_imerg_early_live.py")
archive = load_script("archive_imerg_early_probe", "scripts/archive_imerg_early_probe.py")


class CatacaosTargetTests(unittest.TestCase):
    def test_event_interval_excludes_next_midnight(self):
        start = archive.parse_time("2026-08-14T05:00:00+00:00")
        rows = [
            (start, "first", object()),
            (start + archive.timedelta(minutes=30 * 47), "last", object()),
            (start + archive.timedelta(hours=24), "next-day", object()),
        ]
        selected = probe.filter_half_open_interval(
            rows,
            "2026-08-14T05:00:00+00:00",
            "2026-08-15T05:00:00+00:00",
        )
        self.assertEqual([row[1] for row in selected], ["first", "last"])

    def test_required_targets_include_catacaos(self):
        targets = {target["id"]: target for target in probe.load_targets()}
        self.assertTrue(probe.REQUIRED_TARGET_IDS.issubset(set(targets)))
        self.assertEqual(
            [area["weight"] for area in targets["catacaos"]["sampling_areas"]],
            [0.35, 0.65],
        )

    def test_catacaos_uses_existing_weighted_sampling_contract(self):
        target = next(target for target in probe.load_targets() if target["id"] == "catacaos")
        metadata = {
            "cells_intersected": 2,
            "valid_cells": 2,
            "grid_resolution_deg": [0.1, 0.1],
            "covered_geometry_pct": 100.0,
        }
        with patch.object(probe, "polygon_mean", side_effect=[(2.0, metadata), (8.0, metadata)]):
            value, sampling = probe.sample_target(target, None, None, None)
        self.assertAlmostEqual(value, 5.9)
        self.assertEqual(sampling["sampling_method"], "provisional_weighted_operational_sampling_areas")
        self.assertEqual(sampling["available_weight"], 1.0)
        self.assertEqual(len(sampling["sampling_areas"]), 2)

    def test_complete_local_day_replay_is_test_only(self):
        start = archive.parse_time("2026-08-14T05:00:00+00:00")
        granules = []
        for index in range(48):
            timestamp = start + archive.timedelta(minutes=30 * index)
            granules.append({
                "time_utc": timestamp.isoformat(),
                "granule": f"test-{index}",
                "targets": [{
                    "target_id": "catacaos",
                    "rate_mm_hr": 0.2,
                    "accum_30min_mm": 0.1,
                }],
            })
        replay = archive.build_event_replays(granules)[0]
        self.assertEqual(replay["status"], "COMPLETE")
        self.assertTrue(replay["continuous"])
        self.assertEqual(replay["complete_accum_mm"], 4.8)
        self.assertEqual(replay["decision_use"], "TEST_ONLY")

    def test_verified_phase2_event_is_sampled_without_joining_core_targets(self):
        targets = {target["id"]: target for target in probe.load_targets()}
        target_id = "phase2_event:villa-el-salvador-2026-08-16-coen"
        self.assertIn(target_id, targets)
        self.assertNotIn(target_id, probe.REQUIRED_TARGET_IDS)
        case = probe.phase2_event_bootstraps(list(targets.values()))[0]
        self.assertEqual(case["target_id"], target_id)
        self.assertEqual(case["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(case["counts_toward_v08_closeout"])
        self.assertEqual(case["start_utc"], "2026-08-15T10:00:00+00:00")
        self.assertEqual(case["end_utc"], "2026-08-16T10:00:00+00:00")

        intake = json.loads(
            (ROOT / "site/data/validation/phase2_event_intake/villa-el-salvador-2026-08-16-coen.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(intake["research_role"], "METEOROLOGICAL_REFERENCE_EVENT")
        self.assertFalse(intake["is_huaico_or_torrent_event"])
        self.assertFalse(intake["can_train_zone_activation_model"])

    def test_phase2_event_replay_remains_research_only(self):
        cases = archive.phase2_event_cases()
        case = next(row for row in cases if row["case_id"] == "villa-el-salvador-2026-08-16-coen")
        replay = archive.build_event_replays([], cases=[case])[0]
        self.assertEqual(replay["status"], "ACCUMULATING")
        self.assertEqual(replay["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(replay["counts_toward_v08_closeout"])
        self.assertEqual(replay["decision_use"], "TEST_ONLY")


class BoundedSelectionTests(unittest.TestCase):
    def row(self, minute, name):
        start = archive.parse_time("2026-08-15T00:00:00+00:00")
        return (start + archive.timedelta(minutes=minute), name, object())

    def test_prioritizes_recent_continuity_gaps_before_event_replay(self):
        live = [self.row(0, "live-old"), self.row(30, "live-gap"), self.row(60, "live-new")]
        repairs = [self.row(-60, "repair-old"), self.row(30, "live-gap")]
        event = [self.row(-1440, "event-1"), self.row(-1410, "event-2")]

        selected = probe.select_bounded_granules(live, repairs, event, limit=3)

        self.assertEqual([row[1] for row in selected], ["event-1", "event-2", "live-new"])

    def test_verified_event_backfill_cannot_be_starved_by_recent_repair(self):
        live = [self.row(0, "newest")]
        repairs = [self.row(-30 * index, f"repair-{index}") for index in range(1, 8)]
        event = [self.row(-1440, "event-1"), self.row(-1410, "event-2")]

        selected = probe.select_bounded_granules(live, repairs, event, limit=4)

        self.assertEqual({row[1] for row in selected} & {"event-1", "event-2"}, {"event-1", "event-2"})
        self.assertIn("newest", {row[1] for row in selected})

    def test_deduplicates_candidates_and_preserves_download_cap(self):
        live = [self.row(0, "newest")]
        repeated = [self.row(0, "newest"), self.row(-30, "gap-1"), self.row(-60, "gap-2")]

        selected = probe.select_bounded_granules(live, repeated, repeated, limit=2)

        self.assertEqual(len(selected), 2)
        self.assertEqual(len({row[1] for row in selected}), 2)
        self.assertIn("newest", {row[1] for row in selected})

    def test_finite_event_replay_gets_reserved_slot_before_recent_target_backfill(self):
        live = [self.row(0, "newest")]
        event = [self.row(-1440, "event")]
        incomplete = [self.row(-30, "incomplete")]

        selected = probe.select_bounded_granules(
            live,
            continuity_missing=[],
            bootstrap_missing=event,
            target_incomplete=incomplete,
            limit=2,
        )

        self.assertEqual({row[1] for row in selected}, {"newest", "event"})

    def test_empty_catalogue_is_safe(self):
        self.assertEqual(probe.select_bounded_granules([], [], [], limit=4), [])

    def test_event_backfill_policy_reserves_six_of_eight_downloads(self):
        live = [self.row(0, "newest")]
        repairs = [self.row(-30 * index, f"repair-{index}") for index in range(1, 8)]
        event = [self.row(-1440 + 30 * index, f"event-{index}") for index in range(8)]
        policy = probe.download_policy(event)

        selected = probe.select_bounded_granules(
            live,
            repairs,
            event,
            limit=policy["limit"],
            event_slots=policy["event_slots"],
        )

        self.assertEqual(policy["mode"], "VERIFIED_RESEARCH_EVENT_BACKFILL")
        self.assertEqual(len(selected), 8)
        self.assertEqual(sum(row[1].startswith("event-") for row in selected), 6)
        self.assertIn("newest", {row[1] for row in selected})

    def test_download_policy_self_reverts_when_event_backfill_is_complete(self):
        self.assertEqual(probe.download_policy([]), {
            "mode": "NORMAL_CONTINUITY",
            "limit": 4,
            "event_slots": 2,
        })


class ProbeCadenceTests(unittest.TestCase):
    def test_reports_observed_probe_gaps_separately(self):
        records = [
            {"probe_generated_at": "2026-08-15T00:00:00Z"},
            {"probe_generated_at": "2026-08-15T00:30:00Z"},
            {"probe_generated_at": "2026-08-15T02:00:00Z"},
        ]

        result = archive.probe_cadence_summary(records)

        self.assertEqual(result["probe_timestamp_count"], 3)
        self.assertEqual(result["probe_interval_count"], 2)
        self.assertEqual(result["probe_gap_median_hours"], 1.0)
        self.assertEqual(result["probe_gap_max_hours"], 1.5)
        self.assertIn("cadence", result["interpretation"].lower())

    def test_invalid_probe_timestamps_do_not_create_false_intervals(self):
        result = archive.probe_cadence_summary([
            {"probe_generated_at": None},
            {"probe_generated_at": "not-a-date"},
        ])

        self.assertEqual(result["probe_timestamp_count"], 0)
        self.assertEqual(result["probe_interval_count"], 0)
        self.assertIsNone(result["probe_gap_max_hours"])


class HistoricalWindowValidationTests(unittest.TestCase):
    def granule(self, timestamp, value=0.1):
        return {
            "time_utc": timestamp.isoformat(),
            "granule": f"test-{timestamp.isoformat()}",
            "targets": [{
                "target_id": "san_ildefonso",
                "accum_30min_mm": value,
            }],
        }

    def test_delayed_live_tail_does_not_erase_prior_24h_validation(self):
        start = archive.parse_time("2026-08-15T00:00:00+00:00")
        granules = [
            self.granule(start + archive.timedelta(minutes=30 * index))
            for index in range(48)
        ]
        granules.extend([
            self.granule(start + archive.timedelta(hours=26)),
            self.granule(start + archive.timedelta(hours=26, minutes=30)),
        ])

        rolling = archive.rolling_summary(granules)["san_ildefonso"]["24h"]
        validated = archive.validated_windows_summary(granules)["san_ildefonso"]["24h"]

        self.assertFalse(rolling["available"])
        self.assertTrue(validated["available"])
        self.assertTrue(validated["continuous"])
        self.assertEqual(validated["start_utc"], start.isoformat())
        self.assertEqual(
            validated["end_utc"],
            (start + archive.timedelta(minutes=30 * 47)).isoformat(),
        )

    def test_missing_target_sample_cannot_validate_24h_window(self):
        start = archive.parse_time("2026-08-15T00:00:00+00:00")
        granules = [
            self.granule(start + archive.timedelta(minutes=30 * index))
            for index in range(48)
            if index != 20
        ]

        validated = archive.validated_windows_summary(granules)["san_ildefonso"]["24h"]

        self.assertFalse(validated["available"])
        self.assertFalse(validated["continuous"])

    def test_summary_distinguishes_current_tail_from_retained_validation(self):
        start = archive.parse_time("2026-08-15T00:00:00+00:00")
        granules = [
            self.granule(start + archive.timedelta(minutes=30 * index))
            for index in range(48)
        ]
        granules.extend([
            self.granule(start + archive.timedelta(hours=26)),
            self.granule(start + archive.timedelta(hours=26, minutes=30)),
        ])
        rolling = archive.rolling_summary(granules)
        validated = archive.validated_windows_summary(granules)

        summary = archive.target_continuity_summary(rolling, validated)

        self.assertEqual(summary["targets_with_current_continuous_24h"], [])
        self.assertEqual(
            summary["targets_with_validated_continuous_24h"],
            ["san_ildefonso"],
        )
        self.assertEqual(summary["targets_with_continuous_24h"], ["san_ildefonso"])
        self.assertIn("historical", summary["continuous_24h_summary_semantics"])


class ImergPublishHandoffTests(unittest.TestCase):
    def test_probe_dispatches_publisher_with_exact_main_sha(self):
        workflow = (ROOT / ".github/workflows/imerg-early-probe.yml").read_text(encoding="utf-8")
        self.assertIn('EXPECTED_SHA="$(git rev-parse origin/main)"', workflow)
        self.assertIn('-f expected_sha="$EXPECTED_SHA"', workflow)

    def test_publisher_checks_out_and_verifies_expected_sha(self):
        workflow = (ROOT / ".github/workflows/publish-committed-data.yml").read_text(encoding="utf-8")
        self.assertIn("expected_sha:", workflow)
        self.assertIn("ref: ${{ inputs.expected_sha || github.sha }}", workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "${{ inputs.expected_sha }}"', workflow)

    def test_publisher_verifies_public_imerg_freshness(self):
        workflow = (ROOT / ".github/workflows/publish-committed-data.yml").read_text(encoding="utf-8")
        self.assertIn("/tmp/irfen-published/imerg.json", workflow)
        self.assertIn("published.get(freshness_key) == expected.get(freshness_key)", workflow)
        self.assertIn("published_probe == expected_probe", workflow)

    def test_publisher_reruns_use_unique_artifact_and_retry_smoke_dispatch(self):
        workflow = (ROOT / ".github/workflows/publish-committed-data.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            workflow.count("github-pages-${{ github.run_attempt }}"),
            2,
        )
        self.assertIn("artifact_name: github-pages-${{ github.run_attempt }}", workflow)
        self.assertIn("for attempt in 1 2 3 4", workflow)
        self.assertIn("sleep $((attempt * 5))", workflow)

    def test_pull_request_validation_is_non_deploying(self):
        workflow = (ROOT / ".github/workflows/pr-validation.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("Hidratar evidencia transitoria publicada", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("python scripts/run_v08_regression_tests.py", workflow)
        self.assertNotIn("actions/deploy-pages", workflow)


if __name__ == "__main__":
    unittest.main()
