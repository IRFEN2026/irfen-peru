#!/usr/bin/env python3
"""Install and freeze exact SNAP runtime metadata after verified installer bytes.

RESEARCH_ONLY / TEST_ONLY. The installer is re-downloaded and SHA-256 checked
against the preregistered ESA value immediately before unattended installation.
No SNAP update command is invoked. No Sentinel-1 response values are read and no
pre/post comparison or activation inference is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = "IRFEN-IBVF/0.3 RESEARCH_ONLY TEST_ONLY"
CHUNK = 8 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); n = 0
    with path.open("rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b); n += len(b)
    return h.hexdigest(), n


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def base(c: dict) -> dict:
    return {
        "schema_version": "irfen-ibvf-snap-runtime-install-freeze-v0.1",
        "generated_at": now(),
        "case_id": c["case_id"],
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
        "automatic_update_invoked": False,
        "r2_processing_executed": False,
        "r3_common_support_built": False,
        "r4_difference_computed": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--byte-report", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    a = ap.parse_args()

    c = json.loads(a.contract.read_text(encoding="utf-8"))
    b = json.loads(a.byte_report.read_text(encoding="utf-8"))
    for d in (c, b):
        assert d["deployment_status"] == "RESEARCH_ONLY"
        assert d["test_only"] is True
        assert d["production_use"] is False
        assert d["production_ready"] is False
        assert d["operational_alerting_enabled"] is False
        assert d["uses_operational_event_none_labels"] is False
        assert d["territorial_activation_evidence_blinded"] is True
    assert b["installer_byte_verified"] is True and b["sha256_match"] is True
    assert b["status"] == "INSTALLER_BYTES_VERIFIED_INSTALLATION_METADATA_PENDING"

    expected = c["published_checksum_freeze"]["published_installer_sha256"].lower()
    assert b["actual_installer_sha256"].lower() == expected
    rel = c["official_release"]
    url = rel["linux_sentinel_toolboxes_installer_url"]
    filename = rel["installer_filename"]

    report = base(c)
    report.update({
        "installer_filename": filename,
        "installer_url": url,
        "expected_installer_sha256": expected,
        "prior_byte_freeze_sha256": b["actual_installer_sha256"].lower(),
        "download_integrity_gate": "PENDING_REVERIFY_BEFORE_INSTALL",
        "installation_runtime_metadata_gate": "PENDING",
        "r2_execution_allowed_by_runtime_gate": False,
        "r2_execution_allowed": False,
    })

    if a.work_dir.exists():
        shutil.rmtree(a.work_dir)
    a.work_dir.mkdir(parents=True, exist_ok=True)
    installer = a.work_dir / filename
    install_dir = a.work_dir / "snap14"

    h = hashlib.sha256(); n = 0
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=(30, 180), headers={"User-Agent": UA}) as r:
            r.raise_for_status()
            report["http_status"] = r.status_code
            report["response_content_length"] = r.headers.get("Content-Length")
            report["response_last_modified"] = r.headers.get("Last-Modified")
            with installer.open("wb") as f:
                for chunk in r.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    f.write(chunk); h.update(chunk); n += len(chunk)
    except Exception as exc:
        report.update({
            "status": "TRANSPORT_BLOCKED_UNKNOWN_NOT_MISSING",
            "transport_status": "TRANSPORT_BLOCKED",
            "downloaded_bytes_before_failure": n,
            "error": repr(exc),
            "download_integrity_gate": "UNKNOWN_TRANSPORT_BLOCKED",
        })
        write_report(a.output, report)
        print(json.dumps({"status": report["status"], "downloaded_bytes": n}, sort_keys=True))
        return 0

    actual = h.hexdigest()
    report.update({"downloaded_bytes": n, "installer_sha256_reverified": actual, "sha256_match": actual == expected})
    if actual != expected:
        report.update({
            "status": "CHECKSUM_MISMATCH_FAIL_CLOSED",
            "download_integrity_gate": "FAIL",
            "installation_runtime_metadata_gate": "BLOCKED",
        })
        write_report(a.output, report)
        print(json.dumps({"status": report["status"], "actual": actual, "expected": expected}, sort_keys=True))
        return 0
    report["download_integrity_gate"] = "PASS_REVERIFIED_IMMEDIATELY_BEFORE_INSTALL"

    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
    cmd = [str(installer), "-q", "-dir", str(install_dir)]
    report["install_command_contract"] = [filename, "-q", "-dir", "<EPHEMERAL_INSTALL_DIR>"]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
    except Exception as exc:
        report.update({
            "status": "INSTALLATION_BLOCKED_UNKNOWN_NOT_MISSING",
            "installation_runtime_metadata_gate": "UNKNOWN_INSTALLATION_BLOCKED",
            "error": repr(exc),
        })
        write_report(a.output, report)
        print(json.dumps({"status": report["status"]}, sort_keys=True))
        return 0
    report["installer_returncode"] = p.returncode
    report["installer_output_tail"] = p.stdout[-6000:]
    if p.returncode != 0:
        report.update({
            "status": "INSTALLATION_BLOCKED_UNKNOWN_NOT_MISSING",
            "installation_runtime_metadata_gate": "UNKNOWN_INSTALLATION_BLOCKED",
        })
        write_report(a.output, report)
        print(json.dumps({"status": report["status"], "returncode": p.returncode}, sort_keys=True))
        return 0

    gpt = install_dir / "bin" / "gpt"
    snap = install_dir / "bin" / "snap"
    if not gpt.exists():
        report.update({"status": "RUNTIME_METADATA_GATE_FAIL_CLOSED", "installation_runtime_metadata_gate": "FAIL_GPT_MISSING"})
        write_report(a.output, report); print(json.dumps({"status": report["status"]})); return 0

    diag = subprocess.run([str(gpt), "--diag"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
    report["gpt_diag_returncode"] = diag.returncode
    report["gpt_diag"] = diag.stdout[-12000:]
    m = re.search(r"SNAP Release version\s+([^\s]+)", diag.stdout)
    release = m.group(1) if m else None
    report["gpt_release_version"] = release

    modules_out = ""; modules_rc = None
    if snap.exists():
        try:
            mp = subprocess.run([str(snap), "--nosplash", "--nogui", "--modules", "--list"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
            modules_rc = mp.returncode; modules_out = mp.stdout
        except Exception as exc:
            modules_out = repr(exc)
    report["modules_list_returncode"] = modules_rc
    report["modules_list_output_sha256"] = hashlib.sha256(modules_out.encode("utf-8", errors="replace")).hexdigest()
    report["modules_list_line_count"] = len(modules_out.splitlines())
    report["modules_list_tail"] = modules_out[-8000:]

    jars = sorted(install_dir.rglob("*.jar"))
    mh = hashlib.sha256(); total_jar_bytes = 0
    for jar in jars:
        jsha, jn = sha256_file(jar); total_jar_bytes += jn
        relp = jar.relative_to(install_dir).as_posix()
        mh.update(f"{relp}\t{jn}\t{jsha}\n".encode("utf-8"))
    report["installed_jar_count"] = len(jars)
    report["installed_jar_total_bytes"] = total_jar_bytes
    report["installed_jar_manifest_sha256"] = mh.hexdigest()
    report["top_level_entries"] = sorted(x.name for x in install_dir.iterdir()) if install_dir.exists() else []
    report["microwave_toolbox_directory_present"] = (install_dir / "s1tbx").exists()
    report["gpt_launcher_sha256"], report["gpt_launcher_bytes"] = sha256_file(gpt)

    expected_version = rel["version"]
    runtime_pass = (
        diag.returncode == 0
        and release == expected_version
        and report["microwave_toolbox_directory_present"] is True
        and report["installed_jar_count"] > 0
    )
    if runtime_pass:
        report.update({
            "status": "SNAP_RUNTIME_METADATA_FROZEN_R2_EXECUTION_GATE_PASS",
            "installation_runtime_metadata_gate": "PASS",
            "r2_execution_allowed_by_runtime_gate": True,
            "r2_execution_allowed": True,
            "next_gate": "EXECUTE_IDENTICAL_PREREGISTERED_R2_GRAPH_PRE_AND_POST_THEN_BUILD_R3_COMMON_SUPPORT",
        })
    else:
        report.update({
            "status": "RUNTIME_METADATA_GATE_FAIL_CLOSED",
            "installation_runtime_metadata_gate": "FAIL",
            "r2_execution_allowed_by_runtime_gate": False,
            "r2_execution_allowed": False,
        })

    installer.unlink(missing_ok=True)
    write_report(a.output, report)
    print(json.dumps({
        "status": report["status"],
        "release": release,
        "jar_count": report["installed_jar_count"],
        "jar_manifest_sha256": report["installed_jar_manifest_sha256"],
        "microwave_toolbox": report["microwave_toolbox_directory_present"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
