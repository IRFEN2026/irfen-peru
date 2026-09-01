#!/usr/bin/env python3
"""PRIMARY6 R2 prerequisite runner using frozen POEORB overlap resolution v0.2.

All dataset, guardrail, vertical-grid and manifest logic remains in the v0.1
runner. Only the precise-orbit metadata resolver is replaced by the globally
frozen science-independent overlap rule.
"""
from __future__ import annotations

import ibvf_primary6_sentinel1_r2_prerequisites as base
from ibvf_sentinel1_r2_orbit_resolver_v02 import freeze_orbit

base.freeze_orbit = freeze_orbit

if __name__ == "__main__":
    raise SystemExit(base.main())
