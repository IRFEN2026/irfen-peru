"""Tests for Claude E — Phase-2 Climate Evidence and Normalization Layer."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "phase2_climate_evidence_under_test",
    ROOT / "scripts/build_phase2_climate_evidence.py",
)
ce = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(ce)


class EventWindowTests(unittest.TestCase):
    def test_complete_event_window_normalizes(self):
        raw = {"continuous": True, "accum_mm": 12.5, "coverage_pct": 100.0}
        row = ce.normalize_event_window("3h", raw, "evt")
        self.assertTrue(row["complete"])
        self.assertEqual(row["accumulated_mm"], 12.5)
        self.assertEqual(row["evidence_status"], "HISTORICAL_EVIDENCE_ONLY")

    def test_partial_event_window_never_normalizes_partial_sum(self):
        raw = {
            "continuous": False,
            "accum_mm": None,
            "partial_accum_mm_non_decisional": 7.2,
            "coverage_pct": 83.3,
        }
        row = ce.normalize_event_window("6h", raw, "evt")
        self.assertFalse(row["complete"])
        self.assertIsNone(row["accumulated_mm"])
        self.assertEqual(row["evidence_status"], "INSUFFICIENT_EVIDENCE")

    def test_negative_precipitation_rejected(self):
        with self.assertRaises(ce.EvidenceNormalizationError):
            ce.normalize_event_window(
                "24h",
                {"continuous": True, "accum_mm": -1},
                "evt",
            )


class DailyAccumulationTests(unittest.TestCase):
    def test_complete_consecutive_daily_series(self):
        rows = [
            {"date": f"2026-09-{day:02d}", "rain_mm": float(day)}
            for day in range(13, 20)
        ]
        result = ce.complete_daily_accumulations(rows, "2026-09-19")
        self.assertEqual(result["24h"], 19.0)
        self.assertEqual(result["72h"], 19.0 + 18.0 + 17.0)
        self.assertEqual(result["7d"], sum(float(x) for x in range(13, 20)))

    def test_missing_day_fails_closed(self):
        rows = [
            {"date": "2026-09-19", "rain_mm": 10.0},
            {"date": "2026-09-17", "rain_mm": 5.0},
        ]
        result = ce.complete_daily_accumulations(rows, "2026-09-19")
        self.assertEqual(result["24h"], 10.0)
        self.assertIsNone(result["72h"])
        self.assertIsNone(result["7d"])

    def test_duplicate_day_fails_closed_for_affected_windows(self):
        rows = [
            {"date": "2026-09-19", "rain_mm": 10.0},
            {"date": "2026-09-19", "rain_mm": 11.0},
        ]
        result = ce.complete_daily_accumulations(rows, "2026-09-19")
        self.assertIsNone(result["24h"])


class GeneratedLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layer = ce.generate(write=False)
        cls.inventory = json.loads(
            (ROOT / "config/phase2_candidate_inventory_v0_2.json").read_text(
                encoding="utf-8"
            )
        )

    def test_exactly_18_candidate_records(self):
        self.assertEqual(len(self.layer["candidate_evidence"]), 18)
        self.assertEqual(self.layer["summary"]["candidate_count"], 18)

    def test_candidate_ids_match_inventory(self):
        expected = {row["candidate_id"] for row in self.inventory["candidates"]}
        actual = {row["candidate_id"] for row in self.layer["candidate_evidence"]}
        self.assertEqual(actual, expected)

    def test_no_current_candidate_rainfall_is_fabricated(self):
        for record in self.layer["candidate_evidence"]:
            self.assertEqual(
                record["assessment_context"]["status"],
                "NO_ASSESSMENT_CONTEXT",
            )
            for window in record["rainfall_windows"].values():
                self.assertIsNone(window["accumulated_mm"])
                self.assertEqual(
                    window["evidence_status"],
                    "INSUFFICIENT_EVIDENCE",
                )

    def test_antecedent_state_thresholds_remain_unresolved(self):
        for record in self.layer["candidate_evidence"]:
            antecedent = record["antecedent_accumulations"]
            self.assertEqual(antecedent["state"], "UNKNOWN")
            self.assertEqual(
                antecedent["state_methodology_status"],
                "UNRESOLVED_THRESHOLDS",
            )

    def test_no_candidate_climatology_is_invented(self):
        for record in self.layer["candidate_evidence"]:
            climate = record["climatology"]
            self.assertIsNone(climate["percentile"])
            self.assertIsNone(climate["anomaly_mm"])
            self.assertIsNone(climate["baseline_ref"])

    def test_source_contracts_derived_from_current_inputs(self):
        registry = {
            row["source_id"]: row
            for row in self.layer["source_registry"]
        }
        event = json.loads(
            (ROOT / "site/data/phase2/event_reanalysis.json").read_text(
                encoding="utf-8"
            )
        )
        imerg = json.loads(
            (
                ROOT
                / "site/data/forecast/imerg_verification_history.json"
            ).read_text(encoding="utf-8")
        )
        goes = json.loads(
            (
                ROOT
                / "site/data/calibration/goes19_rrqpe_archive.json"
            ).read_text(encoding="utf-8")
        )
        geos = json.loads(
            (
                ROOT
                / "site/data/forecast/historical_daily.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            registry["IMERG_EARLY_PHASE2_EVENT_REANALYSIS"]["record_count"],
            len(event.get("items") or []),
        )
        self.assertEqual(
            registry["IMERG_LATE_V08_SCIENTIFIC_HISTORY"]["record_count"],
            len(imerg.get("observations") or []),
        )
        self.assertEqual(
            registry["GOES19_RRQPE_AVAILABILITY_ARCHIVE"]["record_count"],
            len(goes.get("records") or []),
        )
        self.assertEqual(
            registry["GEOS_CF_V08_HISTORICAL_DAILY"]["record_count"],
            len(geos.get("records") or []),
        )

    def test_imerg_late_v08_never_silently_transfers(self):
        registry = {
            row["source_id"]: row
            for row in self.layer["source_registry"]
        }
        row = registry["IMERG_LATE_V08_SCIENTIFIC_HISTORY"]
        self.assertEqual(
            row["phase2_candidate_use"],
            "FORBIDDEN_WITHOUT_NEW_EXACT_SPATIAL_CONTRACT",
        )
        self.assertFalse(row["cross_zone_transfer_allowed"])

    def test_goes_availability_is_not_precipitation(self):
        registry = {
            row["source_id"]: row
            for row in self.layer["source_registry"]
        }
        row = registry["GOES19_RRQPE_AVAILABILITY_ARCHIVE"]
        self.assertEqual(
            row["source_kind"],
            "SOURCE_AVAILABILITY_METADATA",
        )
        self.assertFalse(row["precipitation_values_archived"])
        self.assertEqual(row["supports_windows"], [])

    def test_geos_remains_forecast(self):
        registry = {
            row["source_id"]: row
            for row in self.layer["source_registry"]
        }
        row = registry["GEOS_CF_V08_HISTORICAL_DAILY"]
        self.assertEqual(row["source_kind"], "FORECAST")
        self.assertFalse(row["forecast_as_observation"])

    def test_event_linkage_is_exact_only(self):
        valid_ids = {
            row["candidate_id"]
            for row in self.inventory["candidates"]
        }
        for event in self.layer["phase2_event_evidence"]:
            if event["target_zone_id"] is not None:
                self.assertIn(event["target_zone_id"], valid_ids)
                self.assertEqual(
                    event["linkage_status"],
                    "EXACT_REGISTERED_PHASE2_CANDIDATE",
                )
            else:
                self.assertEqual(
                    event["linkage_status"],
                    "UNLINKED_TO_REGISTERED_PHASE2_CANDIDATE",
                )

    def test_no_classification_outputs_created(self):
        self.assertEqual(
            self.layer["summary"]["classification_outputs_created"],
            0,
        )
        self.assertEqual(
            self.layer["summary"]["operational_activations"],
            0,
        )
        text = json.dumps(self.layer)
        self.assertNotIn('"physical_plausibility_assessment"', text)
        self.assertNotIn('"physical_response_plausibility_score"', text)
        self.assertNotIn('"promotion_gate_met"', text)

    def test_claude_d_remains_not_calibrated(self):
        matrix = json.loads(
            (
                ROOT
                / "site/data/phase2/climate_conditioned_activation_matrix_v0_1.json"
            ).read_text(encoding="utf-8")
        )
        for record in matrix["records"]:
            assessment = record["physical_plausibility_assessment"]
            self.assertEqual(
                assessment["classification_method_status"],
                "NOT_YET_CALIBRATED",
            )
            self.assertEqual(
                assessment["category"],
                "INSUFFICIENT_EVIDENCE",
            )
            self.assertIsNone(
                assessment["physical_response_plausibility_score"]
            )

    def test_deterministic_generation(self):
        first = ce.generate(write=False)
        second = ce.generate(write=False)
        first.pop("generated_at", None)
        second.pop("generated_at", None)
        self.assertEqual(first, second)


class SchemaAndValidatorTests(unittest.TestCase):
    def test_schema_conformance(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads(
            (
                ROOT
                / "config/phase2_climate_evidence_normalization.schema.json"
            ).read_text(encoding="utf-8")
        )
        jsonschema.validate(ce.generate(write=False), schema)

    def test_validator_passes(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/validate_phase2_climate_evidence.py"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
