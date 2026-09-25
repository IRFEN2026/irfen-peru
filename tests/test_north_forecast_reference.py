import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "north_forecast_reference",
    ROOT / "scripts/build_north_forecast_reference.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sealed(row):
    row = copy.deepcopy(row)
    row["record_sha256"] = MODULE.record_sha256(row)
    return row


def ledger(records):
    return {
        **MODULE.GUARDS,
        "retention_mode": "APPEND_ONLY",
        "records": records,
    }


def forecast(**updates):
    row = {
        "record_id": "geos-cycle-a-window-1",
        "source_kind": "NASA_GEOS_CF_V2_TPREC",
        "model": "GEOS-CF",
        "model_version": "v2",
        "cycle_id": "cycle-a",
        "issue_time_utc": "2026-09-23T00:00:00Z",
        "issue_time_verified": True,
        "retrieved_at_utc": "2026-09-23T00:20:00Z",
        "valid_start_utc": "2026-09-23T06:00:00Z",
        "valid_end_utc": "2026-09-23T12:00:00Z",
        "duration_hours": 6,
        "accumulation_mm": 8.0,
        "units": "mm",
        "temporal_coverage_complete": True,
        "time_bounds_basis": "DOCUMENTED_PRODUCT_SPECIFICATION",
        "payload_sha256": "a" * 64,
        "spatial_support": {
            "support_id": "geos-cell-01",
            "support_kind": "GRID_CELL",
            "comparison_support_id": "cmp-piura-01",
            "sampling_method": "nearest_native_cell",
            "comparison_basis": "DOCUMENTED_NATIVE_CELL_TO_REFERENCE_SUPPORT",
            "interpolation_to_finer_resolution": False,
        },
    }
    row.update(updates)
    return sealed(row)


def observation(**updates):
    row = {
        "record_id": "imerg-early-window-1-r1",
        "source_kind": "IMERG_EARLY",
        "product_version": "V07B",
        "revision_id": "r1",
        "retrieved_at_utc": "2026-09-23T13:00:00Z",
        "published_at_utc": "2026-09-23T12:30:00Z",
        "valid_start_utc": "2026-09-23T06:00:00Z",
        "valid_end_utc": "2026-09-23T12:00:00Z",
        "duration_hours": 6,
        "accumulation_mm": 10.0,
        "units": "mm",
        "temporal_coverage_complete": True,
        "time_bounds_basis": "EXPLICIT_DATASET_BOUNDS",
        "payload_sha256": "b" * 64,
        "spatial_support": {
            "support_id": "imerg-common-01",
            "support_kind": "COMMON_GRID_AGGREGATE",
            "comparison_support_id": "cmp-piura-01",
            "sampling_method": "area_weighted_to_preregistered_common_support",
            "comparison_basis": "DOCUMENTED_NATIVE_CELL_TO_REFERENCE_SUPPORT",
            "interpolation_to_finer_resolution": False,
        },
    }
    row.update(updates)
    return sealed(row)


class NorthForecastReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(
            (ROOT / "config/phase2_north_rainfall_episode_20260923_v0_1.json").read_text(
                encoding="utf-8"
            )
        )

    def build(self, forecasts=None, observations=None, fpath="frozen/geos.json", opath="frozen/obs.json"):
        return MODULE.build_output(
            self.contract,
            ledger(forecasts if forecasts is not None else [forecast()]),
            ledger(observations if observations is not None else [observation()]),
            fpath,
            opath,
        )

    def test_contract_preserves_fail_closed_phase2_guards(self):
        MODULE.validate_contract(self.contract)
        for key, expected in MODULE.GUARDS.items():
            self.assertEqual(self.contract[key], expected)
        self.assertFalse(self.contract["protected_logic"]["v0_7_1_mutation_allowed"])
        self.assertFalse(self.contract["protected_logic"]["candidate_promotion_allowed"])

    def test_demo_latest_is_rejected_before_pairing(self):
        with self.assertRaisesRegex(MODULE.ValidationError, "latest.json"):
            self.build(fpath="site/data/latest.json")

    def test_demo_marker_is_rejected(self):
        bad = ledger([forecast()])
        bad["source"] = "DEMO historical"
        with self.assertRaisesRegex(MODULE.ValidationError, "DEMO"):
            MODULE.validate_forecasts(bad, "frozen/geos.json")

    def test_geos_half_hour_is_rejected(self):
        row = forecast(
            valid_end_utc="2026-09-23T06:30:00Z",
            duration_hours=0.5,
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "GEOS duration"):
            self.build(forecasts=[row], observations=[])

    def test_mm_per_hour_is_not_accepted_as_accumulated_mm(self):
        row = forecast(units="mm/h")
        with self.assertRaisesRegex(MODULE.ValidationError, "accumulated mm"):
            self.build(forecasts=[row], observations=[])

    def test_unverified_issue_time_never_becomes_prospective_from_retrieval(self):
        f = forecast(issue_time_utc=None, issue_time_verified=False)
        out = self.build(forecasts=[f])
        self.assertEqual(out["pair_count"], 1)
        self.assertEqual(out["prospective_pair_count"], 0)
        self.assertEqual(out["pairs"][0]["anticipation_status"], "ISSUE_TIME_UNVERIFIED")
        self.assertIsNone(out["pairs"][0]["lead_to_window_start_hours"])
        self.assertEqual(out["metrics_prospective_only"], [])

    def test_forecast_issued_after_window_start_is_not_prior_anticipation(self):
        f = forecast(issue_time_utc="2026-09-23T07:00:00Z")
        out = self.build(forecasts=[f])
        pair = out["pairs"][0]
        self.assertEqual(pair["anticipation_status"], "ISSUED_AFTER_WINDOW_START")
        self.assertEqual(pair["lead_to_window_start_hours"], -1.0)
        self.assertEqual(out["prospective_pair_count"], 0)

    def test_signed_absolute_and_percent_error_are_traceable(self):
        out = self.build()
        pair = out["pairs"][0]
        self.assertEqual(pair["forecast_mm"], 8.0)
        self.assertEqual(pair["observed_mm"], 10.0)
        self.assertEqual(pair["error_forecast_minus_observed_mm"], -2.0)
        self.assertEqual(pair["absolute_error_mm"], 2.0)
        self.assertEqual(pair["percent_error"], -20.0)
        self.assertEqual(pair["comparison_semantics"], "PRODUCT_DISCREPANCY_NOT_GROUND_TRUTH")
        self.assertEqual(out["metrics_prospective_only"][0]["bias_mm"], -2.0)

    def test_percent_error_is_not_applicable_near_zero(self):
        out = self.build(observations=[observation(accumulation_mm=0.05)])
        self.assertIsNone(out["pairs"][0]["percent_error"])

    def test_zero_observation_is_preserved_as_rainfall_not_activation_negative(self):
        out = self.build(observations=[observation(accumulation_mm=0.0)])
        self.assertEqual(out["pairs"][0]["observed_mm"], 0.0)
        self.assertIsNone(out["pairs"][0]["percent_error"])
        self.assertFalse(out["interpretation"]["rainfall_confirms_activation"])

    def test_homonym_or_different_support_does_not_pair(self):
        other = observation(
            spatial_support={
                "support_id": "other-cell",
                "support_kind": "COMMON_GRID_AGGREGATE",
                "comparison_support_id": "cmp-unrelated-rio-seco",
                "sampling_method": "area_weighted_to_preregistered_common_support",
                "comparison_basis": "DOCUMENTED_NATIVE_CELL_TO_REFERENCE_SUPPORT",
                "interpolation_to_finer_resolution": False,
            }
        )
        out = self.build(observations=[other])
        self.assertEqual(out["pair_count"], 0)

    def test_station_must_remain_point_reference(self):
        station = observation(
            source_kind="SENAMHI_STATION",
            station_is_basin_truth=False,
            spatial_support={
                "support_id": "station-x",
                "support_kind": "POLYGON",
                "comparison_support_id": "cmp-piura-01",
                "sampling_method": "station",
                "comparison_basis": "DOCUMENTED_NATIVE_CELL_TO_REFERENCE_SUPPORT",
                "interpolation_to_finer_resolution": False,
            },
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "station must remain point"):
            self.build(observations=[station])

    def test_station_cannot_claim_basin_truth(self):
        station = observation(
            source_kind="SENAMHI_STATION",
            station_is_basin_truth=True,
            spatial_support={
                "support_id": "station-x",
                "support_kind": "POINT_STATION",
                "comparison_support_id": "cmp-piura-01",
                "sampling_method": "station_point",
                "comparison_basis": "DOCUMENTED_NATIVE_CELL_TO_REFERENCE_SUPPORT",
                "interpolation_to_finer_resolution": False,
            },
        )
        with self.assertRaisesRegex(MODULE.ValidationError, "not basin truth"):
            self.build(observations=[station])

    def test_revisions_are_preserved_not_overwritten(self):
        r1 = observation()
        r2 = observation(
            record_id="imerg-early-window-1-r2",
            revision_id="r2",
            accumulation_mm=9.0,
            payload_sha256="c" * 64,
        )
        out = self.build(observations=[r1, r2])
        self.assertEqual(out["pair_count"], 2)
        self.assertEqual({p["reference_revision_id"] for p in out["pairs"]}, {"r1", "r2"})

    def test_conflicting_same_cycle_requery_fails_closed(self):
        f1 = forecast()
        f2 = forecast(record_id="geos-cycle-a-window-1-requery", accumulation_mm=9.0)
        with self.assertRaisesRegex(MODULE.ValidationError, "conflicting same-cycle requery"):
            self.build(forecasts=[f1, f2], observations=[])

    def test_record_hash_mutation_is_detected(self):
        f = forecast()
        f["accumulation_mm"] = 99.0
        with self.assertRaisesRegex(MODULE.ValidationError, "record_sha256"):
            self.build(forecasts=[f], observations=[])

    def test_comparison_basis_must_match(self):
        obs = observation()
        obs["spatial_support"]["comparison_basis"] = "DIFFERENT_BASIS"
        obs = sealed(obs)
        with self.assertRaisesRegex(MODULE.ValidationError, "comparison_basis"):
            self.build(observations=[obs])


if __name__ == "__main__":
    unittest.main()
