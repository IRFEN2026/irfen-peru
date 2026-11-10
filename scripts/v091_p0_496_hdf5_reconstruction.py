#!/usr/bin/env python3
"""IRFEN v0.9.1 · incidente P0 #496 (Tumbes, 04–05/11/2026): reconstrucción desde los HDF5 originales de NASA.

RESEARCH_ONLY / TEST_ONLY. No calibra, no corrige, no cambia umbrales ni colorea nada.

Responde a una sola pregunta con evidencia: ¿la lluvia baja que IRFEN dio para Tumbes en la ventana
2026-11-04T12:00Z – 2026-11-05T12:00Z (07–07 PET) se debe a un error de procesamiento de IRFEN (variable, unidades,
×0,5, orientación de la rejilla, huecos, geometría) o es lo que contiene el propio producto IMERG Early?

1. Descarga (vía Earthdata, con el token del proyecto) las 48 medias horas GPM_3IMERGHHE V07 de la ventana y registra
   nombre, versión, tamaño y SHA-256 de cada archivo.
2. Lee cada HDF5 por DOS caminos: el de producción (probe_imerg_early_live.read_grid) y uno independiente (h5py directo,
   con el orden de dimensiones declarado en el atributo DimensionNames). Ambos deben dar el mismo valor en cada celda.
3. Comprueba unidades (mm/hr), valor de relleno, ejes (rejilla global 0,1°, centros −179,95…179,95 y −89,95…89,95).
4. Acumula 24 h = Σ tasa × 0,5 h por celda; una media hora sin dato deja la celda como desconocida (nunca 0 mm).
5. Para las estaciones con coordenada documentada: celda(s) compatibles con la precisión de la coordenada (atlas
   SENAMHI redondeado a 0,1°: el punto cae en una arista o esquina, 2×2 celdas), vecindario 3×3 y máximo; Cabo Inga
   además en su subventana 16–19 PET. Valores de estación = reportados por prensa, NO verificados.
6. Recalcula, desde los HDF5, las medias areales de las 134 áreas aportantes y de las zonas/provincias del norte con
   el mismo código de producción (cell_weights / polygon_mean) y las compara con lo archivado en main.
7. Guarda un recorte regional (Tumbes–Piura) de cada media hora y del acumulado, y un mapa PNG.

    python3 scripts/v091_p0_496_hdf5_reconstruction.py --download --archived-catchments a.json --archived-north n.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
STATIONS = ROOT / "config/v091_p0_496_stations_v0_1.json"
CATCHMENTS = ROOT / "data/v09/research/catchments/checkpoint_catchments_v0_1.geojson"
OUT_DIR = ROOT / "data/v09/research/p0_496"
UTC = timezone.utc
START = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
N_SLOTS = 48
CROP = dict(lon_min=-81.5, lon_max=-79.0, lat_min=-5.5, lat_max=-3.0)  # Tumbes, Zarumilla, Puyango, Chira–Piura bajo
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, public_alerting=False,
              notifications_enabled=False, activation_gate="BLOCKED", calibration=None, thresholds_changed=False)
NAME = re.compile(r"^3B-HHR-(?P<run>[EL])\.MS\.MRG\.3IMERG\.(?P<d>\d{8})-S(?P<s>\d{6})-E(?P<e>\d{6})\.(?P<min>\d{4})\.(?P<v>V\d{2}[A-Z]?)\.HDF5$")
EXTRA_VARS = ("MWprecipitation", "precipitationQualityIndex", "IRinfluence", "probabilityLiquidPrecipitation")


def slots(start: datetime = START, n: int = N_SLOTS) -> list[datetime]:
    return [start + timedelta(minutes=30 * i) for i in range(n)]


def parse_name(name: str) -> dict:
    """Start/end, run and version from a NASA IMERG half-hourly file name. Refuses anything else."""
    m = NAME.match(name)
    if not m:
        raise ValueError(f"not an IMERG half-hourly granule name: {name}")
    t0 = datetime.strptime(m["d"] + m["s"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    t1 = datetime.strptime(m["d"] + m["e"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    if t1 - t0 != timedelta(minutes=29, seconds=59):
        raise ValueError(f"granule does not cover one half-hour: {name}")
    if int(m["min"]) != t0.hour * 60 + t0.minute:
        raise ValueError(f"minute-of-day field does not match the start time: {name}")
    return dict(start=t0, run="Early" if m["run"] == "E" else "Late", version=m["v"])


def check_axes(lon: np.ndarray, lat: np.ndarray) -> None:
    """IMERG V07 global grid: 3600 × 1800 cell centres, 0.1°, increasing, starting at −179.95 / −89.95."""
    for ax, n, first in ((lon, 3600, -179.95), (lat, 1800, -89.95)):
        ax = np.asarray(ax, dtype=float)
        if ax.shape != (n,) or not np.all(np.diff(ax) > 0) or abs(ax[0] - first) > 1e-3 or abs(float(np.median(np.diff(ax))) - 0.1) > 1e-5:
            raise ValueError(f"unexpected IMERG axis: n={ax.shape}, first={ax[:1]}, step={np.median(np.diff(ax)) if ax.size > 1 else None}")


def cell_index(axis_first: float, x: float, step: float = 0.1) -> float:
    """Fractional cell index of coordinate x (cell k spans [first−step/2 + k·step, first−step/2 + (k+1)·step))."""
    return (x - (axis_first - step / 2)) / step


def candidate_cells(lon_first: float, lat_first: float, x: float, y: float, precision: float) -> list[tuple[int, int]]:
    """Every (lon_idx, lat_idx) cell the true location can be in, given the coordinate's rounding (±precision/2).
    A coordinate rounded to 0.1° lies exactly on cell edges of the 0.1° grid: it is compatible with 2×2 cells."""
    half = (precision or 0.0) / 2
    out = []
    eps = 1e-9
    i0, i1 = math.floor(cell_index(lon_first, x - half) + eps), math.floor(cell_index(lon_first, x + half) - eps)
    j0, j1 = math.floor(cell_index(lat_first, y - half) + eps), math.floor(cell_index(lat_first, y + half) - eps)
    for i in range(i0, max(i0, i1) + 1):
        for j in range(j0, max(j0, j1) + 1):
            out.append((i, j))
    return out


def accumulate(rates: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Σ rate[mm/h] × 0.5 h over the half-hours; a cell with any missing half-hour is NaN (unknown), never 0 mm.
    Returns (accum_mm, valid_halfhours)."""
    stack = np.stack(rates).astype(float)
    valid = np.isfinite(stack).sum(axis=0)
    acc = np.where(valid == stack.shape[0], np.nansum(stack, axis=0) * 0.5, np.nan)
    return acc, valid


