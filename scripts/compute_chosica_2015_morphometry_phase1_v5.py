#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.5.

Retains revision 0.4 exact binary regeneration of every frozen geometry-generation DEM.
Adds one fail-closed raster-vector-raster routing rule for an excluded frozen outlet with
no direct predecessor in the re-rasterized frozen polygon: reconstruct the canonical D8
upstream topology from the unchanged frozen outlet on the exact frozen DEM, while keeping
all polygon masks and metric inclusion rules unchanged. No A6680 numeric reference,
observed 2015 outcome, rainfall, or post-anchor predictor is read.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import compute_chosica_2015_morphometry_phase1_v4 as v4

v3 = v4.v3
v2 = v4.v2
base = v4.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V5 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_5.json"
ROUNDTRIP_AUDIT: dict[str, dict] = {}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _direct_predecessors(fdir: np.ndarray, basin: np.ndarray, orow: int, ocol: int):
    out: list[tuple[int, int]] = []
    for r, c in np.argwhere(basin):
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if nr == orow and nc == ocol:
            out.append((int(r), int(c)))
    return out


def _moore_neighbor_mask(basin: np.ndarray) -> np.ndarray:
    rows, cols = basin.shape
    near = np.zeros_like(basin, dtype=bool)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            src_r = slice(max(0, -dr), min(rows, rows - dr))
            src_c = slice(max(0, -dc), min(cols, cols - dc))
            dst_r = slice(max(0, dr), min(rows, rows + dr))
            dst_c = slice(max(0, dc), min(cols, cols + dc))
            near[dst_r, dst_c] |= basin[src_r, src_c]
    return near


def _canonical_reverse_distances(
    fdir: np.ndarray,
    orow: int,
    ocol: int,
    dx: float,
    dy: float,
):
    rows, cols = fdir.shape
    upstream: dict[int, list[tuple[int, int, float]]] = {}
    valid_codes = np.isin(fdir, np.fromiter(base.D8_STEPS.keys(), dtype=fdir.dtype))
    for r, c in np.argwhere(valid_codes):
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if not (0 <= nr < rows and 0 <= nc < cols):
            continue
        link = math.hypot(dx * step[1], dy * step[0])
        upstream.setdefault(nr * cols + nc, []).append((int(r), int(c), link))

    dist = np.full((rows, cols), np.nan, dtype="float64")
    dist[orow, ocol] = 0.0
    q = deque([(orow, ocol)])
    while q:
        r, c = q.popleft()
        base_distance = float(dist[r, c])
        for ur, uc, link in upstream.get(r * cols + c, []):
            if math.isnan(dist[ur, uc]):
                dist[ur, uc] = base_distance + link
                q.append((ur, uc))
    return dist


