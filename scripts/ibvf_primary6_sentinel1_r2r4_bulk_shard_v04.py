#!/usr/bin/env python3
"""PRIMARY6 blind R2-R4 shard v0.4 with preregistered blocker-only repairs.

All normal paths remain the v0.2/v0.3 frozen orchestration. This wrapper routes
R2 through the exact preidentified POEORB amendment, transport-only local cache
repair, and the separately frozen signal-blind cache-consumption proof; R3 goes
through the already-frozen general rectangular-window blocker rule.

Neither route may consult R4 magnitudes or territorial outcomes to decide
whether it applies. No window, pair, threshold, geometry, imputation rule, or
activation-evidence gate is changed.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import ibvf_primary6_sentinel1_r2r4_bulk_shard_v02 as core

AMENDMENT_STATUS = "FROZEN_SIGNAL_BLIND_BLOCKER_AMENDMENT_BEFORE_REPAIR_RERUN_NO_OUTCOMES_NO_R4_MAGNITUDES"
LOCAL_CACHE_PROOF = "site/data/validation/ibvf_primary6_sentinel1_r2_local_cache_consumption_proof_v01.json"


def extract_pair(argv: list[str], name: str) -> tuple[list[str], str]:
    try:
        i = argv.index(name)
        value = argv[i + 1]
    except (ValueError, IndexError) as exc:
        raise SystemExit(f"missing required v0.4 wrapper argument {name}") from exc
    return argv[:i] + argv[i + 2 :], value


def main() -> int:
    filtered, amendment_arg = extract_pair(sys.argv[1:], "--blocker-amendment")
    amendment_path = Path(amendment_arg)
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    if amendment.get("status") != AMENDMENT_STATUS:
        raise SystemExit("blinded blocker amendment is not frozen")
    if amendment.get("territorial_activation_evidence_blinded") is not True:
        raise SystemExit("blinded blocker amendment blindness guard failed")
    if amendment.get("r4_values_read_during_amendment_design") is not False or amendment.get("territorial_outcomes_read_during_amendment_design") is not False:
        raise SystemExit("blinded blocker amendment was not designed signal/outcome blind")
    if not Path(LOCAL_CACHE_PROOF).is_file():
        raise SystemExit("frozen local-cache consumption proof missing")

    original_load = core.load
    original_run = core.run

    def load_with_canonical_bulk_gate_alias(path: Path) -> dict[str, Any]:
        doc = original_load(path)
        if doc.get("schema_version") == "irfen-ibvf-primary6-sentinel1-r2r4-execution-contract-v0.1":
            gate = doc.get("bulk_gate") or {}
            canonical = "pilot_r2_r3_must_pass_implementation_integrity_before_bulk"
            obsolete = "pilot_implementation_integrity_must_pass_before_bulk"
            if gate.get(canonical) is not True:
                raise ValueError("canonical frozen pre-bulk pilot-integrity gate is absent or false")
            if obsolete in gate:
                raise ValueError("unexpected obsolete pre-bulk gate key already present in frozen contract")
            doc = copy.deepcopy(doc)
            doc["bulk_gate"][obsolete] = True
        return doc

    def run_with_preregistered_blocker_routes(cmd: list[str], allowed: set[int] | None = None) -> int:
        routed = list(cmd)
        if "scripts/ibvf_primary6_sentinel1_r2_execute_v02.py" in routed:
            i = routed.index("scripts/ibvf_primary6_sentinel1_r2_execute_v02.py")
            routed[i] = "scripts/ibvf_primary6_sentinel1_r2_execute_v05.py"
            routed.extend([
                "--blocker-amendment", str(amendment_path),
                "--local-cache-proof-amendment", LOCAL_CACHE_PROOF,
            ])
        elif "scripts/ibvf_primary6_sentinel1_r3_tiled_storage_wrapper.py" in routed:
            i = routed.index("scripts/ibvf_primary6_sentinel1_r3_tiled_storage_wrapper.py")
            routed[i] = "scripts/ibvf_primary6_sentinel1_r3_blinded_amendment_wrapper_v02.py"
            routed.extend(["--blocker-amendment", str(amendment_path)])
        return original_run(routed, allowed=allowed)

    core.load = load_with_canonical_bulk_gate_alias
    core.run = run_with_preregistered_blocker_routes
    original_argv = sys.argv
    sys.argv = [original_argv[0]] + filtered
    try:
        return core.main()
    finally:
        sys.argv = original_argv
        core.load = original_load
        core.run = original_run


if __name__ == "__main__":
    raise SystemExit(main())
