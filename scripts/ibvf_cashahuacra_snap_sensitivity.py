#!/usr/bin/env python3
"""Secondary positional sensitivity for the Cashahuacra v0.3 hydrologic snap.

RESEARCH_ONLY / TEST_ONLY. This test is declared without reference to a target
basin area or territorial activation outcome. It holds the Copernicus GLO-30
conditioned D8 field and reconstructed main channel fixed, then perturbs only
the ANA 0+000 search seed by half a nominal DEM pixel (15 m) and one nominal
pixel (30 m) in the four cardinal directions.

The half-pixel gate is deliberately exact and parameter-free with respect to
basin size: center + N/S/E/W 15 m must select the identical raster outlet cell.
The 30 m perturbations are diagnostic only; their outlet movement, area change,
and catchment Jaccard are reported but do not retroactively tune the snap.
DEM-conditioning sensitivity remains a separate pending gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import shape

import ibvf_cashahuacra_dem_snap as base
import ibvf_cashahuacra_nearest_channel_snap as near

PERTURBATIONS_M = [
    ("CENTER", 0.0, 0.0),
    ("E15", 15.0, 0.0),
    ("W15", -15.0, 0.0),
    ("N15", 0.0, 15.0),
    ("S15", 0.0, -15.0),
    ("E30", 30.0, 0.0),
    ("W30", -30.0, 0.0),
    ("N30", 0.0, 30.0),
    ("S30", 0.0, -30.0),
]
HALF_PIXEL_LABELS = {"CENTER", "E15", "W15", "N15", "S15"}


def channel_hash(cells: list[tuple[int, int]]) -> str:
    canonical = "\n".join(f"{r},{c}" for r, c in cells) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def catchment_mask(grid: Any, fdir: Any, selected: dict[str, Any]) -> np.ndarray:
    catch = grid.catchment(
        x=selected["lon"],
        y=selected["lat"],
        fdir=fdir,
        dirmap=base.DIRMAP,
        xytype="coordinate",
    )
    return np.asarray(catch).astype(bool)


def geod_area_km2(grid: Any, fdir: Any, transform: Any, selected: dict[str, Any]) -> float:
    feature = base.delineate_if_stable(grid, fdir, transform, selected)
    geom = shape(feature["geometry"])
    area_m2, _ = base.GEOD.geometry_area_perimeter(geom)
    return abs(float(area_m2)) / 1e6


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    inter = int(np.logical_and(a, b).sum())
    union = int(np.logical_or(a, b).sum())
    return float(inter / union) if union else 1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    seed_e = float(base.ANA_SEED_UTM18S["easting_m"])
    seed_n = float(base.ANA_SEED_UTM18S["northing_m"])
    to_wgs84 = Transformer.from_crs(base.ANA_SEED_UTM18S["epsg"], 4326, always_xy=True)
    seed_lon, seed_lat = to_wgs84.transform(seed_e, seed_n)

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-cashahuacra-snap-positional-sensitivity-v0.1",
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
            "test_dimension": "ANA_SEED_POSITION_ONLY",
            "dem_and_conditioning_held_fixed": True,
            "channel_held_fixed": True,
            "perturbations_utm18s_m": [
                {"label": label, "east_m": de, "north_m": dn}
                for label, de, dn in PERTURBATIONS_M
            ],
            "half_pixel_gate": "CENTER_PLUS_CARDINAL_15M_MUST_SELECT_EXACT_SAME_RASTER_CELL",
            "one_pixel_30m_role": "DIAGNOSTIC_ONLY",
            "target_basin_area_used": False,
            "historical_candidate_area_used_for_selection": False,
            "territorial_activation_evidence_used": False,
            "operational_threshold_used": False,
            "conditioning_sensitivity_is_separate_gate": True,
        },
        "dem": {
            "collection": "cop-dem-glo-30",
            "item_id": base.TILE_ID,
            "url": base.TILE_URL,
        },
        "ana_seed": {
            **base.ANA_SEED_UTM18S,
            "lon": seed_lon,
            "lat": seed_lat,
        },
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_cash_possens_") as td_raw:
        td = Path(td_raw)
        raw = td / f"{base.TILE_ID}.tif"
        frozen = base.download(base.TILE_URL, raw)
        report["dem"]["acquisition"] = frozen
        if frozen.get("transport_status") != "SUCCESS":
            report["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
            report["secondary_sensitivity_status"] = "NOT_RUN_TRANSPORT_BLOCKED"
        else:
            cropped = td / "cashahuacra_dem_crop.tif"
            base.crop_tile(raw, cropped)
            report["dem"]["crop_sha256"] = base.sha256_file(cropped)

            grid = base.Grid.from_raster(str(cropped))
            z = grid.read_raster(str(cropped))
            conditioned = grid.fill_pits(z)
            conditioned = grid.fill_depressions(conditioned)
            conditioned = grid.resolve_flats(conditioned)
            fdir = grid.flowdir(conditioned, dirmap=base.DIRMAP)
            acc = grid.accumulation(fdir, dirmap=base.DIRMAP)
            fdir_arr, acc_arr = np.asarray(fdir), np.asarray(acc)
            with rasterio.open(cropped) as src:
                transform = src.transform

            anchors = [
                base.select_max_acc_within_radius(acc_arr, transform, seed_lon, seed_lat, radius)
                for radius in base.SNAP_RADII_M
            ]
            channels: list[list[tuple[int, int]]] = []
            channel_records = []
            for anchor in anchors:
                channel = near.channel_from_anchor(fdir_arr, acc_arr, (anchor["row"], anchor["col"]))
                channels.append(channel)
                channel_records.append({
                    "anchor_radius_m": anchor["radius_m"],
                    "cell_count": len(channel),
                    "sha256": channel_hash(channel),
                })
            channel_hashes = {x["sha256"] for x in channel_records}
            exact_channel_agreement = len(channel_hashes) == 1
            report["channel_reconstruction"] = {
                "records": channel_records,
                "exact_sequence_agreement": exact_channel_agreement,
            }
            if not exact_channel_agreement:
                report["scientific_data_status"] = "PRESENT"
                report["secondary_sensitivity_status"] = "BLOCKED_ANCHOR_CHANNEL_SEQUENCES_DIFFER"
            else:
                canonical = channels[0]
                variants: list[dict[str, Any]] = []
                masks: dict[str, np.ndarray] = {}
                for label, de, dn in PERTURBATIONS_M:
                    lon, lat = to_wgs84.transform(seed_e + de, seed_n + dn)
                    selected = near.nearest_cell(canonical, acc_arr, transform, lon, lat)
                    rec: dict[str, Any] = {
                        "label": label,
                        "seed_offset_east_m": de,
                        "seed_offset_north_m": dn,
                        "seed_lon": lon,
                        "seed_lat": lat,
                        **selected,
                    }
                    if selected.get("status") == "SELECTED":
                        mask = catchment_mask(grid, fdir, selected)
                        masks[label] = mask
                        rec["catchment_cells"] = int(mask.sum())
                        rec["area_km2"] = round(geod_area_km2(grid, fdir, transform, selected), 6)
                    variants.append(rec)

                baseline = next(x for x in variants if x["label"] == "CENTER")
                base_cell = (baseline.get("row"), baseline.get("col"))
                base_area = float(baseline.get("area_km2") or 0.0)
                base_mask = masks.get("CENTER")
                for rec in variants:
                    if rec.get("status") != "SELECTED" or base_mask is None:
                        continue
                    rec["outlet_distance_from_center_m"] = round(
                        base.distance_m(
                            baseline["lon"], baseline["lat"], rec["lon"], rec["lat"]
                        ),
                        3,
                    )
                    rec["same_outlet_cell_as_center"] = (rec.get("row"), rec.get("col")) == base_cell
                    rec["area_difference_from_center_pct"] = (
                        round((float(rec["area_km2"]) - base_area) / base_area * 100.0, 6)
                        if base_area else None
                    )
                    rec["catchment_jaccard_vs_center"] = round(jaccard(base_mask, masks[rec["label"]]), 9)

                half = [x for x in variants if x["label"] in HALF_PIXEL_LABELS]
                half_exact = len(half) == len(HALF_PIXEL_LABELS) and all(
                    x.get("status") == "SELECTED" and (x.get("row"), x.get("col")) == base_cell
                    for x in half
                )
                one_pixel = [x for x in variants if x["label"].endswith("30")]
                report["variants"] = variants
                report["half_pixel_exact_cell_stable"] = half_exact
                report["one_pixel_diagnostics"] = {
                    "max_outlet_distance_from_center_m": round(max(float(x.get("outlet_distance_from_center_m") or 0.0) for x in one_pixel), 3),
                    "min_jaccard_vs_center": round(min(float(x.get("catchment_jaccard_vs_center") or 0.0) for x in one_pixel), 9),
                    "max_abs_area_difference_pct": round(max(abs(float(x.get("area_difference_from_center_pct") or 0.0)) for x in one_pixel), 6),
                }
                report["scientific_data_status"] = "PRESENT"
                report["secondary_sensitivity_status"] = (
                    "HALF_PIXEL_EXACT_CELL_STABLE_CONDITIONING_SENSITIVITY_PENDING"
                    if half_exact
                    else "HALF_PIXEL_EXACT_CELL_UNSTABLE_REVIEW_REQUIRED"
                )
                report["conditioning_sensitivity_status"] = "PENDING_NOT_RUN"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "secondary_sensitivity_status": report.get("secondary_sensitivity_status"),
        "channel_reconstruction": report.get("channel_reconstruction"),
        "half_pixel_exact_cell_stable": report.get("half_pixel_exact_cell_stable"),
        "one_pixel_diagnostics": report.get("one_pixel_diagnostics"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