def clean(values: np.ndarray, fill) -> np.ndarray:
    v = np.asarray(values, dtype=float).copy()
    if fill is not None:
        v[np.isclose(v, float(fill))] = np.nan
    v[v < 0] = np.nan
    return v


def _attr(ds, k):
    v = ds.attrs.get(k)
    if isinstance(v, bytes):
        v = v.decode(errors="ignore")
    if isinstance(v, np.ndarray) and v.size == 1:
        v = v.item()
        if isinstance(v, bytes):
            v = v.decode(errors="ignore")
    return v


def read_independent(path: Path) -> dict:
    """h5py directly: Grid/precipitation in the dimension order declared by the file (DimensionNames), as [lat, lon]."""
    import h5py
    with h5py.File(path, "r") as f:
        g = f["Grid"]
        ds = g["precipitation"]
        units = str(_attr(ds, "units") or "")
        if units.strip().lower() not in ("mm/hr", "mm h-1", "mm/hour"):
            raise ValueError(f"precipitation units not mm/hr: {units!r}")
        dims = str(_attr(ds, "DimensionNames") or "")
        lon, lat = np.asarray(g["lon"][:], float), np.asarray(g["lat"][:], float)
        check_axes(lon, lat)
        fill = _attr(ds, "_FillValue")
        arr = np.asarray(ds[...])
        order = [d.strip() for d in dims.split(",")] if dims else None
        if arr.ndim == 3:
            if order and order[0] == "time":
                order = order[1:]
            arr = arr[0]
        if order == ["lon", "lat"] or (order is None and arr.shape == (lon.size, lat.size)):
            arr = arr.T
        elif not (order == ["lat", "lon"] or (order is None and arr.shape == (lat.size, lon.size))):
            raise ValueError(f"cannot establish dimension order: dims={dims!r} shape={arr.shape}")
        out = dict(units=units, dimension_names=dims, fill_value=None if fill is None else float(fill), lon=lon, lat=lat,
                   precipitation=clean(arr, fill), extras={})
        for k in EXTRA_VARS:
            if k in g:
                e = np.asarray(g[k][...])
                e = e[0] if e.ndim == 3 else e
                e = e.T if e.shape == (lon.size, lat.size) else e
                out["extras"][k] = clean(e, _attr(g[k], "_FillValue")) if k != "IRinfluence" else np.asarray(e, float)
        hdr = f.attrs.get("FileHeader")
        out["file_header"] = hdr.decode(errors="ignore") if isinstance(hdr, bytes) else (str(hdr) if hdr is not None else None)
        return out


