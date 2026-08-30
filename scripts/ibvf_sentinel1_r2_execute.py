#!/usr/bin/env python3
"""Execute the frozen Cashahuacra Sentinel-1 R2 graph, fail-closed.

RESEARCH_ONLY / TEST_ONLY. Reconstructs the two exact SAFE inputs from the
Earth Search assets already frozen by SHA-256, runs the same archived SNAP
R2 graph independently for pre and post, and verifies the expected precise
orbit filename appears in each execution log. It does NOT build common
support, compute pre/post differences, assign case/control roles, or infer an
activation outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import rasterio
import requests

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
USER_AGENT = "IRFEN-IBVF/0.2 RESEARCH_ONLY TEST_ONLY"
REQUIRED_ASSETS = ("safe-manifest", "schema-calibration-vv", "schema-noise-vv", "schema-product-vv", "vv")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def fetch_item(item_id: str) -> dict[str, Any]:
    url = f"{EARTH_SEARCH}/collections/sentinel-1-grd/items/{quote(item_id, safe='')}"
    r = requests.get(url, timeout=(20, 120), headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.json()


def relative_safe_path(href: str, item_id: str) -> tuple[str, Path]:
    raw = href[5:] if href.startswith("s3://") else urlparse(href).path.lstrip("/")
    raw = unquote(raw)
    parts = Path(raw).parts
    safe_i = next((i for i, p in enumerate(parts) if p.endswith(".SAFE")), None)
    if safe_i is None:
        name = Path(raw).name
        if name == "manifest.safe":
            return f"{item_id}.SAFE", Path("manifest.safe")
        raise ValueError(f"asset path is not inside a SAFE package: {href}")
    return parts[safe_i], Path(*parts[safe_i + 1 :])


def download_verified(href: str, expected: dict[str, Any], target: Path) -> dict[str, Any]:
    url = s3_to_https(href)
    target.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    n = 0
    with requests.get(url, stream=True, timeout=(30, 1200), headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with target.open("wb") as fh:
            for chunk in r.iter_content(4 * 1024 * 1024):
                if not chunk:
                    continue
                fh.write(chunk)
                h.update(chunk)
                n += len(chunk)
    got = h.hexdigest()
    if got != expected.get("sha256"):
        raise ValueError(f"SHA256 mismatch {target}: expected {expected.get('sha256')} got {got}")
    if expected.get("bytes") is not None and n != int(expected["bytes"]):
        raise ValueError(f"byte mismatch {target}: expected {expected['bytes']} got {n}")
    return {"bytes": n, "sha256": got, "resolved_url": url, "relative_path": str(target)}


def build_safe(side: str, frozen: dict[str, Any], root: Path) -> dict[str, Any]:
    item_id = frozen["item_id"]
    item = fetch_item(item_id)
    assets = item.get("assets") or {}
    safe_name: str | None = None
    downloaded: dict[str, Any] = {}
    for key in REQUIRED_ASSETS:
        href = (assets.get(key) or {}).get("href")
        expected = (frozen.get("assets") or {}).get(key) or {}
        if not href or not expected.get("sha256"):
            raise ValueError(f"{side} missing Earth Search href or frozen identity for {key}")
        derived_safe, rel = relative_safe_path(href, item_id)
        safe_name = safe_name or derived_safe
        if derived_safe != safe_name:
            raise ValueError(f"{side} assets disagree on SAFE root: {safe_name} vs {derived_safe}")
        target = root / safe_name / rel
        downloaded[key] = download_verified(href, expected, target)
    manifest = root / str(safe_name) / "manifest.safe"
    if not manifest.is_file():
        raise ValueError(f"{side} manifest.safe absent after reconstruction")
    return {
        "side": side,
        "item_id": item_id,
        "safe_root": str(root / str(safe_name)),
        "manifest": str(manifest),
        "assets": downloaded,
        "status": "PASS_FROZEN_SAFE_SCIENCE_ASSETS_RECONSTRUCTED",
    }


def raster_metadata(path: Path) -> dict[str, Any]:
    with rasterio.open(path) as ds:
        return {
            "width": ds.width,
            "height": ds.height,
            "count": ds.count,
            "crs": str(ds.crs),
            "transform": [float(x) for x in tuple(ds.transform)],
            "dtypes": list(ds.dtypes),
            "nodata": ds.nodata,
            "bounds": [float(ds.bounds.left), float(ds.bounds.bottom), float(ds.bounds.right), float(ds.bounds.top)],
        }


def run_one(side: str, gpt: Path, graph: Path, manifest: Path, dem: Path, output: Path, user_home: Path, expected_eof: Path, log_path: Path) -> dict[str, Any]:
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
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=5400, env={**os.environ, "HOME": str(user_home)})
    text = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    log_path.write_text(text, encoding="utf-8")
    orbit_name = expected_eof.name
    orbit_logged = orbit_name in text
    output_exists = output.is_file() and output.stat().st_size > 0
    rec: dict[str, Any] = {
        "side": side,
        "returncode": p.returncode,
        "gpt_command_without_signal_values": cmd,
        "log_sha256": sha256_file(log_path),
        "log_bytes": log_path.stat().st_size,
        "expected_aux_poeorb_filename": orbit_name,
        "expected_aux_poeorb_sha256": sha256_file(expected_eof),
        "expected_aux_poeorb_logged": orbit_logged,
        "output_exists": output_exists,
    }
    if output_exists:
        rec["output"] = {
            "path": str(output),
            "bytes": output.stat().st_size,
            "sha256": sha256_file(output),
            "metadata_only": raster_metadata(output),
        }
    rec["status"] = (
        "PASS_R2_SIDE_EXECUTED_AND_EXPECTED_POEORB_LOGGED"
        if p.returncode == 0 and output_exists and orbit_logged
        else "R2_SIDE_BLOCKED_OR_POEORB_CONSUMPTION_UNVERIFIED"
    )
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", type=Path, required=True)
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--graph-report", type=Path, required=True)
    ap.add_argument("--gpt", type=Path, required=True)
    ap.add_argument("--dem", type=Path, required=True)
    ap.add_argument("--user-home", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    graph_report = json.loads(args.graph_report.read_text(encoding="utf-8"))
    for d in (freeze, graph_report):
        assert d["deployment_status"] == "RESEARCH_ONLY"
        assert d["production_use"] is False and d["production_ready"] is False and d["operational_alerting_enabled"] is False
        assert d["uses_operational_event_none_labels"] is False and d["territorial_activation_evidence_blinded"] is True
    assert freeze["compatible_pair"] == "YES"
    assert sha256_file(args.graph) == graph_report["graph_sha256"]
    assert graph_report["status"] == "PASS_GRAPH_COMPILED_AND_EXACT_ORBITS_STAGED_EXECUTION_NOT_RUN"

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    safe_root = args.work_dir / "safe"
    pre_safe = build_safe("pre", freeze["pre"], safe_root)
    post_safe = build_safe("post", freeze["post"], safe_root)

    orbit_by_side = {x["side"]: Path(x["staged_eof"].replace("/tmp/ibvf-r2-graph/home", str(args.user_home))) for x in graph_report["orbit_staging"]}
    for side, path in orbit_by_side.items():
        expected = next(x for x in graph_report["orbit_staging"] if x["side"] == side)
        if not path.is_file() or sha256_file(path) != expected["staged_eof_sha256"]:
            raise ValueError(f"{side} frozen POEORB is not staged exactly at {path}")

    pre_out = args.work_dir / "cashahuacra_pre_r2_gamma0_tc.tif"
    post_out = args.work_dir / "cashahuacra_post_r2_gamma0_tc.tif"
    pre = run_one("pre", args.gpt, args.graph, Path(pre_safe["manifest"]), args.dem, pre_out, args.user_home, orbit_by_side["pre"], args.work_dir / "pre_gpt.log")
    post = run_one("post", args.gpt, args.graph, Path(post_safe["manifest"]), args.dem, post_out, args.user_home, orbit_by_side["post"], args.work_dir / "post_gpt.log")

    both_outputs = pre["returncode"] == 0 and post["returncode"] == 0 and pre["output_exists"] and post["output_exists"]
    both_orbits = pre["expected_aux_poeorb_logged"] and post["expected_aux_poeorb_logged"]
    if both_outputs and both_orbits:
        status = "PASS_R2_PRE_POST_EXECUTED_EXACT_GRAPH_AND_POEORB_CONSUMPTION_VERIFIED_R3_ALLOWED"
    elif both_outputs:
        status = "R2_OUTPUTS_GENERATED_POEORB_CONSUMPTION_UNVERIFIED_R3_BLOCKED"
    else:
        status = "R2_EXECUTION_BLOCKED_UNKNOWN_NOT_MISSING"

    report = {
        "schema_version": "irfen-ibvf-cashahuacra-sentinel1-r2-execution-v0.1",
        "generated_at": now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "graph_sha256": graph_report["graph_sha256"],
        "identical_graph_rule_satisfied": True,
        "safe_reconstruction": {"pre": pre_safe, "post": post_safe},
        "r2": {"pre": pre, "post": post},
        "r2_processing_executed": both_outputs,
        "poeorb_consumption_verified_both_dates": both_orbits,
        "paired_pixel_values_extracted_for_comparison": False,
        "comparison_performed": False,
        "r3_common_support_built": False,
        "r4_difference_computed": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "status": status,
        "next_gate": "BUILD_R3_COMMON_VALID_PIXEL_INTERSECTION_AND_REQUIRE_SUPPORT_GTE_0P95" if both_outputs and both_orbits else "RESOLVE_R2_OR_POEORB_EXECUTION_EVIDENCE_WITHOUT_INTERPRETING_OUTCOME",
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "pre_returncode": pre["returncode"], "post_returncode": post["returncode"], "poeorb_verified": both_orbits}, indent=2))
    return 0 if both_outputs else 2


if __name__ == "__main__":
    raise SystemExit(main())
