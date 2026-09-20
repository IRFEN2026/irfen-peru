"""Tests for Claude G — Phase-2 subunit rainfall evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_script(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


sampling = load_script("phase2_subunit_sampling_test", "scripts/phase2_subunit_sampling.py")
probe = load_script("probe_imerg_early_live_g", "scripts/probe_imerg_early_live.py")
archive = load_script("archive_imerg_early_probe_g", "scripts/archive_imerg_early_probe.py")
late = load_script("update_phase2_subunit_imerg_late_g", "scripts/update_phase2_subunit_imerg_late.py")
builder = load_script("build_phase2_subunit_rainfall_evidence_g", "scripts/build_phase2_subunit_rainfall_evidence.py")


class SubunitResolverTests(unittest.TestCase):
    def test_exact_four_research_subunits(self):
        targets = sampling.load_research_subunit_targets()
        self.assertEqual(len(targets), 4)
        ids = {target["subunit_id"] for target in targets}
        self.assertEqual(
            ids,
            {
                "cashahuacra",
                "shingolay",
                "lambayeque_chancay_lambayeque_chongoyape",
                "lambayeque_zana_oyotun",
            },
        )
        parents = {target["candidate_id"] for target in targets}
        self.assertEqual(
            parents,
            {
                "lima_este_santa_eulalia_rimac",
                "lambayeque_chongoyape_oyotun_zana",
            },
        )
        for target in targets:
            self.assertTrue(target["id"].startswith("phase2_subunit:"))
            self.assertGreater(target["geometry"].area, 0)
            self.assertFalse(
                target["phase2_subunit"]["counts_as_candidate_wide_geometry"]
            )
            self.assertFalse(
                target["phase2_subunit"]["counts_as_operational_geometry"]
            )

    def test_probe_includes_subunits_without_changing_v08_core(self):
        targets = {target["id"]: target for target in probe.load_targets()}
        subunit_ids = {
            target["id"] for target in sampling.load_research_subunit_targets()
        }
        self.assertTrue(subunit_ids.issubset(targets))
        self.assertTrue(probe.REQUIRED_TARGET_IDS.isdisjoint(subunit_ids))
        required_for_run = probe.required_target_ids_for_run(list(targets.values()))
        self.assertTrue(probe.REQUIRED_TARGET_IDS.issubset(required_for_run))
        self.assertTrue(subunit_ids.issubset(required_for_run))

    def test_subunit_backfill_policy_is_bounded(self):
        policy = probe.download_policy([], research_subunit_missing=True)
        self.assertEqual(policy["mode"], "PHASE2_SUBUNIT_CONTINUITY_BACKFILL")
        self.assertEqual(policy["limit"], 8)
        self.assertEqual(policy["event_slots"], 0)


class EarlyWindowTests(unittest.TestCase):
    def test_early_windows_cover_fast_monitoring_horizons(self):
        self.assertEqual(
            archive.WINDOWS,
            {"1h": 2, "3h": 6, "6h": 12, "12h": 24, "24h": 48},
        )

    def test_continuous_one_hour_window_accumulates(self):
        start = archive.parse_time("2026-09-20T00:00:00+00:00")
        granules = [
            {
                "time_utc": (start + archive.timedelta(minutes=30 * idx)).isoformat(),
                "granule": f"g-{idx}",
                "targets": [{
                    "target_id": "phase2_subunit:lima_este_santa_eulalia_rimac:cashahuacra",
                    "accum_30min_mm": 0.5,
                }],
            }
            for idx in range(2)
        ]
        result = archive.rolling_for_target(
            granules,
            "phase2_subunit:lima_este_santa_eulalia_rimac:cashahuacra",
            2,
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["accum_mm"], 1.0)


class LateDailyWindowTests(unittest.TestCase):
    def test_complete_daily_windows(self):
        rows = [
            {"date": f"2026-09-{day:02d}", "rain_mm": float(day)}
            for day in range(14, 21)
        ]
        self.assertEqual(late.consecutive_window(rows, 1)["accum_mm"], 20.0)
        self.assertEqual(
            late.consecutive_window(rows, 3)["accum_mm"],
            20.0 + 19.0 + 18.0,
        )
        self.assertEqual(
            late.consecutive_window(rows, 7)["accum_mm"],
            sum(float(day) for day in range(14, 21)),
        )

    def test_daily_gap_fails_closed(self):
        rows = [
            {"date": "2026-09-20", "rain_mm": 3.0},
            {"date": "2026-09-18", "rain_mm": 2.0},
        ]
        self.assertTrue(late.consecutive_window(rows, 1)["available"])
        self.assertFalse(late.consecutive_window(rows, 3)["available"])
        self.assertIsNone(late.consecutive_window(rows, 3)["accum_mm"])


class ConsolidatedEvidenceTests(unittest.TestCase):
    def test_builder_has_four_research_subunits(self):
        result = builder.generate(write=False)
        self.assertEqual(result["summary"]["research_subunit_count"], 4)
        self.assertEqual(len(result["targets"]), 4)
        for row in result["targets"]:
            self.assertFalse(row["counts_as_candidate_wide_rainfall"])
            self.assertFalse(row["counts_as_operational_evidence"])
            self.assertEqual(row["activation_gate"], "BLOCKED")
            self.assertFalse(row["production_use"])
            self.assertFalse(row["production_ready"])

    def test_no_decision_outputs_exist(self):
        result = builder.generate(write=False)
        text = json.dumps(result)
        for forbidden in (
            '"risk_score"',
            '"activation_score"',
            '"alert_score"',
            '"physical_response_plausibility_score"',
            '"promotion_gate_met"',
        ):
            self.assertNotIn(forbidden, text)
        self.assertEqual(result["summary"]["candidate_wide_rainfall_outputs"], 0)
        self.assertEqual(result["summary"]["operational_activations"], 0)
        self.assertEqual(result["summary"]["thresholds_created"], 0)

    def test_builder_is_deterministic_except_timestamp(self):
        first = builder.generate(write=False)
        second = builder.generate(write=False)
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        self.assertEqual(first, second)


class WorkflowContractTests(unittest.TestCase):
    def test_half_hour_workflow_builds_and_persists_subunit_evidence(self):
        workflow = (
            ROOT / ".github/workflows/imerg-early-probe.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("update_phase2_subunit_imerg_late.py", workflow)
        self.assertIn("build_phase2_subunit_rainfall_evidence.py", workflow)
        self.assertIn("validate_phase2_subunit_rainfall_evidence.py", workflow)
        self.assertIn("subunit_imerg_late_v0_1.json", workflow)
        self.assertIn("subunit_rainfall_evidence_v0_1.json", workflow)
        self.assertIn("PHASE2_SUBUNIT_CONTINUITY_BACKFILL", workflow)
        self.assertIn(
            "get('research_subunit_count',-1)) == 4",
            workflow,
        )

    def test_goes_probe_regenerates_dependent_climate_evidence(self):
        workflow = (
            ROOT / ".github/workflows/goes19-rrqpe-probe.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python scripts/build_phase2_climate_evidence.py", workflow)
        self.assertIn("python scripts/validate_phase2_climate_evidence.py", workflow)
        self.assertIn(
            "site/data/phase2/climate_evidence_normalized_v0_1.json",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
