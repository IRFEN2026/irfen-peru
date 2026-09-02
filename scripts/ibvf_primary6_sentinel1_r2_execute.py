#!/usr/bin/env python3
"""Execute one frozen PRIMARY6 Sentinel-1 R2 pair under the global blind contract.

RESEARCH_ONLY / TEST_ONLY. The executor generalizes only case/output paths and
pre-frozen unit identities. It reconstructs the exact pre/post SAFE science
assets from the R1 freeze, stages the exact AUX_POEORB bytes frozen before R2,
reproduces the unit DEM identity, and runs the archived unit graph independently
for pre and post. It does not compare pre/post pixels, build R3 support, compute
R4 change features, read territorial outcomes, or assign case/control roles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import rasterio
import requests

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
UA = "IRFEN-IBVF/0.4 RESEARCH_ONLY TEST_ONLY"
REQUIRED_ASSETS = ("safe-manifest", "schema-calibration-vv", "schema-noise-vv", "schema-product-vv", "vv")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def guard(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True


def s3_to_https(uri: str) -> str:
    if not uri.startswith("s3://"):
        return uri
    rest = uri[5:]
    bucket, key = rest.split("/", 1)
    return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"


def download_verified(url: str, expected_sha: str, expected_bytes: int | None, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    n = 0
    try:
        with requests.get(s3_to_https(url), stream=True, timeout=(30, 1200), headers={"User-Agent": UA}) as r:
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
    if got != expected_sha:
        raise ValueError(f"SHA256 mismatch {target}: {got} != {expected_sha}")
    if expected_bytes is not None and n != int(expected_bytes):
        raise ValueError(f"byte mismatch {target}: {n} != {expected_bytes}")
    return {"bytes": n, "sha256": got, "resolved_url": s3_to_https(url)}


def fetch_item(item_id: str) -> dict[str, Any]:
    url = f"{EARTH_SEARCH}/collections/sentinel-1-grd/items/{quote(item_id, safe='')}"
    r = requests.get(url, timeout=(20, 120), headers={"User-Agent": UA})
    r.raise_for_status()
    return r.json()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_manifest_href(href: str) -> PurePosixPath:
    value = href.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe manifest href: {href}")
    return p


def manifest_locations(path: Path) -> list[PurePosixPath]:
    root = ET.parse(path).getroot()
    refs: list[PurePosixPath] = []
    for elem in root.iter():
        if local_name(elem.tag) == "fileLocation":
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
        raise ValueError(f"unsupported asset key {asset_key}")
    if len(candidates) != 1:
        raise ValueError(f"manifest classification {asset_key} returned {len(candidates)} candidates")
    return candidates[0]


def build_safe(side: str, frozen: dict[str, Any], root: Path) -> dict[str, Any]:
    item_id = frozen["item_id"]
    item = fetch_item(item_id)
    assets = item.get("assets") or {}
    safe_root = root / f"{item_id}.SAFE"
    manifest_expected = (frozen.get("assets") or {}).get("safe-manifest") or {}
    manifest_href = (assets.get("safe-manifest") or {}).get("href")
    if not manifest_href or not manifest_expected.get("sha256"):
        raise ValueError(f"{side} manifest identity unavailable")
    manifest_path = safe_root / "manifest.safe"
    m = download_verified(manifest_href, manifest_expected["sha256"], manifest_expected.get("bytes"), manifest_path)
    refs = manifest_locations(manifest_path)
    downloaded = {"safe-manifest": m}
    relative_paths = {"safe-manifest": "manifest.safe"}
    for key in REQUIRED_ASSETS[1:]:
        expected = (frozen.get("assets") or {}).get(key) or {}
        href = (assets.get(key) or {}).get("href")
        if not href or not expected.get("sha256"):
            raise ValueError(f"{side} missing frozen Earth Search asset {key}")
        rel = select_manifest_path(refs, key)
        target = safe_root.joinpath(*rel.parts)
        downloaded[key] = download_verified(href, expected["sha256"], expected.get("bytes"), target)
        relative_paths[key] = str(rel)
    return {
        "side": side,
        "item_id": item_id,
        "safe_root": str(safe_root),
        "manifest": str(manifest_path),
        "assets": downloaded,
        "frozen_asset_to_manifest_path": relative_paths,
        "status": "PASS_FROZEN_SAFE_RECONSTRUCTED",
    }


def find_case(doc: dict[str, Any], case_id: str) -> dict[str, Any]:
    rows = [x for x in doc.get("entries", []) if x.get("case_id") == case_id]
    if len(rows) != 1:
        raise ValueError(f"{case_id} expected exactly once, found {len(rows)}")
    return rows[0]


def stage_orbit(side: str, rec: dict[str, Any], user_home: Path) -> dict[str, Any]:
    acq = datetime.fromisoformat(rec["acquisition_utc"].replace("Z", "+00:00"))
    platform = rec["platform_code"]
    if platform not in {"S1A", "S1B"}:
        raise ValueError(f"unexpected platform code {platform}")
    daily = user_home / ".snap" / "auxdata" / "Orbits" / "Sentinel-1" / "POEORB" / platform / f"{acq.year:04d}" / f"{acq.month:02d}" / f"{acq.day:02d}"
    daily.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"ibvf-{side}-poeorb-") as td_raw:
        td = Path(td_raw)
        zip_path = td / Path(rec["url"]).name
        dl = download_verified(rec["url"], rec["zip_sha256"], rec["zip_bytes"], zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            member = rec["inner_eof_member"]
            if member not in names:
                raise ValueError(f"{side} frozen EOF member absent from verified ZIP")
            raw = zf.read(member)
        got = hashlib.sha256(raw).hexdigest()
        if got != rec["inner_eof_sha256"] or len(raw) != int(rec["inner_eof_bytes"]):
            raise ValueError(f"{side} inner EOF identity mismatch")
        eof = daily / Path(member).name
        eof.write_bytes(raw)
    return {
        "side": side,
        "platform_code": platform,
        "acquisition_utc": rec["acquisition_utc"],
        "source_zip_sha256": dl["sha256"],
        "source_zip_bytes": dl["bytes"],
        "staged_eof": str(eof),
        "staged_eof_filename": eof.name,
        "staged_eof_sha256": sha256_file(eof),
        "staged_eof_bytes": eof.stat().st_size,
        "status": "PASS_EXACT_AUX_POEORB_STAGED",
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


def run_side(side: str, gpt: Path, graph: Path, manifest: Path, dem: Path, output: Path, user_home: Path, orbit: dict[str, Any], log_path: Path) -> dict[str, Any]:
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
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=5400, env={**os.environ, "HOME": str(user_home)})
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    log_path.write_text(text, encoding="utf-8")
    orbit_logged = orbit["staged_eof_filename"] in text
    output_exists = output.is_file() and output.stat().st_size > 0
    row: dict[str, Any] = {
        "side": side,
        "returncode": proc.returncode,
        "gpt_command_without_signal_values": cmd,
        "log_sha256": sha256_file(log_path),
        "log_bytes": log_path.stat().st_size,
        "expected_aux_poeorb_filename": orbit["staged_eof_filename"],
        "expected_aux_poeorb_sha256": orbit["staged_eof_sha256"],
        "expected_aux_poeorb_logged": orbit_logged,
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
        "PASS_R2_SIDE_EXECUTED_EXPECTED_POEORB_LOGGED"
        if proc.returncode == 0 and output_exists and orbit_logged
        else "R2_SIDE_BLOCKED_OR_POEORB_CONSUMPTION_UNVERIFIED"
    )
    return row


def write_blocked(args: argparse.Namespace, base: dict[str, Any], stage: str, exc: Exception) -> int:
    base["status"] = f"{stage}_BLOCKED_UNKNOWN_NOT_MISSING"
    base["blocker"] = {"stage": stage, "error_class": type(exc).__name__, "message": str(exc)[:2000]}
    base["next_gate"] = "FIX_IMPLEMENTATION_OR_TRANSPORT_ONLY_WITHOUT_CHANGING_FROZEN_SCIENTIFIC_RULES"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": base["status"], "message": str(exc)[:500]}, indent=2))
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", type=Path, required=True)
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
    entry_doc = load(args.r2_entry)
    prereq_doc = load(args.prerequisites)
    dem_report = load(args.dem_report)
    for d in (contract, entry_doc, prereq_doc, dem_report):
        guard(d)
    if contract["status"] != "FROZEN_BEFORE_PRIMARY6_R2_SCIENCE_VALUES_GENERIC_EXECUTION_ALLOWED_ONLY_UNDER_THIS_CONTRACT":
        raise SystemExit("global execution contract not frozen")
    entry = find_case(entry_doc, args.case_id)
    prereq = find_case(prereq_doc, args.case_id)
    if entry["r2_entry_status"] != "PASS_R2_ENTRY_IDENTITY_FROZEN_EXECUTION_NOT_RUN":
        raise SystemExit("case is not an executable frozen R2 entry")
    if prereq["status"] != "PASS_EXACT_AUX_POEORB_BOTH_DATES_SHA256_FROZEN":
        raise SystemExit("exact R2 prerequisites are not frozen")
    if entry["case_control_role"] != "UNASSIGNED":
        raise SystemExit("case/control role must remain unassigned")
    unit_id = entry["unit_id"]
    unit = contract["unit_geometry_and_projection"][unit_id]
    identity_fields = ["unit_id", "season_id", "date_local", "source_window_execution_identity_sha256", "projection", "pre_item_id", "post_item_id"]
    for key in identity_fields:
        if entry[key] != prereq[key]:
            raise SystemExit(f"entry/prerequisite identity mismatch: {key}")
    if unit["target_projection"] != entry["projection"]:
        raise SystemExit("unit projection differs from frozen R2 entry")
    graph = Path(entry["r2_graph_path"])
    if str(graph) != unit["r2_graph_path"] or sha256_file(graph) != entry["r2_graph_sha256"] or entry["r2_graph_sha256"] != unit["r2_graph_sha256"]:
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
        raise SystemExit("DEM was not exactly reproduced from its archived freeze")
    if dem_report["target_projection"] != entry["projection"]:
        raise SystemExit("DEM target projection provenance mismatch")
    if sha256_file(args.dem) != dem_report["output_dem"]["sha256"]:
        raise SystemExit("actual DEM bytes differ from reproduced DEM report")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    user_home = args.work_dir / "home"
    user_home.mkdir(parents=True, exist_ok=True)
    base = {
        "schema_version": "irfen-ibvf-primary6-sentinel1-r2-execution-v0.1",
        "generated_at": now(),
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
        "execution_contract_path": str(args.contract),
        "execution_contract_sha256": sha256_file(args.contract),
        "r2_entry_path": str(args.r2_entry),
        "r2_entry_sha256": sha256_file(args.r2_entry),
        "prerequisites_path": str(args.prerequisites),
        "prerequisites_sha256": sha256_file(args.prerequisites),
        "r1_freeze_path": str(freeze),
        "r1_freeze_sha256": sha256_file(freeze),
        "r2_graph_path": str(graph),
        "r2_graph_sha256": sha256_file(graph),
        "target_projection": entry["projection"],
        "external_dem_sha256": sha256_file(args.dem),
        "external_dem_report_sha256": sha256_file(args.dem_report),
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

    try:
        orbit_pre = stage_orbit("pre", prereq["precise_orbits"]["pre"], user_home)
        orbit_post = stage_orbit("post", prereq["precise_orbits"]["post"], user_home)
    except Exception as exc:
        return write_blocked(args, base, "POEORB_STAGING", exc)
    base["orbit_staging"] = {"pre": orbit_pre, "post": orbit_post}

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
        return write_blocked(args, base, "SNAP_R2_RUNTIME", exc)

    base["pre"] = pre
    base["post"] = post
    both_outputs = pre["returncode"] == 0 and post["returncode"] == 0 and pre["output_exists"] and post["output_exists"]
    both_orbits = pre["expected_aux_poeorb_logged"] and post["expected_aux_poeorb_logged"]
    base["r2_processing_executed"] = bool(both_outputs)
    base["poeorb_consumption_verified_both_dates"] = bool(both_orbits)
    if both_outputs and both_orbits:
        base["status"] = "PASS_R2_PRE_POST_INDEPENDENT_PROCESSING_POEORB_VERIFIED_NO_COMPARISON"
        base["next_gate"] = "R3_COMMON_SUPPORT_MINIMUM_0_95_BEFORE_ANY_RADIOMETRIC_DIFFERENCE"
    elif both_outputs:
        base["status"] = "R2_OUTPUTS_EXIST_POEORB_CONSUMPTION_UNVERIFIED_R3_BLOCKED"
        base["next_gate"] = "RESOLVE_ORBIT_CONSUMPTION_VERIFICATION_WITHOUT_COMPARING_PRE_POST_PIXELS"
    else:
        base["status"] = "R2_EXECUTION_BLOCKED_UNKNOWN_NOT_MISSING"
        base["next_gate"] = "RESOLVE_RUNTIME_WITHOUT_CHANGING_FROZEN_SCIENTIFIC_RULES"

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