def crop_slices(lon: np.ndarray, lat: np.ndarray):
    i = np.where((lon >= CROP["lon_min"]) & (lon <= CROP["lon_max"]))[0]
    j = np.where((lat >= CROP["lat_min"]) & (lat <= CROP["lat_max"]))[0]
    return slice(int(i[0]), int(i[-1]) + 1), slice(int(j[0]), int(j[-1]) + 1)


def station_rows(stations: list[dict], acc: np.ndarray, valid: np.ndarray, lon: np.ndarray, lat: np.ndarray, sub_acc=None) -> list[dict]:
    rows = []
    for s in stations:
        r = dict(name=s["name"], reported_mm=s["reported_mm"], reported_status="PRENSA_NO_VERIFICADO", senamhi_code=s.get("senamhi_code"))
        if s.get("lon") is None:
            r.update(pairing="NO_EMPAREJABLE", reason_es=s.get("pairing_block_es"))
            rows.append(r)
            continue
        cand = candidate_cells(float(lon[0]), float(lat[0]), s["lon"], s["lat"], s.get("coordinate_precision_deg") or 0.0)
        vals = [float(acc[j, i]) for i, j in cand]
        ci, cj = int(round(np.mean([c[0] for c in cand]))), int(round(np.mean([c[1] for c in cand])))
        nb = acc[max(cj - 1, 0):cj + 2, max(ci - 1, 0):ci + 2]
        r.update(pairing="EMPAREJAMIENTO_DIAGNOSTICO" if len(cand) == 1 else "AMBIGUO_POR_PRECISION_DE_COORDENADA",
                 coordinate=[s["lon"], s["lat"]], coordinate_precision_deg=s.get("coordinate_precision_deg"),
                 candidate_cells=[dict(lon=round(float(lon[i]), 2), lat=round(float(lat[j]), 2), imerg_24h_mm=None if not np.isfinite(acc[j, i]) else round(float(acc[j, i]), 2),
                                       valid_halfhours=int(valid[j, i])) for i, j in cand],
                 imerg_candidates_min_mm=None if not np.isfinite(vals).all() else round(min(vals), 2),
                 imerg_candidates_max_mm=None if not np.isfinite(vals).all() else round(max(vals), 2),
                 imerg_3x3_mean_mm=None if not np.isfinite(nb).all() else round(float(nb.mean()), 2),
                 imerg_3x3_max_mm=None if not np.isfinite(nb).all() else round(float(nb.max()), 2))
        if np.isfinite(vals).all():
            r["difference_reported_minus_max_candidate_mm"] = round(s["reported_mm"] - max(vals), 2)
        if s.get("alt_coordinate"):
            a = s["alt_coordinate"]
            (ai, aj), = candidate_cells(float(lon[0]), float(lat[0]), a["lon"], a["lat"], 0.0)
            r["alt_coordinate_cell"] = dict(lon=round(float(lon[ai]), 2), lat=round(float(lat[aj]), 2),
                                            imerg_24h_mm=None if not np.isfinite(acc[aj, ai]) else round(float(acc[aj, ai]), 2), source=a["source"])
        if sub_acc is not None and s.get("subwindow"):
            sv = [float(sub_acc[j, i]) for i, j in cand]
            nbs = sub_acc[max(cj - 1, 0):cj + 2, max(ci - 1, 0):ci + 2]
            r["subwindow"] = dict(s["subwindow"], imerg_candidates_max_mm=None if not np.isfinite(sv).all() else round(max(sv), 2),
                                  imerg_3x3_max_mm=None if not np.isfinite(nbs).all() else round(float(nbs.max()), 2))
        rows.append(r)
    return rows


