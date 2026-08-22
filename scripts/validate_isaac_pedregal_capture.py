#!/usr/bin/env python3
"""Valida manifiestos manuales ISAAC Pedregal Koica v0.1.

No realiza scraping, no clasifica EVENT/NONE y no acepta observaciones científicas.
Sólo verifica integridad del original, estructura mínima, procedencia de campos y
guardas fail-closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys


SCHEMA_VERSION = "isaac-pedregal-manual-capture-v0.1"
EVIDENCE_SOURCES = {
    "TOOLTIP",
    "AXIS",
    "CHART_TITLE",
    "CHART_NOTE",
    "VISIBLE_FILTER",
    "OPERATOR_ANNOTATION",
    "INSTITUTIONAL_METADATA",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ManifestValidationError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestValidationError(message)


def _require_keys(obj: dict, keys: tuple[str, ...], scope: str) -> None:
    for key in keys:
        _require(key in obj, f"{scope}.{key}: required")


def _parse_iso8601(value: str, field: str) -> None:
    _require(isinstance(value, str) and value.strip(), f"{field}: non-empty string required")
    candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ManifestValidationError(f"{field}: invalid ISO-8601 timestamp") from exc
    _require(parsed.tzinfo is not None, f"{field}: timezone offset required")


def _validate_evidence(value, field: str) -> None:
    if value is None:
        return
    _require(isinstance(value, dict), f"{field}: object or null required")
    _require_keys(value, ("source", "detail"), field)
    _require(value["source"] in EVIDENCE_SOURCES, f"{field}.source: unsupported provenance")
    _require(isinstance(value["detail"], str) and value["detail"].strip(), f"{field}.detail: required")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    _require(len(header) >= 24 and header[:8] == PNG_SIGNATURE, "original: expected PNG")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    _require(width > 0 and height > 0, "original: invalid PNG dimensions")
    return width, height


def validate_manifest(manifest: dict, original_path: Path) -> dict:
    _require(isinstance(manifest, dict), "manifest: top-level object required")
    _require(manifest.get("schema_version") == SCHEMA_VERSION, "schema_version: unsupported version")
    _require_keys(
        manifest,
        ("capture", "source", "station", "observation", "filters", "quality", "export", "scientific_use"),
        "manifest",
    )

    capture = manifest["capture"]
    source = manifest["source"]
    station = manifest["station"]
    observation = manifest["observation"]
    quality = manifest["quality"]
    scientific = manifest["scientific_use"]

    for name, obj in (
        ("capture", capture),
        ("source", source),
        ("station", station),
        ("observation", observation),
        ("quality", quality),
        ("scientific_use", scientific),
    ):
        _require(isinstance(obj, dict), f"{name}: object required")

    _require_keys(
        capture,
        (
            "capture_session_id",
            "captured_at_utc",
            "captured_at_local",
            "capture_timezone",
            "operator",
            "reviewer",
            "original_filename",
            "mime_type",
            "file_size_bytes",
            "width_px",
            "height_px",
            "sha256",
        ),
        "capture",
    )
    _require(isinstance(capture["capture_session_id"], str) and capture["capture_session_id"].strip(),
             "capture.capture_session_id: required")
    _parse_iso8601(capture["captured_at_utc"], "capture.captured_at_utc")
    _parse_iso8601(capture["captured_at_local"], "capture.captured_at_local")
    _require(isinstance(capture["capture_timezone"], str) and capture["capture_timezone"].strip(),
             "capture.capture_timezone: required")
    _require(isinstance(capture["operator"], str) and capture["operator"].strip(),
             "capture.operator: required")
    _require(capture["reviewer"] is None or (isinstance(capture["reviewer"], str) and capture["reviewer"].strip()),
             "capture.reviewer: string or null required")
    _require(capture["mime_type"] == "image/png", "capture.mime_type: must be image/png")
    _require(isinstance(capture["sha256"], str) and SHA256_RE.fullmatch(capture["sha256"]) is not None,
             "capture.sha256: lowercase 64-char SHA-256 required")

    _require(original_path.is_file(), "original: file does not exist")
    actual_size = original_path.stat().st_size
    _require(capture["file_size_bytes"] == actual_size, "capture.file_size_bytes: does not match original")
    actual_width, actual_height = png_dimensions(original_path)
    _require(capture["width_px"] == actual_width, "capture.width_px: does not match original")
    _require(capture["height_px"] == actual_height, "capture.height_px: does not match original")
    actual_sha = sha256_file(original_path)
    _require(capture["sha256"] == actual_sha, "capture.sha256: does not match original")

    _require(source.get("institution") == "SENAMHI", "source.institution: must be SENAMHI")
    _require(source.get("platform") == "ISAAC", "source.platform: must be ISAAC")
    _require(isinstance(source.get("report_url"), str) and source["report_url"].strip(),
             "source.report_url: required")
    _require(isinstance(source.get("visual_title"), str) and source["visual_title"].strip(),
             "source.visual_title: required")

    _require(station.get("displayed_name") == "Pedregal Koica",
             "station.displayed_name: must be Pedregal Koica")
    _require(isinstance(station.get("selected"), bool), "station.selected: boolean required")
    _validate_evidence(station.get("selection_evidence"), "station.selection_evidence")
    if station["selected"]:
        _require(station.get("selection_evidence") is not None,
                 "station.selection_evidence: required when selected=true")

    for evidence_field in ("unit_evidence", "period_evidence"):
        _validate_evidence(observation.get(evidence_field), f"observation.{evidence_field}")

    value_raw = observation.get("value_raw")
    value_numeric = observation.get("value_numeric")
    if value_raw is None:
        _require(value_numeric is None, "observation.value_numeric: must be null when value_raw is null")
    else:
        _require(isinstance(value_raw, str) and value_raw.strip(), "observation.value_raw: non-empty string or null")
        _require(isinstance(value_numeric, (int, float)) and not isinstance(value_numeric, bool),
                 "observation.value_numeric: number required when value_raw is present")

    if observation.get("unit") is not None:
        _require(observation.get("unit_evidence") is not None,
                 "observation.unit_evidence: required when unit is present")
    if observation.get("period") is not None:
        _require(observation.get("period_evidence") is not None,
                 "observation.period_evidence: required when period is present")

    if observation.get("unit_evidence") is not None:
        evidence = observation["unit_evidence"]
        if evidence["source"] == "AXIS":
            _require("axis" in evidence["detail"].lower() or "eje" in evidence["detail"].lower(),
                     "observation.unit_evidence: AXIS provenance must describe the axis")

    _validate_evidence(quality.get("qc_evidence"), "quality.qc_evidence")
    _require(quality.get("completeness") in {"PARTIAL", "COMPLETE", "FAILED_OR_UNVERIFIABLE"},
             "quality.completeness: unsupported state")
    _require(isinstance(quality.get("ambiguities"), list), "quality.ambiguities: array required")

    qc_flag = quality.get("displayed_qc_flag")
    if qc_flag is not None:
        _require(qc_flag not in {"Normal", "Operativo", "Normal / Operativo"},
                 "quality.displayed_qc_flag: station Normal/Operativo is not observation QA/QC")
        _require(quality.get("qc_evidence") is not None,
                 "quality.qc_evidence: required when displayed_qc_flag is present")

    missing_indicator = quality.get("missing_data_indicator")
    if missing_indicator is not None:
        _require(value_raw is None and value_numeric is None,
                 "missing data must remain null; never encode missing as zero")

    guard_expectations = {
        "scientific_observation_accepted": False,
        "automatic_outcome_classification": False,
        "automatic_bias_correction": False,
        "bias_correction_applied": False,
        "threshold_changes": False,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
    }
    for field, expected in guard_expectations.items():
        _require(scientific.get(field) is expected, f"scientific_use.{field}: must be false")
    _require(scientific.get("outcome_label") is None, "scientific_use.outcome_label: must remain null in v0.1")
    _require(scientific.get("missing_data_rule") == "UNKNOWN_NOT_ZERO",
             "scientific_use.missing_data_rule: must be UNKNOWN_NOT_ZERO")
    _require(isinstance(scientific.get("rainfall_candidate"), bool),
             "scientific_use.rainfall_candidate: boolean required")

    if scientific["rainfall_candidate"]:
        _require(capture["reviewer"] is not None, "promotion request requires named reviewer")
        _require(station["selected"] is True, "promotion request requires station.selected=true")
        selection = station.get("selection_evidence")
        _require(selection is not None and selection.get("source") == "VISIBLE_FILTER",
                 "promotion request requires visible station-selection evidence")
        _require(observation.get("displayed_timestamp_raw") is not None,
                 "promotion request requires displayed timestamp")
        _require(observation.get("displayed_timezone") is not None,
                 "promotion request requires displayed timezone")
        _require(value_raw is not None and value_numeric is not None,
                 "promotion request requires rainfall value")
        _require(observation.get("unit") is not None and observation.get("unit_evidence") is not None,
                 "promotion request requires unit and provenance")
        _require(observation.get("period") is not None and observation.get("period_evidence") is not None,
                 "promotion request requires period and provenance")
        _require(observation.get("exact_window_semantics") is not None,
                 "promotion request requires exact window semantics")
        _require(quality.get("completeness") == "COMPLETE",
                 "promotion request requires completeness=COMPLETE")

    return {
        "valid": True,
        "schema_version": SCHEMA_VERSION,
        "original_sha256": actual_sha,
        "rainfall_candidate_requested": scientific["rainfall_candidate"],
        "scientific_observation_accepted": False,
        "outcome_label": None,
        "production_use": False,
        "missing_data_rule": "UNKNOWN_NOT_ZERO",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--original", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = validate_manifest(manifest, args.original)
    except (OSError, json.JSONDecodeError, ManifestValidationError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
