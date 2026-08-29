#!/usr/bin/env python3
"""Verify the exact ESA SNAP installer bytes against the preregistered SHA-256.

IRFEN Independent Basin Validation Framework only.
RESEARCH_ONLY / TEST_ONLY. This script never reads Sentinel-1 response values,
never compares pre/post scenes, and never infers activation. Transport failure
is preserved as UNKNOWN/TRANSPORT_BLOCKED rather than being mislabeled MISSING.
A byte-hash PASS only closes the download-integrity gate; installation/runtime
metadata must still be frozen before R2 execution is allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = "IRFEN-IBVF/0.2 RESEARCH_ONLY TEST_ONLY"
CHUNK = 8 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def base_report(contract: dict) -> dict:
    return {
        "schema_version": "irfen-ibvf-snap-runtime-installer-byte-freeze-v0.1",
        "generated_at": now(),
        "case_id": contract["case_id"],
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "pre_post_sar_values_read": False,
        "comparison_performed": False,
        "activation_inference_allowed": False,
        "scientific_data_status": "NOT_APPLICABLE_RUNTIME_RESOURCE",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--download-dir", required=True, type=Path)
    args = ap.parse_args()

    c = json.loads(args.contract.read_text(encoding="utf-8"))
    assert c["deployment_status"] == "RESEARCH_ONLY"
    assert c["test_only"] is True
    assert c["production_use"] is False
    assert c["production_ready"] is False
    assert c["operational_alerting_enabled"] is False
    assert c["uses_operational_event_none_labels"] is False
    assert c["territorial_activation_evidence_blinded"] is True
    assert c["comparison_performed"] is False
    assert c["activation_inference_allowed"] is False
    assert c["published_checksum_without_installer_byte_verification_sufficient_for_r2_execution"] is False

    rel = c["official_release"]
    expected = c["published_checksum_freeze"]["published_installer_sha256"].lower()
    if len(expected) != 64:
        raise RuntimeError("preregistered published installer SHA-256 is not 64 hex chars")
    url = rel["linux_sentinel_toolboxes_installer_url"]
    filename = rel["installer_filename"]

    report = base_report(c)
    report.update(
        {
            "installer_filename": filename,
            "installer_url": url,
            "expected_published_sha256": expected,
            "installer_byte_verified": False,
            "download_integrity_gate": "PENDING",
            "installation_runtime_metadata_gate": "PENDING",
            "r2_execution_allowed_by_runtime_gate": False,
            "r2_execution_allowed": False,
        }
    )

    args.download_dir.mkdir(parents=True, exist_ok=True)
    target = args.download_dir / filename
    h = hashlib.sha256()
    nbytes = 0
    try:
        with requests.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=(30, 180),
            headers={"User-Agent": UA},
        ) as r:
            r.raise_for_status()
            report["http_status"] = r.status_code
            report["response_content_length"] = r.headers.get("Content-Length")
            report["response_last_modified"] = r.headers.get("Last-Modified")
            report["response_etag"] = r.headers.get("ETag")
            with target.open("wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    f.write(chunk)
                    h.update(chunk)
                    nbytes += len(chunk)
    except Exception as exc:
        report.update(
            {
                "status": "TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING",
                "transport_status": "TRANSPORT_BLOCKED",
                "error": repr(exc),
                "downloaded_bytes_before_failure": nbytes,
                "download_integrity_gate": "UNKNOWN_TRANSPORT_BLOCKED",
                "installer_byte_verified": False,
                "r2_execution_allowed_by_runtime_gate": False,
                "r2_execution_allowed": False,
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if target.exists():
            target.unlink()
        print(json.dumps({"status": report["status"], "downloaded_bytes": nbytes}, sort_keys=True))
        return 0

    actual = h.hexdigest()
    report.update(
        {
            "downloaded_bytes": nbytes,
            "actual_installer_sha256": actual,
            "sha256_match": actual == expected,
        }
    )

    if actual != expected:
        report.update(
            {
                "status": "CHECKSUM_MISMATCH_FAIL_CLOSED",
                "download_integrity_gate": "FAIL",
                "installer_byte_verified": False,
                "r2_execution_allowed_by_runtime_gate": False,
                "r2_execution_allowed": False,
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        target.unlink(missing_ok=True)
        print(json.dumps({"status": report["status"], "actual": actual, "expected": expected}, sort_keys=True))
        return 2

    report.update(
        {
            "status": "INSTALLER_BYTES_VERIFIED_INSTALLATION_METADATA_PENDING",
            "transport_status": "SUCCESS",
            "download_integrity_gate": "PASS",
            "installer_byte_verified": True,
            "installation_runtime_metadata_gate": "PENDING",
            "r2_execution_allowed_by_runtime_gate": False,
            "r2_execution_allowed": False,
            "next_gate": "INSTALL_NONINTERACTIVELY_AND_FREEZE_GPT_VERSION_AND_MODULE_METADATA",
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    target.unlink(missing_ok=True)
    print(json.dumps({"status": report["status"], "bytes": nbytes, "sha256": actual}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
