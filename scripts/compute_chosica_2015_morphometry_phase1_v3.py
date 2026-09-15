#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.3.

Preserves revision-0.2 canonical DEM alignment and the frozen morphometry formulas.
The only added rule handles a frozen catchment polygon whose boolean polygonization
excludes its pour-point cell: the polygon mask is left untouched, while D8 routing may
terminate at the frozen outlet if at least one in-mask predecessor flows directly into it.
No A6680 numeric reference, observed 2015 outcome, or post-anchor predictor is read.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import compute_chosica_2015_morphometry_phase1_v2 as v2

base = v2.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V3 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_3.json"
BASE_IMPLEMENTATION = ROOT / "scripts/compute_chosica_2015_morphometry_phase1.py"
ALIGNMENT_IMPLEMENTATION = ROOT / "scripts/compute_chosica_2015_morphometry_phase1_v2.py"
POURPOINT_AUDIT: dict[str, dict] = {}
ORIGINAL_D8_METRICS = base.d8_metrics


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def d8_metrics_with_frozen_pourpoint(
    fdir: np.ndarray,
    accumulation: np.ndarray,
    basin: np.ndarray,
    outlet_rc,
    area_m2: float,
    dx: float,
    dy: float,
):
    rows, cols = fdir.shape
    orow, ocol = int(outlet_rc[0]), int(outlet_rc[1])
    target_id = v2.CURRENT_TARGET
    if target_id is None:
        raise RuntimeError("FAIL_CLOSED_POURPOINT_TARGET_CONTEXT")
    if not (0 <= orow < rows and 0 <= ocol < cols):
        raise RuntimeError("FAIL_CLOSED_OUTLET_OUTSIDE_DEM")

    if bool(basin[orow, ocol]):
        out = ORIGINAL_D8_METRICS(fdir, accumulation, basin, (orow, ocol), area_m2, dx, dy)
        audit = {
            "outlet_cell_in_frozen_geometry_mask": True,
            "pourpoint_excluded_geometry_semantics_applied": False,
            "pourpoint_direct_in_basin_predecessor_count": 0,
            "frozen_polygon_mask_modified": False,
            "routing_coverage_denominator_is_frozen_polygon_cells_only": True,
            "drainage_density_rule_changed": False,
        }
        POURPOINT_AUDIT[target_id] = audit
        return {**out, **audit}

    basin_rc = np.argwhere(basin)
    direct_predecessors: list[tuple[int, int]] = []
    for r, c in basin_rc:
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if nr == orow and nc == ocol:
            direct_predecessors.append((int(r), int(c)))
    if not direct_predecessors:
        raise RuntimeError(f"FAIL_CLOSED_EXCLUDED_POURPOINT_NO_DIRECT_PREDECESSOR {target_id}")

    dist = np.full((rows, cols), np.nan, dtype="float64")
    dist[orow, ocol] = 0.0
    upstream: dict[int, list[tuple[int, int, float]]] = {}
    for r, c in basin_rc:
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if not (0 <= nr < rows and 0 <= nc < cols):
            continue
        downstream_is_in_basin = bool(basin[nr, nc])
        downstream_is_frozen_outlet = nr == orow and nc == ocol
        if not downstream_is_in_basin and not downstream_is_frozen_outlet:
            continue
        link = math.hypot(dx * step[1], dy * step[0])
        upstream.setdefault(nr * cols + nc, []).append((int(r), int(c), link))

    q = deque([(orow, ocol)])
    while q:
        r, c = q.popleft()
        base_distance = float(dist[r, c])
        for ur, uc, link in upstream.get(r * cols + c, []):
            if math.isnan(dist[ur, uc]):
                dist[ur, uc] = base_distance + link
                q.append((ur, uc))

    reached = basin & np.isfinite(dist)
    reached_count = int(reached.sum())
    basin_count = int(basin.sum())
    coverage = reached_count / basin_count if basin_count else 0.0
    if coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_D8_ROUTING_COVERAGE {coverage:.9f}")
    main_length = float(np.nanmax(dist[reached]))

    threshold_m2 = 0.01 * area_m2
    acc_area = np.asarray(accumulation, dtype="float64") * base.CELL_AREA_M2
    channel = basin & (acc_area >= threshold_m2)
    channel_length = 0.0
    qualifying_links = 0
    for r, c in np.argwhere(channel):
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        # Deliberately preserve revision-1 drainage-density semantics: the final
        # link to an excluded pour point is not added because its downstream cell
        # is outside the exact frozen polygon mask.
        if 0 <= nr < rows and 0 <= nc < cols and basin[nr, nc]:
            channel_length += math.hypot(dx * step[1], dy * step[0])
            qualifying_links += 1
    drainage_density = (channel_length / 1000.0) / (area_m2 / 1e6)

    audit = {
        "outlet_cell_in_frozen_geometry_mask": False,
        "pourpoint_excluded_geometry_semantics_applied": True,
        "pourpoint_direct_in_basin_predecessor_count": len(direct_predecessors),
        "frozen_polygon_mask_modified": False,
        "routing_coverage_denominator_is_frozen_polygon_cells_only": True,
        "drainage_density_rule_changed": False,
    }
    POURPOINT_AUDIT[target_id] = audit
    return {
        "routing_coverage_fraction": coverage,
        "routing_reached_cell_count": reached_count,
        "basin_center_cell_count": basin_count,
        "main_channel_length_m": main_length,
        "channel_contributing_area_threshold_m2": threshold_m2,
        "channel_qualifying_link_count": qualifying_links,
        "channel_length_km": channel_length / 1000.0,
        "drainage_density_km_per_km2": drainage_density,
        **audit,
    }


def annotate_report(report_path: Path) -> None:
    if not report_path.exists():
        return
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    doc["execution_revision"] = "0.3_FROZEN_POURPOINT_ROUTING_SEMANTICS"
    doc["base_implementation_sha256"] = sha256_path(BASE_IMPLEMENTATION)
    doc["alignment_implementation_sha256"] = sha256_path(ALIGNMENT_IMPLEMENTATION)
    doc["alignment_audit"] = v2.ALIGNMENT_AUDIT
    doc["pourpoint_semantics_audit"] = POURPOINT_AUDIT
    doc["revision_guards"] = {
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "selection_or_tuning_from_metric_values": False,
        "frozen_polygon_mask_modified": False,
    }
    report_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    base.EXECUTION = EXECUTION_V3
    base.build_exact_geometry_dem = v2.build_canonical_geometry_dem
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = d8_metrics_with_frozen_pourpoint
    base.__file__ = str(Path(__file__).resolve())

    import sys
    report_path = None
    for idx, arg in enumerate(sys.argv[:-1]):
        if arg == "--report":
            report_path = Path(sys.argv[idx + 1])
            break

    rc = base.main()
    if report_path is not None:
        annotate_report(report_path)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
