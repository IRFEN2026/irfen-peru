#!/usr/bin/env python3
"""Compatibility entry point for PRIMARY6 blind R2-R4 bulk execution.

RESEARCH_ONLY / TEST_ONLY. The historical v0.3 workflow remains the validated
workflow shell, but execution now delegates to the preregistered v0.4
blocker-only wrapper. The amendment path is fixed in-repository and was frozen
before any repair rerun, R4-magnitude review, territorial outcome read, or
case/control assignment.

No selected window, Sentinel-1 pair, R3 threshold, basin geometry, imputation
rule, production flag, or territorial evidence gate is changed here.
"""
from __future__ import annotations

import sys

import ibvf_primary6_sentinel1_r2r4_bulk_shard_v04 as amended

BLOCKER_AMENDMENT = "site/data/validation/ibvf_primary6_blinded_blocker_amendment_v01.json"


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