def d8_metrics_with_canonical_roundtrip_bridge(
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
        raise RuntimeError("FAIL_CLOSED_ROUNDTRIP_TARGET_CONTEXT")
    if not (0 <= orow < rows and 0 <= ocol < cols):
        raise RuntimeError("FAIL_CLOSED_OUTLET_OUTSIDE_DEM")

    direct = _direct_predecessors(fdir, basin, orow, ocol)
    if bool(basin[orow, ocol]) or direct:
        out = v3.d8_metrics_with_frozen_pourpoint(
            fdir, accumulation, basin, (orow, ocol), area_m2, dx, dy
        )
        audit = dict(v3.POURPOINT_AUDIT[target_id])
        audit.update({
            "canonical_d8_roundtrip_boundary_bridge_applied": False,
            "canonical_d8_extra_cell_count": 0,
            "canonical_d8_unexpected_nonboundary_extra_cell_count": 0,
            "polygon_cells_not_routing_to_outlet_count": 0,
            "bridge_entry_from_polygon_count": 0,
            "frozen_outlet_modified": False,
        })
        v3.POURPOINT_AUDIT[target_id] = audit
        ROUNDTRIP_AUDIT[target_id] = dict(audit)
        return {**out, **audit}

    # The vector polygon remains immutable. Routing alone is reconstructed from the
    # exact D8 topology that generated the frozen catchment, using the same frozen outlet.
    dist = _canonical_reverse_distances(fdir, orow, ocol, dx, dy)
    canonical = np.isfinite(dist)
    basin_count = int(basin.sum())
    reached = basin & canonical
    reached_count = int(reached.sum())
    coverage = reached_count / basin_count if basin_count else 0.0
    if coverage < 0.995:
        raise RuntimeError(f"FAIL_CLOSED_CANONICAL_D8_POLYGON_COVERAGE {target_id} {coverage:.9f}")

    extra = canonical & ~basin
    near_polygon = _moore_neighbor_mask(basin)
    allowed_extra = extra & near_polygon
    if extra[orow, ocol]:
        allowed_extra[orow, ocol] = True
    unexpected_extra = extra & ~allowed_extra
    unexpected_count = int(unexpected_extra.sum())
    if unexpected_count:
        raise RuntimeError(
            f"FAIL_CLOSED_CANONICAL_D8_NONBOUNDARY_EXTRA {target_id} {unexpected_count}"
        )

    bridge_entries = 0
    for r, c in np.argwhere(basin):
        step = base.D8_STEPS.get(int(fdir[r, c]))
        if step is None:
            continue
        nr, nc = int(r + step[0]), int(c + step[1])
        if 0 <= nr < rows and 0 <= nc < cols and extra[nr, nc] and canonical[nr, nc]:
            bridge_entries += 1
    if bridge_entries < 1:
        raise RuntimeError(f"FAIL_CLOSED_CANONICAL_D8_NO_BOUNDARY_BRIDGE_ENTRY {target_id}")

    if reached_count == 0:
        raise RuntimeError(f"FAIL_CLOSED_CANONICAL_D8_EMPTY_REACHED {target_id}")
    main_length = float(np.nanmax(dist[reached]))

    # Preserve the frozen drainage-density semantics exactly: only qualifying links
    # whose upstream and downstream centers are both inside the frozen polygon mask count.
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
        if 0 <= nr < rows and 0 <= nc < cols and basin[nr, nc]:
            channel_length += math.hypot(dx * step[1], dy * step[0])
            qualifying_links += 1
    drainage_density = (channel_length / 1000.0) / (area_m2 / 1e6)

    audit = {
        "outlet_cell_in_frozen_geometry_mask": False,
        "pourpoint_excluded_geometry_semantics_applied": True,
        "pourpoint_direct_in_basin_predecessor_count": 0,
        "canonical_d8_roundtrip_boundary_bridge_applied": True,
        "canonical_d8_extra_cell_count": int(extra.sum()),
        "canonical_d8_unexpected_nonboundary_extra_cell_count": unexpected_count,
        "polygon_cells_not_routing_to_outlet_count": basin_count - reached_count,
        "bridge_entry_from_polygon_count": int(bridge_entries),
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
        "routing_coverage_denominator_is_frozen_polygon_cells_only": True,
        "drainage_density_rule_changed": False,
    }
    v3.POURPOINT_AUDIT[target_id] = dict(audit)
    ROUNDTRIP_AUDIT[target_id] = dict(audit)
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
    v4.annotate_report(report_path)
    if not report_path.exists():
        return
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    doc["execution_revision"] = "0.5_CANONICAL_D8_ROUNDTRIP_BOUNDARY_BRIDGE"
    doc["roundtrip_implementation_sha256"] = sha256_path(Path(__file__).resolve())
    doc["roundtrip_routing_audit"] = ROUNDTRIP_AUDIT
    doc["revision_guards"] = {
        "a6680_numeric_reference_read": False,
        "outcome_evidence_read": False,
        "post_anchor_predictor_read": False,
        "selection_or_tuning_from_metric_values": False,
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
    }
    report_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    base.EXECUTION = EXECUTION_V5
    base.build_exact_geometry_dem = v4.build_exact_frozen_geometry_dem
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = d8_metrics_with_canonical_roundtrip_bridge
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