def archived_sums(archive: dict, kind: str, times: list[str]) -> dict:
    """24 h sums per target from an archived IRFEN file, exactly as stored (rate × 0.5, no imputation)."""
    by = {g["time_utc"]: g for g in archive["granules"]}
    out = {}
    if kind == "catchments":
        ids = [t["id"] for t in archive["targets"]]
        for k, tid in enumerate(ids):
            v = [by[t]["rate_mm_hr"][k] if t in by else None for t in times]
            out[tid] = None if any(x is None for x in v) else sum(x * 0.5 for x in v)
    else:
        for tid in archive["targets"]:
            v = [((by.get(t) or {}).get("targets") or {}).get(tid, {}).get("rate_mm_hr") for t in times]
            out[tid] = None if any(x is None for x in v) else sum(x * 0.5 for x in v)
    return out


def granule_names(archive: dict, times: list[str]) -> dict:
    return {g["time_utc"]: g.get("granule") for g in archive.get("granules", []) if g["time_utc"] in times}


def download(tmp: Path) -> list[Path]:
    import earthaccess

    A = _archive_module()
    import probe_imerg_early_live as probe
    found, attempts = A.contact_with_retries(probe, earthaccess, START + timedelta(hours=26))
    want = set(slots())
    rows = [r for r in probe.index_granules(found) if r[0] in want and ".V07" in r[1] and "3B-HHR-E" in r[1]]
    paths, failures = A.download_granules(earthaccess, sorted(rows, key=lambda r: r[0]), str(tmp))
    if failures:
        print("::warning::download failures:", json.dumps(failures)[:500])
    return sorted(Path(p) for p in paths)


