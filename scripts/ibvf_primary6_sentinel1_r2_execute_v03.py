#!/usr/bin/env python3
"""Run PRIMARY6 R2 v0.2 engine with the preregistered blinded blocker amendment.

RESEARCH_ONLY / TEST_ONLY. The amendment is intentionally narrow: only the
preidentified San Ildefonso 2018-02-25 POST acquisition receives the exact
SNAP14-requested AUX_POEORB bytes frozen by the metadata-only audit. No raster
values, R4 values, territorial outcomes, event dates, or case/control roles are
read to choose the override. All unaffected cases use the original v0.2 inputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import ibvf_primary6_sentinel1_r2_execute_v02 as core

AMENDMENT_STATUS = "FROZEN_SIGNAL_BLIND_BLOCKER_AMENDMENT_BEFORE_REPAIR_RERUN_NO_OUTCOMES_NO_R4_MAGNITUDES"
EFFECTIVE_SELECTOR = "SNAP14_POEORB_V03_EXACT_PREIDENTIFIED_MONTH_BOUNDARY_RESOURCE_FREEZE"
EFFECTIVE_RULE = "EXACT_PREIDENTIFIED_SNAP14_REQUESTED_AUX_POEORB_FILENAME_AND_SHA256_FOR_MONTH_BOUNDARY_CASE_ONLY; GLOBAL_V02_RULE_UNCHANGED_ELSEWHERE"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def arg_value(argv: list[str], name: str) -> str:
    try:
        return argv[argv.index(name) + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"missing required wrapper argument {name}") from exc


def strip_pair(argv: list[str], name: str) -> tuple[list[str], str]:
    try:
        i = argv.index(name)
        value = argv[i + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"missing required wrapper argument {name}") from exc
    return argv[:i] + argv[i + 2 :], value


def guard_amendment(doc: dict[str, Any]) -> None:
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_only"] is True
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["territorial_activation_evidence_blinded"] is True
    assert doc["status"] == AMENDMENT_STATUS
    assert doc["r4_values_read_during_amendment_design"] is False
    assert doc["territorial_outcomes_read_during_amendment_design"] is False
    assert doc["known_event_dates_read_during_amendment_design"] is False
    assert doc["case_control_role_assigned_during_amendment_design"] is False


def main() -> int:
    argv = sys.argv[1:]
    argv, amendment_arg = strip_pair(argv, "--blocker-amendment")
    case_id = arg_value(argv, "--case-id")
    prereq_path = Path(arg_value(argv, "--prerequisites"))
    output_path = Path(arg_value(argv, "--output"))
    amendment_path = Path(amendment_arg)
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    guard_amendment(amendment)
    amend_sha = sha256_file(amendment_path)

    orbit_amend = amendment["poeorb_catalog_scope_amendment"]
    affected_case = orbit_amend["affected_case_id"]
    affected_side = orbit_amend["affected_side"]
    if affected_side != "post":
        raise SystemExit("unexpected preregistered POEORB amendment side")
    apply_override = case_id == affected_case

    original_load = core.load

    def amended_load(path: Path) -> dict[str, Any]:
        doc = original_load(path)
        if Path(path) != prereq_path or not apply_override:
            return doc
        if doc.get("schema_version") != "irfen-ibvf-primary6-sentinel1-r2-prerequisites-v0.2":
            raise ValueError("POEORB override may only patch the frozen v0.2 prerequisites in memory")
        patched = copy.deepcopy(doc)
        rows = [x for x in patched.get("entries", []) if x.get("case_id") == case_id]
        if len(rows) != 1:
            raise ValueError("affected case absent or duplicated in frozen prerequisites")
        row = rows[0]
        rec = row["precise_orbits"][affected_side]
        frozen = orbit_amend["snap14_observed_requested_resource"]
        if rec.get("side") != affected_side:
            raise ValueError("frozen prerequisite side mismatch")
        if rec.get("acquisition_utc", "").replace("+00:00", "Z") != orbit_amend["acquisition_utc"]:
            raise ValueError("frozen prerequisite acquisition timestamp differs from preregistered amendment")
        rec.update({
            "status": "PASS",
            "selector_version": EFFECTIVE_SELECTOR,
            "selection_rule": EFFECTIVE_RULE,
            "filename": frozen["filename"],
            "url": frozen["url"],
            "validity_start": frozen["validity_start_utc"].replace("Z", "+00:00"),
            "validity_stop": frozen["validity_end_utc"].replace("Z", "+00:00"),
            "zip_sha256": frozen["zip_sha256"],
            "zip_bytes": frozen["zip_bytes"],
            "inner_eof_member": frozen["filename"][:-4],
            "inner_eof_member_count": frozen["duplicate_matching_eof_members"],
            "inner_eof_duplicate_payloads_identical": frozen["duplicate_matching_eof_members_byte_identical"],
            "inner_eof_sha256": frozen["inner_eof_sha256"],
            "inner_eof_bytes": frozen["inner_eof_bytes"],
            "product_class_aux_poeorb_confirmed": True,
            "validity_covers_acquisition": True,
        })
        patched["effective_signal_blind_blocker_amendment_sha256"] = amend_sha
        patched["effective_poeorb_override_case_id"] = case_id
        patched["effective_poeorb_override_side"] = affected_side
        return patched

    core.load = amended_load
    original_argv = sys.argv
    sys.argv = [original_argv[0]] + argv
    try:
        rc = core.main()
    finally:
        sys.argv = original_argv
        core.load = original_load

    if output_path.is_file():
        report = json.loads(output_path.read_text(encoding="utf-8"))
        report["signal_blind_blocker_amendment_path"] = str(amendment_path)
        report["signal_blind_blocker_amendment_sha256"] = amend_sha
        report["poeorb_catalog_scope_amendment_applied"] = apply_override
        report["legacy_v02_selector_rule_retained_for_unaffected_cases"] = True
        report["effective_poeorb_selector_version"] = EFFECTIVE_SELECTOR if apply_override else report.get("poeorb_selector_version")
        report["effective_poeorb_selector_rule"] = EFFECTIVE_RULE if apply_override else report.get("poeorb_selector_rule")
        report["prerequisite_file_modified_on_disk"] = False
        report["prerequisite_in_memory_exact_resource_override_applied"] = apply_override
        report["r4_values_read_for_override_decision"] = False
        report["territorial_outcomes_read_for_override_decision"] = False
        report["known_event_dates_read_for_override_decision"] = False
        report["case_control_role_used_for_override_decision"] = False
        if apply_override and rc == 0:
            frozen = orbit_amend["snap14_observed_requested_resource"]
            if report[affected_side]["expected_aux_poeorb_zip_filename"] != frozen["filename"]:
                raise SystemExit("post-run effective POEORB filename differs from preregistered exact resource")
            if report[affected_side]["frozen_zip_sha256"] != frozen["zip_sha256"]:
                raise SystemExit("post-run effective POEORB ZIP hash differs from preregistered exact resource")
            if report[affected_side]["requested_exact_v02_frozen_resource"] is not True:
                raise SystemExit("SNAP14 did not request the preregistered exact month-boundary resource")
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
