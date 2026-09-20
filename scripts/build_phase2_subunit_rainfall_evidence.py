#!/usr/bin/env python3
"""Build consolidated Phase-2 subunit rainfall evidence from IMERG Early + Late.

RESEARCH_ONLY / TEST_ONLY. The output is observational evidence only and
contains no activation, risk, threshold, or candidate-wide inference.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from phase2_subunit_sampling import load_research_subunit_targets

ROOT = Path(__file__).resolve().parents[1]
EARLY_ARCHIVE = ROOT / "site/data/calibration/imerg_early_live_archive.json"
LATE = ROOT / "site/data/phase2/subunit_imerg_late_v0_1.json"
SPATIAL = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
OUT = ROOT / "site/data/phase2/subunit_rainfall_evidence_v0_1.json"

EARLY_WINDOWS = ("1h", "3h", "6h", "12h", "24h")
LATE_WINDOWS = ("24h", "72h", "7d")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def optional_json(path: Path):
    try:
        return load_json(path)
    except Exception:
        return {}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def normalize_early_window(raw):
    raw = raw or {}
    available = (
        raw.get("available") is True
        and raw.get("continuous") is True
        and raw.get("accum_mm") is not None
    )
    return {
        "evidence_status": (
            "OBSERVED_NEAR_REAL_TIME" if available else "INSUFFICIENT_EVIDENCE"
        ),
        "available": available,
        "continuous": bool(raw.get("continuous") is True),
        "accum_mm": float(raw["accum_mm"]) if available else None,
        "required_samples": raw.get("required_samples"),
        "available_samples": raw.get("available_samples"),
        "start_utc": raw.get("start_utc") if available else None,
        "end_utc": raw.get("end_utc") if available else None,
        "source_role": "IMERG_EARLY_HALF_HOURLY_OBSERVATION",
    }


def normalize_late_window(raw):
    raw = raw or {}
    available = raw.get("available") is True and raw.get("accum_mm") is not None
    return {
        "evidence_status": (
            "OBSERVED_DAILY_SATELLITE" if available else "INSUFFICIENT_EVIDENCE"
        ),
        "available": available,
        "accum_mm": float(raw["accum_mm"]) if available else None,
        "days_required": raw.get("days_required"),
        "days_available": raw.get("days_available"),
        "start_date": raw.get("start_date") if available else None,
        "end_date": raw.get("end_date") if available else None,
        "source_role": "IMERG_LATE_DAILY_OBSERVATION",
    }


def build():
    targets = load_research_subunit_targets()
    spatial = load_json(SPATIAL)
    early = optional_json(EARLY_ARCHIVE)
    late = optional_json(LATE)

    if (spatial.get("summary") or {}).get("research_subunit_contract_count") != len(targets):
        raise ValueError("spatial subunit contract count no longer matches resolved targets")
    if (spatial.get("summary") or {}).get("operational_spatial_contract_count") != 0:
        raise ValueError("operational spatial contracts must remain zero")

    early_map = early.get("rolling_by_target") or {}
    late_map = {
        row.get("target_id"): row
        for row in late.get("targets") or []
        if row.get("target_id")
    }

    rows = []
    for target in targets:
        target_id = target["id"]
        early_windows = {
            window: normalize_early_window(
                (early_map.get(target_id) or {}).get(window)
            )
            for window in EARLY_WINDOWS
        }
        late_row = late_map.get(target_id) or {}
        late_windows = {
            window: normalize_late_window(
                (late_row.get("windows") or {}).get(window)
            )
            for window in LATE_WINDOWS
        }
        rows.append({
            "target_id": target_id,
            "candidate_id": target["candidate_id"],
            "subunit_id": target["subunit_id"],
            "geometry_path": target["geometry_path"],
            "geometry_sha256": target["geometry_sha256"],
            "declared_area_km2": target["declared_area_km2"],
            "deployment_status": "RESEARCH_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "counts_as_candidate_wide_rainfall": False,
            "counts_as_operational_evidence": False,
            "near_real_time_imerg_early": {
                "archive_updated_at": early.get("updated_at"),
                "source": early.get("source"),
                "windows": early_windows,
            },
            "daily_imerg_late": {
                "artifact_generated_at": late.get("generated_at"),
                "latest_observation_date": late.get("latest_observation_date"),
                "source": late.get("source"),
                "status": late.get("status"),
                "windows": late_windows,
            },
        })

    summary = {
        "research_subunit_count": len(rows),
        "early_targets_with_1h": sum(
            row["near_real_time_imerg_early"]["windows"]["1h"]["available"]
            for row in rows
        ),
        "early_targets_with_3h": sum(
            row["near_real_time_imerg_early"]["windows"]["3h"]["available"]
            for row in rows
        ),
        "early_targets_with_6h": sum(
            row["near_real_time_imerg_early"]["windows"]["6h"]["available"]
            for row in rows
        ),
        "early_targets_with_12h": sum(
            row["near_real_time_imerg_early"]["windows"]["12h"]["available"]
            for row in rows
        ),
        "early_targets_with_24h": sum(
            row["near_real_time_imerg_early"]["windows"]["24h"]["available"]
            for row in rows
        ),
        "late_targets_with_24h": sum(
            row["daily_imerg_late"]["windows"]["24h"]["available"]
            for row in rows
        ),
        "late_targets_with_72h": sum(
            row["daily_imerg_late"]["windows"]["72h"]["available"]
            for row in rows
        ),
        "late_targets_with_7d": sum(
            row["daily_imerg_late"]["windows"]["7d"]["available"]
            for row in rows
        ),
        "candidate_wide_rainfall_outputs": 0,
        "operational_activations": 0,
        "thresholds_created": 0,
    }

    return {
        "version": "phase2-subunit-rainfall-evidence-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "decision_thresholds": None,
        "interpretation": (
            "Observed satellite rainfall over Claude-F research subunits only; "
            "not candidate-wide rainfall and not activation/risk evidence."
        ),
        "guardrails": {
            "subunit_rainfall_is_not_parent_candidate_rainfall": True,
            "rainfall_observation_is_not_activation": True,
            "rainfall_observation_is_not_risk_classification": True,
            "missing_data_is_unknown_never_zero": True,
            "no_threshold_inference": True,
            "no_cross_candidate_transfer": True,
            "early_and_late_sources_remain_separate": True,
        },
        "targets": rows,
        "summary": summary,
    }


def generate(write=True):
    result = build()
    if write:
        write_json(OUT, result)
    return result


def main():
    result = generate(write=True)
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