def _archive_module():
    spec = importlib.util.spec_from_file_location("v09_imerg_north_archive_p0", ROOT / "scripts/v09_imerg_north_archive.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def analyse(files: list[Path], archived_catchments: dict | None, archived_north: dict | None) -> tuple[dict, dict]:
    import probe_imerg_early_live as probe
    A = _archive_module()
    st = json.loads(STATIONS.read_text(encoding="utf-8"))
    by_time, granules = {}, []
    for p in files:
        meta = parse_name(p.name)
        if meta["start"] in by_time:
            raise ValueError(f"duplicate half-hour {meta['start']}")
        by_time[meta["start"]] = p
    want = slots()
    missing = [t.isoformat() for t in want if t not in by_time]
    times = [t.isoformat() for t in want]
    ctargets, ntargets = A.load_catchment_targets(), A.load_targets()
    cw = nw = None
    crop_rates, crop_extras, cat_sum, north_sum = [], {k: [] for k in EXTRA_VARS}, {}, {}
    max_path_diff, lon = 0.0, None
    for t in want:
        p = by_time.get(t)
        if p is None:
            crop_rates.append(None)
            continue
        meta = parse_name(p.name)
        ind = read_independent(p)
        plat, plon, pvals, punits = probe.read_grid(str(p))  # production read path
        check_axes(plon, plat)
        lon, lat = ind["lon"], ind["lat"]
        diff = np.nanmax(np.abs(np.where(np.isfinite(ind["precipitation"]) & np.isfinite(pvals), ind["precipitation"] - pvals, 0.0)))
        nan_mismatch = int((np.isfinite(ind["precipitation"]) != np.isfinite(pvals)).sum())
        max_path_diff = max(max_path_diff, float(diff))
        si, sj = crop_slices(lon, lat)
        crop = ind["precipitation"][sj, si]
        crop_rates.append(crop)
        for k in EXTRA_VARS:
            if k in ind["extras"]:
                crop_extras[k].append(ind["extras"][k][sj, si])
        if cw is None:
            cw = [A.cell_weights(x["geometry"], plat, plon) for x in ctargets]
            nw = [A.cell_weights(x["geometry"], plat, plon) for x in ntargets]
        for x, w in zip(ctargets, cw):
            m, _ = A.weighted_mean(w, pvals)
            cat_sum.setdefault(x["id"], []).append(m)
        for x, w in zip(ntargets, nw):
            m, _ = A.weighted_mean(w, pvals)
            north_sum.setdefault(x["id"], []).append(m)
        raw = p.read_bytes()
        granules.append(dict(time_utc=t.isoformat(), granule=p.name, run=meta["run"], version=meta["version"], bytes=len(raw),
                             sha256=hashlib.sha256(raw).hexdigest(), units=ind["units"], dimension_names=ind["dimension_names"],
                             fill_value=ind["fill_value"], production_vs_independent_max_abs_diff=float(diff),
                             production_vs_independent_missing_mismatch=nan_mismatch,
                             crop_valid_cells=int(np.isfinite(crop).sum()), crop_cells=int(crop.size),
                             crop_max_rate_mm_hr=None if not np.isfinite(crop).any() else round(float(np.nanmax(crop)), 3)))
    res = dict(schema_version="irfen_v091_p0_496_hdf5_reconstruction_v0_1", **GUARDS,
               product="NASA GPM IMERG Early V07 half-hourly (GPM_3IMERGHHE), Grid/precipitation [mm/hr]",
               window_utc=[START.isoformat(), (START + timedelta(minutes=30 * N_SLOTS)).isoformat()], half_hours_required=N_SLOTS,
               half_hours_found=len(granules), missing_half_hours=missing, granules=granules,
               production_read_path_matches_independent=max_path_diff == 0.0 and all(g["production_vs_independent_missing_mismatch"] == 0 for g in granules),
               production_vs_independent_max_abs_diff=max_path_diff,
               status="NO_EVALUABLE" if missing else "RECONSTRUIDO")
    if missing:
        res["reason_es"] = "Faltan medias horas originales: el acumulado de 24 h no se reconstruye (desconocido, nunca 0 mm)."
        return res, {}
    si, sj = crop_slices(lon, lat)
    clon, clat = lon[si], lat[sj]
    acc, valid = accumulate(crop_rates)
    sub_idx = [k for k, t in enumerate(want) if datetime(2026, 11, 4, 21, tzinfo=UTC) <= t < datetime(2026, 11, 5, 0, tzinfo=UTC)]
    sub_acc, _ = accumulate([crop_rates[k] for k in sub_idx])
    res["stations"] = station_rows(st["stations"], acc, valid, clon, clat, sub_acc)
    res["stations_note_es"] = st["values_note_es"]
    res["crop"] = dict(CROP, lon=[round(float(x), 2) for x in clon], lat=[round(float(y), 2) for y in clat],
                       accum_24h_mm_lat_by_lon=[[None if not np.isfinite(v) else round(float(v), 2) for v in row] for row in acc],
                       max_24h_mm=round(float(np.nanmax(acc)), 2), max_24h_at=None)
    jm, im = np.unravel_index(int(np.nanargmax(acc)), acc.shape)
    res["crop"]["max_24h_at"] = [round(float(clon[im]), 2), round(float(clat[jm]), 2)]
    res["crop"]["halfhour_rates_mm_hr"] = {t: [[None if not np.isfinite(v) else round(float(v), 3) for v in row] for row in r]
                                          for t, r in zip(times, crop_rates)}
    for k, arrs in crop_extras.items():
        if len(arrs) == N_SLOTS:
            if k == "MWprecipitation":
                n_mw = np.stack([np.isfinite(a) for a in arrs]).sum(axis=0)
                res["crop"]["halfhours_with_microwave_estimate_lat_by_lon"] = n_mw.astype(int).tolist()
            elif k == "precipitationQualityIndex":
                res["crop"]["mean_quality_index_lat_by_lon"] = [[None if not np.isfinite(v) else round(float(v), 3) for v in row]
                                                               for row in np.nanmean(np.stack(arrs), axis=0)]
    # the same areal means as production, recomputed from the originals, against what main archived
    cmp = []
    for kind, sums, arch in (("catchments", cat_sum, archived_catchments), ("north", north_sum, archived_north)):
        a = archived_sums(arch, kind, times) if arch else {}
        names = granule_names(arch, times) if arch else {}
        for tid, v in sorted(sums.items()):
            rec = None if any(x is None for x in v) else sum(x * 0.5 for x in v)
            cmp.append(dict(kind=kind, target=tid, reconstructed_24h_mm=None if rec is None else round(rec, 3),
                            archived_24h_mm=None if a.get(tid) is None else round(a[tid], 3),
                            abs_diff_mm=None if rec is None or a.get(tid) is None else round(abs(rec - a[tid]), 4)))
        if names:
            res.setdefault("archived_granule_names_match", {})[kind] = all(names.get(g["time_utc"]) == g["granule"] for g in granules)
    res["areal_recomputation"] = cmp
    diffs = [c["abs_diff_mm"] for c in cmp if c["abs_diff_mm"] is not None]
    res["areal_recomputation_max_abs_diff_mm"] = max(diffs) if diffs else None
    res["areal_recomputation_compared"] = len(diffs)
    figs = dict(acc=acc, clon=clon, clat=clat, stations=res["stations"])
    return res, figs


def figure(figs: dict, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    acc, clon, clat = figs["acc"], figs["clon"], figs["clat"]
    bounds = [0, 1, 5, 10, 20, 40, 60, 80, 100, 150]
    cmap = ListedColormap(["#f7fbff", "#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"])
    fig, ax = plt.subplots(figsize=(8, 8), dpi=110)
    m = ax.pcolormesh(np.r_[clon - 0.05, clon[-1] + 0.05], np.r_[clat - 0.05, clat[-1] + 0.05], np.ma.masked_invalid(acc),
                      cmap=cmap, norm=BoundaryNorm(bounds, cmap.N), shading="flat")
    fc = json.loads(CATCHMENTS.read_text(encoding="utf-8"))
    for f in fc["features"]:
        if f["properties"]["checkpoint_id"] in ("TUM-R-TUMBES-BAJO", "TUM-R-ZARUMILLA-BAJO", "PIU-R-CHIRA-BAJO", "PIU-R-PIURA-BAJO"):
            for poly in f["geometry"]["coordinates"]:
                xy = np.array(poly[0])
                ax.plot(xy[:, 0], xy[:, 1], color="#b2182b", lw=1)
    for s in figs["stations"]:
        if s.get("coordinate"):
            x, y = s["coordinate"]
            ax.plot(x, y, "o", ms=6, mfc="#ffd92f", mec="black")
            ax.annotate(f"{s['name']}\nreportado {s['reported_mm']:.0f} · IMERG ≤{s['imerg_candidates_max_mm']}", (x, y),
                        xytext=(5, 5), textcoords="offset points", fontsize=7)
    ax.set_xlim(CROP["lon_min"], CROP["lon_max"])
    ax.set_ylim(CROP["lat_min"], CROP["lat_max"])
    ax.set_aspect(1 / math.cos(math.radians(-4.2)))
    fig.colorbar(m, ax=ax, shrink=0.7, label="IMERG Early V07 · acumulado 24 h (mm)")
    ax.set_title("IMERG Early 04-11 12Z → 05-11 12Z (07–07 PET) desde los HDF5 originales\n"
                 "Rojo: áreas aportantes Tumbes, Zarumilla, Chira, Piura. Valores de estación: prensa, no verificados", fontsize=9)
    fig.tight_layout()
    fig.savefig(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--hdf5-dir")
    ap.add_argument("--archived-catchments")
    ap.add_argument("--archived-north")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args(argv)
    ac = json.loads(Path(a.archived_catchments).read_text(encoding="utf-8")) if a.archived_catchments else None
    an = json.loads(Path(a.archived_north).read_text(encoding="utf-8")) if a.archived_north else None
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="irfen_p0_496_") as td:
        files = download(Path(td)) if a.download else sorted(Path(a.hdf5_dir).glob("*.HDF5"))
        res, figs = analyse(files, ac, an)
        if figs:
            figure(figs, out / "imerg_24h_tumbes_hdf5_v0_1.png")
    (out / "imerg_hdf5_reconstruction_v0_1.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = {k: res.get(k) for k in ("status", "half_hours_found", "production_read_path_matches_independent",
                                       "areal_recomputation_max_abs_diff_mm", "areal_recomputation_compared", "archived_granule_names_match")}
    summary["stations"] = [(s["name"], s["reported_mm"], s.get("imerg_candidates_max_mm"), s.get("imerg_3x3_max_mm")) for s in res.get("stations", [])]
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
