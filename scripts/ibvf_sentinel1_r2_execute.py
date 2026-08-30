#!/usr/bin/env python3
"""Execute the frozen Cashahuacra Sentinel-1 R2 graph, fail-closed.

RESEARCH_ONLY / TEST_ONLY. Reconstructs the two exact SAFE inputs from the
Earth Search assets already frozen by SHA-256, runs the same archived SNAP
R2 graph independently for pre and post, and verifies the expected precise
orbit filename appears in each execution log. It does NOT build common
support, compute pre/post differences, assign case/control roles, or infer an
activation outcome.

Earth Search stores Sentinel-1 science assets below a flattened S3 product
prefix rather than a literal ``*.SAFE`` directory. The reconstruction rule is
therefore derived from each frozen ``manifest.safe``: the manifest's own
``fileLocation`` references define the internal SAFE paths, while the bytes
still come only from the exact Earth Search assets frozen by SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import rasterio
import requests

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
USER_AGENT = "IRFEN-IBVF/0.3 RESEARCH_ONLY TEST_ONLY"
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


def download_verified(href: str, expected: dict[str, Any], target: Path) -> dict[str, Any]:
    url = s3_to_https(href)
    target.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(url, stream=True, timeout=(30, 1200), headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with target.open("wb") as fh:
                for chunk in r.iter_content(4 * 1024 * 1024):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    h.update(chunk)
                    n += len(chunk)
    except requests.RequestException as exc:
        if target.exists():
            target.unlink()
        raise RuntimeError(f"TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING {type(exc).__name__}: {exc}") from exc
    got = h.hexdigest()
    if got != expected.get("sha256"):
        raise ValueError(f"SHA256 mismatch {target}: expected {expected.get('sha256')} got {got}")
    if expected.get("bytes") is not None and n != int(expected["bytes"]):
        raise ValueError(f"byte mismatch {target}: expected {expected['bytes']} got {n}")
    return {"bytes": n, "sha256": got, "resolved_url": url, "safe_relative_path": str(target)}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_manifest_href(href: str) -> PurePosixPath:
    value = href.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe manifest fileLocation href: {href}")
    return p


def manifest_file_locations(path: Path) -> list[PurePosixPath]:
    root = ET.parse(path).getroot()
    refs: list[PurePosixPath] = []
    for elem in root.iter():
        if local_name(elem.tag) != "fileLocation":
            continue
        href = elem.attrib.get("href")
        if href:
            refs.append(normalize_manifest_href(href))
    if not refs:
        raise ValueError("manifest.safe contains no fileLocation references")
    return refs


def select_manifest_path(refs: list[PurePosixPath], asset_key: str) -> PurePosixPath:
    def lower(p: PurePosixPath) -> str:
        return str(p).lower()

    if asset_key == "schema-calibration-vv":
        candidates = [p for p in refs if "/annotation/calibration/calibration-" in "/" + lower(p) and "vv" in p.name.lower() and p.suffix.lower() == ".xml"]
    elif asset_key == "schema-noise-vv":
        candidates = [p for p in refs if "/annotation/calibration/noise-" in "/" + lower(p) and "vv" in p.name.lower() and p.suffix.lower() == ".xml"]
    elif asset_key == "schema-product-vv":
        candidates = [p for p in refs if lower(p).startswith("annotation/") and "/calibration/" not in "/" + lower(p) and "vv" in p.name.lower() and p.suffix.lower() == ".xml"]
    elif asset_key == "vv":
        candidates = [p for p in refs if lower(p).startswith("measurement/") and "vv" in p.name.lower() and p.suffix.lower() in {".tif", ".tiff"}]
    else:
        raise ValueError(f"unsupported manifest classification key {asset_key}")
    if len(candidates) != 1:
        raise ValueError(f"manifest path classification for {asset_key} returned {len(candidates)} candidates: {[str(x) for x in candidates]}")
    return candidates[0]


def build_safe(side: str, frozen: dict[str, Any], root: Path) -> dict[str, Any]:
    item_id = frozen["item_id"]
    item = fetch_item(item_id)
    assets = item.get("assets") or {}
    safe_root = root / f"{item_id}.SAFE"
    manifest_href = (assets.get("safe-manifest") or {}).get("href")
    manifest_expected = (frozen.get("assets") or {}).get("safe-manifest") or {}
    if not manifest_href or not manifest_expected.get("sha256"):
        raise ValueError(f"{side} missing Earth Search manifest href or frozen identity")
    manifest = safe_root / "manifest.safe"
    manifest_result = download_verified(manifest_href, manifest_expected, manifest)
    refs = manifest_file_locations(manifest)

    downloaded: dict[str, Any] = {"safe-manifest": manifest_result}
    path_map: dict[str, str] = {"safe-manifest": "manifest.safe"}
    for key in REQUIRED_ASSETS[1:]:
        href = (assets.get(key) or {}).get("href")
        expected = (frozen.get("assets") or {}).get(key) or {}
        if not href or not expected.get("sha256"):
            raise ValueError(f"{side} missing Earth Search href or frozen identity for {key}")
        rel = select_manifest_path(refs, key)
        target = safe_root.joinpath(*rel.parts)
        downloaded[key] = download_verified(href, expected, target)
        path_map[key] = str(rel)

    return {
        "side": side,
        "item_id": item_id,
        "safe_root": str(safe_root),
        "manifest": str(manifest),
        "manifest_file_location_count": len(refs),
        "frozen_asset_to_manifest_path": path_map,
        "assets": downloaded,
        "status": "PASS_FROZEN_SAFE_SCIENCE_ASSETS_RECONSTRUCTED_FROM_MANIFEST_REFERENCES",
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


def base_report(graph_sha: str) -> dict[str, Any]:
    return {
        "schema_version": "irfen-ibvf-cashahuacra-sentinel1-r2-execution-v0.2",
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
        "graph_sha256": graph_sha,
        "identical_graph_rule_satisfied": True,
        "r2_processing_executed": False,
        "poeorb_consumption_verified_both_dates": False,
        "paired_pixel_values_extracted_for_comparison": False,
        "comparison_performed": False,
        "r3_common_support_built": False,
        "r4_difference_computed": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
    }


def write_blocked(args: argparse.Namespace, report: dict[str, Any], stage: str, exc: Exception) -> int:
    report["status"] = f"{stage}_BLOCKED_UNKNOWN_NOT_MISSING"
    report["blocker"] = {"stage": stage, "error_class": type(exc).__name__, "message": str(exc)[:2000]}
    report["next_gate"] = "RESOLVE_TECHNICAL_BLOCKER_WITHOUT_INTERPRETING_SAR_OR_OUTCOME"
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "error_class": type(exc).__name__, "message": str(exc)[:500]}, indent=2))
    return 2


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
    report = base_report(graph_report["graph_sha256"])
    safe_root = args.work_dir / "safe"
    try:
        pre_safe = build_safe("pre", freeze["pre"], safe_root)
        post_safe = build_safe("post", freeze["post"], safe_root)
    except Exception as exc:
        return write_blocked(args, report, "SAFE_RECONSTRUCTION", exc)
    report["safe_reconstruction"] = {"pre": pre_safe, "post": post_safe}

    orbit_by_side = {x["side"]: Path(x["staged_eof"].replace("/tmp/ibvf-r2-graph/home", str(args.user_home))) for x in graph_report["orbit_staging"]}
    try:
        for side, path in orbit_by_side.items():
            expected = next(x for x in graph_report["orbit_staging"] if x["side"] == side)
            if not path.is_file() or sha256_file(path) != expected["staged_eof_sha256"]:
                raise ValueError(f"{side} frozen POEORB is not staged exactly at {path}")
    except Exception as exc:
        return write_blocked(args, report, "POEORB_STAGING", exc)

    pre_out = args.work_dir / "cashahuacra_pre_r2_gamma0_tc.tif"
    post_out = args.work_dir / "cashahuacra_post_r2_gamma0_tc.tif"
    try:
        pre = run_one("pre", args.gpt, args.graph, Path(pre_safe["manifest"]), args.dem, pre_out, args.user_home, orbit_by_side["pre"], args.work_dir / "pre_gpt.log")
        post = run_one("post", args.gpt, args.graph, Path(post_safe["manifest"]), args.dem, post_out, args.user_home, orbit_by_side["post"], args.work_dir / "post_gpt.log")
    except Exception as exc:
        return write_blocked(args, report, "SNAP_R2_RUNTIME", exc)

    both_outputs = pre["returncode"] == 0 and post["returncode"] == 0 and pre["output_exists"] and post["output_exists"]
    both_orbits = pre["expected_aux_poeorb_logged"] and post["expected_aux_poeorb_logged"]
    report["r2"] = {"pre": pre, "post": post}
    report["r2_processing_executed"] = both_outputs
    report["poeorb_consumption_verified_both_dates"] = both_orbits
    if both_outputs and both_orbits:
        report["status"] = "PASS_R2_PRE_POST_EXECUTED_EXACT_GRAPH_AND_POEORB_CONSUMPTION_VERIFIED_R3_ALLOWED"
    elif both_outputs:
        report["status"] = "R2_OUTPUTS_GENERATED_POEORB_CONSUMPTION_UNVERIFIED_R3_BLOCKED"
    else:
        report["status"] = "R2_EXECUTION_BLOCKED_UNKNOWN_NOT_MISSING"
    report["next_gate"] = "BUILD_R3_COMMON_VALID_PIXEL_INTERSECTION_AND_REQUIRE_SUPPORT_GTE_0P95" if both_outputs and both_orbits else "RESOLVE_R2_OR_POEORB_EXECUTION_EVIDENCE_WITHOUT_INTERPRETING_OUTCOME"
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "pre_returncode": pre["returncode"], "post_returncode": post["returncode"], "poeorb_verified": both_orbits}, indent=2))
    return 0 if both_outputs else 2


if __name__ == "__main__":
    raise SystemExit(main())
