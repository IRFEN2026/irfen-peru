"""Fail-closed tests for IRFEN's coast-wide closeout and observational ledger."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from scripts.v09_coast_closeout import (
    closeout, evaluate_forecasts, inspect_geometry, inspect_rain,
    parse_time, stage_latest_derived_observations, utc_text,
)

START = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)


def fixture(n=150):
    return {
        "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
        "activation_gate": "BLOCKED", "production_use": False,
        "public_alerting": False, "notifications_enabled": False,
        "map_publishable": False,
        "source": {"product": "GPM_3IMERGHHE", "version": "07"},
        "geometry_sha256": "a" * 64,
        "targets": [
            {"checkpoint_id": "TUM-R-TUMBES-MEDIO"},
            {"checkpoint_id": "TAC-R-CAPLINA-BAJO"},
        ],
        "granules": [
            {
                "time_utc": utc_text(START + timedelta(minutes=30*i)),
                "retrieved_at_utc": utc_text(START + timedelta(minutes=30*i, hours=5)),
                "granule": "synthetic-granule",
                "rate_mm_hr": [1.2, 0.0],
                "covered_pct": [100.0, 100.0],
            }
            for i in range(n)
        ],
        "status": {"written_at_utc": utc_text(START + timedelta(hours=80))},
    }


class CoastCloseoutTests(unittest.TestCase):
    def test_all_horizons_on_exact_half_hourly_samples(self):
        d = fixture()
        asof = START + timedelta(hours=81)
        report = inspect_rain(d, asof)
        self.assertEqual(report["n_missing_halfhours"], 0)
        self.assertEqual(report["catchments_by_department"]["Tumbes"], 1)
        self.assertEqual(report["catchments_by_department"]["Tacna"], 1)
        self.assertEqual(len(report["catchments_by_department"]), 11)
        for window in report["windows_ending_at_latest"].values():
            self.assertTrue(window["continuous"])
            self.assertEqual(window["eligible_catchments"], 2)

    def test_gap_is_not_a_zero_and_invalidates_all_current_windows(self):
        d = fixture()
        # Removing only one of the last two half-hours leaves a one-hour jump.
        d["granules"].pop(-2)
        r = inspect_rain(d, START + timedelta(hours=81))
        self.assertEqual(r["n_missing_halfhours"], 1)
        for window in r["windows_ending_at_latest"].values():
            self.assertFalse(window["continuous"])
            self.assertEqual(window["eligible_catchments"], 0)

    def test_bad_input_rejected(self):
        d = fixture()
        d["granules"][-1]["rate_mm_hr"][0] = -3
        with self.assertRaises(ValueError):
            inspect_rain(d, START + timedelta(hours=81))
        d = fixture()
        d["granules"][-1]["covered_pct"][0] = float("nan")
        with self.assertRaises(ValueError):
            inspect_rain(d, START + timedelta(hours=81))
        d = fixture()
        d["public_alerting"] = True
        with self.assertRaises(ValueError):
            inspect_rain(d, START + timedelta(hours=81))
        d = fixture()
        d["granules"][-1]["time_utc"] = "2026-11-04T02:15:00Z"
        with self.assertRaises(ValueError):
            inspect_rain(d, START + timedelta(hours=81))

    def test_stale_archive_no_longer_current_even_if_complete(self):
        d = fixture()
        r = inspect_rain(d, START + timedelta(days=4))
        self.assertFalse(r["fresh_under_12h_research_policy"])
        self.assertTrue(r["windows_ending_at_latest"]["72h"]["continuous"])

    def test_low_spatial_coverage_is_unknown_not_zero(self):
        d = fixture()
        d["granules"][-1]["covered_pct"][1] = 0
        r = inspect_rain(d, START + timedelta(hours=81))
        self.assertEqual(r["windows_ending_at_latest"]["1h"]["eligible_catchments"], 1)

    def test_stages_actual_derived_snapshots_without_backdating(self):
        d = fixture()
        asof = START + timedelta(hours=81)
        with tempfile.TemporaryDirectory() as td:
            r = stage_latest_derived_observations(d, Path(td), asof)
            self.assertEqual(r["derived_snapshots_created"], 2)
            envelopes = [json.loads(p.read_text()) for p in Path(td).rglob("*.json")]
            self.assertEqual(len(envelopes), 2)
            for item in envelopes:
                self.assertEqual(item["ingest_time"], utc_text(asof))
                self.assertEqual(item["observation"]["published_at"], None)
                self.assertEqual(item["observation"]["qc"], "UNVERIFIED")
                self.assertFalse(item["eligible_for_prospective_replay"])
                self.assertEqual(item["mode"], "RESEARCH_ONLY")
            again = stage_latest_derived_observations(d, Path(td), asof)
            self.assertEqual(again["derived_snapshots_created"], 0)

    def test_missing_retrieval_time_never_infers_publication(self):
        d = fixture()
        d["granules"][-1].pop("retrieved_at_utc")
        with tempfile.TemporaryDirectory() as td:
            stage_latest_derived_observations(d, Path(td), START + timedelta(hours=81))
            for path in Path(td).rglob("*.json"):
                env = json.loads(path.read_text())
                self.assertIsNone(env["observation"]["available_at"])
                self.assertFalse(env["eligible_for_prospective_replay"])

    def test_forecast_truth_causality_and_baseline_require_independent_data(self):
        issue = START + timedelta(hours=2)
        r = {
            "horizon_hours": 3,
            "issue_time": utc_text(issue),
            "valid_time": utc_text(issue + timedelta(hours=3)),
            "last_input_available_at": utc_text(issue - timedelta(minutes=10)),
            "observed_at": utc_text(issue + timedelta(hours=3)),
            "observed_available_at": utc_text(issue + timedelta(hours=4)),
            "independent_observation": True, "qc": "VERIFIED",
            "actual_flow": 100.0, "model_flow": 90.0, "baseline_flow": 101.0,
        }
        x = evaluate_forecasts([r])
        self.assertEqual(x["3h"]["accepted_pairs"], 1)
        self.assertEqual(x["3h"]["status"], "NO_EVALUABLE_INSUFFICIENT_INDEPENDENT_SUBDAILY_TRUTH")
        r["last_input_available_at"] = utc_text(issue + timedelta(hours=2))
        x = evaluate_forecasts([r])
        self.assertEqual(x["3h"]["rejected_pairs"], 1)
        self.assertEqual(x["3h"]["accepted_pairs"], 0)

    def test_thirty_synthetic_pairs_do_not_create_an_operational_claim(self):
        rows = []
        for i in range(30):
            issue = START + timedelta(hours=i)
            rows.append({
                "horizon_hours": 1, "issue_time": utc_text(issue),
                "valid_time": utc_text(issue + timedelta(hours=1)),
                "last_input_available_at": utc_text(issue),
                "observed_at": utc_text(issue + timedelta(hours=1)),
                "observed_available_at": utc_text(issue + timedelta(hours=2)),
                "independent_observation": True, "qc": "VERIFIED",
                "actual_flow": 10, "model_flow": 9, "baseline_flow": 8,
            })
        result = evaluate_forecasts(rows)["1h"]
        self.assertEqual(result["accepted_pairs"], 30)
        self.assertEqual(result["status"], "DESCRIPTIVE_RESEARCH_ONLY_NOT_VALIDATED")
        self.assertFalse(result["predictive_skill_demonstrated"])

    def test_geography_variants_remain_under_review(self):
        geo = {"checkpoints": [
            {"id": "LAM-R-LA_LECHE-ALTO", "type": "rio",
             "q3_contributing_area": {
                 "status": "APORTACION_DELIMITADA_EXPERIMENTAL",
                 "hydrorivers_ratio": .81}},
            {"id": "ICA-R-SAN_JUAN-BAJO", "type": "rio",
             "q3_contributing_area": {"status": "NO_VERIFICABLE"}},
            {"id": "TUM-Q-TEST", "type": "quebrada",
             "q3_contributing_area": {"status": "NO_VERIFICABLE"}},
        ]}
        x = inspect_geometry(geo)
        self.assertEqual(x["areas_different_over_1pct"], 1)
        self.assertEqual(len(x["high_priority_differences_over_10pct"]), 1)
        self.assertEqual(x["rivers_without_evaluable_catchment"], ["ICA-R-SAN_JUAN-BAJO"])
        self.assertEqual(x["verified_hydrologically"], 0)

    def test_closeout_does_not_claim_forecast_skill(self):
        x = closeout(fixture(), None, START + timedelta(hours=81))
        self.assertEqual(x["activation_gate"], "BLOCKED")
        self.assertFalse(x["public_alerting"])
        self.assertIn("PREDICTIVE_CLOSURE_REJECTED", x["closure"])
        self.assertTrue(all(not item["predictive_skill_demonstrated"]
                            for item in x["prediction_by_horizon"].values()))


if __name__ == "__main__":
    unittest.main()
