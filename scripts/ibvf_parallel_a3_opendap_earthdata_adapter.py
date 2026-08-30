#!/usr/bin/env python3
"""Adapter for the CMR-advertised Earthdata OPeNDAP service URL.

RESEARCH_ONLY / TEST_ONLY. This changes transport URL resolution only; it does
not alter the frozen A3 time, spatial, feature, ranking, or anti-leakage rules.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ibvf_parallel_a3_opendap_preflight as impl  # noqa: E402

_original_resolver = impl.resolve_opendap_url


def resolve_opendap_url(cmr):
    for link in cmr.get("links") or []:
        href = str(link.get("href") or "")
        low = href.lower()
        if low.startswith("https://opendap.earthdata.nasa.gov/collections/") and "/granules/" in low:
            return href.rstrip("/")
    return _original_resolver(cmr)


impl.resolve_opendap_url = resolve_opendap_url

if __name__ == "__main__":
    raise SystemExit(impl.main())
