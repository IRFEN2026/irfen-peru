#!/usr/bin/env python3
"""Compatibility entry point for frozen PRIMARY6 blind R2-R4 bulk shard v0.2.

RESEARCH_ONLY / TEST_ONLY. The first bulk orchestration draft used an obsolete
metadata key name for the pre-bulk pilot-integrity gate. The canonical frozen
contract uses `pilot_r2_r3_must_pass_implementation_integrity_before_bulk`.
This entry point verifies that canonical key and exposes the old name only to
the v0.2 orchestration guard in memory. It does not modify the contract file,
its hash, any R1-R4 science rule, any selected window, or any outcome state.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import ibvf_primary6_sentinel1_r2r4_bulk_shard_v02 as core

_original_load = core.load


def load_with_canonical_bulk_gate_alias(path: Path) -> dict[str, Any]:
    doc = _original_load(path)
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


def main() -> int:
    core.load = load_with_canonical_bulk_gate_alias
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
