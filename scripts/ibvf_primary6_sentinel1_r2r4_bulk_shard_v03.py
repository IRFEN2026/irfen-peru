#!/usr/bin/env python3
"""Compatibility entry point for PRIMARY6 blind R2-R4 bulk execution.

RESEARCH_ONLY / TEST_ONLY. The historical v0.3 workflow remains the validated
workflow shell, while execution delegates to the blocker-only v0.4 wrapper.
The same amendment was frozen before repair reruns and remains the scientific
source of truth. The current implementation revision only (a) pre-seeds SNAP14
with already frozen, SHA-verified POEORB bytes to remove transport dependence,
(b) corrects one preidentified acquisition-timestamp transcription from the
immutable prerequisite, and (c) applies the amendment's already-frozen general
R3 footprint rule to every exact legacy containment blocker rather than treating
two diagnostic examples as an exhaustive whitelist.

No selected window, Sentinel-1 pair, R3 threshold, basin geometry, imputation
rule, production flag, R4 rule, or territorial evidence gate is changed here.
No R4 magnitude, territorial outcome, known event date, or case/control role is
used to choose any repair.
"""
from __future__ import annotations

import sys

import ibvf_primary6_sentinel1_r2r4_bulk_shard_v04 as amended

BLOCKER_AMENDMENT = "site/data/validation/ibvf_primary6_blinded_blocker_amendment_v01.json"
IMPLEMENTATION_REPAIR_REVISION = "blind-transport-and-general-scope-v01"


def main() -> int:
    if "--blocker-amendment" in sys.argv[1:]:
        raise SystemExit("v0.3 compatibility entry requires the frozen in-repository blocker amendment path")
    original_argv = sys.argv
    sys.argv = [original_argv[0], "--blocker-amendment", BLOCKER_AMENDMENT, *original_argv[1:]]
    try:
        return amended.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
