"""Frozen legacy sampling method for original-versus-archive replay; no capture."""
from pathlib import Path
import json, gzip
BASE=Path(__file__).resolve().parents[1]/'research/issue496/baseline'
def load(name):
    from shapely.geometry import shape
    return [dict(f['properties'],geometry=shape(f['geometry'])) for f in json.loads(gzip.decompress((BASE/(name+'.geojson.gz')).read_bytes()))['features']]
def load_catchment_targets():return load('catchments')
def load_targets():return load('north')

def cell_weights(geom, lat, lon) -> dict:
    """Area of the intersection of `geom` with each 0.1° IMERG cell: the weights of probe_imerg_early_live.polygon_mean,
    computed once per run (the IMERG grid is fixed) instead of once per granule."""
    import numpy as np
    from shapely.geometry import box

    dx = float(np.median(np.abs(np.diff(lon))))
    dy = float(np.median(np.abs(np.diff(lat))))
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - dx / 2) & (lon <= maxx + dx / 2))[0]
    ys = np.where((lat >= miny - dy / 2) & (lat <= maxy + dy / 2))[0]
    rows, cols, areas = [], [], []
    for r in ys:
        for c in xs:
            inter = geom.intersection(box(float(lon[c]) - dx / 2, float(lat[r]) - dy / 2, float(lon[c]) + dx / 2, float(lat[r]) + dy / 2))
            if not inter.is_empty and inter.area > 0:
                rows.append(int(r))
                cols.append(int(c))
                areas.append(inter.area)
    return dict(rows=np.array(rows, dtype=int), cols=np.array(cols, dtype=int), areas=np.array(areas), geom_area=geom.area)

def weighted_mean(w: dict, values):
    """Same result as polygon_mean: area-weighted mean over the finite cells; None when no cell is valid (unknown,
    never 0 mm). Returns (mean, covered_pct)."""
    import numpy as np

    if not len(w["areas"]):
        return None, 0.0
    v = values[w["rows"], w["cols"]]
    ok = np.isfinite(v)
    sw = float(w["areas"][ok].sum())
    if not sw:
        return None, 0.0
    return float((w["areas"][ok] * v[ok]).sum() / sw), round(min(100.0, 100.0 * sw / max(w["geom_area"], 1e-15)), 1)
