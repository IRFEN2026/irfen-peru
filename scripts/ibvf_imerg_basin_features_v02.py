#!/usr/bin/env python3
"""Precision-gated v0.2 wrapper for Cashahuacra IMERG basin features.

The native 0.1-degree grid reconstructed from float coordinate centers can leave
sub-0.01% numerical slivers when intersected with a detailed DEM-derived basin.
This wrapper requires at least 99.995% raw geometric coverage, records that raw
fraction, and only then normalizes the geometric weights to one. It does not
relax the separate missing-value rule: valid precipitation coverage after
normalization must still satisfy the strict base extractor gate and missing
values are never imputed as zero.
"""
from __future__ import annotations

import h5py
import numpy as np
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform

import ibvf_imerg_basin_features as base

MIN_GRID_GEOMETRY_COVERAGE = 0.99995
MAX_GRID_GEOMETRY_COVERAGE = 1.00005


def build_weights(h5_path, basin):
    with h5py.File(h5_path, "r") as h5:
        _, lon, lat = base.dataset_values(h5)
    dlon=float(np.median(np.diff(lon))); dlat=float(np.median(np.diff(lat)))
    if not (0.09 <= abs(dlon) <= 0.11 and 0.09 <= abs(dlat) <= 0.11):
        raise ValueError(f"unexpected IMERG grid spacing {dlon},{dlat}")
    hx,hy=abs(dlon)/2.0,abs(dlat)/2.0
    minx,miny,maxx,maxy=basin.bounds
    lon_idx=np.where((lon+hx >= minx) & (lon-hx <= maxx))[0]
    lat_idx=np.where((lat+hy >= miny) & (lat-hy <= maxy))[0]
    to_utm=Transformer.from_crs("EPSG:4326","EPSG:32718",always_xy=True).transform
    basin_area=float(transform(to_utm,basin).area)
    cells=[]
    for i in lon_idx:
        for j in lat_idx:
            cell=box(float(lon[i]-hx),float(lat[j]-hy),float(lon[i]+hx),float(lat[j]+hy))
            inter=basin.intersection(cell)
            if inter.is_empty: continue
            area=float(transform(to_utm,inter).area)
            if area <= 0: continue
            cells.append({"lon_index":int(i),"lat_index":int(j),"lon":float(lon[i]),"lat":float(lat[j]),"overlap_m2":area,"raw_basin_fraction":area/basin_area})
    raw_coverage=sum(c["raw_basin_fraction"] for c in cells)
    if not cells or not (MIN_GRID_GEOMETRY_COVERAGE <= raw_coverage <= MAX_GRID_GEOMETRY_COVERAGE):
        raise ValueError(f"IMERG raw grid geometry coverage outside preregistered tolerance: {raw_coverage}")
    for c in cells:
        c["basin_fraction"] = c["raw_basin_fraction"] / raw_coverage
    return {
        "weight_contract_version":"AREA_OVERLAP_V0.2_PRECISION_GATED_NORMALIZED",
        "grid_spacing_deg":{"lon":abs(dlon),"lat":abs(dlat)},
        "basin_area_m2":basin_area,
        "cells":cells,
        "raw_overlap_fraction_sum":raw_coverage,
        "min_raw_geometry_coverage_required":MIN_GRID_GEOMETRY_COVERAGE,
        "normalized_weight_sum":sum(c["basin_fraction"] for c in cells),
        "normalization_reason":"FLOAT_GRID_EDGE_NUMERICAL_SLIVER_ONLY_AFTER_99_995_PERCENT_COVERAGE_GATE"
    }


base.build_weights = build_weights

if __name__ == "__main__":
    raise SystemExit(base.main())
