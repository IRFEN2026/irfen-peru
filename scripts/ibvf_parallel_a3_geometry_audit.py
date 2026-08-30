#!/usr/bin/env python3
"""Audit frozen geometry semantics before parallel A3 basin weighting.

RESEARCH_ONLY / TEST_ONLY. This script reads geometry metadata only. It never
reads precipitation, territorial outcomes, event dates, risk, alerts, or
case/control labels. Multiple alternative candidates are never unioned into a
canonical basin and are never chosen using A3 magnitudes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACKS = ("shingolay", "pedregal", "huaycoloro", "san_ildefonso")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(raw)


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def guard(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def geometry_file(repo: Path, rel: str) -> Path:
    return repo / (rel if rel.startswith("site/") else f"site/{rel}")


def selected_features(repo: Path, case: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    path = geometry_file(repo, str(case["geometry_path"]))
    raw = load_json(path)
    feats = raw.get("features", []) if raw.get("type") == "FeatureCollection" else [raw]
    sel = case.get("geometry_selector") or {}
    prop = sel.get("property")
    val = sel.get("value")
    if prop:
        feats = [f for f in feats if (f.get("properties") or {}).get(prop) == val]
    return path, [f for f in feats if f.get("geometry")]


def feature_id(f: dict[str, Any]) -> str:
    p = f.get("properties") or {}
    return str(p.get("id") or p.get("unit_id") or p.get("name") or canonical_sha(f)[:16])


def feature_record(f: dict[str, Any]) -> dict[str, Any]:
    p = f.get("properties") or {}
    return {
        "feature_id": feature_id(f),
        "geometry_type": (f.get("geometry") or {}).get("type"),
        "candidate_status": p.get("candidate_status"),
        "production_use": p.get("production_use"),
        "production_ready": p.get("production_ready"),
        "official_outlet_validated": p.get("official_outlet_validated"),
        "official_area_validated": p.get("official_area_validated"),
        "delineated_area_km2": p.get("delineated_area_km2"),
        "accumulation_area_approx_km2": p.get("accumulation_area_approx_km2"),
        "canonical_feature_sha256": canonical_sha(f),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--manifest", type=Path, default=Path("site/data/validation/independent_basin_validation_map.json"))
    ap.add_argument("--semantics-contract", type=Path, default=Path("site/data/validation/ibvf_parallel_a3_geometry_semantics_contract.json"))
    ap.add_argument("--a3-contract", type=Path, default=Path("site/data/validation/ibvf_parallel_a3_opendap_contract.json"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo_root.resolve()

    manifest = load_json(repo / args.manifest)
    semantics = load_json(repo / args.semantics_contract)
    a3 = load_json(repo / args.a3_contract)
    guard(manifest)
    guard(semantics)
    guard(a3)
    assert semantics["tracks"] == list(TRACKS)
    assert a3["tracks"] == list(TRACKS)
    assert a3["expected_track_day_rows"] == 11628

    by_unit = {c.get("unit_id"): c for c in manifest.get("cases", [])}
    tracks: list[dict[str, Any]] = []
    for unit in TRACKS:
        case = by_unit.get(unit)
        if not case:
            raise AssertionError(f"missing manifest case for {unit}")
        path, feats = selected_features(repo, case)
        ids = sorted(feature_id(f) for f in feats)
        records = sorted((feature_record(f) for f in feats), key=lambda x: x["feature_id"])
        if len(feats) == 1:
            gate = "PASS_SINGLE_SELECTED_FEATURE_CANONICAL_WEIGHTING_ALLOWED"
            canonical_allowed = True
        elif len(feats) > 1:
            gate = "BLOCKED_CANONICAL_WEIGHTING_MULTIPLE_ALTERNATIVE_CANDIDATES"
            canonical_allowed = False
        else:
            gate = "BLOCKED_NO_SELECTED_GEOMETRY"
            canonical_allowed = False
        tracks.append({
            "unit_id": unit,
            "geometry_path": str(path.relative_to(repo)),
            "geometry_file_sha256": sha256_bytes(path.read_bytes()),
            "geometry_selector": case.get("geometry_selector"),
            "selected_feature_count": len(feats),
            "selected_feature_ids": ids,
            "selected_features_canonical_sha256": canonical_sha(records),
            "canonical_track_weighting_allowed": canonical_allowed,
            "gate": gate,
            "features": records,
        })

    p = next(x for x in tracks if x["unit_id"] == "pedregal")
    expected = semantics["pedregal_specific_freeze"]["expected_alternative_candidate_ids"]
    assert p["selected_feature_count"] == semantics["pedregal_specific_freeze"]["expected_candidate_count"]
    assert p["selected_feature_ids"] == sorted(expected)
    assert p["canonical_track_weighting_allowed"] is False
    for f in p["features"]:
        assert f["candidate_status"] == "REVIEW_ONLY"
        assert f["production_use"] is False
        assert f["production_ready"] is False
        assert f["official_outlet_validated"] is False
        assert f["official_area_validated"] is False

    for unit in ("shingolay", "huaycoloro", "san_ildefonso"):
        t = next(x for x in tracks if x["unit_id"] == unit)
        assert t["selected_feature_count"] == 1, (unit, t["selected_feature_count"])
        assert t["canonical_track_weighting_allowed"] is True

    report = {
        "schema_version": "irfen-ibvf-parallel-a3-geometry-audit-v0.1",
        "generated_at": utc_now(),
        "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "precipitation_values_read": False,
        "territorial_outcome_fields_read": False,
        "window_selection_performed": False,
        "meteorological_ranking_performed": False,
        "case_control_assignment_performed": False,
        "union_of_alternative_candidates_used_for_canonical_weighting": False,
        "expected_canonical_track_day_rows": 11628,
        "tracks": tracks,
        "summary": {
            "single_geometry_tracks_ready_for_canonical_a3": 3,
            "multiple_alternative_geometry_tracks": 1,
            "pedregal_track_level_status": "UNKNOWN_GEOMETRY_UNRESOLVED",
            "pedregal_candidate_sidecar_allowed": True,
            "pedregal_candidate_union_forbidden": True,
            "bulk_a3_can_proceed_fail_closed": True,
            "ranking_can_treat_pedregal_as_numeric_before_geometry_resolution": False,
        },
        "provenance": {
            "manifest_sha256": sha256_bytes((repo / args.manifest).read_bytes()),
            "semantics_contract_sha256": sha256_bytes((repo / args.semantics_contract).read_bytes()),
            "a3_contract_sha256": sha256_bytes((repo / args.a3_contract).read_bytes()),
        },
        "next_gate": "IMPLEMENT_A3_EXTRACTION_WITH_THREE_CANONICAL_SINGLE_GEOMETRY_TRACKS_PLUS_PEDREGAL_NULL_CANONICAL_ROWS_AND_SEPARATE_CANDIDATE_SIDECARS",
        "modeling_allowed": False,
    }
    write_json(args.output, report)
    print(json.dumps({"summary": report["summary"], "pedregal_ids": p["selected_feature_ids"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
