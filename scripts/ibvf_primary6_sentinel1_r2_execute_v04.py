#!/usr/bin/env python3
"""Run PRIMARY6 R2 through the frozen v0.3 blocker amendment with transport-only repair.

RESEARCH_ONLY / TEST_ONLY. This wrapper changes no selected window, Sentinel-1
pair, POEORB scientific selector, orbit bytes, R2 graph, DEM, R3/R4 rule, or
territorial gate. It only pre-seeds SNAP 14's local POEORB cache with the exact
AUX_POEORB ZIP that v0.2 already downloaded and SHA-256 verified, avoiding a
non-deterministic STEP directory/download timeout observed in the blind bulk
run. It also applies one metadata-transcription erratum for the already frozen
San Ildefonso 2018-02-25 POST blocker: the authoritative acquisition timestamp
is the immutable v0.2 prerequisite timestamp; the v0.1 blocker-amendment field
was copied incorrectly. No signal pixels, R4 values, outcomes, event dates, or
case/control roles are consulted.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ibvf_primary6_sentinel1_r2_execute_v03 as amended

PARENT_BLOCKER_AMENDMENT_SHA256 = "bbc0b3cd9f520911703b0a98f4a1d58f7f4bd2cebc1d13c1604401e8ae33ef7a"
AFFECTED_CASE = "primary6_san_ildefonso_2018-02-25"
AFFECTED_SIDE = "post"
ERRONEOUS_TRANSCRIBED_ACQUISITION_UTC = "2018-03-01T23:34:05Z"
AUTHORITATIVE_PREREQUISITE_ACQUISITION_UTC = "2018-03-01T23:34:17.838693Z"
POEORB_NAME = re.compile(r"^(S1[AB])_OPER_AUX_POEORB_.*_V(\d{4})(\d{2})\d{2}T\d{6}_")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone-naive timestamp")
    return dt.astimezone(timezone.utc)


def arg_value(argv: list[str], name: str) -> str:
    try:
        return argv[argv.index(name) + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"missing required wrapper argument {name}") from exc


def find_case(doc: dict[str, Any], case_id: str) -> dict[str, Any]:
    rows = [x for x in doc.get("entries", []) if x.get("case_id") == case_id]
    if len(rows) != 1:
        raise ValueError(f"case absent or duplicated in prerequisites: {case_id}")
    return rows[0]


def main() -> int:
    argv = sys.argv[1:]
    case_id = arg_value(argv, "--case-id")
    prereq_path = Path(arg_value(argv, "--prerequisites"))
    output_path = Path(arg_value(argv, "--output"))
    amendment_path = Path(arg_value(argv, "--blocker-amendment"))

    if sha256_file(amendment_path) != PARENT_BLOCKER_AMENDMENT_SHA256:
        raise SystemExit("unexpected blocker-amendment bytes for v0.4 repair")
    amendment_doc = json.loads(amendment_path.read_text(encoding="utf-8"))
    if amendment_doc.get("territorial_activation_evidence_blinded") is not True:
        raise SystemExit("territorial blindness guard failed")
    if amendment_doc.get("r4_values_read_during_amendment_design") is not False or amendment_doc.get("territorial_outcomes_read_during_amendment_design") is not False:
        raise SystemExit("blocker amendment was not designed blind")

    # Validate the one known metadata transcription erratum from immutable inputs.
    apply_timestamp_erratum = case_id == AFFECTED_CASE
    if apply_timestamp_erratum:
        prereq = json.loads(prereq_path.read_text(encoding="utf-8"))
        row = find_case(prereq, case_id)
        rec = row["precise_orbits"][AFFECTED_SIDE]
        if rec.get("acquisition_utc") != AUTHORITATIVE_PREREQUISITE_ACQUISITION_UTC:
            raise SystemExit("authoritative frozen prerequisite acquisition timestamp changed")
        orbit_amend = amendment_doc["poeorb_catalog_scope_amendment"]
        if orbit_amend.get("affected_case_id") != AFFECTED_CASE or orbit_amend.get("affected_side") != AFFECTED_SIDE:
            raise SystemExit("parent amendment affected-case identity changed")
        if orbit_amend.get("acquisition_utc") != ERRONEOUS_TRANSCRIBED_ACQUISITION_UTC:
            raise SystemExit("expected parent-amendment transcription value changed")
        frozen = orbit_amend["snap14_observed_requested_resource"]
        acq = parse_utc(AUTHORITATIVE_PREREQUISITE_ACQUISITION_UTC)
        if not (parse_utc(frozen["validity_start_utc"]) <= acq <= parse_utc(frozen["validity_end_utc"])):
            raise SystemExit("exact preregistered POEORB resource does not cover authoritative acquisition")

    original_parse_utc = amended.parse_utc
    original_run_side = amended.core.run_side

    def parse_utc_with_frozen_erratum(value: str) -> datetime:
        if apply_timestamp_erratum and value == ERRONEOUS_TRANSCRIBED_ACQUISITION_UTC:
            return original_parse_utc(AUTHORITATIVE_PREREQUISITE_ACQUISITION_UTC)
        return original_parse_utc(value)

    def run_side_with_verified_local_poeorb(
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
        expected = orbit_verified["expected_zip_filename"]
        match = POEORB_NAME.match(expected)
        if not match:
            raise ValueError(f"cannot derive deterministic SNAP POEORB cache path from {expected}")
        platform, year, month = match.groups()
        source = output.parent / "verified-orbit-resources" / f"{side}_{expected}"
        if not source.is_file():
            raise ValueError("exact verified POEORB ZIP missing before local-cache preload")
        if sha256_file(source) != orbit_verified["zip_sha256"]:
            raise ValueError("exact verified POEORB ZIP changed before local-cache preload")
        cache_dir = user_home / ".snap" / "auxdata" / "Orbits" / "Sentinel-1" / "POEORB" / platform / year / month
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / expected
        shutil.copy2(source, cached)
        if sha256_file(cached) != orbit_verified["zip_sha256"]:
            raise ValueError("locally pre-seeded POEORB ZIP hash mismatch")
        row = original_run_side(side, gpt, graph, manifest, dem, output, user_home, orbit_verified, log_path)
        row["transport_only_local_poeorb_preseed"] = True
        row["local_poeorb_preseed_sha256"] = orbit_verified["zip_sha256"]
        row["local_poeorb_preseed_exact_frozen_resource"] = True
        row["poeorb_selector_or_resource_changed_by_preseed"] = False
        return row

    amended.parse_utc = parse_utc_with_frozen_erratum
    amended.core.run_side = run_side_with_verified_local_poeorb
    try:
        rc = amended.main()
    finally:
        amended.parse_utc = original_parse_utc
        amended.core.run_side = original_run_side

    if output_path.is_file():
        report = json.loads(output_path.read_text(encoding="utf-8"))
        report["r2_v04_transport_only_repair"] = True
        report["exact_frozen_poeorb_locally_preseeded_for_snap14"] = True
        report["poeorb_selector_changed_by_v04"] = False
        report["poeorb_resource_identity_changed_by_v04"] = False
        report["timestamp_transcription_erratum_applied"] = apply_timestamp_erratum
        if apply_timestamp_erratum:
            report["timestamp_transcription_erratum"] = {
                "case_id": AFFECTED_CASE,
                "side": AFFECTED_SIDE,
                "non_authoritative_parent_amendment_value": ERRONEOUS_TRANSCRIBED_ACQUISITION_UTC,
                "authoritative_frozen_prerequisite_value": AUTHORITATIVE_PREREQUISITE_ACQUISITION_UTC,
                "scientific_selection_changed": False,
            }
        report["r4_values_read_for_v04_repair_decision"] = False
        report["territorial_outcomes_read_for_v04_repair_decision"] = False
        report["known_event_dates_read_for_v04_repair_decision"] = False
        report["case_control_role_used_for_v04_repair_decision"] = False
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
