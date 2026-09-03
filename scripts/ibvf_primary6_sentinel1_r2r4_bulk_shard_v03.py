#!/usr/bin/env python3
"""Compatibility entry point for PRIMARY6 blind R2-R4 bulk execution.

RESEARCH_ONLY / TEST_ONLY. The historical v0.3 workflow remains the validated
workflow shell, while execution delegates to the blocker-only v0.4 wrapper.
Scientific selection remains frozen. The implementation path now combines:
(a) exact SHA-verified local POEORB preseed to remove transport dependence,
(b) the separately preregistered signal-blind cache-exclusivity proof required
    when SNAP14 satisfies Apply-Orbit-File silently from local cache,
(c) the preidentified San Ildefonso timestamp transcription erratum, and
(d) the already-frozen general R3 footprint rule for exact legacy rectangular
    containment blockers.

No selected window, Sentinel-1 pair, R3 threshold, basin geometry, imputation
rule, production flag, R4 rule, or territorial evidence gate is changed here.
No R4 magnitude, territorial outcome, known event date, or case/control role is
used to choose any repair.
"""
from __future__ import annotations

import sys

import ibvf_primary6_sentinel1_r2r4_bulk_shard_v04 as amended

BLOCKER_AMENDMENT = "site/data/validation/ibvf_primary6_blinded_blocker_amendment_v01.json"
IMPLEMENTATION_REPAIR_REVISION = "blind-transport-cache-proof-and-general-r3-scope-v02"


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
