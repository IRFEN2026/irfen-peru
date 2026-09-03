#!/usr/bin/env python3
"""Apply the frozen R3 footprint amendment to every exact legacy containment blocker.

RESEARCH_ONLY / TEST_ONLY. The parent amendment v0.1 already froze a general
rule whose scope is every case that hits the exact legacy rectangular basin
window containment blocker. The original implementation accidentally treated
its two pre-audited diagnostic cases as an exhaustive whitelist. This wrapper
repairs that implementation mismatch: only after the unchanged legacy R3 path
returns the exact blocker, it computes the same geometry-only joint-footprint
fraction from R2 metadata. No raster pixel is read for this precheck. Existing
pre-audited cases must still reproduce their frozen fraction exactly. Newly
encountered blocker cases use the already-frozen deterministic rule, not a new
case-specific exception. The 0.95 threshold and all scientific inputs remain
unchanged; no R4 magnitude, territorial outcome, known event date, or
case/control role is consulted.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import rasterio
from rasterio.warp import transform_geom
from shapely.geometry import box, shape

import ibvf_primary6_sentinel1_r3_blinded_amendment_wrapper_v01 as parent

EXPECTED_PARENT_AMENDMENT_SHA256 = "bbc0b3cd9f520911703b0a98f4a1d58f7f4bd2cebc1d13c1604401e8ae33ef7a"
EXPECTED_SCOPE = "ONLY_CASES_THAT_HIT_LEGACY_RECTANGULAR_FROZEN_BASIN_WINDOW_CONTAINMENT_BLOCKER"


def compute_metadata_only_joint_fraction(args, amendment: dict[str, Any]) -> float:
    contract = parent.load(args.global_contract)
    anchor = parent.load(args.anchor_r3_contract)
    r2 = parent.load(args.r2_report)
    for d in (contract, anchor, r2, amendment):
        parent.guard(d)
    if r2.get("case_id") != args.case_id or r2.get("territorial_outcomes_read") is not False:
        raise SystemExit("R2 identity/blindness mismatch before geometry-only blocker audit")
    threshold = float(contract["r3_rule"]["minimum_common_support_fraction"])
    if threshold != 0.95 or float(anchor["common_support"]["minimum_fraction"]) != 0.95:
        raise SystemExit("frozen R3 threshold changed")
    unit = contract["unit_geometry_and_projection"][r2["unit_id"]]
    if Path(unit["geometry_path"]) != args.basin:
        raise SystemExit("basin differs from frozen geometry")
    if parent.sha256_file(args.pre) != r2["pre"]["output"]["sha256"] or parent.sha256_file(args.post) != r2["post"]["output"]["sha256"]:
        raise SystemExit("R2 raster identity mismatch before geometry-only blocker audit")
    geom_wgs84 = parent.legacy.select_geometry(args.basin, unit.get("geometry_selector"))
    with rasterio.open(args.pre) as pre_ds, rasterio.open(args.post) as post_ds:
        # Opening datasets for CRS/bounds/transform is metadata-only; no read()/dataset_mask() occurs here.
        tol = float(anchor["target_pixel_lattice_gate"]["absolute_coordinate_tolerance"])
        tol_pixels = float(anchor["target_pixel_lattice_gate"]["integer_phase_tolerance_pixels"])
        parent.integer_phase(pre_ds, post_ds, tol, tol_pixels)
        geom = shape(transform_geom("EPSG:4326", pre_ds.crs, geom_wgs84, precision=-1))
        if geom.is_empty or geom.area <= 0:
            raise SystemExit("projected frozen basin geometry invalid")
        return float(geom.intersection(box(*pre_ds.bounds)).intersection(box(*post_ds.bounds)).area / geom.area)


def main() -> int:
    original_apply = parent.apply_amendment

    def apply_general_frozen_scope(args, legacy_report: dict[str, Any]) -> int:
        if legacy_report.get("status") != parent.LEGACY_BLOCKER:
            raise SystemExit("general footprint rule may run only after exact legacy containment blocker")
        if parent.sha256_file(args.blocker_amendment) != EXPECTED_PARENT_AMENDMENT_SHA256:
            raise SystemExit("unexpected parent blocker-amendment bytes")
        amendment = parent.load(args.blocker_amendment)
        r3a = amendment["r3_spatial_footprint_amendment"]
        if r3a.get("amendment_scope") != EXPECTED_SCOPE:
            raise SystemExit("parent amendment does not freeze the expected general blocker scope")
        if float(r3a.get("minimum_common_support_fraction", 0.0)) != 0.95:
            raise SystemExit("parent amendment R3 threshold changed")
        if amendment.get("r4_values_read_during_amendment_design") is not False or amendment.get("territorial_outcomes_read_during_amendment_design") is not False:
            raise SystemExit("parent amendment blindness provenance invalid")

        frozen_cases = {x["case_id"]: x for x in r3a.get("diagnostic_cases_frozen_before_amendment", [])}
        precomputed = args.case_id in frozen_cases
        if precomputed:
            rc = original_apply(args, legacy_report)
        else:
            # This calculation occurs only after the exact legacy blocker above and reads metadata only.
            fraction = compute_metadata_only_joint_fraction(args, amendment)
            runtime_doc = copy.deepcopy(amendment)
            runtime_doc["r3_spatial_footprint_amendment"]["diagnostic_cases_frozen_before_amendment"].append({
                "case_id": args.case_id,
                "joint_geometry_footprint_coverage_fraction": fraction,
                "runtime_general_rule_application": True,
                "case_specific_scientific_exception": False,
                "raster_pixels_read_for_geometry_precheck": False,
                "r4_values_read_for_geometry_precheck": False,
                "territorial_outcomes_read_for_geometry_precheck": False,
            })
            original_load = parent.load

            def load_with_runtime_general_rule(path: Path) -> dict[str, Any]:
                if Path(path) == Path(args.blocker_amendment):
                    return copy.deepcopy(runtime_doc)
                return original_load(path)

            parent.load = load_with_runtime_general_rule
            try:
                rc = original_apply(args, legacy_report)
            finally:
                parent.load = original_load

        if Path(args.report_output).is_file():
            report = json.loads(Path(args.report_output).read_text(encoding="utf-8"))
            report["r3_v02_general_scope_implementation_repair"] = True
            report["parent_amendment_general_scope_applied"] = True
            report["parent_diagnostic_case_precomputed_before_amendment"] = precomputed
            report["case_specific_scientific_exception_added"] = False
            report["geometry_precheck_computed_only_after_exact_legacy_blocker"] = True
            report["raster_pixels_read_to_choose_general_scope_route"] = False
            report["r4_values_read_to_choose_general_scope_route"] = False
            report["territorial_outcomes_read_to_choose_general_scope_route"] = False
            report["minimum_common_support_fraction_changed"] = False
            Path(args.report_output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return rc

    parent.apply_amendment = apply_general_frozen_scope
    try:
        return parent.main()
    finally:
        parent.apply_amendment = original_apply


if __name__ == "__main__":
    raise SystemExit(main())
