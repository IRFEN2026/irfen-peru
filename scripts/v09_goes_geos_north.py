#!/usr/bin/env python3
"""IRFEN v0.9 — GOES-19 RRQPE y GEOS-CF TEST_ONLY sobre las zonas del norte (ampliación experimental).

Reutiliza los conectores v0.8 sin modificarlos:
* GOES-19 RRQPE (scripts/probe_goes19_rrqpe.py): catálogo S3 público, descarga acotada del último escaneo de disco
  completo y lectura de la proyección geoestacionaria. Aquí, en lugar de una ventana de 5×5 píxeles en un punto, se
  toman TODOS los píxeles cuyo centro cae dentro del polígono de la zona y se usan solo los de calidad DQF=0. Se
  guarda la tasa instantánea (mm/h) media y máxima, el número de píxeles válidos y la fracción válida. Es una tasa
  de un instante, no un acumulado; RRQPE no está validado localmente.
* GEOS-CF v2 (scripts/fetch_geos_forecast.py): pesos por celda de 0,25° (~27 km) dentro del polígono y serie horaria
  futura. Para cuencas más pequeñas que una celda el valor representa la celda, no la cuenca; se registra el número
  de celdas y el área de la zona frente al área de celda.

Nada de esto inventa precisión: los píxeles o celdas y la resolución se publican junto a cada valor.

  python scripts/v09_goes_geos_north.py --goes
  python scripts/v09_goes_geos_north.py --geos
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
GOES_OUT = ROOT / "data/v09/rain/goes19_rrqpe_north_v0_1.json"
GEOS_OUT = ROOT / "data/v09/rain/geos_cf_north_v0_1.json"
GOES_RETAIN_HOURS = 48
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_if_changed(path: Path, obj: dict, volatile: tuple = ()) -> bool:
    old = load(path)
    strip = lambda o: {k: v for k, v in (o or {}).items() if k not in volatile}  # noqa: E731
    if old is not None and strip(old) == strip(obj):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def targets():
    import v09_imerg_north_archive as imerg  # same zone polygons as the IMERG Early archive

    return imerg.load_targets()


# --------------------------------------------------------------------------- GOES-19 RRQPE (polygon sampling)
def polygon_pixels(project, height, x_axis, y_axis, geom):
    """Indices of pixels whose centre lies inside `geom` (lon/lat). Pure apart from numpy/shapely."""
    import numpy as np
    from shapely import contains_xy

    minx, miny, maxx, maxy = geom.bounds
    xs, ys = [], []
    for lon in np.linspace(minx, maxx, 7):
        for lat in np.linspace(miny, maxy, 7):
            xm, ym = project(lon, lat)
            if math.isfinite(xm) and math.isfinite(ym):
                xs.append(xm / height)
                ys.append(ym / height)
    if not xs:
        return None
    dx = float(np.median(np.abs(np.diff(x_axis))))
    dy = float(np.median(np.abs(np.diff(y_axis))))
    ix = np.where((x_axis >= min(xs) - 2 * dx) & (x_axis <= max(xs) + 2 * dx))[0]
    iy = np.where((y_axis >= min(ys) - 2 * dy) & (y_axis <= max(ys) + 2 * dy))[0]
    if not len(ix) or not len(iy):
        return None
    gx, gy = np.meshgrid(x_axis[ix] * height, y_axis[iy] * height)
    lon, lat = project(gx, gy, inverse=True)
    inside = contains_xy(geom, np.asarray(lon), np.asarray(lat))
    rows, cols = np.nonzero(inside)
    return iy[rows], ix[cols]


def goes_run() -> int:
    import h5py
    import numpy as np
    from pyproj import Proj

    import probe_goes19_rrqpe as goes

    now = datetime.now(timezone.utc)
    archive = load(GOES_OUT) or dict(schema_version="0.1", archive_id="irfen-v09-goes19-rrqpe-north:v0.1", **GUARDS,
                                     map_publishable=False, source=dict(product="NOAA GOES-19 ABI-L2-RRQPEF (full disk)",
                                     bucket="noaa-goes19", quality="DQF=0 only", nature="instantaneous rain rate (mm/h); not an accumulation; not locally validated"),
                                     sampling="all pixels whose centre falls inside the zone polygon", scans=[], status={})
    try:
        objects, _ = goes.catalog(now)
        if not objects:
            raise RuntimeError("NO_RECENT_RRQPE_OBJECTS")
        latest = objects[-1]
        if any(s["key"] == latest["key"] for s in archive["scans"]):
            print(f"::notice title=V09_GOES_NORTH::latest scan already sampled ({latest['key'][-40:]})")
            return 0
        if not 0 < latest["size_bytes"] <= goes.MAX_FILE_BYTES:
            raise RuntimeError("LATEST_OBJECT_SIZE_OUT_OF_BOUNDS")
        body, _ = goes.open_bytes(f"{goes.BASE}/{quote(latest['key'], safe='/')}", timeout=60)
        if len(body) != latest["size_bytes"]:
            raise RuntimeError("DOWNLOADED_SIZE_MISMATCH")
    except Exception as exc:  # noqa: BLE001 - a failure is recorded, never read as zero rain
        state = dict(state="SOURCE_UNREACHABLE", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        if archive["status"].get("state") != state["state"]:
            archive["status"] = dict(state, since_utc=now.isoformat())
            write_if_changed(GOES_OUT, archive)
        print(f"::warning::GOES-19 not sampled: {state['error']}")
        return 0
    with NamedTemporaryFile(suffix=".nc") as tmp:
        tmp.write(body)
        tmp.flush()
        with h5py.File(tmp.name, "r") as handle:
            pj = handle["goes_imager_projection"]
            height = float(goes._scalar(pj.attrs["perspective_point_height"]))
            project = Proj(proj="geos", h=height, lon_0=float(goes._scalar(pj.attrs["longitude_of_projection_origin"])),
                           sweep=str(goes._scalar(pj.attrs["sweep_angle_axis"])), a=float(goes._scalar(pj.attrs["semi_major_axis"])),
                           b=float(goes._scalar(pj.attrs["semi_minor_axis"])))
            x_axis, y_axis = goes._unpack(handle["x"]), goes._unpack(handle["y"])
            rain, dqf = handle["RRQPE"], handle["DQF"]
            fill = int(goes._scalar(rain.attrs["_FillValue"]))
            scale, offset = float(goes._scalar(rain.attrs["scale_factor"])), float(goes._scalar(rain.attrs["add_offset"]))
            units = str(goes._scalar(rain.attrs.get("units")))
            if units != "mm h-1":
                print(f"::warning::unexpected RRQPE units {units!r}; not archived")
                return 0
            raw_all, q_all = np.asarray(rain[:]), np.asarray(dqf[:])
            rows = {}
            for t in targets():
                idx = polygon_pixels(project, height, x_axis, y_axis, t["geometry"])
                if idx is None or not len(idx[0]):
                    rows[t["id"]] = dict(pixels=0, valid_pixels=0, rate_mean_mm_h=None, rate_max_mm_h=None,
                                         note="no pixel centre inside the polygon")
                    continue
                raw, q = raw_all[idx], q_all[idx]
                valid = (raw != fill) & (q == 0)
                vals = raw[valid].astype(float) * scale + offset
                rows[t["id"]] = dict(pixels=int(raw.size), valid_pixels=int(valid.sum()),
                                     valid_fraction=round(float(valid.mean()), 3),
                                     rate_mean_mm_h=round(float(vals.mean()), 3) if valid.any() else None,
                                     rate_max_mm_h=round(float(vals.max()), 3) if valid.any() else None)
    scan = dict(key=latest["key"], scan_start=latest["scan_start"], scan_end=latest["scan_end"], sampled_at_utc=now.isoformat(), targets=rows)
    horizon = (now - timedelta(hours=GOES_RETAIN_HOURS)).isoformat()
    archive["scans"] = [s for s in archive["scans"] if s["scan_end"] >= horizon] + [scan]
    archive["status"] = dict(state="AVAILABLE", latest_scan_end=latest["scan_end"])
    write_if_changed(GOES_OUT, archive)
    print(f"::notice title=V09_GOES_NORTH::sampled {len(rows)} zones; scan_end {latest['scan_end']}")
    return 0


# --------------------------------------------------------------------------- GEOS-CF (polygon cell weights)
def geos_run() -> int:
    import numpy as np
    import xarray as xr

    import fetch_geos_forecast as geos

    ds = xr.open_zarr(geos.STORE, storage_options={"anon": True}, consolidated=None)
    times = np.asarray(ds["time"].values).astype("datetime64[ns]")
    cycle = str(times[0])
    old = load(GEOS_OUT)
    if old and old.get("dataset_time_start") == cycle:
        print(f"::notice title=V09_GEOS_NORTH::cycle {cycle} already processed")
        return 0
    da = ds["tprec"]
    lat, lon = np.asarray(ds["lat"].values, dtype=float), np.asarray(ds["lon"].values, dtype=float)
    step = int(round(float(np.median(np.diff(times).astype("timedelta64[s]").astype(float)))))
    if not 1800 <= step <= 10800:
        raise RuntimeError(f"unexpected GEOS step {step}s")
    now64 = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None), "ns")
    future = np.where(times > now64)[0]
    prepared, need_r, need_c = [], set(), set()
    for t in targets():
        groups = geos.build_weights(dict(areas=[(t["geometry"], 1.0)]), lat, lon)
        if not groups:
            continue
        cells = groups[0]["cells"]
        need_r.update(r for r, _, _ in cells)
        need_c.update(c for _, c, _ in cells)
        prepared.append(dict(t, global_groups=groups, cells=len(cells)))
    rows, cols = sorted(need_r), sorted(need_c)
    rpos, cpos = {v: i for i, v in enumerate(rows)}, {v: i for i, v in enumerate(cols)}
    cube = np.asarray(da.isel(time=future.tolist(), lat=rows, lon=cols).values, dtype=float)
    cell_km2 = (geos.grid_step(lat) * 111.2) * (geos.grid_step(lon) * 111.2 * math.cos(math.radians(7)))
    zones = {}
    for p in prepared:
        groups = geos.localize_groups(p["global_groups"], rpos, cpos)
        hourly = []
        for k, gt in enumerate(future):
            rate = geos.weighted_rate(cube[k], groups)
            hourly.append(dict(valid_time=str(times[gt]).replace(".000000000", "Z"),
                               precip_mm=None if rate is None else round(max(0.0, rate * step), 3)))
        from pyproj import Geod

        area_km2 = abs(Geod(ellps="WGS84").geometry_area_perimeter(p["geometry"])[0]) / 1e6
        zones[p["id"]] = dict(cells=p["cells"], zone_area_km2=round(area_km2, 1), approx_cell_area_km2=round(cell_km2),
                              resolution_note=("zone smaller than one 0.25° cell: the value represents the cell(s), not the basin"
                                               if area_km2 < cell_km2 else "area-weighted mean of 0.25° cells"),
                              hourly=hourly[:120])
    out = dict(schema_version="0.1", archive_id="irfen-v09-geos-cf-north:v0.1", **GUARDS, map_publishable=False,
               source=dict(product="NASA GMAO GEOS-CF v2 forecast (tprec)", store=geos.STORE, grid_deg=[geos.grid_step(lat), geos.grid_step(lon)],
                           integration=f"tprec x {step} s", nature="experimental research forecast; not validated against observations"),
               dataset_time_start=cycle, dataset_time_end=str(times[-1]), generated_at_utc=datetime.now(timezone.utc).isoformat(), zones=zones)
    write_if_changed(GEOS_OUT, out, volatile=("generated_at_utc",))
    print(f"::notice title=V09_GEOS_NORTH::cycle {cycle}; {len(zones)} zones")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goes", action="store_true")
    parser.add_argument("--geos", action="store_true")
    args = parser.parse_args(argv)
    rc = 0
    if args.goes:
        rc |= goes_run()
    if args.geos:
        try:
            rc |= geos_run()
        except Exception as exc:  # noqa: BLE001 - GEOS is optional context; a failure is reported, not hidden
            print(f"::warning::GEOS-CF north not updated: {type(exc).__name__}: {str(exc)[:200]}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
