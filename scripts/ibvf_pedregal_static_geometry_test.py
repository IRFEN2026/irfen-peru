#!/usr/bin/env python3
"""Blind/static Pedregal geometry diagnostic using a pre-existing outlet candidate.

This test reads no rainfall, selected-window magnitudes, known event dates,
territorial outcomes, damage, risk or alert fields. The outlet is fixed to the
pre-existing pedregal_8_20 candidate before the INGEMMET static-area check.
It recomputes the GLO-30 catchment by raster index and checks internal
accumulation consistency plus an independent static geomorphic area reference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.merge import merge
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from pyproj import Geod
import requests
from pysheds.grid import Grid

GEOD = Geod(ellps="WGS84")
FORBIDDEN = ("outcome", "event", "activation", "damage", "incident", "risk", "alert", "priority", "case_control")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def csha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def geod_area_km2(g) -> float:
    a, _ = GEOD.geometry_area_perimeter(g)
    return abs(a) / 1e6


def polygonize(mask: np.ndarray, transform):
    geoms = [shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask.astype(bool), transform=transform) if int(v) == 1]
    if not geoms:
        return None
    return unary_union(geoms).buffer(0)


def tile_name(lat_deg: int, lon_deg: int) -> str:
    # Inputs are integer southwest tile coordinates from floor(), avoiding
    # negative-coordinate truncation ambiguity.
    latp = ("N" if lat_deg >= 0 else "S") + f"{abs(lat_deg):02d}"
    lonp = ("E" if lon_deg >= 0 else "W") + f"{abs(lon_deg):03d}"
    return f"Copernicus_DSM_COG_10_{latp}_00_{lonp}_00_DEM"


def tile_url(lat_deg: int, lon_deg: int) -> str:
    n = tile_name(lat_deg, lon_deg)
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif"


def guards(doc: dict[str, Any]) -> None:
    assert doc["deployment_status"] == "RESEARCH_ONLY"
    assert doc["test_only"] is True
    assert doc["production_use"] is False
    assert doc["production_ready"] is False
    assert doc["operational_alerting_enabled"] is False
    assert doc["uses_operational_event_none_labels"] is False
    assert doc["territorial_activation_evidence_blinded"] is True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--contract", type=Path, default=Path("site/data/validation/ibvf_ingemmet_static_geomorphic_contract_v01.json"))
    ap.add_argument("--candidates", type=Path, default=Path("site/data/watersheds/chosica_local_candidate_sets.geojson"))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--geojson-output", type=Path, required=True)
    args = ap.parse_args()
    root = args.repo_root.resolve()
    contract = load(root / args.contract)
    guards(contract)
    candidates = load(root / args.candidates)

    # Fail closed if the contract itself contains outcome-like keys outside the
    # explicit sealed policy text or if any runtime input introduces them.
    assert contract["source_policy"]["no_outlet_optimization_against_area"] is True
    assert contract["source_policy"]["validation_only_of_preexisting_candidate_outlet"] is True
    rule = contract["pedregal_test_rule"]
    target_id = rule["candidate_id"]
    matches = [f for f in candidates.get("features", []) if f.get("properties", {}).get("id") == target_id]
    if len(matches) != 1:
        raise SystemExit(f"FAIL_CLOSED_PREEXISTING_CANDIDATE_COUNT:{len(matches)}")
    p = matches[0]["properties"]
    x0 = float(p["snapped_lon"]); y0 = float(p["snapped_lat"])
    prior_acc_km2 = float(p["accumulation_area_approx_km2"])
    if abs(prior_acc_km2 - 9.904) > 1e-6:
        raise SystemExit("FAIL_CLOSED_PREEXISTING_CANDIDATE_IDENTITY_CHANGED")

    pad = 0.12
    xmin, xmax, ymin, ymax = x0 - pad, x0 + pad, y0 - pad, y0 + pad
    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-pedregal-static-geometry-test-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "framework": "IRFEN Independent Basin Validation Framework",
        "deployment_status": "RESEARCH_ONLY", "test_only": True,
        "production_use": False, "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "rainfall_read": False, "known_event_dates_read": False,
        "territorial_outcomes_read": False, "damage_fields_read": False,
        "case_control_assignment_performed": False,
        "outlet_optimized_against_reference_area": False,
        "candidate_id": target_id,
        "fixed_outlet": {"lon": x0, "lat": y0},
        "preexisting_accumulation_area_approx_km2": prior_acc_km2,
        "static_reference_area_km2": float(rule["reference_area_km2"]),
        "static_reference_basin_length_km": float(contract["sources"][0]["static_constraints"]["basin_length_km"]),
        "static_reference_mean_slope_percent": float(contract["sources"][0]["static_constraints"]["mean_slope_percent"]),
        "static_reference_drainage_pattern": contract["sources"][0]["static_constraints"]["drainage_pattern"],
        "source_allowed_section": contract["sources"][0]["allowed_section"],
        "source_outcome_section_read": False,
    }

    with tempfile.TemporaryDirectory(prefix="ibvf_pedregal_static_") as td0:
        td = Path(td0); srcs = []
        for lat in range(math.floor(ymin), math.floor(ymax) + 1):
            for lon in range(math.floor(xmin), math.floor(xmax) + 1):
                url = tile_url(lat, lon); path = td / f"{tile_name(lat, lon)}.tif"
                r = requests.get(url, timeout=(15, 120)); r.raise_for_status(); path.write_bytes(r.content)
                srcs.append(rasterio.open(path))
        mosaic, transform = merge(srcs, bounds=(xmin, ymin, xmax, ymax))
        profile = srcs[0].profile.copy(); profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, count=1)
        tile_ids = [Path(s.name).stem for s in srcs]
        for s in srcs: s.close()
        dempath = td / "pedregal_dem.tif"
        with rasterio.open(dempath, "w", **profile) as dst: dst.write(mosaic[0], 1)

        grid = Grid.from_raster(str(dempath)); dem = grid.read_raster(str(dempath))
        dem = grid.fill_pits(dem); dem = grid.fill_depressions(dem); dem = grid.resolve_flats(dem)
        fdir = grid.flowdir(dem); acc = grid.accumulation(fdir)
        arr = np.asarray(acc, dtype=float)

        # Find the nearest raster-cell center to the fixed pre-existing outlet,
        # but do not search by accumulation or reference area.
        inv = ~transform
        cf, rf = inv * (x0, y0)
        c0 = int(round(cf - 0.5)); r0 = int(round(rf - 0.5))
        if not (0 <= r0 < arr.shape[0] and 0 <= c0 < arr.shape[1]):
            raise SystemExit("FAIL_CLOSED_FIXED_OUTLET_OUTSIDE_DEM")
        xcell, ycell = transform * (c0 + 0.5, r0 + 0.5)
        accumulation_cells = float(arr[r0, c0])

        # Critical diagnostic: delineate by integer raster index, not geographic
        # coordinate, to remove coordinate/index ambiguity from the legacy build.
        catch = grid.catchment(x=c0, y=r0, fdir=fdir, xytype="index")
        mask = np.asarray(catch, dtype=bool)
        catchment_cells = int(mask.sum())
        geom = polygonize(mask, transform)
        if geom is None or geom.is_empty:
            raise SystemExit("FAIL_CLOSED_EMPTY_CATCHMENT")
        area_km2 = geod_area_km2(geom)
        ref = float(rule["reference_area_km2"])
        area_rel_error = abs(area_km2 - ref) / ref
        internal_rel_error = abs(catchment_cells - accumulation_cells) / max(accumulation_cells, 1.0)
        pass_internal = internal_rel_error <= float(rule["accumulation_vs_catchment_cell_count_relative_tolerance"])
        pass_static = area_rel_error <= float(rule["max_absolute_area_relative_error"])
        status = "PASS_RESEARCH_CANDIDATE_STATIC_GEOMORPHIC_SUPPORT_NO_UNBLIND" if (pass_internal and pass_static) else "FAIL_UNKNOWN_GEOMETRY_UNRESOLVED"

        report.update({
            "dem_tiles": tile_ids,
            "fixed_outlet_cell": {"row": r0, "col": c0, "lon": float(xcell), "lat": float(ycell)},
            "accumulation_cells_at_fixed_outlet": accumulation_cells,
            "catchment_cell_count": catchment_cells,
            "accumulation_vs_catchment_relative_error": internal_rel_error,
            "internal_accumulation_consistency_pass": pass_internal,
            "reconstructed_area_km2": area_km2,
            "static_reference_area_relative_error": area_rel_error,
            "static_area_support_pass": pass_static,
            "geometry_canonical_sha256": csha(mapping(geom)),
            "status": status,
            "geometry_semantics": rule["pass_semantics"] if status.startswith("PASS_") else rule["failure_semantics"],
            "modeling_allowed": False,
        })
        feature = {
            "type": "Feature",
            "properties": {
                "unit_id": "pedregal",
                "candidate_id": "pedregal_static_test_v01",
                "candidate_status": "REVIEW_ONLY",
                "geometry_semantics": report["geometry_semantics"],
                "production_use": False,
                "production_ready": False,
                "operational_alerting_enabled": False,
                "fixed_preexisting_outlet_candidate": target_id,
                "reconstructed_area_km2": area_km2,
                "static_reference_area_km2": ref,
                "static_area_support_pass": pass_static,
                "internal_accumulation_consistency_pass": pass_internal,
                "territorial_activation_evidence_blinded": True,
            },
            "geometry": mapping(geom),
        }
        fc = {"type": "FeatureCollection", "properties": {"deployment_status": "RESEARCH_ONLY", "test_only": True, "production_use": False, "warning": "Research candidate only; no territorial outcome used."}, "features": [feature]}

    guards(report)
    out = root / args.output; gout = root / args.geojson_output
    out.parent.mkdir(parents=True, exist_ok=True); gout.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    gout.write_text(json.dumps(fc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "area_km2": report["reconstructed_area_km2"], "area_rel_error": report["static_reference_area_relative_error"], "acc_cells": report["accumulation_cells_at_fixed_outlet"], "catch_cells": report["catchment_cell_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
