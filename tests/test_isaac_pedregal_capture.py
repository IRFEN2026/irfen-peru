import copy
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_isaac_pedregal_capture",
    ROOT / "scripts" / "validate_isaac_pedregal_capture.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_png(path: Path, width: int = 2, height: int = 3) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


def base_manifest(original: Path) -> dict:
    sha = hashlib.sha256(original.read_bytes()).hexdigest()
    return {
        "schema_version": "isaac-pedregal-manual-capture-v0.1",
        "capture": {
            "capture_session_id": "20260822T180000Z-test",
            "captured_at_utc": "2026-08-22T18:00:00+00:00",
            "captured_at_local": "2026-08-22T13:00:00-05:00",
            "capture_timezone": "America/Lima",
            "operator": "test-operator",
            "reviewer": None,
            "original_filename": original.name,
            "mime_type": "image/png",
            "file_size_bytes": original.stat().st_size,
            "width_px": 2,
            "height_px": 3,
            "sha256": sha,
        },
        "source": {
            "institution": "SENAMHI",
            "platform": "ISAAC",
            "report_url": "https://app.powerbi.com/view?r=test",
            "report_page": None,
            "visual_title": "Datos históricos de precipitación horaria",
        },
        "station": {
            "displayed_name": "Pedregal Koica",
            "displayed_code": None,
            "selected": False,
            "selection_evidence": {
                "source": "OPERATOR_ANNOTATION",
                "detail": "El operador declara haber seleccionado Pedregal Koica.",
            },
            "station_status": "Normal",
            "operational_status": "Operativo",
        },
        "observation": {
            "displayed_timestamp_raw": "01/04/2026 19:00:00",
            "displayed_timezone": None,
            "metric_label_raw": "Promedio de Precip",
            "value_raw": "0,43",
            "value_numeric": 0.43,
            "unit": "mm",
            "unit_evidence": {
                "source": "AXIS",
                "detail": "Eje vertical: Precipitación [mm]",
            },
            "period": "horario",
            "period_evidence": {
                "source": "CHART_TITLE",
                "detail": "Datos históricos de precipitación horaria",
            },
            "exact_window_semantics": None,
            "aggregation_scope": None,
        },
        "filters": {
            "station": "Pedregal Koica",
            "temporal_selector": "visible",
            "start_date": None,
            "end_date": None,
            "other_filters": None,
        },
        "quality": {
            "displayed_qc_flag": None,
            "qc_evidence": None,
            "missing_data_indicator": None,
            "completeness": "PARTIAL",
            "ambiguities": [
                "station selection not visually proven",
                "displayed timezone unknown",
                "exact hourly window semantics unknown",
            ],
        },
        "export": {
            "checked": True,
            "available": False,
            "check_method": "operator checked visual menu",
        },
        "scientific_use": {
            "rainfall_candidate": False,
            "scientific_observation_accepted": False,
            "outcome_label": None,
            "automatic_outcome_classification": False,
            "automatic_bias_correction": False,
            "bias_correction_applied": False,
            "threshold_changes": False,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "missing_data_rule": "UNKNOWN_NOT_ZERO",
        },
    }


class IsaacPedregalManualCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = Path(self.tmp.name) / "capture.png"
        make_png(self.original)
        self.manifest = base_manifest(self.original)

    def tearDown(self):
        self.tmp.cleanup()

    def test_partial_design_capture_is_valid_but_not_scientifically_accepted(self):
        result = MODULE.validate_manifest(self.manifest, self.original)
        self.assertTrue(result["valid"])
        self.assertFalse(result["rainfall_candidate_requested"])
        self.assertFalse(result["scientific_observation_accepted"])
        self.assertIsNone(result["outcome_label"])
        self.assertFalse(result["production_use"])

    def test_missing_data_is_never_encoded_as_zero(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["quality"]["missing_data_indicator"] = "MISSING_OR_UNREADABLE"
        manifest["observation"]["value_raw"] = "0"
        manifest["observation"]["value_numeric"] = 0.0
        with self.assertRaisesRegex(MODULE.ManifestValidationError, "never encode missing as zero"):
            MODULE.validate_manifest(manifest, self.original)

        manifest["observation"]["value_raw"] = None
        manifest["observation"]["value_numeric"] = None
        manifest["observation"]["unit"] = None
        manifest["observation"]["unit_evidence"] = None
        manifest["observation"]["period"] = None
        manifest["observation"]["period_evidence"] = None
        result = MODULE.validate_manifest(manifest, self.original)
        self.assertEqual(result["missing_data_rule"], "UNKNOWN_NOT_ZERO")

    def test_normal_operativo_cannot_be_observation_qc(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["quality"]["displayed_qc_flag"] = "Normal"
        manifest["quality"]["qc_evidence"] = {
            "source": "VISIBLE_FILTER",
            "detail": "Estado de estación visible",
        }
        with self.assertRaisesRegex(MODULE.ManifestValidationError, "not observation QA/QC"):
            MODULE.validate_manifest(manifest, self.original)

    def test_capture_cannot_generate_event_or_none(self):
        for label in ("EVENT", "NONE", "UNCERTAIN"):
            manifest = copy.deepcopy(self.manifest)
            manifest["scientific_use"]["outcome_label"] = label
            with self.assertRaisesRegex(MODULE.ManifestValidationError, "must remain null"):
                MODULE.validate_manifest(manifest, self.original)

    def test_scientific_promotion_requires_visible_station_selection(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["scientific_use"]["rainfall_candidate"] = True
        manifest["capture"]["reviewer"] = "second-reviewer"
        manifest["station"]["selected"] = True
        manifest["observation"]["displayed_timezone"] = "America/Lima"
        manifest["observation"]["exact_window_semantics"] = "hour ending at displayed timestamp"
        manifest["quality"]["completeness"] = "COMPLETE"
        with self.assertRaisesRegex(MODULE.ManifestValidationError, "visible station-selection evidence"):
            MODULE.validate_manifest(manifest, self.original)

        manifest["station"]["selection_evidence"] = {
            "source": "VISIBLE_FILTER",
            "detail": "Pedregal Koica resaltada en filtro visible",
        }
        result = MODULE.validate_manifest(manifest, self.original)
        self.assertTrue(result["rainfall_candidate_requested"])
        self.assertFalse(result["scientific_observation_accepted"])

    def test_axis_inferred_unit_must_be_marked_as_axis_evidence(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["observation"]["unit_evidence"] = {
            "source": "AXIS",
            "detail": "Tooltip sin unidad",
        }
        with self.assertRaisesRegex(MODULE.ManifestValidationError, "must describe the axis"):
            MODULE.validate_manifest(manifest, self.original)

        manifest["observation"]["unit_evidence"] = {
            "source": "AXIS",
            "detail": "Eje vertical: Precipitación [mm]",
        }
        MODULE.validate_manifest(manifest, self.original)

    def test_unknown_window_semantics_remains_null_for_partial_capture(self):
        self.assertIsNone(self.manifest["observation"]["exact_window_semantics"])
        result = MODULE.validate_manifest(self.manifest, self.original)
        self.assertTrue(result["valid"])

    def test_bias_correction_and_threshold_changes_are_fail_closed(self):
        for field in ("automatic_bias_correction", "bias_correction_applied", "threshold_changes"):
            manifest = copy.deepcopy(self.manifest)
            manifest["scientific_use"][field] = True
            with self.assertRaisesRegex(MODULE.ManifestValidationError, f"{field}: must be false"):
                MODULE.validate_manifest(manifest, self.original)

    def test_sha256_must_match_original(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["capture"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(MODULE.ManifestValidationError, "does not match original"):
            MODULE.validate_manifest(manifest, self.original)


if __name__ == "__main__":
    unittest.main()
