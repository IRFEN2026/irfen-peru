#!/usr/bin/env python3
"""Metadata-only POEORB mismatch audit for blinded PRIMARY6 execution.

RESEARCH_ONLY / TEST_ONLY. It reads R2 JSON and GPT log metadata only, and may
redownload the exact POEORB ZIP URL requested by SNAP to fingerprint its bytes.
It never opens Sentinel-1 raster outputs or reads territorial outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import requests

ORBIT_URL_RE = re.compile(r"https?://step\.esa\.int/auxdata/orbits/Sentinel-1/POEORB/[^\s]+?\.EOF\.zip")
VALIDITY_RE = re.compile(r"_V(?P<start>\d{8}T\d{6})_(?P<end>\d{8}T\d{6})\.EOF\.zip$")
ACQ_RE = re.compile(r"_(?P<acq>\d{8}T\d{6})_\d{8}T\d{6}_")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def validity(filename: str) -> tuple[datetime, datetime]:
    m = VALIDITY_RE.search(filename)
    if not m:
        raise ValueError(f"cannot parse POEORB validity from {filename}")
    return parse_dt(m.group("start")), parse_dt(m.group("end"))


def acquisition(side_doc: dict[str, Any]) -> datetime:
    safe = side_doc.get("gpt_command_without_signal_values") or []
    joined = " ".join(str(x) for x in safe)
    m = ACQ_RE.search(joined)
    if not m:
        raise ValueError("cannot parse acquisition timestamp from GPT command")
    return parse_dt(m.group("acq"))


def path_catalog_month(url: str) -> str | None:
    parts = urlparse(url).path.strip("/").split("/")
    try:
        idx = parts.index("POEORB")
        return f"{parts[idx+2]}-{parts[idx+3]}"
    except (ValueError, IndexError):
        return None


def allowed_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname == "step.esa.int" and parsed.path.startswith("/auxdata/orbits/Sentinel-1/POEORB/") and parsed.path.endswith(".EOF.zip")


def fingerprint_url(url: str) -> dict[str, Any]:
    if not allowed_url(url):
        raise ValueError(f"refusing non-canonical POEORB URL: {url}")
    r = requests.get(url, timeout=180, headers={"User-Agent": "IRFEN-IBVF-RESEARCH-ONLY/0.1"})
    r.raise_for_status()
    data = r.content
    zip_filename = Path(urlparse(url).path).name
    target_eof_basename = zip_filename[:-4] if zip_filename.endswith(".zip") else zip_filename
    eof_inventory: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    duplicate_matches_byte_identical = False
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [x for x in zf.infolist() if not x.is_dir()]
        eof_members = [x for x in members if x.filename.endswith(".EOF")]
        if not eof_members:
            raise ValueError("POEORB ZIP contains no EOF members")
        for member in eof_members:
            eof = zf.read(member)
            item = {
                "member": member.filename,
                "member_basename": PurePosixPath(member.filename).name,
                "sha256": sha256(eof),
                "bytes": len(eof),
                "crc32_zip_metadata": f"{member.CRC:08x}",
                "exact_zip_stem_basename_match": PurePosixPath(member.filename).name == target_eof_basename,
            }
            eof_inventory.append(item)
        matches = [x for x in eof_inventory if x["exact_zip_stem_basename_match"]]
        if not matches:
            raise ValueError(
                f"no EOF member basename matches ZIP stem {target_eof_basename}; inventory={[x['member'] for x in eof_inventory]}"
            )
        identities = {(x["sha256"], x["bytes"], x["crc32_zip_metadata"]) for x in matches}
        if len(identities) != 1:
            raise ValueError(
                f"multiple basename-matching EOF members are not byte-identical; inventory={matches}"
            )
        duplicate_matches_byte_identical = len(matches) > 1
        selected = sorted(matches, key=lambda x: (x["member"].count("/"), x["member"]))[0]
    assert selected is not None
    return {
        "requested_url": url,
        "resolved_url": r.url,
        "zip_filename": zip_filename,
        "zip_sha256": sha256(data),
        "zip_bytes": len(data),
        "eof_member_count": len(eof_inventory),
        "eof_member_inventory": eof_inventory,
        "matching_eof_member_count": len([x for x in eof_inventory if x["exact_zip_stem_basename_match"]]),
        "duplicate_matching_eof_members_byte_identical": duplicate_matches_byte_identical,
        "selected_inner_eof_member_rule": "EXACT_BASENAME_MATCH_TO_REQUESTED_ZIP_STEM; IF_DUPLICATED_REQUIRE_BYTE_IDENTITY_THEN_SHORTEST_PATH_LEXICAL",
        "inner_eof_member": selected["member"],
        "inner_eof_sha256": selected["sha256"],
        "inner_eof_bytes": selected["bytes"],
        "inner_eof_crc32_zip_metadata": selected["crc32_zip_metadata"],
        "catalog_month_from_url": path_catalog_month(url),
    }


def find_log(case_dir: Path, side: str) -> Path:
    p = case_dir / "execution-v02" / f"{side}_gpt.log"
    if p.is_file():
        return p
    matches = list(case_dir.rglob(f"{side}_gpt.log"))
    if len(matches) != 1:
        raise ValueError(f"expected one {side}_gpt.log in {case_dir}; found {len(matches)}")
    return matches[0]


def audit_case(case_dir: Path) -> list[dict[str, Any]]:
    r2 = load(case_dir / "r2-v02.json")
    if r2.get("deployment_status") != "RESEARCH_ONLY" or r2.get("test_only") is not True:
        raise ValueError("R2 research/test guard mismatch")
    if r2.get("production_use") is not False or r2.get("production_ready") is not False:
        raise ValueError("R2 production guard mismatch")
    if r2.get("operational_alerting_enabled") is not False:
        raise ValueError("R2 operational alerting guard mismatch")
    if r2.get("territorial_activation_evidence_blinded") is not True or r2.get("territorial_outcomes_read") is not False:
        raise ValueError("R2 blindness guard mismatch")

    out: list[dict[str, Any]] = []
    for side in ("pre", "post"):
        s = r2.get(side) or {}
        if s.get("requested_exact_v02_frozen_resource") is not False:
            continue
        requested_names = s.get("requested_aux_poeorb_filenames") or []
        if len(requested_names) != 1:
            raise ValueError("expected exactly one SNAP-requested POEORB filename")
        requested_name = requested_names[0]
        log = find_log(case_dir, side)
        urls = ORBIT_URL_RE.findall(log.read_text(encoding="utf-8", errors="replace"))
        urls = list(dict.fromkeys(urls))
        if len(urls) != 1:
            raise ValueError(f"expected exactly one canonical POEORB URL in {log}; found {len(urls)}")
        if Path(urlparse(urls[0]).path).name != requested_name:
            raise ValueError("GPT log requested URL filename differs from R2 report")
        observed = fingerprint_url(urls[0])
        expected_name = s["expected_aux_poeorb_zip_filename"]
        expected_start, expected_end = validity(expected_name)
        actual_start, actual_end = validity(requested_name)
        acq = acquisition(s)
        expected_url = (r2.get("frozen_orbit_resource_verification") or {}).get(side, {}).get("url")
        expected_catalog_month = path_catalog_month(expected_url) if expected_url else None
        acq_month = acq.strftime("%Y-%m")
        out.append({
            "schema_version": "irfen-ibvf-primary6-orbit-resource-audit-v0.1",
            "generated_at": now(),
            "case_id": r2["case_id"],
            "unit_id": r2["unit_id"],
            "season_id": r2.get("season_id"),
            "date_local": r2.get("date_local"),
            "side": side,
            "deployment_status": "RESEARCH_ONLY",
            "test_only": True,
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "territorial_activation_evidence_blinded": True,
            "source_r2_status": r2.get("status"),
            "source_side_status": s.get("status"),
            "frozen_selector_version": r2.get("poeorb_selector_version"),
            "frozen_selector_rule": r2.get("poeorb_selector_rule"),
            "acquisition_utc": acq.isoformat().replace("+00:00", "Z"),
            "acquisition_catalog_month": acq_month,
            "expected_frozen_zip_filename": expected_name,
            "expected_frozen_zip_sha256": s.get("frozen_zip_sha256"),
            "expected_validity_start_utc": expected_start.isoformat().replace("+00:00", "Z"),
            "expected_validity_end_utc": expected_end.isoformat().replace("+00:00", "Z"),
            "expected_covers_acquisition": expected_start <= acq <= expected_end,
            "expected_catalog_month_from_frozen_url": expected_catalog_month,
            "snap_requested_zip_filename": requested_name,
            "snap_requested_validity_start_utc": actual_start.isoformat().replace("+00:00", "Z"),
            "snap_requested_validity_end_utc": actual_end.isoformat().replace("+00:00", "Z"),
            "snap_requested_covers_acquisition": actual_start <= acq <= actual_end,
            "snap_requested_catalog_month_matches_acquisition_month": observed["catalog_month_from_url"] == acq_month,
            "expected_catalog_month_matches_acquisition_month": expected_catalog_month == acq_month,
            "observed_requested_resource": observed,
            "selector_diagnostic": "BOTH_RESOURCES_COVER_ACQUISITION_BUT_SNAP_REQUESTS_RESOURCE_IN_ACQUISITION_CATALOG_MONTH" if (expected_start <= acq <= expected_end and actual_start <= acq <= actual_end and observed["catalog_month_from_url"] == acq_month and expected_catalog_month != acq_month) else "MISMATCH_REQUIRES_ADDITIONAL_METADATA_REVIEW",
            "selector_contract_changed": False,
            "resource_accepted_as_canonical_by_this_audit": False,
            "raster_files_opened": False,
            "raster_pixels_read": False,
            "radiometric_values_read": False,
            "r4_values_read": False,
            "territorial_outcomes_read": False,
            "known_event_dates_read": False,
            "case_control_role_assigned": False,
            "activation_inference_allowed": False,
            "modeling_allowed": False,
            "status": "PASS_METADATA_ONLY_POEORB_MISMATCH_FINGERPRINTED_NOT_ACCEPTED",
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    audits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for r2_path in sorted(args.artifact_root.rglob("r2-v02.json")):
        for item in audit_case(r2_path.parent):
            key = (item["case_id"], item["side"])
            if key not in seen:
                seen.add(key)
                audits.append(item)

    summary = {
        "schema_version": "irfen-ibvf-primary6-orbit-resource-audit-summary-v0.1",
        "generated_at": now(),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "territorial_activation_evidence_blinded": True,
        "mismatches_fingerprinted": len(audits),
        "all_are_cross_catalog_month_overlap_diagnostic": bool(audits) and all(x["selector_diagnostic"] == "BOTH_RESOURCES_COVER_ACQUISITION_BUT_SNAP_REQUESTS_RESOURCE_IN_ACQUISITION_CATALOG_MONTH" for x in audits),
        "selector_contract_changed": False,
        "resource_accepted_as_canonical_by_this_audit": False,
        "raster_files_opened": False,
        "raster_pixels_read": False,
        "radiometric_values_read": False,
        "r4_values_read": False,
        "territorial_outcomes_read": False,
        "case_control_role_assigned": False,
        "activation_inference_allowed": False,
        "modeling_allowed": False,
        "audits": audits,
        "status": "PASS_METADATA_ONLY_POEORB_MISMATCH_AUDIT_NOT_ACCEPTED" if audits else "NO_POEORB_MISMATCH_FOUND",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if audits else 4


if __name__ == "__main__":
    raise SystemExit(main())
