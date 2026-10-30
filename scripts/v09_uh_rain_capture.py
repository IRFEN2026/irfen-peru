#!/usr/bin/env python3
"""IRFEN v0.9 · investigación: IMERG Early (GPM_3IMERGHHE V07, 30 min) sobre unidades hidrográficas ANA.
RESEARCH_ONLY / TEST_ONLY. Se ejecuta en un runner con EARTHDATA_TOKEN; NO escribe en los archivos de las capturas
operativas (data/v09/rain/…) ni en el motor.

Para cada gránulo de las últimas --hours horas (intervalo semiabierto [inicio, fin) por la marca S del nombre):
1. lectura con el lector existente `probe_imerg_early_live.read_grid` y comprobación de unidades (mm/hr);
2. media espacial con el muestreador existente `probe_imerg_early_live.polygon_mean` (ponderación por el área de
   intersección de cada celda de 0,1° con el polígono: las celdas parciales cuentan en proporción; celdas sin dato
   se excluyen y bajan `covered_pct`);
3. método independiente de control: 10×10 sub-puntos por celda, ponderados por cos(lat), con shapely.contains_xy;
4. acumulado del gránulo = tasa media (mm/h) × 0,5 h.
Duplicados (mismo inicio, distinta versión de proceso) se registran y se conserva uno solo (el de versión más alta).
Un gránulo que no se descarga o no se puede leer queda como AUSENTE con su motivo: nunca como 0 mm.

Muestra de validación: para 3 gránulos se relee el HDF5 directamente con h5py (sin el lector existente) y se guardan
la marca de tiempo interna, las unidades, el valor de relleno, los centros de celda y los valores crudos de las celdas
que tocan las unidades prioritarias, para recomputar las medias fuera de línea.

    EARTHDATA_TOKEN=… python scripts/v09_uh_rain_capture.py --hours 120
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
UNITS_GEO = ROOT / "data/v09/research/uh_units_v0_1.geojson"
OUT_DIR = ROOT / "data/v09/research/uh_rain"
OUT = OUT_DIR / "imerg_early_uh_halfhours_v0_1.json"
VALIDATION = OUT_DIR / "imerg_validation_sample_v0_1.json"
PRIORITY = ("1378", "138", "13778", "13779")
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False, used_by_rain_engine_or_priority=False)
NAME_RE = re.compile(r"(20\d{6})-S(\d{6})-E(\d{6})\.(\d{4})\.(V\d+[A-Z]?)\.HDF5", re.I)


def parse_name(name: str) -> dict | None:
    m = NAME_RE.search(name)
    if not m:
        return None
    d, s, e, minutes, ver = m.groups()
    start = datetime.strptime(d + s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    end_incl = datetime.strptime(d + e, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return dict(start=start, end=end_incl + timedelta(seconds=1), minute_of_day=int(minutes), version=ver.upper())


def dedupe(rows: list[tuple]) -> tuple[list[tuple], list[dict]]:
    """rows: (start, name, granule). One granule per start time; keep the highest processing version."""
    by, dups = {}, []
    for r in rows:
        meta = parse_name(r[1])
        if meta is None:
            continue
        k = meta["start"]
        if k in by:
            keep, drop = sorted([by[k], r], key=lambda x: parse_name(x[1])["version"], reverse=True)
            dups.append(dict(start_utc=k.isoformat(), kept=keep[1], dropped=drop[1]))
            by[k] = keep
        else:
            by[k] = r
    return [by[k] for k in sorted(by)], dups


def independent_mean(geom, lat, lon, values, sub: int = 10):
    """Control method: sub-sample each 0.1° cell, weight by cos(lat). Returns (rate, covered_fraction)."""
    import numpy as np
    import shapely
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - 0.05) & (lon <= maxx + 0.05))[0]
    ys = np.where((lat >= miny - 0.05) & (lat <= maxy + 0.05))[0]
    off = (np.arange(sub) + 0.5) / sub * 0.1 - 0.05
    sw = sv = st = 0.0
    for r in ys:
        for c in xs:
            px, py = np.meshgrid(lon[c] + off, lat[r] + off)
            inside = shapely.contains_xy(geom, px.ravel(), py.ravel())
            if not inside.any():
                continue
            w = float((np.cos(np.radians(py.ravel()[inside]))).sum())
            st += w
            v = float(values[r, c])
            if math.isfinite(v):
                sw += w
                sv += w * v
    return (sv / sw if sw else None), (sw / st if st else 0.0)


def direct_read(path: str, units_geo: list, codes: tuple) -> dict:
    """Independent HDF5 read (no project reader): time, units, fill value, grid centres and raw cells."""
    import h5py
    import numpy as np
    with h5py.File(path, "r") as f:
        g = f["Grid"]
        p = g["precipitation"]
        attrs = {k: (v.decode() if isinstance(v, bytes) else (v.tolist() if hasattr(v, "tolist") else v)) for k, v in p.attrs.items()
                 if k in ("units", "_FillValue", "CodeMissingValue", "DimensionNames", "LongName")}
        t = g["time"]
        time_units = t.attrs.get("units", b"")
        time_units = time_units.decode() if isinstance(time_units, bytes) else str(time_units)
        tval = int(np.asarray(t[:]).ravel()[0])
        lat = np.asarray(g["lat"][:])
        lon = np.asarray(g["lon"][:])
        shape = list(p.shape)
        out = dict(dataset_shape=shape, dims_attr=attrs.get("DimensionNames"), units=attrs.get("units"),
                   fill_value=attrs.get("_FillValue"), time_units=time_units, time_value=tval,
                   time_utc=epoch_from_units(time_units, tval),
                   lat_first=float(lat[0]), lat_step=float(lat[1] - lat[0]), lon_first=float(lon[0]), lon_step=float(lon[1] - lon[0]),
                   units_cells={})
        for feat in units_geo:
            code = feat["properties"]["code"]
            if code not in codes:
                continue
            b = bbox(feat["geometry"])
            i0, i1 = int(np.searchsorted(lon, b[0] - 0.05)), int(np.searchsorted(lon, b[2] + 0.05))
            j0, j1 = int(np.searchsorted(lat, b[1] - 0.05)), int(np.searchsorted(lat, b[3] + 0.05))
            block = np.asarray(p[0, i0:i1, j0:j1], dtype=float)  # dims (time, lon, lat)
            out["units_cells"][code] = dict(lon=[round(float(x), 3) for x in lon[i0:i1]], lat=[round(float(y), 3) for y in lat[j0:j1]],
                                            values_lon_by_lat=[[None if v < 0 else round(float(v), 4) for v in row] for row in block])
    return out


def bbox(geom) -> list[float]:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    xs = [pt[0] for p in polys for pt in p[0]]
    ys = [pt[1] for p in polys for pt in p[0]]
    return [min(xs), min(ys), max(xs), max(ys)]


def epoch_from_units(units: str, value: int) -> str | None:
    """IMERG V07 declares «seconds since 1980-01-06 00:00:00 UTC» (GPS epoch): use the epoch the file declares."""
    m = re.match(r"seconds since (\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", units or "")
    if not m:
        return None
    return (datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}+00:00") + timedelta(seconds=int(value))).isoformat()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=120)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--budget-s", type=int, default=1800)
    a = ap.parse_args(argv)
    if not os.getenv("EARTHDATA_TOKEN"):
        print("::warning::EARTHDATA_TOKEN missing: nothing captured (not a zero-rain result)")
        return 0
    import earthaccess
    from shapely.geometry import shape
    import probe_imerg_early_live as probe

    t0 = time.time()
    now = datetime.now(timezone.utc)
    geo = json.loads(UNITS_GEO.read_text(encoding="utf-8"))["features"]
    units = [(f["properties"]["code"], shape(f["geometry"]).buffer(0)) for f in geo]
    start = (now - timedelta(hours=a.hours)).replace(minute=0, second=0, microsecond=0)
    earthaccess.login(strategy="environment")
    found = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07", temporal=(start.isoformat(), now.isoformat()),
                                    count=a.hours * 2 + 40)
    indexed = [r for r in probe.index_granules(found) if r[1] and parse_name(r[1]) and r[0] >= start]
    selected, dups = dedupe(indexed)
    print(f"::notice title=catalog::found={len(found)} in_span={len(indexed)} unique={len(selected)} duplicates={len(dups)} "
          f"first={selected[0][0].isoformat() if selected else None} last={selected[-1][0].isoformat() if selected else None}", flush=True)
    rows, absent, validation = [], [], []
    val_pick = set()
    if selected:
        val_pick = {selected[-1][1], selected[len(selected) // 2][1], selected[0][1]}
    for i in range(0, len(selected), a.batch):
        if time.time() - t0 > a.budget_s:
            for r in selected[i:]:
                absent.append(dict(granule=r[1], start_utc=r[0].isoformat(), reason="TIME_BUDGET_EXHAUSTED_NOT_DOWNLOADED"))
            break
        chunk = selected[i:i + a.batch]
        with tempfile.TemporaryDirectory(prefix="irfen_uh_") as td:
            try:
                paths = earthaccess.download([r[2] for r in chunk], local_path=td, threads=6, show_progress=False)
            except Exception as exc:  # noqa: BLE001
                paths = []
                print(f"::warning::download batch failed: {type(exc).__name__}: {str(exc)[:150]}")
            by_name = {Path(p).name: p for p in paths}
            for ts, name, _ in chunk:
                path = by_name.get(name)
                meta = parse_name(name)
                if path is None:
                    absent.append(dict(granule=name, start_utc=ts.isoformat(), reason="DOWNLOAD_FAILED"))
                    continue
                try:
                    lat, lon, values, units_attr = probe.read_grid(path)
                except Exception as exc:  # noqa: BLE001
                    absent.append(dict(granule=name, start_utc=ts.isoformat(), reason=f"READ_FAILED: {str(exc)[:120]}"))
                    continue
                if not any(u in units_attr.lower() for u in ("mm/hr", "mm h-1", "mm/hour")):
                    absent.append(dict(granule=name, start_utc=ts.isoformat(), reason=f"UNEXPECTED_UNITS: {units_attr!r}"))
                    continue
                per = {}
                for code, geom in units:
                    rate, m = probe.polygon_mean(geom, lat, lon, values)
                    ind_rate, ind_cov = independent_mean(geom, lat, lon, values)
                    per[code] = dict(rate_mm_hr=None if rate is None else round(rate, 5),
                                     depth_30min_mm=None if rate is None else round(rate * 0.5, 5),
                                     cells_intersected=m["cells_intersected"], valid_cells=m["valid_cells"],
                                     covered_pct=m["covered_geometry_pct"],
                                     control_rate_mm_hr=None if ind_rate is None else round(ind_rate, 5),
                                     control_covered_fraction=round(ind_cov, 4))
                rows.append(dict(granule=name, start_utc=meta["start"].isoformat(), end_utc=meta["end"].isoformat(),
                                 version=meta["version"], units=units_attr, file_sha256=sha256_file(path),
                                 file_bytes=os.path.getsize(path), units_values=per))
                if name in val_pick:
                    try:
                        validation.append(dict(granule=name, start_utc=meta["start"].isoformat(), file_sha256=rows[-1]["file_sha256"],
                                               direct=direct_read(path, geo, PRIORITY)))
                    except Exception as exc:  # noqa: BLE001
                        validation.append(dict(granule=name, error=f"{type(exc).__name__}: {str(exc)[:200]}"))
        print(f"processed {min(i + a.batch, len(selected))}/{len(selected)} in {time.time() - t0:.0f}s", flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = dict(schema_version="irfen_v09_imerg_early_uh_halfhours_v0_1", **GUARDS,
               source=dict(product="GPM_3IMERGHHE", version="07", provider="NASA GES DISC via earthaccess",
                           variable="Grid/precipitation (mm/hr)", interval="[S, E+1 s) por el nombre del gránulo"),
               sampler=dict(primary="scripts/probe_imerg_early_live.py:polygon_mean (área de intersección celda∩polígono, grados²)",
                            control="10×10 sub-puntos por celda ponderados por cos(lat) (shapely.contains_xy)",
                            depth="tasa media × 0,5 h"),
               units_geometry=f"{UNITS_GEO.relative_to(ROOT)} sha256 {hashlib.sha256(UNITS_GEO.read_bytes()).hexdigest()}",
               requested_span=dict(start_utc=start.isoformat(), now_utc=now.replace(microsecond=0).isoformat(), hours=a.hours),
               catalog=dict(found=len(found), in_span=len(indexed), unique_starts=len(selected), duplicates=dups),
               granules=sorted(rows, key=lambda r: r["start_utc"]), absent=absent,
               runtime_s=round(time.time() - t0))
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    VALIDATION.write_text(json.dumps(dict(schema_version="irfen_v09_imerg_validation_sample_v0_1", **GUARDS, samples=validation),
                                     ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    worst = max((abs(v["rate_mm_hr"] - v["control_rate_mm_hr"]) for r in rows for v in r["units_values"].values()
                 if v["rate_mm_hr"] is not None and v["control_rate_mm_hr"] is not None), default=None)
    print(f"::notice title=uh_rain::granules={len(rows)} absent={len(absent)} duplicates={len(dups)} validation={len(validation)} "
          f"max_abs_diff_primary_vs_control_mm_hr={worst} runtime_s={round(time.time() - t0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
