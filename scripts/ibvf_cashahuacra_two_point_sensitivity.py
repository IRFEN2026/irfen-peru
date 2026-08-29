#!/usr/bin/env python3
"""Sensitivity audit for Cashahuacra ANA two-point D8 channel identity.

RESEARCH_ONLY / TEST_ONLY.

The freeze gate tests one nominal GLO-30 pixel (30 m) of positional uncertainty
around ANA 2+180 while keeping the predeclared hydrologic preprocessing fixed.
A second deliberately under-conditioned DEM route is run only as a diagnostic
stress test; changing the conditioning algorithm is changing the method, so it
does not retrospectively redefine the positional freeze gate.

No published basin area/length/elevation, territorial activation outcome,
operational threshold, or EVENT/NONE label is used.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer

import ibvf_cashahuacra_dem_snap as base
import ibvf_cashahuacra_two_point_snap as two

EXPECTED_DEM_SHA256 = "d9f8d410da66bfb85c73b957401aea73043f8618cccdb7d1fc76082d30a31130"
POSITIONAL_STEP_M = 30.0
POSITIONAL_OFFSETS_M = [-POSITIONAL_STEP_M, 0.0, POSITIONAL_STEP_M]
ANCHOR_RADIUS_M = 120.0
DOWNSTREAM_GATE_M = 360.0
STANDARD_VARIANT = "FILL_PITS_FILL_DEPRESSIONS_RESOLVE_FLATS"
STRESS_VARIANT = "FILL_PITS_RESOLVE_FLATS_NO_MULTICELL_DEPRESSION_FILL"
CONDITIONING_VARIANTS = [STANDARD_VARIANT, STRESS_VARIANT]


def offset_lonlat(easting: float, northing: float, de: float, dn: float) -> tuple[float, float]:
    tr = Transformer.from_crs(32718, 4326, always_xy=True)
    return tr.transform(easting + de, northing + dn)


def condition(grid: Any, z: Any, variant: str) -> Any:
    if variant == STANDARD_VARIANT:
        out = grid.fill_pits(z)
        out = grid.fill_depressions(out)
        return grid.resolve_flats(out)
    if variant == STRESS_VARIANT:
        out = grid.fill_pits(z)
        return grid.resolve_flats(out)
    raise ValueError(f"Unknown conditioning variant: {variant}")


def downstream_seed_grid() -> list[dict[str, Any]]:
    p = base.ANA_SEED_UTM18S
    out: list[dict[str, Any]] = []
    for de in POSITIONAL_OFFSETS_M:
        for dn in POSITIONAL_OFFSETS_M:
            lon, lat = offset_lonlat(float(p["easting_m"]), float(p["northing_m"]), de, dn)
            out.append({"de_m": de, "dn_m": dn, "lon": lon, "lat": lat})
    return out


def scenario_summary(scenarios: list[dict[str, Any]], catchments: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    selected = [s for s in scenarios if s["conditioning_variant"] == variant and s.get("status") == "SELECTED_PRE_LARGER_BRANCH_CONFLUENCE"]
    expected = len(POSITIONAL_OFFSETS_M) ** 2
    all_selected = len(selected) == expected
    cells = sorted({(s["outlet_row"], s["outlet_col"]) for s in selected}) if selected else []
    c = [x for x in catchments if x["conditioning_variant"] == variant]
    counts = sorted({int(x["catchment_cells"]) for x in c})
    return {
        "expected_scenarios": expected,
        "successful_selected_scenarios": len(selected),
        "all_scenarios_selected": all_selected,
        "unique_outlet_cells": [{"row": r, "col": col} for r, col in cells],
        "exact_outlet_cell_agreement": all_selected and len(cells) == 1,
        "all_downstream_seed_grid_distances_within_gate": all_selected and all(float(s["max_distance_to_downstream_seed_grid_m"]) <= DOWNSTREAM_GATE_M for s in selected),
        "all_catchments_match_outlet_accumulation": bool(c) and all(bool(x["exact_internal_cell_count_agreement"]) for x in c),
        "unique_catchment_cell_counts": counts,
        "same_catchment_cell_count": bool(counts) and len(counts) == 1,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    down_lon, down_lat = base.seed_lonlat()
    upstream = two.ANA_UPSTREAM_UTM18S
    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-cashahuacra-two-point-sensitivity-v0.2",
        "generated_at": base.now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "contract": {
            "purpose": "POSITIONAL_GATE_PLUS_SEPARATE_CONDITIONING_STRESS_DIAGNOSTIC",
            "nominal_dem_pixel_step_m": POSITIONAL_STEP_M,
            "upstream_anchor_offsets_east_m": POSITIONAL_OFFSETS_M,
            "upstream_anchor_offsets_north_m": POSITIONAL_OFFSETS_M,
            "upstream_anchor_radius_m": ANCHOR_RADIUS_M,
            "standard_conditioning_variant": STANDARD_VARIANT,
            "conditioning_stress_variant": STRESS_VARIANT,
            "conditioning_stress_is_diagnostic_not_freeze_gate": True,
            "downstream_seed_offsets_east_m": POSITIONAL_OFFSETS_M,
            "downstream_seed_offsets_north_m": POSITIONAL_OFFSETS_M,
            "downstream_seed_max_distance_m": DOWNSTREAM_GATE_M,
            "positional_pass_requires_same_outlet_row_col_all_standard_scenarios": True,
            "positional_pass_requires_same_catchment_cell_count_all_standard_scenarios": True,
            "positional_pass_requires_each_standard_catchment_cells_equal_outlet_accumulation": True,
            "target_basin_area_used": False,
            "published_basin_length_used": False,
            "published_elevation_envelope_used": False,
            "territorial_activation_evidence_used": False,
            "operational_threshold_used": False,
            "event_none_label_used": False
        },
        "dem": {
            "collection": "cop-dem-glo-30",
            "item_id": base.TILE_ID,
            "url": base.TILE_URL,
            "expected_sha256": EXPECTED_DEM_SHA256
        }
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_cash_two_point_sens_") as td_raw:
        td = Path(td_raw)
        raw = td / f"{base.TILE_ID}.tif"
        frozen = base.download(base.TILE_URL, raw)
        report["dem"]["acquisition"] = frozen
        if frozen.get("transport_status") != "SUCCESS":
            report["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
            report["sensitivity_status"] = "NOT_RUN_TRANSPORT_BLOCKED"
        elif frozen.get("sha256") != EXPECTED_DEM_SHA256:
            report["scientific_data_status"] = "PRESENT_HASH_MISMATCH"
            report["sensitivity_status"] = "BLOCKED_DEM_HASH_MISMATCH"
        else:
            cropped = td / "cashahuacra_dem_crop.tif"
            base.crop_tile(raw, cropped)
            report["dem"]["crop_sha256"] = base.sha256_file(cropped)
            grid = base.Grid.from_raster(str(cropped))
            z = grid.read_raster(str(cropped))
            with rasterio.open(cropped) as src:
                transform = src.transform

            seed_grid = downstream_seed_grid()
            scenarios: list[dict[str, Any]] = []
            catchment_signatures: list[dict[str, Any]] = []

            for variant in CONDITIONING_VARIANTS:
                conditioned = condition(grid, z, variant)
                fdir = grid.flowdir(conditioned, dirmap=base.DIRMAP)
                acc = grid.accumulation(fdir, dirmap=base.DIRMAP)
                fdir_arr, acc_arr = np.asarray(fdir), np.asarray(acc)
                variant_selected: list[dict[str, Any]] = []

                for de in POSITIONAL_OFFSETS_M:
                    for dn in POSITIONAL_OFFSETS_M:
                        up_lon, up_lat = offset_lonlat(float(upstream["easting_m"]), float(upstream["northing_m"]), de, dn)
                        anchor = base.select_max_acc_within_radius(acc_arr, transform, up_lon, up_lat, ANCHOR_RADIUS_M)
                        scenario: dict[str, Any] = {
                            "conditioning_variant": variant,
                            "upstream_offset_e_m": de,
                            "upstream_offset_n_m": dn,
                            "anchor_radius_m": ANCHOR_RADIUS_M,
                            "anchor_status": anchor.get("status")
                        }
                        if anchor.get("status") != "SELECTED":
                            scenario["status"] = "UPSTREAM_ANCHOR_UNAVAILABLE"
                            scenarios.append(scenario)
                            continue
                        path = base.trace_downstream_cells(fdir_arr, (int(anchor["row"]), int(anchor["col"])))
                        selected = two.pre_larger_branch_confluence(path, fdir_arr, acc_arr, transform, down_lon, down_lat)
                        scenario.update({
                            "status": selected.get("status"),
                            "anchor_row": int(anchor["row"]),
                            "anchor_col": int(anchor["col"]),
                            "anchor_seed_distance_m": anchor.get("seed_distance_m"),
                            "anchor_accumulation_cells": anchor.get("accumulation_cells"),
                            "path_cell_count": len(path)
                        })
                        if selected.get("status") == "SELECTED_PRE_LARGER_BRANCH_CONFLUENCE":
                            distances = [base.distance_m(s["lon"], s["lat"], selected["lon"], selected["lat"]) for s in seed_grid]
                            scenario.update({
                                "outlet_row": int(selected["row"]),
                                "outlet_col": int(selected["col"]),
                                "outlet_lon": selected["lon"],
                                "outlet_lat": selected["lat"],
                                "outlet_accumulation_cells": int(round(float(selected["accumulation_cells"]))),
                                "max_distance_to_downstream_seed_grid_m": round(max(distances), 3),
                                "min_distance_to_downstream_seed_grid_m": round(min(distances), 3)
                            })
                            variant_selected.append(scenario)
                        scenarios.append(scenario)

                unique_cells = sorted({(s["outlet_row"], s["outlet_col"]) for s in variant_selected})
                for row, col in unique_cells:
                    example = next(s for s in variant_selected if (s["outlet_row"], s["outlet_col"]) == (row, col))
                    expected_cells = int(example["outlet_accumulation_cells"])
                    catch = grid.catchment(x=int(col), y=int(row), fdir=fdir, dirmap=base.DIRMAP, xytype="index")
                    actual_cells = int(np.asarray(catch).astype(bool).sum())
                    catchment_signatures.append({
                        "conditioning_variant": variant,
                        "outlet_row": int(row),
                        "outlet_col": int(col),
                        "outlet_accumulation_cells": expected_cells,
                        "catchment_cells": actual_cells,
                        "exact_internal_cell_count_agreement": actual_cells == expected_cells
                    })

            standard = scenario_summary(scenarios, catchment_signatures, STANDARD_VARIANT)
            stress = scenario_summary(scenarios, catchment_signatures, STRESS_VARIANT)
            positional_pass = all([
                standard["all_scenarios_selected"],
                standard["exact_outlet_cell_agreement"],
                standard["all_downstream_seed_grid_distances_within_gate"],
                standard["all_catchments_match_outlet_accumulation"],
                standard["same_catchment_cell_count"]
            ])
            standard_cells = {(x["row"], x["col"]) for x in standard["unique_outlet_cells"]}
            stress_cells = {(x["row"], x["col"]) for x in stress["unique_outlet_cells"]}
            conditioning_agrees = bool(standard_cells) and standard_cells == stress_cells and standard.get("unique_catchment_cell_counts") == stress.get("unique_catchment_cell_counts")

            report["scientific_data_status"] = "PRESENT"
            report["scenarios"] = scenarios
            report["catchment_signatures"] = catchment_signatures
            report["summary"] = {
                "standard_positional_gate": standard,
                "conditioning_stress_diagnostic": stress,
                "conditioning_stress_exactly_agrees_with_standard": conditioning_agrees
            }
            if positional_pass:
                report["sensitivity_status"] = "PASS_POSITIONAL_30M_STANDARD_PREPROCESSING"
                report["morphometry_disposition"] = "CANDIDATE_MORPHOMETRY_SUPPORTED_BY_POSITIONAL_SENSITIVITY_NOT_OPERATIONAL"
            else:
                report["sensitivity_status"] = "FAIL_POSITIONAL_SENSITIVITY_REVIEW_REQUIRED"
                report["morphometry_disposition"] = "BLOCKED_BY_POSITIONAL_SENSITIVITY"
            report["conditioning_stress_status"] = "AGREES_WITH_STANDARD" if conditioning_agrees else "DIFFERS_FROM_STANDARD_DIAGNOSTIC_ONLY"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "sensitivity_status": report.get("sensitivity_status"),
        "conditioning_stress_status": report.get("conditioning_stress_status"),
        "summary": report.get("summary"),
        "morphometry_disposition": report.get("morphometry_disposition")
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
