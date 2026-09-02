#!/usr/bin/env python3
"""Storage-only wrapper for the frozen PRIMARY6 Sentinel-1 R3 algorithm.

RESEARCH_ONLY / TEST_ONLY. This wrapper changes only the physical GeoTIFF
storage layout used for lossless basin crops. The scientific R3 algorithm,
frozen basin windows, native pixels, masks, support threshold, and blind gates
remain inherited unchanged from ``ibvf_primary6_sentinel1_r3_common_support``.

The wrapper exists because the runner combination used by the blind pilot wrote
an internal TIFF mask into a single full-image compressed strip; the resulting
mask IFD could not be read back by GDAL (``Invalid strip byte count 0``). Using
fixed 512x512 lossless Deflate tiles avoids that storage failure while the
existing exact array and mask identity checks still gate acceptance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.windows import Window

import ibvf_primary6_sentinel1_r3_common_support as core


def write_lossless_crop_tiled(
    src: rasterio.DatasetReader,
    arr: np.ndarray,
    mask: np.ndarray,
    window: Window,
    path: Path,
) -> dict[str, Any]:
    """Write the same native crop and dataset mask with a robust tiled layout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = src.profile.copy()
    profile.update(
        driver="GTiff",
        width=int(window.width),
        height=int(window.height),
        transform=src.window_transform(window),
        count=1,
        dtype=src.dtypes[0],
        compress="deflate",
        tiled=True,
        blockxsize=512,
        blockysize=512,
    )
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr.astype(src.dtypes[0], copy=False), 1)
            dst.write_mask(mask.astype("uint8", copy=False))

    expected_arr = arr.astype(src.dtypes[0], copy=False)
    expected_mask = mask.astype("uint8", copy=False)
    with rasterio.open(path) as check:
        reread = check.read(1, masked=False)
        remask = check.dataset_mask()
        if not np.array_equal(reread, expected_arr, equal_nan=True):
            raise ValueError(f"lossless crop pixel identity failed: {path}")
        if not np.array_equal(remask, expected_mask):
            raise ValueError(f"lossless crop mask identity failed: {path}")
        if not check.profile.get("tiled"):
            raise ValueError(f"R3 storage repair did not create tiled GeoTIFF: {path}")

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": core.sha256_file(path),
        "dtype": src.dtypes[0],
        "nodata": src.nodata,
        "pixel_identity_check": "PASS_EXACT_ARRAY_EQUAL",
        "mask_identity_check": "PASS_EXACT_ARRAY_EQUAL",
        "resampling_performed": False,
        "radiometric_transformation_performed": False,
    }


def main() -> int:
    core.write_lossless_crop = write_lossless_crop_tiled
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
