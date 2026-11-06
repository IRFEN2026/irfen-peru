"""Offline original-file audit. RESEARCH_ONLY/TEST_ONLY; never changes alerts.

HDF5 samples are satellite pixel estimates, not station observations. All
intervals are half-open UTC and require complete half-hour coverage.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import numpy as np
import h5py

RATE_UNITS = {'mm/hr', 'mm/h', 'mm h-1', 'mm/hour'}


def text_attr(value):
    value = np.asarray(value).reshape(-1)
    if value.size != 1:
        raise ValueError('Expected scalar attribute')
    v = value[0]
    return v.decode() if isinstance(v, bytes) else str(v)


def read_original(path):
    """Read explicit calibrated precipitation, decode packing, retain provenance.

    Native V07 axis order is time,longitude,latitude. Ambiguous square grids
    require DimensionNames; unexpected extra time slices are rejected.
    """
    with h5py.File(path, 'r') as f:
        g = f['Grid']
        key = next((k for k in ('precipitation', 'precipitationCal') if k in g), None)
        if key is None:
            raise ValueError('Calibrated precipitation missing; uncalibrated substitution forbidden')
        ds = g[key]
        units = text_attr(ds.attrs.get('units', '')).strip()
        if units not in RATE_UNITS:
            raise ValueError(f'Unexpected precipitation rate units: {units!r}')
        lat, lon = np.asarray(g['lat'][:]), np.asarray(g['lon'][:])
        for a in (lat, lon):
            if a.ndim != 1 or a.size < 2 or not np.isfinite(a).all():
                raise ValueError('Invalid coordinate axis')
            if not (np.all(np.diff(a) > 0) or np.all(np.diff(a) < 0)):
                raise ValueError('Coordinate axis must be strictly monotonic')
            if not np.allclose(abs(np.diff(a)), .1, atol=2e-5):
                raise ValueError('Expected 0.1 degree grid')
        raw = np.asarray(ds[:], dtype=float)
        dims = text_attr(ds.attrs['DimensionNames']) if 'DimensionNames' in ds.attrs else ''
        dims = [d.strip().lower() for d in dims.split(',') if d.strip()]
        if raw.ndim == 3:
            if raw.shape[0] != 1 or (dims and dims[0] != 'time'):
                raise ValueError('Expected exactly one time slice')
            raw = raw[0]
            dims = dims[1:] if dims else []
        if raw.ndim != 2:
            raise ValueError('Expected two spatial dimensions')
        invalid = ~np.isfinite(raw)
        for attr in ('_FillValue', 'missing_value'):
            for value in np.asarray(ds.attrs.get(attr, [])).reshape(-1):
                invalid |= raw == float(value)
        scale = float(np.asarray(ds.attrs.get('scale_factor', 1)).item())
        offset = float(np.asarray(ds.attrs.get('add_offset', 0)).item())
        if not np.isfinite(scale) or scale <= 0 or not np.isfinite(offset):
            raise ValueError('Invalid packing metadata')
        p = raw * scale + offset
        p[invalid | (p < 0) | ~np.isfinite(p)] = np.nan
        if dims:
            if dims == ['lon', 'lat']:
                p = p.T
            elif dims != ['lat', 'lon']:
                raise ValueError(f'Unknown dimension names: {dims}')
        elif lat.size == lon.size:
            raise ValueError('Ambiguous square grid without dimension metadata')
        elif p.shape == (lon.size, lat.size):
            p = p.T
        if p.shape != (lat.size, lon.size):
            raise ValueError('Shape does not match coordinate axes')
        meta = dict(variable=ds.name, units=units, dimensions=dims,
                    scale_factor=scale, add_offset=offset,
                    sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                    filename=Path(path).name, source_kind='ORIGINAL_HDF5',
                    spatial_support='SATELLITE_PIXEL_0.1_DEG')
    return lat, lon, p, meta


def accumulate(grids, times, start, end):
    """No missing/duplicate/unaligned times, no zero fill or changing spatial mask."""
    from datetime import timedelta
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError('Explicit timezone and positive interval required')
    expected, t = [], start
    while t < end:
        expected.append(t)
        t += timedelta(minutes=30)
    if t != end or start.minute not in (0, 30) or start.second or start.microsecond:
        raise ValueError('Half-hour boundaries required')
    if len(set(times)) != len(times) or sorted(times) != expected:
        raise ValueError('Incomplete, duplicate or out-of-window half-hours')
    a = np.asarray(grids, dtype=float)
    if len(a) != len(times):
        raise ValueError('Grid/time count mismatch')
    return np.where(np.isfinite(a).all(axis=0), np.sum(a * .5, axis=0), np.nan)


def point_neighborhood(lat, lon, accumulation, station_lat, station_lon):
    """Return containing pixel and 3x3 context; boundary points are ambiguous."""
    iy = np.flatnonzero(abs(lat - station_lat) < .05 - 2e-5)
    ix = np.flatnonzero(abs(lon - station_lon) < .05 - 2e-5)
    if len(iy) != 1 or len(ix) != 1:
        raise ValueError('Outside grid or ambiguous boundary; verify station coordinates')
    r, c = int(iy[0]), int(ix[0])
    if r < 1 or c < 1 or r + 1 >= len(lat) or c + 1 >= len(lon):
        raise ValueError('Full 3x3 neighborhood unavailable')
    a = accumulation[r-1:r+2, c-1:c+2]
    valid = np.isfinite(a)
    return dict(pixel_center_lat=float(lat[r]), pixel_center_lon=float(lon[c]),
                pixel_mm=float(accumulation[r,c]) if np.isfinite(accumulation[r,c]) else None,
                neighborhood_valid_cells=int(valid.sum()),
                neighborhood_mean_mm=float(a.mean()) if valid.all() else None,
                neighborhood_max_mm=float(a.max()) if valid.all() else None,
                neighborhood_p50_mm=float(np.percentile(a,50)) if valid.all() else None,
                neighborhood_p90_mm=float(np.percentile(a,90)) if valid.all() else None,
                comparison_kind='POINT_VS_PIXEL_NOT_AREAL_VALIDATION')


def basin_mean(lat, lon, accumulation, geom):
    """Equal-area intersection weights; complete fixed spatial mask required."""
    from shapely.geometry import box
    from shapely.ops import transform
    from pyproj import Transformer
    project = Transformer.from_crs('EPSG:4326', 'EPSG:6933', always_xy=True).transform
    total = transform(project, geom).area
    if total <= 0:
        raise ValueError('Empty basin')
    weighted = covered = 0.
    minx, miny, maxx, maxy = geom.bounds
    for r in np.flatnonzero((lat >= miny-.05) & (lat <= maxy+.05)):
        for c in np.flatnonzero((lon >= minx-.05) & (lon <= maxx+.05)):
            area = transform(project, geom.intersection(box(lon[c]-.05,lat[r]-.05,lon[c]+.05,lat[r]+.05))).area
            if area > 0 and np.isfinite(accumulation[r,c]):
                covered += area
                weighted += area * accumulation[r,c]
    fraction = min(1., covered/total)
    return dict(mean_mm=float(weighted/covered) if fraction >= 1-1e-6 else None,
                coverage_fraction=fraction, weight_method='EPSG:6933_EQUAL_AREA',
                spatial_support='BASIN_MEAN_NOT_STATION')
