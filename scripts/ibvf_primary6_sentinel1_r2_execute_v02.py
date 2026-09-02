#!/usr/bin/env python3
"""Execute one PRIMARY6 Sentinel-1 R2 pair using frozen SNAP14 POEORB selector v0.2.

RESEARCH_ONLY / TEST_ONLY. This executor accepts no v0.1 prerequisite manifest.
It independently verifies the exact frozen AUX_POEORB resource bytes, runs the
unchanged frozen SNAP graph in a clean user.home, and accepts each R2 side only
when the SNAP Apply-Orbit-File log requests exactly the v0.2-frozen resource.
No pre/post pixel comparison, R3/R4 calculation, territorial evidence, or
case/control assignment occurs here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import rasterio

from ibvf_primary6_sentinel1_r2_execute import (
    build_safe,
    download_verified,
    find_case,
    guard,
    load,
    raster_metadata,
    sha256_file,
)

POEORB_RE = re.compile(r"(?:https?://\S*/)?(S1[AB]_OPER_AUX_POEORB_[^\s/'\"]+?\.EOF(?:\.zip)?)", re.I)


def verify_frozen_orbit_resource(side: str, rec: dict[str, Any], work: Path) -> dict[str, Any]:
    expected_zip_name = Path(rec["url"]).name
    if rec.get("filename") and Path(rec["filename"]).name != expected_zip_name:
        raise ValueError(f"{side} frozen orbit filename/url mismatch")
    zip_path = work / f"{side}_{expected_zip_name}"
    dl = download_verified(rec["url"], rec["zip_sha256"], int(rec["zip_bytes"]), zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        member = rec["inner_eof_member"]
        if member not in zf.namelist():
            raise ValueError(f"{side} frozen EOF member absent from exact verified ZIP")
        raw = zf.read(member)
    eof_sha = hashlib.sha256(raw).hexdigest()
    if eof_sha != rec["inner_eof_sha256"] or len(raw) != int(rec["inner_eof_bytes"]):
        raise ValueError(f"{side} inner EOF identity mismatch")
    expected_eof_name = Path(member).name
    if expected_zip_name.endswith(".zip") and expected_zip_name[:-4] != expected_eof_name:
        raise ValueError(f"{side} ZIP/EOF basename mismatch")
    return {
        "side": side,
        "url": rec["url"],
        "expected_zip_filename": expected_zip_name,
        "expected_eof_filename": expected_eof_name,
        "zip_sha256": dl["sha256"],
        "zip_bytes": dl["bytes"],
        "inner_eof_member": member,
        "inner_eof_sha256": eof_sha,
        "inner_eof_bytes": len(raw),
        "selector_version": rec.get("selector_version"),
        "selection_rule": rec.get("selection_rule"),
        "status": "PASS_FROZEN_SNAP14_CANONICAL_POEORB_RESOURCE_BYTES_VERIFIED",
    }


def parse_requested_poeorb(log_text: str) -> list[str]:
    names = []
    for m in POEORB_RE.finditer(log_text):
        name = Path(m.group(1)).name
        if name not in names:
            names.append(name)
    return names


def run_side(
    side: str,
    gpt: Path,
    graph: Path,
    manifest: Path,
    dem: Path,
    output: Path,
    user_home: Path,
    orbit_verified: dict[str, Any],
    log_path: Path,
) -> dict[str, Any]:
    cmd = [
        str(gpt),
        "-J-Xmx5G",
        f"-J-Duser.home={user_home}",
        "-c", "2048M",
        str(graph),
        f"-PinputFile={manifest}",
        f"-PexternalDEMFile={dem}",
        f"-PoutputFile={output}",
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=5400,
        env={**os.environ, "HOME": str(user_home)},
    )
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    log_path.write_text(text, encoding="utf-8")
    requested = parse_requested_poeorb(text)
    expected_zip = orbit_verified["expected_zip_filename"]
    expected_eof = orbit_verified["expected_eof_filename"]
    normalized = [x[:-4] if x.lower().endswith(".zip") else x for x in requested]
    exact_requested = len(normalized) == 1 and normalized[0] == expected_eof
    output_exists = output.is_file() and output.stat().st_size > 0
    row: dict[str, Any] = {
        "side": side,
        "returncode": proc.returncode,
        "gpt_command_without_signal_values": cmd,
        "log_sha256": sha256_file(log_path),
        "log_bytes": log_path.stat().st_size,
        "requested_aux_poeorb_filenames": requested,
        "expected_aux_poeorb_zip_filename": expected_zip,
        "expected_aux_poeorb_eof_filename": expected_eof,
        "requested_exact_v02_frozen_resource": exact_requested,
        "frozen_resource_bytes_independently_verified": True,
        "frozen_zip_sha256": orbit_verified["zip_sha256"],
        "frozen_inner_eof_sha256": orbit_verified["inner_eof_sha256"],
        "output_exists": output_exists,
    }
    if output_exists:
        row["output"] = {
            "path": str(output),
            "bytes": output.stat().st_size,
            "sha256": sha256_file(output),
            "metadata_only": raster_metadata(output),
        }
    row["status"] = (
        "PASS_R2_V02_SIDE_EXECUTED_SNAP14_CANONICAL_POEORB_REQUEST_AND_BYTES_VERIFIED"
        if proc.returncode == 0 and output_exists and exact_requested
        else "R2_V02_SIDE_BLOCKED_CANONICAL_POEORB_CONSUMPTION_UNVERIFIED"
    )
    return row


def write_blocked(args: argparse.Namespace, base: dict[str, Any], stage: str, exc: Exception) -> int:
    base["status"] = f"{stage}_BLOCKED_UNKNOWN_NOT_MISSING"
    base["blocker"] = {"stage": stage, "error_class": type(exc).__name__, "message": str(exc)[:2000]}
    base["next_gate"] = "FIX_IMPLEMENTATION_OR_TRANSPORT_ONLY_WITHOUT_CHANGING_FROZEN_SCIENTIFIC_RULES_OR_POEORB_SELECTOR_V02"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": base["status"], "message": str(exc)[:500]}, indent=2))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--orbit-amendment", type=Path, required=True)
    ap.add_argument("--selector-validation", type=Path, required=True)
    ap.add_argument("--r2-entry", type=Path, required=True)
    ap.add_argument("--prerequisites", type=Path, required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--gpt", type=Path, required=True)
    ap.add_argument("--dem", type=Path, required=True)
    ap.add_argument("--dem-report", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    contract = load(args.contract)
    amendment = load(args.orbit_amendment)
    selector_validation = load(args.selector_validation)
    entry_doc = load(args.r2_entry)
    prereq_doc = load(args.prerequisites)
    dem_report = load(args.dem_report)
    for d in (contract, amendment, selector_validation, entry_doc, prereq_doc, dem_report):
        guard(d)

    if contract["status"] != "FROZEN_BEFORE_PRIMARY6_R2_SCIENCE_VALUES_GENERIC_EXECUTION_ALLOWED_ONLY_UNDER_THIS_CONTRACT":
        raise SystemExit("global execution contract not frozen")
    if amendment["status"] != "FROZEN_PRE_ACCEPTED_R2_VALUES_POEORB_SELECTOR_V02_MUST_VALIDATE_AGAINST_PILOT_AND_ANCHOR_BEFORE_BULK":
        raise SystemExit("orbit-consumption amendment v0.2 not frozen")
    if selector_validation["status"] != "PASS_SELECTOR_MATCHES_FIRST_GENERIC_PILOT_SNAP14_AND_CASHAHUACRA_ANCHOR_BEFORE_ACCEPTED_PRIMARY6_R2":
        raise SystemExit("SNAP14 POEORB selector validation has not passed")
    if prereq_doc.get("schema_version") != "irfen-ibvf-primary6-sentinel1-r2-prerequisites-v0.2":
        raise SystemExit("v0.1 prerequisites are superseded and forbidden for R2 execution")
    if prereq_doc["status"] != "PASS_ALL_SNAP14_CANONICAL_R2_PREREQUISITES_V02_FROZEN_NO_SCIENCE_VALUES":
        raise SystemExit("v0.2 exact R2 prerequisites are not fully frozen")
    if prereq_doc.get("selector_version") != "SNAP14_POEORB_V02":
        raise SystemExit("unexpected prerequisite selector version")
    if prereq_doc.get("selector_rule") != amendment["v02_selector"]["selection_rule"]:
        raise SystemExit("prerequisite selector rule differs from frozen amendment")
    if prereq_doc.get("source_orbit_consumption_amendment_sha256") != sha256_file(args.orbit_amendment):
        raise SystemExit("prerequisite amendment hash mismatch")

    entry = find_case(entry_doc, args.case_id)
    prereq = find_case(prereq_doc, args.case_id)
    if entry["r2_entry_status"] != "PASS_R2_ENTRY_IDENTITY_FROZEN_EXECUTION_NOT_RUN":
        raise SystemExit("case is not an executable frozen R2 entry")
    if prereq["status"] != "PASS_SNAP14_CANONICAL_AUX_POEORB_BOTH_DATES_SHA256_FROZEN":
        raise SystemExit("case v0.2 canonical orbit resources are not frozen")
    if entry["case_control_role"] != "UNASSIGNED":
        raise SystemExit("case/control role must remain unassigned")

    unit_id = entry["unit_id"]
    unit = contract["unit_geometry_and_projection"][unit_id]
    for key in ("unit_id", "season_id", "date_local", "source_window_execution_identity_sha256", "projection", "pre_item_id", "post_item_id"):
        if entry[key] != prereq[key]:
            raise SystemExit(f"entry/prerequisite v0.2 identity mismatch: {key}")
    if unit["target_projection"] != entry["projection"]:
        raise SystemExit("unit projection differs from frozen R2 entry")

    graph = Path(entry["r2_graph_path"])
    graph_sha = sha256_file(graph)
    if str(graph) != unit["r2_graph_path"] or graph_sha != entry["r2_graph_sha256"] or graph_sha != unit["r2_graph_sha256"]:
        raise SystemExit("archived R2 graph identity mismatch")
    freeze = Path(entry["r1_freeze_path"])
    if sha256_file(freeze) != entry["r1_freeze_sha256"] or entry["r1_freeze_sha256"] != prereq["r1_freeze_sha256"]:
        raise SystemExit("R1 freeze identity mismatch")
    frozen = load(freeze)
    guard(frozen)
    if frozen["case_id"] != args.case_id or frozen["unit_id"] != unit_id:
        raise SystemExit("R1 freeze case identity mismatch")
    if frozen["pre"]["item_id"] != entry["pre_item_id"] or frozen["post"]["item_id"] != entry["post_item_id"]:
        raise SystemExit("R1 freeze pair identity mismatch")

    if dem_report["unit_id"] != unit_id:
        raise SystemExit("DEM unit mismatch")
    if dem_report["status"] != "PASS_TRACK_DEM_REPRODUCED_EXACTLY_R2_EXECUTION_ALLOWED_FOR_UNIT":
        raise SystemExit("DEM was not exactly reproduced from archived freeze")
    if dem_report["target_projection"] != entry["projection"]:
        raise SystemExit("DEM target projection provenance mismatch")
    if sha256_file(args.dem) != dem_report["output_dem"]["sha256"]:
        raise SystemExit("actual DEM bytes differ from reproduced DEM report")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    user_home = args.work_dir / "clean-home"
    if user_home.exists() and any(user_home.iterdir()):
        raise SystemExit("R2 v0.2 requires an initially empty SNAP user.home")
    user_home.mkdir(parents=True, exist_ok=True)

    base: dict[str, Any] = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-r2-execution-v0.2",
        "case_id": args.case_id,
        "unit_id": unit_id,
        "season_id": entry["season_id"],
        "date_local": entry["date_local"],
        "source_window_execution_identity_sha256": entry["source_window_execution_identity_sha256"],
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_UNTIL_PRIMARY6_A5_FREEZE_AND_ANTI_LEAKAGE_AUDIT",
        "execution_contract_sha256": sha256_file(args.contract),
        "orbit_consumption_amendment_sha256": sha256_file(args.orbit_amendment),
        "selector_validation_sha256": sha256_file(args.selector_validation),
        "r2_entry_sha256": sha256_file(args.r2_entry),
        "prerequisites_v02_sha256": sha256_file(args.prerequisites),
        "r1_freeze_sha256": sha256_file(freeze),
        "r2_graph_sha256": graph_sha,
        "target_projection": entry["projection"],
        "external_dem_sha256": sha256_file(args.dem),
        "external_dem_report_sha256": sha256_file(args.dem_report),
        "poeorb_selector_version": "SNAP14_POEORB_V02",
        "poeorb_selector_rule": amendment["v02_selector"]["selection_rule"],
        "snap_user_home_initially_empty": True,
        "r2_processing_executed": False,
        "poeorb_consumption_verified_both_dates": False,
        "paired_pixel_values_extracted_for_comparison": False,
        "comparison_performed": False,
        "r3_common_support_built": False,
        "r4_difference_computed": False,
        "territorial_outcomes_read": False,
        "known_event_dates_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
    }

    orbit_work = args.work_dir / "verified-orbit-resources"
    orbit_work.mkdir(parents=True, exist_ok=True)
    try:
        orbit_pre = verify_frozen_orbit_resource("pre", prereq["precise_orbits"]["pre"], orbit_work)
        orbit_post = verify_frozen_orbit_resource("post", prereq["precise_orbits"]["post"], orbit_work)
    except Exception as exc:
        return write_blocked(args, base, "POEORB_V02_RESOURCE_VERIFICATION", exc)
    base["frozen_orbit_resource_verification"] = {"pre": orbit_pre, "post": orbit_post}

    safe_root = args.work_dir / "safe"
    try:
        pre_safe = build_safe("pre", frozen["pre"], safe_root)
        post_safe = build_safe("post", frozen["post"], safe_root)
    except Exception as exc:
        return write_blocked(args, base, "SAFE_RECONSTRUCTION", exc)
    base["safe_reconstruction"] = {"pre": pre_safe, "post": post_safe}

    pre_out = args.work_dir / f"{args.case_id}_pre_r2_gamma0_tc.tif"
    post_out = args.work_dir / f"{args.case_id}_post_r2_gamma0_tc.tif"
    try:
        pre = run_side("pre", args.gpt, graph, Path(pre_safe["manifest"]), args.dem, pre_out, user_home, orbit_pre, args.work_dir / "pre_gpt.log")
        post = run_side("post", args.gpt, graph, Path(post_safe["manifest"]), args.dem, post_out, user_home, orbit_post, args.work_dir / "post_gpt.log")
    except Exception as exc:
        return write_blocked(args, base, "SNAP_R2_V02_RUNTIME", exc)

    base["pre"] = pre
    base["post"] = post
    both_outputs = pre["returncode"] == 0 and post["returncode"] == 0 and pre["output_exists"] and post["output_exists"]
    both_orbits = pre["requested_exact_v02_frozen_resource"] and post["requested_exact_v02_frozen_resource"]
    base["r2_processing_executed"] = bool(both_outputs)
    base["poeorb_consumption_verified_both_dates"] = bool(both_orbits)
    if both_outputs and both_orbits:
        base["status"] = "PASS_R2_V02_PRE_POST_INDEPENDENT_SNAP14_CANONICAL_POEORB_VERIFIED_NO_COMPARISON"
        base["next_gate"] = "R3_COMMON_SUPPORT_MINIMUM_0_95_BEFORE_ANY_RADIOMETRIC_DIFFERENCE"
    elif both_outputs:
        base["status"] = "R2_V02_OUTPUTS_EXIST_CANONICAL_POEORB_CONSUMPTION_UNVERIFIED_R3_BLOCKED"
        base["next_gate"] = "DO_NOT_REUSE_OUTPUTS_RESOLVE_CONSUMPTION_VERIFICATION_WITHOUT_COMPARING_PRE_POST_PIXELS"
    else:
        base["status"] = "R2_V02_EXECUTION_BLOCKED_UNKNOWN_NOT_MISSING"
        base["next_gate"] = "RESOLVE_RUNTIME_WITHOUT_CHANGING_FROZEN_SCIENTIFIC_RULES_OR_POEORB_SELECTOR_V02"

    args.output.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": base["status"],
        "case_id": args.case_id,
        "r2_processing_executed": base["r2_processing_executed"],
        "poeorb_consumption_verified_both_dates": base["poeorb_consumption_verified_both_dates"],
        "comparison_performed": False,
        "activation_inference_allowed": False,
    }, indent=2))
    return 0 if both_outputs and both_orbits else 2


if __name__ == "__main__":
    raise SystemExit(main())
