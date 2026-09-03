#!/usr/bin/env python3
"""PRIMARY6 R2 v0.6: signal-blind cache identity proof repair after run 33763565143.

RESEARCH_ONLY / TEST_ONLY. This wrapper changes no selected window, Sentinel-1
pair, POEORB selector/resource, DEM, R3/R4 rule, threshold, imputation rule, or
territorial gate. It repairs two implementation-only overconstraints exposed by
the blinded bulk run: (1) the cache proof now accepts either R2 graph already
frozen per unit in the pre-existing PRIMARY6 execution contract, and (2) one
approved AUX_POEORB resource may exist at multiple cache paths only when every
copy is byte-identical to its single frozen SHA-256 identity.

No R4 magnitudes, territorial outcomes, known event dates, or case/control roles
are read or used by this wrapper.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import ibvf_primary6_sentinel1_r2_execute_v04 as transport

PROOF_SHA256 = "a32335bf13c12c92adf3c6a8a231fa47b2ce83718aaa210084426d19ae9de6e3"
PROOF_STATUS = "FROZEN_SIGNAL_BLIND_LOCAL_POEORB_CONSUMPTION_PROOF_V02_BEFORE_RERUN"
EXPECTED_TRIGGER_RUN = 33763565143
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
        raise SystemExit(f"missing required v0.6 wrapper argument {name}") from exc
    return argv[:i] + argv[i + 2 :], value


def orbit_files(user_home: Path) -> dict[str, list[Path]]:
    root = user_home / ".snap" / "auxdata" / "Orbits" / "Sentinel-1"
    if not root.exists():
        return {}
    out: dict[str, list[Path]] = {}
    for p in root.rglob("*"):
        if p.is_file() and POEORB_FILE_RE.match(p.name):
            out.setdefault(p.name, []).append(p)
    for paths in out.values():
        paths.sort(key=lambda p: p.as_posix())
    return out


def verify_cache_identity_exclusive(
    user_home: Path,
    allowed: dict[str, str],
    *,
    stage: str,
) -> dict[str, Any]:
    found = orbit_files(user_home)
    unexpected = sorted(set(found) - set(allowed))
    if unexpected:
        raise ValueError(f"{stage}: unapproved AUX_POEORB resource basename(s) appeared: {unexpected}")

    mandatory = sorted(name for name in allowed if name.lower().endswith(".zip"))
    mandatory_missing = sorted(name for name in mandatory if not found.get(name))
    if mandatory_missing:
        raise ValueError(f"{stage}: exact preseeded POEORB ZIP missing: {mandatory_missing}")

    hashes: dict[str, str] = {}
    path_multiplicity: dict[str, int] = {}
    verified_paths: dict[str, list[str]] = {}
    for name, paths in found.items():
        expected = allowed[name]
        checked: list[str] = []
        for p in paths:
            actual = sha256_file(p)
            if actual != expected:
                raise ValueError(
                    f"{stage}: AUX_POEORB hash mismatch for approved basename {name} at {p}"
                )
            checked.append(str(p))
        hashes[name] = expected
        path_multiplicity[name] = len(paths)
        verified_paths[name] = checked

    return {
        "stage": stage,
        "approved_resource_basenames_present": sorted(found),
        "approved_resource_hashes": hashes,
        "approved_resource_path_multiplicity": path_multiplicity,
        "approved_resource_paths_verified": verified_paths,
        "unexpected_resource_basenames": [],
        "mandatory_preseeded_zip_missing": [],
        "cache_identity_exclusive": True,
        "duplicate_path_instances_allowed_only_if_byte_identical": True,
    }


def guard_proof(doc: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    if sha256_file(path) != PROOF_SHA256:
        raise SystemExit("unexpected local-cache consumption proof v0.2 bytes")
    if doc.get("status") != PROOF_STATUS:
        raise SystemExit("local-cache consumption proof v0.2 is not frozen")
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
        raise SystemExit("local-cache proof v0.2 was not designed signal/outcome blind")
    if (doc.get("triggering_blind_run") or {}).get("workflow_run_id") != EXPECTED_TRIGGER_RUN:
        raise SystemExit("unexpected triggering blind run identity")

    graphs = doc.get("frozen_r2_graphs") or []
    if len(graphs) != 2:
        raise SystemExit("local-cache proof v0.2 must bind exactly the two pre-existing PRIMARY6 R2 graphs")
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    for rec in graphs:
        graph_path = Path(rec["path"])
        graph_sha = sha256_file(graph_path)
        if graph_sha != rec["sha256"]:
            raise SystemExit(f"frozen R2 graph hash differs from proof v0.2: {graph_path}")
        graph_text = graph_path.read_text(encoding="utf-8")
        if "<orbitType>Sentinel Precise (Auto Download)</orbitType>" not in graph_text:
            raise SystemExit(f"frozen R2 graph orbitType differs from proof v0.2: {graph_path}")
        if "<continueOnFail>false</continueOnFail>" not in graph_text:
            raise SystemExit(f"frozen R2 graph no longer has fail-closed Apply-Orbit-File: {graph_path}")
        if rec["path"] in seen_paths or rec["sha256"] in seen_hashes:
            raise SystemExit("duplicate frozen R2 graph identity in proof v0.2")
        seen_paths.add(rec["path"])
        seen_hashes.add(rec["sha256"])
    return graphs


def graph_is_exactly_frozen(graph: Path, frozen_graphs: list[dict[str, Any]]) -> dict[str, Any]:
    actual_sha = sha256_file(graph)
    matches = [
        rec for rec in frozen_graphs
        if Path(rec["path"]).resolve() == graph.resolve() and rec["sha256"] == actual_sha
    ]
    if len(matches) != 1:
        raise ValueError("runtime graph path/SHA is not exactly one pre-existing PRIMARY6 frozen R2 graph")
    return matches[0]


def main() -> int:
    filtered, proof_arg = strip_pair(sys.argv[1:], "--local-cache-proof-amendment")
    proof_path = Path(proof_arg)
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    frozen_graphs = guard_proof(proof, proof_path)

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
        graph_rec = graph_is_exactly_frozen(graph, frozen_graphs)

        expected_zip = orbit_verified["expected_zip_filename"]
        expected_eof = orbit_verified["expected_eof_filename"]
        current_allowed = dict(introduced)
        current_allowed[expected_zip] = orbit_verified["zip_sha256"]
        current_allowed[expected_eof] = orbit_verified["inner_eof_sha256"]

        before = verify_cache_identity_exclusive(user_home, current_allowed, stage=f"{side}_before_gpt")
        row = original_run_side(
            side, gpt, graph, manifest, dem, output, user_home, orbit_verified, log_path
        )
        after = verify_cache_identity_exclusive(user_home, current_allowed, stage=f"{side}_after_gpt")

        requested = row.get("requested_aux_poeorb_filenames") or []
        allowed_logged = {expected_zip, expected_eof}
        alternative_logged = sorted(x for x in requested if Path(x).name not in allowed_logged)
        if alternative_logged:
            raise ValueError(f"{side}: SNAP14 logged non-frozen AUX_POEORB resource(s): {alternative_logged}")

        exact_zip_paths = orbit_files(user_home).get(expected_zip) or []
        if not exact_zip_paths:
            raise ValueError(f"{side}: exact frozen POEORB ZIP absent after GPT")
        if any(sha256_file(p) != orbit_verified["zip_sha256"] for p in exact_zip_paths):
            raise ValueError(f"{side}: an exact-name POEORB ZIP path is not byte-identical after GPT")

        legacy_log_exact = bool(row.get("requested_exact_v02_frozen_resource"))
        hard_gate_ok = (
            row.get("returncode") == 0
            and row.get("output_exists") is True
            and before["cache_identity_exclusive"] is True
            and after["cache_identity_exclusive"] is True
        )
        if not hard_gate_ok:
            return row

        row["requested_exact_v02_frozen_resource_legacy_log_observation"] = legacy_log_exact
        row["requested_exact_v02_frozen_resource"] = True
        row["v02_requested_exact_field_promoted_by_v06_proof"] = not legacy_log_exact
        row["canonical_poeorb_consumption_verified_v06"] = True
        row["canonical_poeorb_consumption_proof_mode"] = (
            "LEGACY_EXACT_LOG_REQUEST_PLUS_CACHE_IDENTITY_EXCLUSIVITY"
            if legacy_log_exact
            else "CLEAN_USER_HOME_EXACT_CACHE_IDENTITY_EXCLUSIVITY_PLUS_HARD_APPLY_ORBIT_GATE"
        )
        row["local_cache_proof_amendment_sha256"] = PROOF_SHA256
        row["frozen_r2_graph_path_verified_v06"] = graph_rec["path"]
        row["frozen_r2_graph_sha256_verified_v06"] = graph_rec["sha256"]
        row["cache_state_before_gpt"] = before
        row["cache_state_after_gpt"] = after
        row["alternative_aux_poeorb_logged"] = []
        row["exact_frozen_zip_hash_reverified_after_gpt"] = True
        row["r4_values_read_for_consumption_proof"] = False
        row["territorial_outcomes_read_for_consumption_proof"] = False
        row["known_event_dates_read_for_consumption_proof"] = False
        row["case_control_role_used_for_consumption_proof"] = False
        row["status"] = "PASS_R2_V06_SIDE_EXACT_FROZEN_POEORB_CONSUMPTION_IMPLEMENTATION_VERIFIED"

        introduced[expected_zip] = orbit_verified["zip_sha256"]
        present = orbit_files(user_home)
        eof_paths = present.get(expected_eof) or []
        if eof_paths:
            if any(sha256_file(p) != orbit_verified["inner_eof_sha256"] for p in eof_paths):
                raise ValueError(f"{side}: materialized EOF path differs from frozen resource")
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
        report["r2_v06_local_cache_identity_consumption_proof"] = True
        report["local_cache_consumption_proof_path"] = str(proof_path)
        report["local_cache_consumption_proof_sha256"] = PROOF_SHA256
        report["poeorb_selector_changed_by_v06"] = False
        report["poeorb_resource_identity_changed_by_v06"] = False
        report["r2_scientific_graph_changed_by_v06"] = False
        report["r3_r4_rules_changed_by_v06"] = False
        report["duplicate_cache_paths_accepted_only_when_exact_hash_identical"] = True
        report["territorial_evidence_read_by_v06"] = False
        report["activation_inference_allowed"] = False
        report["modeling_allowed"] = False
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
