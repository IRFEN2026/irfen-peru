#!/usr/bin/env python3
"""Phase-1 Chosica 2015 morphometry execution revision 0.7.

Replay routing according to each immutable frozen-geometry generator. Cashahuacra used the
project's explicit reverse-D8 upstream traversal from a frozen raster row/col; the other
five frozen geometries used Pysheds catchment from the rasterio containing-cell center
coordinate. Geometry, outlet, metric masks and all scientific guards remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import compute_chosica_2015_morphometry_phase1_v6 as v6

v4 = v6.v4
v3 = v6.v3
v2 = v6.v2
base = v6.base
ROOT = Path(__file__).resolve().parents[1]
EXECUTION_V7 = ROOT / "config/chosica_2015_morphometry_phase1_execution_v0_7.json"
ROUTING_REPLAY_AUDIT: dict[str, dict] = {}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def d8_metrics_provenance_dispatch(fdir, accumulation, basin, outlet_rc, area_m2, dx, dy):
    target_id = v2.CURRENT_TARGET
    if target_id is None:
        raise RuntimeError("FAIL_CLOSED_ROUTING_REPLAY_TARGET_CONTEXT")

    if target_id == "cashahuacra":
        # Frozen Cashahuacra geometry provenance is the explicit reverse-D8 upstream
        # traversal from the frozen row/col. Reuse the same D8 topology semantics.
        out = v3.d8_metrics_with_frozen_pourpoint(
            fdir, accumulation, basin, outlet_rc, area_m2, dx, dy
        )
        audit = {
            "target_id": target_id,
            "routing_replay_method": "FROZEN_GENERATOR_MANUAL_REVERSE_D8_FROM_FROZEN_ROW_COL",
            "geometry_delineator_git_blob_sha": "8b72787b93aafe6c42ed03b3b8af19b01c075658",
            "pysheds_catchment_replay_used": False,
            "manual_reverse_d8_used": True,
            "frozen_polygon_mask_modified": False,
            "frozen_outlet_modified": False,
            "drainage_density_rule_changed": False,
            "routing_coverage_fraction": float(out["routing_coverage_fraction"]),
        }
        ROUTING_REPLAY_AUDIT[target_id] = dict(audit)
        return {**out, **audit}

    out = v6.d8_metrics_exact_geometry_replay(
        fdir, accumulation, basin, outlet_rc, area_m2, dx, dy
    )
    audit = {
        "target_id": target_id,
        "routing_replay_method": "FROZEN_GENERATOR_PYSHEDS_CATCHMENT_FROM_CONTAINING_CELL_CENTER",
        "pysheds_catchment_replay_used": True,
        "manual_reverse_d8_used": False,
        "frozen_polygon_mask_modified": False,
        "frozen_outlet_modified": False,
        "drainage_density_rule_changed": False,
        "routing_coverage_fraction": float(out["routing_coverage_fraction"]),
        "replay_polygon_coverage_fraction": float(out["replay_polygon_coverage_fraction"]),
        "replay_polygon_jaccard": float(out["replay_polygon_jaccard"]),
    }
    ROUTING_REPLAY_AUDIT[target_id] = dict(audit)
    return {**out, **audit}


def annotate_report(report_path: Path) -> None:
    # v4 adds exact geometry-DEM binary-hash audit. Do not call v6 annotator because
    # this revision intentionally has heterogeneous frozen-generation routing semantics.
    v4.annotate_report(report_path)
    if not report_path.exists():
        return
    doc = json.loads(report_path.read_text(encoding="utf-8"))
    doc["execution_revision"] = "0.7_GEOMETRY_PROVENANCE_AWARE_ROUTING_REPLAY"
    doc["routing_replay_implementation_sha256"] = sha256_path(Path(__file__).resolve())
    doc["geometry_generation_routing_replay_audit"] = ROUTING_REPLAY_AUDIT
    doc["pysheds_geometry_replay_audit"] = v6.REPLAY_AUDIT
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
    base.EXECUTION = EXECUTION_V7
    base.build_exact_geometry_dem = v6.build_exact_dem_capture
    base.target_metrics = v2.target_metrics_with_context
    base.d8_metrics = d8_metrics_provenance_dispatch
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
