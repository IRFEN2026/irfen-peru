#!/usr/bin/env python3
"""Synchronize frozen SNAP runtime gates into the RESEARCH_ONLY IBVF map.

This is a projection of already-frozen evidence. It does not execute R2, read
SAR response values, compare pre/post scenes, assign case/control roles, or
change any operational IRFEN state.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def guard(d: dict, label: str) -> None:
    assert d.get("deployment_status") == "RESEARCH_ONLY", label
    assert d.get("test_only") is True, label
    assert d.get("production_use") is False, label
    assert d.get("production_ready") is False, label
    assert d.get("operational_alerting_enabled") is False, label
    assert d.get("uses_operational_event_none_labels") is False, label
    assert d.get("territorial_activation_evidence_blinded") is True, label
    assert d.get("serious_modeling_gate") == "CLOSED_MINIMUM_DATASET_NOT_REACHED", label


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--byte-report", required=True, type=Path)
    ap.add_argument("--runtime-report", required=True, type=Path)
    a = ap.parse_args()

    m = load(a.manifest); b = load(a.byte_report); r = load(a.runtime_report)
    for d, label in ((m, "manifest"), (b, "byte-report"), (r, "runtime-report")):
        guard(d, label)

    assert b["status"] == "INSTALLER_BYTES_VERIFIED_INSTALLATION_METADATA_PENDING"
    assert b["installer_byte_verified"] is True and b["sha256_match"] is True
    assert r["status"] == "SNAP_RUNTIME_METADATA_FROZEN_R2_EXECUTION_GATE_PASS"
    assert r["download_integrity_gate"] == "PASS_REVERIFIED_IMMEDIATELY_BEFORE_INSTALL"
    assert r["installation_runtime_metadata_gate"] == "PASS"
    assert r["r2_execution_allowed_by_runtime_gate"] is True
    assert r["gpt_release_version"] == "14.0.0"
    assert r["microwave_toolbox_directory_present"] is True
    assert r["microwave_toolbox_kit_module_enabled"] is True
    assert r["pre_post_sar_values_read"] is False
    assert r["comparison_performed"] is False
    assert r["r2_processing_executed"] is False
    assert r["r3_common_support_built"] is False
    assert r["r4_difference_computed"] is False
    assert r["activation_inference_allowed"] is False
    assert b["actual_installer_sha256"] == r["installer_sha256_reverified"]

    m["version"] = "irfen-independent-basin-validation-map-v2.0"
    m["generated_at"] = now()
    acq = m.setdefault("acquisition_contract", {})
    acq["sentinel1_r2_runtime_bytes_report"] = "site/data/validation/cashahuacra_sentinel1_r2_runtime_bytes.json"
    acq["sentinel1_r2_runtime_install_report"] = "site/data/validation/cashahuacra_sentinel1_r2_runtime_install.json"
    lv = acq.setdefault("local_validation", {})
    lv["sentinel1_a4_r2_snap14_published_checksum"] = "PASS_786CE26A"
    lv["sentinel1_a4_r2_snap14_installer_bytes"] = "PASS_1126783270_BYTES_SHA256_MATCH"
    lv["sentinel1_a4_r2_snap14_runtime_metadata"] = "PASS_SNAP_14_0_0_MICROWAVE_TOOLBOX_ENABLED_1090_JARS"

    c = next(x for x in m["cases"] if x["unit_id"] == "cashahuacra")
    c["framework_stage"] = "A4_R1_COMPLETE_R2_RESOURCE_AND_RUNTIME_GATES_PASS_EXECUTION_ALLOWED_NO_DIFFERENCE"
    c["remote_sensing_status"] = "S1_A4_R1_COMPLETE_R2_RESOURCE_AND_SNAP14_RUNTIME_GATES_PASS_IDENTICAL_GRAPH_EXECUTION_ALLOWED_NO_PREPOST_DIFFERENCE"
    c["sentinel1_r2_status"] = "PREREGISTERED_R2_RESOURCE_AND_RUNTIME_GATES_PASS_IDENTICAL_GRAPH_EXECUTION_ALLOWED_NO_DIFFERENCE_YET"
    c["sentinel1_r2_execution_gate"] = "PASS_RESOURCE_AND_RUNTIME_GATES_IDENTICAL_R2_GRAPH_EXECUTION_ALLOWED"
    c["sentinel1_r2_runtime_bytes_path"] = "data/validation/cashahuacra_sentinel1_r2_runtime_bytes.json"
    c["sentinel1_r2_runtime_install_path"] = "data/validation/cashahuacra_sentinel1_r2_runtime_install.json"
    c["sentinel1_r2_runtime_installer_byte_verified"] = True
    c["sentinel1_r2_runtime_installer_bytes"] = b["downloaded_bytes"]
    c["sentinel1_r2_runtime_installer_sha256"] = b["actual_installer_sha256"]
    c["sentinel1_r2_runtime_snap_version"] = r["gpt_release_version"]
    c["sentinel1_r2_runtime_java_version"] = "21.0.6"
    c["sentinel1_r2_runtime_microwave_toolbox_enabled"] = True
    c["sentinel1_r2_runtime_installed_jar_count"] = r["installed_jar_count"]
    c["sentinel1_r2_runtime_installed_jar_manifest_sha256"] = r["installed_jar_manifest_sha256"]
    c["sentinel1_r2_runtime_gpt_launcher_sha256"] = r["gpt_launcher_sha256"]
    c["sentinel1_r2_runtime_gate"] = "PASS_SNAP14_INSTALLER_BYTES_AND_INSTALLED_RUNTIME_METADATA_FROZEN"
    c["sentinel1_prepost_difference_computed"] = False

    # Guard all scientific/non-operational invariants after projection.
    guard(m, "updated-manifest")
    assert c["sentinel1_prepost_difference_computed"] is False
    assert c["blind_status"] == "TERRITORIAL_EVIDENCE_SEALED"
    assert c["smap_status"] == "MISSING_FOR_EVENT_WINDOW"
    assert m["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"
    for x in m["cases"]:
        assert x["production_use"] is False
        assert x["production_ready"] is False
        assert x["operational_alerting_enabled"] is False

    a.manifest.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "version": m["version"],
        "cashahuacra_stage": c["framework_stage"],
        "runtime_gate": c["sentinel1_r2_runtime_gate"],
        "prepost_difference": c["sentinel1_prepost_difference_computed"],
        "serious_modeling_gate": m["serious_modeling_gate"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
