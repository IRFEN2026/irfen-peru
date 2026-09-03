#!/usr/bin/env python3
"""PRIMARY6 R2 v0.5: prove exact locally cached POEORB consumption without signal access.

RESEARCH_ONLY / TEST_ONLY. This wrapper implements the preregistered, signal-blind
local-cache consumption proof frozen after workflow run 33741315922 showed that
SNAP14 commonly emits no AUX_POEORB filename when the exact frozen resource is
already present in its clean local cache.

No selected window, Sentinel-1 pair, POEORB selector/resource, R2 graph, DEM,
R3/R4 rule, imputation rule, territorial evidence, event date, or case/control
role is changed. The only new behavior is fail-closed implementation provenance:
a successful side may bridge the legacy "requested_exact..." boolean only when
the exact SHA-verified cached resource is exclusive under clean user.home and the
frozen Apply-Orbit-File hard gate succeeds.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import ibvf_primary6_sentinel1_r2_execute_v04 as transport

PROOF_SHA256 = "444326fdb9ae4c53a59eb1bdc5dba11376b292b661168688ba529997fa192e91"
PROOF_STATUS = "FROZEN_SIGNAL_BLIND_LOCAL_POEORB_CONSUMPTION_PROOF_AMENDMENT_BEFORE_RERUN"
EXPECTED_TRIGGER_RUN = 33741315922
POEORB_FILE_RE = re.compile(r"^S1[AB]_OPER_AUX_POEORB_.*\.EOF(?:\.zip)?$", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_pair(argv: list[str], name: str) -> tuple[list[str], str]:
    try:
        i = argv.index(name)
        value = argv[i + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"missing required v0.5 wrapper argument {name}") from exc
    return argv[:i] + argv[i + 2 :], value


def orbit_files(user_home: Path) -> dict[str, Path]:
    root = user_home / ".snap" / "auxdata" / "Orbits" / "Sentinel-1"
    if not root.exists():
        return {}
    out: dict[str, Path] = {}
    for p in root.rglob("*"):
        if p.is_file() and POEORB_FILE_RE.match(p.name):
            if p.name in out:
                raise ValueError(f"duplicate AUX_POEORB basename under clean user.home: {p.name}")
            out[p.name] = p
    return out


def verify_cache_exclusive(
    user_home: Path,
    allowed: dict[str, str],
    *,
    stage: str,
) -> dict[str, Any]:
    found = orbit_files(user_home)
    unexpected = sorted(set(found) - set(allowed))
    if unexpected:
        raise ValueError(f"{stage}: unapproved AUX_POEORB resource(s) appeared: {unexpected}")
    mandatory = sorted(name for name in allowed if name.lower().endswith(".zip"))
    mandatory_missing = sorted(name for name in mandatory if name not in found)
    if mandatory_missing:
        raise ValueError(f"{stage}: exact preseeded POEORB ZIP missing: {mandatory_missing}")
    hashes: dict[str, str] = {}
    for name, p in found.items():
        actual = sha256_file(p)
        expected = allowed[name]
        if actual != expected:
            raise ValueError(f"{stage}: AUX_POEORB hash mismatch for {name}")
        hashes[name] = actual
    return {
        "stage": stage,
        "approved_resources_present": sorted(found),
        "approved_resource_hashes": hashes,
        "unexpected_resources": [],
        "mandatory_preseeded_zip_missing": [],
        "cache_exclusive": True,
    }


def guard_proof(doc: dict[str, Any], path: Path) -> None:
    if sha256_file(path) != PROOF_SHA256:
        raise SystemExit("unexpected local-cache consumption proof bytes")
    if doc.get("status") != PROOF_STATUS:
        raise SystemExit("local-cache consumption proof is not frozen")
    if doc.get("deployment_status") != "RESEARCH_ONLY" or doc.get("test_only") is not True:
        raise SystemExit("local-cache proof deployment guard failed")
    if doc.get("production_use") is not False or doc.get("production_ready") is not False:
        raise SystemExit("local-cache proof production guard failed")
    if doc.get("operational_alerting_enabled") is not False:
        raise SystemExit("local-cache proof operational alerting guard failed")
    if doc.get("territorial_activation_evidence_blinded") is not True:
        raise SystemExit("local-cache proof territorial blindness guard failed")
    att = doc.get("blindness_attestation") or {}
    if (
        att.get("r4_values_read_during_amendment_design") is not False
        or att.get("territorial_outcomes_read_during_amendment_design") is not False
        or att.get("known_event_dates_read_during_amendment_design") is not False
        or att.get("case_control_roles_used_during_amendment_design") is not False
    ):
        raise SystemExit("local-cache proof was not designed signal/outcome blind")
    if (doc.get("triggering_blind_run") or {}).get("workflow_run_id") != EXPECTED_TRIGGER_RUN:
        raise SystemExit("unexpected triggering blind run identity")


def main() -> int:
    filtered, proof_arg = strip_pair(sys.argv[1:], "--local-cache-proof-amendment")
    proof_path = Path(proof_arg)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    guard_proof(proof, proof_path)

    frozen_graph = proof["frozen_graph"]
    graph_path = Path(frozen_graph["path"])
    if sha256_file(graph_path) != frozen_graph["sha256"]:
        raise SystemExit("frozen R2 graph hash differs from local-cache proof")
    graph_text = graph_path.read_text(encoding="utf-8")
    if "<orbitType>Sentinel Precise (Auto Download)</orbitType>" not in graph_text:
        raise SystemExit("frozen R2 graph orbitType differs from proof")
    if "<continueOnFail>false</continueOnFail>" not in graph_text:
        raise SystemExit("frozen R2 graph no longer has fail-closed Apply-Orbit-File")

    core = transport.amended.core
    original_run_side = core.run_side
    introduced: dict[str, str] = {}

    def run_side_with_preregistered_cache_proof(
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
        if sha256_file(graph) != frozen_graph["sha256"]:
            raise ValueError("runtime graph differs from frozen local-cache proof")

        expected_zip = orbit_verified["expected_zip_filename"]
        expected_eof = orbit_verified["expected_eof_filename"]
        current_allowed = dict(introduced)
        current_allowed[expected_zip] = orbit_verified["zip_sha256"]
        current_allowed[expected_eof] = orbit_verified["inner_eof_sha256"]

        before = verify_cache_exclusive(user_home, current_allowed, stage=f"{side}_before_gpt")
        row = original_run_side(
            side, gpt, graph, manifest, dem, output, user_home, orbit_verified, log_path
        )
        after = verify_cache_exclusive(user_home, current_allowed, stage=f"{side}_after_gpt")

        requested = row.get("requested_aux_poeorb_filenames") or []
        allowed_logged = {expected_zip, expected_eof}
        alternative_logged = sorted(x for x in requested if Path(x).name not in allowed_logged)
        if alternative_logged:
            raise ValueError(f"{side}: SNAP14 logged non-frozen AUX_POEORB resource(s): {alternative_logged}")

        exact_zip_path = orbit_files(user_home).get(expected_zip)
        if exact_zip_path is None or sha256_file(exact_zip_path) != orbit_verified["zip_sha256"]:
            raise ValueError(f"{side}: exact frozen POEORB ZIP not byte-identical after GPT")

        legacy_log_exact = bool(row.get("requested_exact_v02_frozen_resource"))
        hard_gate_ok = (
            row.get("returncode") == 0
            and row.get("output_exists") is True
            and before["cache_exclusive"] is True
            and after["cache_exclusive"] is True
        )
        if not hard_gate_ok:
            return row

        row["requested_exact_v02_frozen_resource_legacy_log_observation"] = legacy_log_exact
        row["requested_exact_v02_frozen_resource"] = True
        row["v02_requested_exact_field_promoted_by_v05_proof"] = not legacy_log_exact
        row["canonical_poeorb_consumption_verified_v05"] = True
        row["canonical_poeorb_consumption_proof_mode"] = (
            "LEGACY_EXACT_LOG_REQUEST_PLUS_CACHE_EXCLUSIVITY"
            if legacy_log_exact
            else "CLEAN_USER_HOME_EXACT_CACHE_EXCLUSIVITY_PLUS_HARD_APPLY_ORBIT_GATE"
        )
        row["local_cache_proof_amendment_sha256"] = PROOF_SHA256
        row["cache_state_before_gpt"] = before
        row["cache_state_after_gpt"] = after
        row["alternative_aux_poeorb_logged"] = []
        row["exact_frozen_zip_hash_reverified_after_gpt"] = True
        row["r4_values_read_for_consumption_proof"] = False
        row["territorial_outcomes_read_for_consumption_proof"] = False
        row["known_event_dates_read_for_consumption_proof"] = False
        row["case_control_role_used_for_consumption_proof"] = False
        row["status"] = "PASS_R2_V05_SIDE_EXACT_FROZEN_POEORB_CONSUMPTION_IMPLEMENTATION_VERIFIED"

        introduced[expected_zip] = orbit_verified["zip_sha256"]
        present = orbit_files(user_home)
        if expected_eof in present:
            if sha256_file(present[expected_eof]) != orbit_verified["inner_eof_sha256"]:
                raise ValueError(f"{side}: materialized EOF hash differs from frozen resource")
            introduced[expected_eof] = orbit_verified["inner_eof_sha256"]
        return row

    core.run_side = run_side_with_preregistered_cache_proof
    original_argv = sys.argv
    sys.argv = [original_argv[0]] + filtered
    try:
        rc = transport.main()
    finally:
        sys.argv = original_argv
        core.run_side = original_run_side

    try:
        out_arg_index = filtered.index("--output")
        output_path = Path(filtered[out_arg_index + 1])
    except (ValueError, IndexError):
        output_path = None
    if output_path is not None and output_path.is_file():
        report = json.loads(output_path.read_text(encoding="utf-8"))
        report["r2_v05_local_cache_consumption_proof"] = True
        report["local_cache_consumption_proof_path"] = str(proof_path)
        report["local_cache_consumption_proof_sha256"] = PROOF_SHA256
        report["poeorb_selector_changed_by_v05"] = False
        report["poeorb_resource_identity_changed_by_v05"] = False
        report["r2_graph_changed_by_v05"] = False
        report["r3_r4_rules_changed_by_v05"] = False
        report["territorial_evidence_read_by_v05"] = False
        report["activation_inference_allowed"] = False
        report["modeling_allowed"] = False
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
