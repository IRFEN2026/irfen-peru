#!/usr/bin/env python3
"""Select PRIMARY6 Landsat pre/post pairs using the preregistered blind QA ordering.

This script consumes only the frozen selected-window A1 catalog and the fully
measured Landsat QA_PIXEL reports. It does not read territorial outcomes,
case/control roles, risk, alerts, incident/damage evidence, or Cashahuacra
feature magnitudes. Meteorological windows are immutable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

PERU = timezone(timedelta(hours=-5))
UTC = timezone.utc
FORBIDDEN_KEY_FRAGMENTS = (
    "outcome", "activation", "damage", "incident", "risk", "alert", "priority"
)


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def csha(x: Any) -> str:
    raw = json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def guards(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def parse_z(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def pair_identity(p: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(p.get("pre_item_id")), str(p.get("post_item_id")),
        str(p.get("platform")), str(p.get("wrs_path")), str(p.get("wrs_row"))
    )


def reject_forbidden_topology(obj: Any, path: str = "$") -> None:
    """Reject prohibited scientific leakage fields, allowing explicit anti-leakage booleans."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            low = str(k).lower()
            if any(f in low for f in FORBIDDEN_KEY_FRAGMENTS):
                # Contract/report guard fields are allowed only when they explicitly deny leakage.
                if v is not False and v not in ("SEALED", "UNASSIGNED"):
                    raise SystemExit(f"FAIL_CLOSED_FORBIDDEN_FIELD_VALUE:{path}.{k}")
            reject_forbidden_topology(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            reject_forbidden_topology(v, f"{path}[{i}]")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--catalog", default="site/data/validation/ibvf_primary6_selected_a1_catalog.json")
    ap.add_argument("--global-qa", default="site/data/validation/ibvf_primary6_landsat_qa_global.json")
    ap.add_argument("--contract", default="site/data/validation/ibvf_primary6_landsat_pair_selection_contract.json")
    ap.add_argument("--track-qa-dir", default="site/data/validation")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()

    catalog_path = root / args.catalog
    global_path = root / args.global_qa
    contract_path = root / args.contract
    catalog = load(catalog_path)
    global_qa = load(global_path)
    contract = load(contract_path)
    for d in (catalog, global_qa, contract):
        guards(d)

    assert contract["cohort_id"] == "PRIMARY6_CHRONOLOGICAL"
    assert contract["execution_status"] == "PREREGISTERED_BEFORE_PAIR_CHOICE_EXECUTION"
    req = contract["required_inputs"]
    if global_qa.get("cohort_id") != "PRIMARY6_CHRONOLOGICAL":
        raise SystemExit("FAIL_CLOSED_WRONG_QA_COHORT")
    if global_qa.get("required_unique_unit_scene_count") != int(req["required_qa_measured_unit_scene_count"]):
        raise SystemExit("FAIL_CLOSED_GLOBAL_QA_REQUIRED_COUNT_MISMATCH")
    if global_qa.get("qa_measured_unit_scene_count") != int(req["required_qa_measured_unit_scene_count"]):
        raise SystemExit("FAIL_CLOSED_GLOBAL_QA_NOT_FULLY_MEASURED")
    if global_qa.get("qa_unknown_unit_scene_count") != int(req["required_qa_unknown_unit_scene_count"]):
        raise SystemExit("FAIL_CLOSED_GLOBAL_QA_UNKNOWN_PRESENT")
    if global_qa.get("global_qa_complete") is not True or global_qa.get("pair_choice_allowed_by_qa_completeness") is not True:
        raise SystemExit("FAIL_CLOSED_GLOBAL_QA_GATE_CLOSED")
    if global_qa.get("pair_choice_performed") is not False:
        raise SystemExit("FAIL_CLOSED_PAIR_CHOICE_ALREADY_REPORTED")
    if global_qa.get("source_a1_catalog_sha256") != sha_file(catalog_path):
        raise SystemExit("FAIL_CLOSED_A1_CATALOG_HASH_MISMATCH")
    if catalog.get("case_control_assignment_performed") is not False or catalog.get("territorial_outcome_fields_read") is not False:
        raise SystemExit("FAIL_CLOSED_A1_ANTI_LEAKAGE")

    # Load exact frozen track reports and verify the hashes frozen by the global QA report.
    track_docs: dict[str, dict[str, Any]] = {}
    track_meta = {str(x["unit_id"]): x for x in global_qa["track_reports"]}
    if set(track_meta) != {"huaycoloro", "san_ildefonso", "shingolay"}:
        raise SystemExit("FAIL_CLOSED_TRACK_SET")
    for unit, meta in track_meta.items():
        p = root / args.track_qa_dir / f"ibvf_primary6_landsat_qa_{unit}.json"
        if sha_file(p) != meta["file_sha256"]:
            raise SystemExit(f"FAIL_CLOSED_TRACK_QA_FILE_HASH:{unit}")
        d = load(p); guards(d)
        if d.get("unit_id") != unit or d.get("qa_unknown_scene_count") != 0:
            raise SystemExit(f"FAIL_CLOSED_TRACK_QA_GATE:{unit}")
        if d.get("qa_measured_scene_count") != d.get("required_unique_scene_count"):
            raise SystemExit(f"FAIL_CLOSED_TRACK_QA_INCOMPLETE:{unit}")
        if d.get("pair_choice_performed") is not False or d.get("selected_window_replaced") is not False:
            raise SystemExit(f"FAIL_CLOSED_TRACK_ALREADY_CHANGED:{unit}")
        track_docs[unit] = d

    # A1 window lookup is the authoritative source of eligible pair identities.
    a1_windows: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for w in catalog.get("windows", []):
        key = (str(w["unit_id"]), str(w["season_id"]), str(w["date_local"]), int(w["selected_target_order"]))
        if key in a1_windows:
            raise SystemExit(f"FAIL_CLOSED_DUPLICATE_A1_WINDOW:{key}")
        a1_windows[key] = w
    if len(a1_windows) != int(req["required_selected_window_count"]):
        raise SystemExit(f"FAIL_CLOSED_A1_WINDOW_COUNT:{len(a1_windows)}")

    selected: list[dict[str, Any]] = []
    track_summary: list[dict[str, Any]] = []
    for unit in sorted(track_docs):
        d = track_docs[unit]
        scene_by_id = {str(x["item_id"]): x for x in d.get("scenes", [])}
        if len(scene_by_id) != int(d["required_unique_scene_count"]):
            raise SystemExit(f"FAIL_CLOSED_SCENE_ID_DUPLICATE_OR_COUNT:{unit}")
        for iid, s in scene_by_id.items():
            if s.get("qa_status") != contract["eligible_pairs"]["both_scene_qa_status_required"]:
                raise SystemExit(f"FAIL_CLOSED_SCENE_QA_NOT_PASS:{unit}:{iid}")
            f = (s.get("metrics") or {}).get("strict_clear_fraction")
            if not finite(f):
                raise SystemExit(f"FAIL_CLOSED_SCENE_CLEAR_UNKNOWN:{unit}:{iid}")

        count = 0
        for tw in d.get("windows", []):
            key = (unit, str(tw["season_id"]), str(tw["date_local"]), int(tw["selected_target_order"]))
            aw = a1_windows.get(key)
            if aw is None:
                raise SystemExit(f"FAIL_CLOSED_TRACK_WINDOW_NOT_IN_A1:{key}")
            al = aw.get("landsat") or {}
            a1_pairs = al.get("compatible_pair_identities") or []
            track_pairs = tw.get("compatible_pair_identities") or []
            if [pair_identity(x) for x in a1_pairs] != [pair_identity(x) for x in track_pairs]:
                raise SystemExit(f"FAIL_CLOSED_ELIGIBLE_PAIR_SET_DRIFT:{key}")
            if not track_pairs:
                raise SystemExit(f"FAIL_CLOSED_NO_COMPATIBLE_PAIR:{key}")

            anchor = datetime.combine(date.fromisoformat(key[2]), time(0), PERU).astimezone(UTC)
            candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
            audit_candidates: list[dict[str, Any]] = []
            for p in track_pairs:
                pre_id, post_id = str(p["pre_item_id"]), str(p["post_item_id"])
                if pre_id not in scene_by_id or post_id not in scene_by_id:
                    raise SystemExit(f"FAIL_CLOSED_PAIR_SCENE_NOT_MEASURED:{key}:{pre_id}:{post_id}")
                pre, post = scene_by_id[pre_id], scene_by_id[post_id]
                pre_clear = float(pre["metrics"]["strict_clear_fraction"])
                post_clear = float(post["metrics"]["strict_clear_fraction"])
                minimum = min(pre_clear, post_clear)
                mean = (pre_clear + post_clear) / 2.0
                pre_dt, post_dt = parse_z(str(pre["datetime"])), parse_z(str(post["datetime"]))
                pre_dist = abs((anchor - pre_dt).total_seconds())
                post_dist = abs((post_dt - anchor).total_seconds())
                total_dist = pre_dist + post_dist
                max_dist = max(pre_dist, post_dist)
                sort_key = (-minimum, -mean, total_dist, max_dist, pre_dt.isoformat(), post_dt.isoformat(), pre_id, post_id)
                a = {
                    "pre_item_id": pre_id,
                    "post_item_id": post_id,
                    "platform": p["platform"],
                    "wrs_path": p["wrs_path"],
                    "wrs_row": p["wrs_row"],
                    "pre_datetime": pre["datetime"],
                    "post_datetime": post["datetime"],
                    "pre_strict_clear_fraction": pre_clear,
                    "post_strict_clear_fraction": post_clear,
                    "minimum_strict_clear_fraction": minimum,
                    "mean_strict_clear_fraction": mean,
                    "pre_anchor_distance_seconds": pre_dist,
                    "post_anchor_distance_seconds": post_dist,
                    "total_anchor_distance_seconds": total_dist,
                    "maximum_side_anchor_distance_seconds": max_dist,
                }
                audit_candidates.append(a)
                candidates.append((sort_key, a))
            _, chosen = min(candidates, key=lambda x: x[0])
            selected.append({
                "unit_id": unit,
                "season_id": key[1],
                "date_local": key[2],
                "selected_target_order": key[3],
                "case_control_role": "UNASSIGNED",
                "territorial_evidence": "SEALED",
                "eligible_pair_count": len(candidates),
                "eligible_pairs_audit_sha256": csha(audit_candidates),
                "selected_pair": chosen,
                "selected_pair_identity_sha256": csha(pair_identity(chosen)),
                "selected_window_replaced": False,
            })
            count += 1
        track_summary.append({"unit_id": unit, "selected_window_count": count, "landsat_pair_selected_count": count})

    selected.sort(key=lambda x: (x["unit_id"], x["season_id"], x["date_local"], x["selected_target_order"]))
    if len(selected) != int(req["required_selected_window_count"]):
        raise SystemExit(f"FAIL_CLOSED_SELECTED_PAIR_COUNT:{len(selected)}")
    if any(x["case_control_role"] != "UNASSIGNED" or x["territorial_evidence"] != "SEALED" for x in selected):
        raise SystemExit("FAIL_CLOSED_ROLE_OR_EVIDENCE_LEAK")

    report = {
        "schema_version": "irfen-ibvf-primary6-landsat-pair-selection-v0.1",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "cohort_id": "PRIMARY6_CHRONOLOGICAL",
        "source_a1_catalog_sha256": sha_file(catalog_path),
        "source_global_qa_sha256": sha_file(global_path),
        "source_pair_selection_contract_sha256": sha_file(contract_path),
        "source_track_qa_sha256": {u: sha_file(root / args.track_qa_dir / f"ibvf_primary6_landsat_qa_{u}.json") for u in sorted(track_docs)},
        "selected_window_count": len(selected),
        "landsat_pair_selected_count": len(selected),
        "pair_choice_performed": True,
        "pair_choice_rule": "FROZEN_QA_ORDERING_V0_1",
        "selected_window_replaced": False,
        "case_control_assignment_performed": False,
        "all_case_control_roles": "UNASSIGNED",
        "territorial_outcome_fields_read": False,
        "known_event_dates_read": False,
        "cashahuacra_feature_magnitudes_read": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "track_summary": track_summary,
        "windows": selected,
        "selected_pairs_canonical_sha256": csha(selected),
        "status": "PASS_PRIMARY6_LANDSAT_108_OF_108_PAIRS_SELECTED_BY_PREREGISTERED_QA_ORDER_NO_OUTCOME",
        "next_gate": "FREEZE_SELECTED_LANDSAT_SPECTRAL_ASSET_BYTES_AND_COMPUTE_PREREGISTERED_OPTICAL_FEATURES_WITHOUT_UNBLINDING"
    }
    guards(report)
    reject_forbidden_topology({
        "production_use": report["production_use"],
        "production_ready": report["production_ready"],
        "operational_alerting_enabled": report["operational_alerting_enabled"],
        "territorial_outcome_fields_read": report["territorial_outcome_fields_read"],
        "activation_inference_allowed": report["activation_inference_allowed"],
    })
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "selected_window_count": report["selected_window_count"],
        "landsat_pair_selected_count": report["landsat_pair_selected_count"],
        "selected_pairs_canonical_sha256": report["selected_pairs_canonical_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
