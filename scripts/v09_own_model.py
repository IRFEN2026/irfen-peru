#!/usr/bin/env python3
"""IRFEN v0.9 — Modelo estadístico propio de lluvia a 1–3 días por provincia (costa norte), TEST_ONLY.

Modelo A (independiente de ECMWF): regresión logística con penalización L2, una por día de anticipación (1–3),
umbral (10, 25, 50 mm) y definición de evento (máximo o media provincial en celdas de 0,25°). Variables:

* oceánicas (OISST v2.1 vía NOAA PSL): TSM costera de Paita (absoluta, anomalía, exceso sobre 26 °C — H1), TSM relativa a la media tropical
  (H8), Niño 1+2 y Niño 4 (o índices E y C del IGP si están disponibles) y su interacción (H9);
* atmosféricas: agua precipitable y viento zonal en 200 y 850 hPa y omega 500 hPa sobre el norte (NCEP/NCAR R1);
* topográficas: elevación media y máxima de las celdas de la provincia, fracción de celdas sobre 1000 m (sierra),
  distancia a la costa; interacciones costa × TSM y sierra × atmósfera;
* estacionales: armónicos del día del año;
* persistencia: lluvia observada del día pluviométrico anterior.

Entrenamiento con PISCOp v2.1 diario de SENAMHI (0,1°, llevado al soporte de 0,25° de ECMWF con la misma rutina que
IMERG) y validación cruzada dejando fuera una temporada hidrológica completa (setiembre–agosto) cada vez. En operación
la persistencia viene de IMERG Late: es un cambio de fuente que la evaluación en sombra debe vigilar.

  python scripts/v09_own_model.py build-inputs     # runner: descarga y resume insumos (acotado, reanudable)
  python scripts/v09_own_model.py refresh          # runner: solo insumos que cambian a diario
  python scripts/v09_own_model.py train            # ajusta, valida y guarda coeficientes
  python scripts/v09_own_model.py predict          # pronóstico en sombra con el mismo formato que el ledger ECMWF
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import v09_ecmwf_ens_north as ens  # noqa: E402 - geometría, grilla y guardas; ningún dato de pronóstico ECMWF

DATA_ROOT = Path(os.environ.get("IRFEN_FC_DATA") or ROOT)
MODEL_DIR = DATA_ROOT / "data/v09/model"
INPUTS = MODEL_DIR / "inputs"
MODEL_JSON = MODEL_DIR / "modelo_propio_v0_1.json"
CV_JSON = MODEL_DIR / "modelo_propio_validacion_v0_1.json"
PROBE_JSON = MODEL_DIR / "insumos_estado_v0_1.json"
LEDGER = DATA_ROOT / "data/v09/forecast/modelo_propio_ledger_v0_1.jsonl"
IMERG_CSV = DATA_ROOT / "data/v09/obs_imerg/imerg_late_provincias_v0_1.csv"

MODEL_VERSION = "0.1"
THRESHOLDS_MM = ens.THRESHOLDS_MM
LEADS = (1, 2, 3)
KINDS = ("max", "mean")
L2 = 1.0
SST_THRESHOLD_C = 26.0
SIERRA_M = 1000.0
PAITA_BOX = dict(lat=(-5.6, -4.6), lon=(-81.9, -81.4))      # mar frente a Paita, fuera de la máscara de tierra
ATMOS_BOX = dict(lat=(-12.5, 0.0), lon=(275.0, 285.0))       # NCEP R1 usa 0–360
CLIM_YEARS = (1991, 2020)
GUARDS = ens.GUARDS

PISCO_URL = ("https://iridl.ldeo.columbia.edu/SOURCES/.SENAMHI/.HSR/.PISCO/.Prec/.v2p1/.stable/.daily/.Prec/"
             "X/-81.75/-76.55/RANGEEDGES/Y/-9.65/-2.95/RANGEEDGES/T/(1%20Jan%20{y})/(31%20Dec%20{y})/RANGEEDGES/data.nc")
PISCO_YEARS = range(1981, 2017)
PISCO_FILE = "pisco_provincias_v0_2.csv.gz"
PISCO_MAX_MM = 1000.0
OISST_PSL = "https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.day.mean.{y}.nc"
CPC_SSTOI = "https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices"
IGP_EC = "http://met.igp.gob.pe/datos/EC.txt"
R1 = "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis.dailyavgs/{group}/{var}.{y}.nc"
R1_VARS = dict(pw=("surface", "pr_wtr.eatm", "pr_wtr", None), u200=("pressure", "uwnd", "uwnd", 200),
               u850=("pressure", "uwnd", "uwnd", 850), w500=("pressure", "omega", "omega", 500))
ETOPO = ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv?"
         "altitude[(-9.65):3:(-2.95)][(-81.75):3:(-76.55)]")


# =========================================================================== utilidades de E/S
def write_csv_gz(path: Path, rows: list[dict], fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(fields), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_bytes(gzip.compress(buf.getvalue().encode("utf-8"), mtime=0))


def read_csv_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def http_text(url: str, timeout: int = 120) -> str:
    import requests

    r = requests.get(url, timeout=timeout, headers={"User-Agent": "IRFEN-research/0.9 (TEST_ONLY)"})
    r.raise_for_status()
    return r.text


def fnum(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# =========================================================================== insumos (solo en el runner)
def build_pisco(provinces, status: dict):
    """Lluvia PISCO por provincia y día (máximo y media en celdas de 0,25°, mismo soporte que ECMWF e IMERG)."""
    import netCDF4

    import v09_imerg_late_province_daily as imerg

    out = INPUTS / PISCO_FILE
    (INPUTS / "pisco_provincias.csv.gz").unlink(missing_ok=True)  # v0.1 contaminada por el relleno del mar (retirada)
    rows = read_csv_gz(out) if out.is_file() else []
    done = {r["fecha"][:4] for r in rows}
    ela, elo = ens.ens_grid()
    a025 = ens.assign_cells(provinces, ela, elo)
    for y in PISCO_YEARS:
        if str(y) in done:
            continue
        try:
            raw = __import__("requests").get(PISCO_URL.format(y=y), timeout=300).content
            ds = netCDF4.Dataset("pisco", memory=raw)
            lat = np.asarray(ds.variables["Y"][:], float)
            lon = np.asarray(ds.variables["X"][:], float)
            t = ds.variables["T"]
            days = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"),
                                    only_use_cftime_datetimes=False, only_use_python_datetimes=True)
            prec = np.ma.filled(np.ma.masked_invalid(ds.variables["Prec"][:]).astype(float), np.nan)  # [T, Y, X]
            prec[(prec < 0) | (prec > PISCO_MAX_MM)] = np.nan  # relleno del mar y valores imposibles = faltante
            land = imerg.land_mask(lat, lon)
        except Exception as exc:  # noqa: BLE001 - se registra y se reintenta en la próxima corrida
            status.setdefault("pisco_errors", []).append(f"{y}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        for k, d in enumerate(days):
            coarse = imerg.regrid_area_mean(prec[k], lat, lon, ela, elo, src_step=_step(lat, lon), land=land).ravel()
            for p in provinces:
                v = coarse[a025[p["id"]]["idx"]]
                ok = np.isfinite(v).all()
                rows.append(dict(fecha=d.date().isoformat(), idprov=p["id"],
                                 max_mm="" if not ok else f"{np.max(v):.2f}",
                                 mean_mm="" if not ok else f"{np.mean(v):.2f}"))
        write_csv_gz(out, rows, ("fecha", "idprov", "max_mm", "mean_mm"))  # guardado por año: reanudable
    status["pisco_years"] = sorted({r["fecha"][:4] for r in rows})


def _step(lat, lon) -> float:
    s = float(np.median(np.abs(np.diff(np.asarray(lat, float)))))
    if abs(s - float(np.median(np.abs(np.diff(np.asarray(lon, float)))))) > 1e-6:
        raise ValueError("grilla PISCO no cuadrada")
    return s


def _open_dap(url: str, attempts: int = 3):
    import netCDF4

    for attempt in range(attempts):  # los servidores OPeNDAP fallan de forma intermitente
        try:
            return netCDF4.Dataset(url)
        except OSError:
            if attempt == attempts - 1:
                raise
            __import__("time").sleep(10 * (attempt + 1))


def _dap_days(ds):
    import netCDF4

    t = ds.variables["time"]
    return [d.date().isoformat() for d in netCDF4.num2date(t[:], t.units, only_use_cftime_datetimes=False,
                                                            only_use_python_datetimes=True)]


def oisst_year(y: int) -> tuple[dict, dict]:
    """TSM diaria media frente a Paita y media tropical muestreada (cada 10° y cada 30 días) de un año de OISST."""
    ds = _open_dap(OISST_PSL.format(y=y))
    lat = np.asarray(ds.variables["lat"][:], float)
    lon = np.asarray(ds.variables["lon"][:], float)  # 0–360
    days = _dap_days(ds)
    sst = ds.variables["sst"]
    ri = np.flatnonzero((lat >= PAITA_BOX["lat"][0]) & (lat <= PAITA_BOX["lat"][1]))
    ci = np.flatnonzero((lon >= PAITA_BOX["lon"][0] % 360) & (lon <= PAITA_BOX["lon"][1] % 360))
    box = np.ma.filled(np.ma.masked_invalid(sst[:, ri[0]:ri[-1] + 1, ci[0]:ci[-1] + 1]).astype(float), np.nan)
    paita = {d: float(np.nanmean(box[k])) for k, d in enumerate(days) if np.isfinite(box[k]).any()}
    ti = np.flatnonzero((lat >= -20.0) & (lat <= 20.0))
    sample = np.ma.filled(np.ma.masked_invalid(sst[::30, ti[0]:ti[-1] + 1:40, ::40]).astype(float), np.nan)
    trop = {days[30 * k]: float(np.nanmean(sample[k])) for k in range(sample.shape[0]) if np.isfinite(sample[k]).any()}
    return paita, trop


def build_ocean(status: dict, years=None):
    """TSM diaria frente a Paita y media tropical 20° S–20° N (OISST v2.1 vía NOAA PSL OPeNDAP), reanudable por año.

    Niño 1+2 no se descarga diario: el modelo usa el índice mensual de CPC (``indices_mensuales``).
    """
    out = INPUTS / "oceano_diario.csv.gz"
    old = {r["fecha"]: r for r in read_csv_gz(out)} if out.is_file() else {}
    raw_path = INPUTS / "oceano_tropical_muestras.csv.gz"
    trop = {r["fecha"]: fnum(r["sst_trop"]) for r in read_csv_gz(raw_path)} if raw_path.is_file() else {}
    paita = {d: fnum(r["sst_paita"]) for d, r in old.items()}
    this_year = datetime.now(timezone.utc).year
    years = years or range(1981, this_year + 1)
    have = {d[:4] for d in paita}
    for y in years:
        if str(y) in have and y < this_year - (1 if datetime.now(timezone.utc).month == 1 else 0):
            continue
        try:
            p, tr = oisst_year(y)
        except Exception as exc:  # noqa: BLE001
            status.setdefault("ocean_errors", []).append(f"{y}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        paita.update(p)
        trop.update(tr)
    tk = sorted(trop)
    tx = np.array([date.fromisoformat(d).toordinal() for d in tk], float)
    ty = np.array([trop[d] for d in tk])
    rows = []
    for d in sorted(paita):
        x = date.fromisoformat(d).toordinal()
        rows.append(dict(fecha=d, sst_paita=f"{paita[d]:.3f}",
                         sst_trop=f"{np.interp(x, tx, ty):.3f}" if tx.size and tx[0] - 45 <= x <= tx[-1] + 45 else ""))
    write_csv_gz(out, rows, ("fecha", "sst_paita", "sst_trop"))
    write_csv_gz(raw_path, [dict(fecha=d, sst_trop=f"{trop[d]:.3f}") for d in tk], ("fecha", "sst_trop"))
    status["ocean_days"] = len(rows)
    status["ocean_last"] = rows[-1]["fecha"] if rows else None
    if not rows:
        raise RuntimeError("sin TSM: " + "; ".join(status.get("ocean_errors", [])[:3]))


def build_indices(status: dict):
    out = INPUTS / "indices_mensuales.csv.gz"
    rows = {}
    text = http_text(CPC_SSTOI)
    for line in text.splitlines()[1:]:
        p = line.split()
        if len(p) >= 10 and p[0].isdigit():
            ym = f"{int(p[0]):04d}-{int(p[1]):02d}"
            rows[ym] = dict(ym=ym, nino12=p[3], nino4=p[7], nino34=p[9], E="", C="")
    status["cpc_months"] = len(rows)
    try:
        ec = http_text(IGP_EC, timeout=60)
        n = 0
        for line in ec.splitlines():
            p = line.split()
            if len(p) >= 4 and p[0].isdigit() and p[1].isdigit():
                ym = f"{int(p[0]):04d}-{int(p[1]):02d}"
                if ym in rows and fnum(p[2]) is not None and fnum(p[3]) is not None:
                    rows[ym]["E"], rows[ym]["C"] = p[2], p[3]
                    n += 1
        status["igp_ec_months"] = n
    except Exception as exc:  # noqa: BLE001 - sin E/C oficiales se usan Niño 1+2 y Niño 4 por separado
        status["igp_ec_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    write_csv_gz(out, sorted(rows.values(), key=lambda r: r["ym"]), ("ym", "nino12", "nino4", "nino34", "E", "C"))


R1_LAST_DAY = date(2026, 3, 17)  # NOAA PSL: NCEP/NCAR R1 dejó de producirse con esa última fecha


def build_atmos(status: dict, years):
    """NCEP/NCAR R1 diario (solo entrenamiento: la producción terminó el 17-03-2026, no sirve en operación)."""
    import netCDF4

    out = INPUTS / "atmosfera_diaria.csv.gz"
    rows = {r["fecha"]: r for r in read_csv_gz(out)} if out.is_file() else {}
    have_years = {f[:4] for f, r in rows.items() if all(r.get(k) for k in R1_VARS)}
    for y in years:
        if str(y) in have_years or y > R1_LAST_DAY.year:
            continue
        for key, (group, fname, var, level) in R1_VARS.items():
            try:
                ds = None
                for attempt in range(3):  # el servidor OPeNDAP de PSL falla de forma intermitente
                    try:
                        ds = netCDF4.Dataset(R1.format(group=group, var=fname, y=y))
                        break
                    except OSError:
                        if attempt == 2:
                            raise
                        __import__("time").sleep(10 * (attempt + 1))
                lat = np.asarray(ds.variables["lat"][:], float)
                lon = np.asarray(ds.variables["lon"][:], float)
                ri = np.flatnonzero((lat >= ATMOS_BOX["lat"][0]) & (lat <= ATMOS_BOX["lat"][1]))
                ci = np.flatnonzero((lon >= ATMOS_BOX["lon"][0]) & (lon <= ATMOS_BOX["lon"][1]))
                v = ds.variables[var]
                if level is None:
                    data = np.asarray(v[:, ri[0]:ri[-1] + 1, ci[0]:ci[-1] + 1], float)
                else:
                    li = int(np.flatnonzero(np.asarray(ds.variables["level"][:], float) == level)[0])
                    data = np.asarray(v[:, li, ri[0]:ri[-1] + 1, ci[0]:ci[-1] + 1], float)
                t = ds.variables["time"]
                days = netCDF4.num2date(t[:], t.units, only_use_cftime_datetimes=False, only_use_python_datetimes=True)
                for k, d in enumerate(days):
                    row = rows.setdefault(d.date().isoformat(), dict(fecha=d.date().isoformat()))
                    row[key] = f"{float(np.nanmean(data[k])):.4f}"
            except Exception as exc:  # noqa: BLE001
                status.setdefault("atmos_errors", []).append(f"{y}/{key}: {type(exc).__name__}: {str(exc)[:120]}")
        write_csv_gz(out, sorted(rows.values(), key=lambda r: r["fecha"]), ("fecha", *R1_VARS))
    status["atmos_days"] = len(rows)
    status["atmos_last"] = max(rows) if rows else None


def build_topography(provinces, status: dict):
    out = INPUTS / "topografia.csv.gz"
    if out.is_file():  # estática: se descarga una sola vez
        status["topography_points"] = "en caché"
        return
    text = http_text(ETOPO, timeout=300)
    pts = []
    for line in text.splitlines()[2:]:
        la, lo, alt = (fnum(x) for x in line.split(","))
        if None not in (la, lo, alt):
            pts.append((la, lo, alt))
    rows = topography_rows(provinces, np.array(pts, float))
    write_csv_gz(out, rows, ("idprov", "elev_mean", "elev_max", "frac_sierra", "coast_km"))
    status["topography_points"] = len(pts)


def topography_rows(provinces, pts: np.ndarray) -> list[dict]:
    """Elevación de las celdas de 0,25° de cada provincia (promedio de puntos ETOPO dentro de cada celda)."""
    ela, elo = ens.ens_grid()
    a025 = ens.assign_cells(provinces, ela, elo)
    glon, glat = np.meshgrid(elo, ela)
    cell_lat, cell_lon = glat.ravel(), glon.ravel()
    cell_elev = np.full(cell_lat.size, np.nan)
    for i, (la, lo) in enumerate(zip(cell_lat, cell_lon)):
        sel = (np.abs(pts[:, 0] - la) <= 0.125) & (np.abs(pts[:, 1] - lo) <= 0.125)
        if sel.any():
            cell_elev[i] = float(np.mean(pts[sel, 2]))
    sea = pts[pts[:, 2] <= 0]
    rows = []
    for p in provinces:
        idx = a025[p["id"]]["idx"]
        e = np.clip(cell_elev[idx], 0, None)
        cx, cy = p["centroid"]
        if sea.size:
            d = np.min(np.hypot((sea[:, 1] - cx) * 111.3 * math.cos(math.radians(cy)), (sea[:, 0] - cy) * 111.3))
        else:
            d = float("nan")
        rows.append(dict(idprov=p["id"], elev_mean=f"{np.nanmean(e):.1f}", elev_max=f"{np.nanmax(e):.1f}",
                         frac_sierra=f"{np.nanmean(e > SIERRA_M):.3f}", coast_km=f"{d:.1f}"))
    return rows


def build_inputs(live_only: bool = False) -> int:
    """Insumos completos (entrenamiento) o solo los que cambian a diario (``live_only``: operación)."""
    provinces = ens.load_provinces(ens.boundaries_paths()[0])
    status = dict(started_at_utc=datetime.now(timezone.utc).isoformat(), live_only=live_only)
    steps = [("indices", lambda: build_indices(status)),
             ("ocean", lambda: build_ocean(status, range(datetime.now(timezone.utc).year - 1,
                                                          datetime.now(timezone.utc).year + 1) if live_only else None))]
    if not live_only:  # la atmósfera R1 ya no se actualiza: solo se completa el histórico
        steps += [("atmos", lambda: build_atmos(status, range(1981, R1_LAST_DAY.year + 1))),
                  ("topography", lambda: build_topography(provinces, status)),
                  ("pisco", lambda: build_pisco(provinces, status))]
    for name, fn in steps:
        try:
            fn()
            status[f"{name}_state"] = "OK"
        except Exception as exc:  # noqa: BLE001 - cada insumo se informa por separado; nunca se rellena con ceros
            status[f"{name}_state"] = f"ERROR {type(exc).__name__}: {str(exc)[:200]}"
        print(f"::notice title=V09_OWN_MODEL_INPUTS::{name}: {status[f'{name}_state']}")
    status["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    PROBE_JSON.parent.mkdir(parents=True, exist_ok=True)
    if live_only and PROBE_JSON.is_file():
        status = dict(json.loads(PROBE_JSON.read_text(encoding="utf-8")).get("status", {}), last_refresh=status)
    PROBE_JSON.write_text(json.dumps(dict(**GUARDS, status=status), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


# =========================================================================== variables
FEATURES = ("sin1", "cos1", "sin2", "cos2", "elev_mean", "elev_max", "frac_sierra", "coast_km",
            "sst_paita_anom", "sst_excess", "sst_rel", "coast_x_excess", "coast_x_rel",
            "enso_e", "enso_c", "enso_ec",
            "pw_anom", "u200", "u850", "w500", "sierra_x_pw", "sierra_x_u200",
            "rain_max_lag1", "rain_mean_lag1", "rain_max_lag2")
RAIN_FEATURES = ("rain_max_lag1", "rain_mean_lag1", "rain_max_lag2")
ATMOS_FEATURES = ("pw_anom", "u200", "u850", "w500", "sierra_x_pw", "sierra_x_u200")
NO_RAIN = tuple(f for f in FEATURES if f not in RAIN_FEATURES)
# Variantes, de la más completa a la mínima; en operación se usa la primera cuyas variables existen todas.
VARIANTS = {
    "full": FEATURES,
    "no_rain": NO_RAIN,
    "no_atmos": tuple(f for f in FEATURES if f not in ATMOS_FEATURES),
    "no_atmos_no_rain": tuple(f for f in NO_RAIN if f not in ATMOS_FEATURES),
}


class Inputs:
    """Insumos ya leídos; todo indexado por fecha ISO o por provincia."""

    def __init__(self, ocean: dict, indices: dict, atmos: dict, topo: dict, rain: dict, clim: dict | None = None):
        self.ocean, self.indices, self.atmos, self.topo, self.rain = ocean, indices, atmos, topo, rain
        self.clim = clim or climatologies(ocean, atmos)

    @classmethod
    def load(cls, rain_source: str = "pisco"):
        ocean = {r["fecha"]: r for r in read_csv_gz(INPUTS / "oceano_diario.csv.gz")}
        indices = {r["ym"]: r for r in read_csv_gz(INPUTS / "indices_mensuales.csv.gz")}
        atmos = {r["fecha"]: r for r in read_csv_gz(INPUTS / "atmosfera_diaria.csv.gz")}
        topo = {r["idprov"]: r for r in read_csv_gz(INPUTS / "topografia.csv.gz")}
        rain = {}
        if rain_source == "pisco":
            for r in read_csv_gz(INPUTS / PISCO_FILE):
                rain[(r["fecha"], r["idprov"])] = (fnum(r["max_mm"]), fnum(r["mean_mm"]))
        else:  # IMERG Late en operación (mismo soporte de 0,25°)
            if IMERG_CSV.is_file():
                with IMERG_CSV.open(encoding="utf-8") as fh:
                    for r in csv.DictReader(fh):
                        rain[(r["fecha_peru"], r["idprov"])] = (fnum(r["lluvia_max_mm"]), fnum(r["lluvia_media_mm"]))
        return cls(ocean, indices, atmos, topo, rain)


def climatologies(ocean: dict, atmos: dict) -> dict:
    """Climatología diaria 1991–2020 (suavizada con armónicos) de la TSM de Paita y del agua precipitable."""
    out = {}
    for name, src, key in (("sst_paita", ocean, "sst_paita"), ("pw", atmos, "pw")):
        xs, ys = [], []
        for d, r in src.items():
            y = int(d[:4])
            v = fnum(r.get(key))
            if v is not None and CLIM_YEARS[0] <= y <= CLIM_YEARS[1]:
                xs.append(date.fromisoformat(d).timetuple().tm_yday)
                ys.append(v)
        if len(xs) < 365:
            out[name] = None
            continue
        t = 2 * np.pi * np.asarray(xs, float) / 365.25
        A = np.column_stack([np.ones_like(t), np.sin(t), np.cos(t), np.sin(2 * t), np.cos(2 * t)])
        out[name] = np.linalg.lstsq(A, np.asarray(ys, float), rcond=None)[0].tolist()
    return out


def _clim(coef, doy: int):
    t = 2 * np.pi * doy / 365.25
    return float(np.dot(coef, [1, np.sin(t), np.cos(t), np.sin(2 * t), np.cos(2 * t)]))


def feature_row(inp: Inputs, issue: date, lead: int, idprov: str, atmos_max_age: int = 0,
                ocean_max_age: int = 0, enso: str = "nino") -> dict | None:
    """Variables para una provincia, emitidas el día ``issue`` con el estado del día ``issue − 1``.

    Núcleo obligatorio (estación, topografía, océano, ENSO): si falta algo devuelve None. Bloques opcionales
    (atmósfera, persistencia): si faltan, sus claves no aparecen y solo aplican las variantes que no los usan.
    Nunca se rellena con ceros. ``enso``: "ec" (índices E y C del IGP) o "nino" (Niño 1+2 y Niño 4 de CPC).
    """
    state = issue - timedelta(days=1)
    target = issue + timedelta(days=lead)
    doy = target.timetuple().tm_yday
    t = 2 * np.pi * doy / 365.25
    topo = inp.topo.get(idprov)
    oc = None
    for age in range(ocean_max_age + 1):  # la TSM diaria se publica con ~1 día de retraso y varía lentamente
        oc = inp.ocean.get((state - timedelta(days=age)).isoformat())
        if oc and fnum(oc.get("sst_paita")) is not None and fnum(oc.get("sst_trop")) is not None:
            break
        oc = None
    atm = None
    for age in range(atmos_max_age + 1):
        atm = inp.atmos.get((state - timedelta(days=age)).isoformat())
        if atm and all(fnum(atm.get(k)) is not None for k in R1_VARS):
            break
        atm = None
    prev_month = (state.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    idx = inp.indices.get(prev_month)
    if not (topo and oc and idx) or inp.clim.get("sst_paita") is None:
        return None
    sst = fnum(oc.get("sst_paita"))
    trop = fnum(oc.get("sst_trop"))
    if enso == "ec":
        e, c = fnum(idx.get("E")), fnum(idx.get("C"))
    else:
        e, c = fnum(idx.get("nino12")), fnum(idx.get("nino4"))
    if None in (sst, trop, e, c):
        return None
    frac_sierra = fnum(topo["frac_sierra"])
    coast = 1.0 - frac_sierra
    sst_rel = sst - trop
    excess = max(sst - SST_THRESHOLD_C, 0.0)
    row = dict(sin1=np.sin(t), cos1=np.cos(t), sin2=np.sin(2 * t), cos2=np.cos(2 * t),
               elev_mean=fnum(topo["elev_mean"]), elev_max=fnum(topo["elev_max"]), frac_sierra=frac_sierra,
               coast_km=fnum(topo["coast_km"]),
               sst_paita_anom=sst - _clim(inp.clim["sst_paita"], state.timetuple().tm_yday), sst_excess=excess,
               sst_rel=sst_rel, coast_x_excess=coast * excess, coast_x_rel=coast * sst_rel,
               enso_e=e, enso_c=c, enso_ec=e * c)
    if atm and inp.clim.get("pw") is not None:
        pw_anom = fnum(atm["pw"]) - _clim(inp.clim["pw"], state.timetuple().tm_yday)
        row.update(pw_anom=pw_anom, u200=fnum(atm["u200"]), u850=fnum(atm["u850"]), w500=fnum(atm["w500"]),
                   sierra_x_pw=frac_sierra * pw_anom, sierra_x_u200=frac_sierra * fnum(atm["u200"]))
    r1 = inp.rain.get((state.isoformat(), idprov))
    r2 = inp.rain.get(((state - timedelta(days=1)).isoformat(), idprov))
    if r1 and r2 and None not in (r1[0], r1[1], r2[0]):
        row.update(rain_max_lag1=math.log1p(r1[0]), rain_mean_lag1=math.log1p(r1[1]), rain_max_lag2=math.log1p(r2[0]))
    if any(v is None or not math.isfinite(v) for v in row.values()):
        return None
    return row


# =========================================================================== regresión logística L2 (IRLS)
def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = L2, iters: int = 50, w: np.ndarray | None = None):
    """Coeficientes con intercepto sin penalizar; ``X`` ya estandarizada."""
    n, k = X.shape
    A = np.column_stack([np.ones(n), X])
    beta = np.zeros(k + 1)
    pen = np.full(k + 1, l2)
    pen[0] = 0.0
    sw = np.ones(n) if w is None else np.asarray(w, float)
    for _ in range(iters):
        z = np.clip(A @ beta, -30, 30)
        p = 1 / (1 + np.exp(-z))
        W = sw * p * (1 - p) + 1e-9
        grad = A.T @ (sw * (y - p)) - pen * beta
        H = (A * W[:, None]).T @ A + np.diag(pen)
        step = np.linalg.solve(H, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta


def predict_logistic(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    z = np.clip(beta[0] + X @ beta[1:], -30, 30)
    return 1 / (1 + np.exp(-z))


def season_of(d: date) -> int:
    """Temporada hidrológica setiembre–agosto, identificada por el año en que empieza."""
    return d.year if d.month >= 9 else d.year - 1


def design(inp: Inputs, issues, provinces_ids, lead: int, features, enso: str = "nino"):
    X, meta = [], []
    for issue in issues:
        for pid in provinces_ids:
            row = feature_row(inp, issue, lead, pid, enso=enso)
            if row is None or any(f not in row for f in features):
                continue
            target = inp.rain.get(((issue + timedelta(days=lead)).isoformat(), pid))
            if not target or target[0] is None or target[1] is None:
                continue
            X.append([row[f] for f in features])
            meta.append((issue, pid, target[0], target[1]))
    return np.asarray(X, float), meta


def enso_source(indices: dict, today: date, max_age_months: int = 3) -> str:
    """'ec' solo si el IGP publicó E y C en los últimos meses; si no, 'nino' para entrenar y operar igual."""
    months = sorted(ym for ym, r in indices.items() if fnum(r.get("E")) is not None and fnum(r.get("C")) is not None)
    if not months:
        return "nino"
    y, m = map(int, months[-1].split("-"))
    age = (today.year - y) * 12 + today.month - m
    return "ec" if age <= max_age_months else "nino"


def train() -> int:
    inp = Inputs.load("pisco")
    provinces = sorted(inp.topo)
    days = sorted({date.fromisoformat(f) for f, _ in inp.rain})
    if not days:
        print("::warning title=V09_OWN_MODEL::sin lluvia PISCO para entrenar")
        return 1
    issues = [d for d in days if d - timedelta(days=2) >= days[0]]
    enso = enso_source(inp.indices, datetime.now(timezone.utc).date())
    model = dict(schema_version="0.1", model_id=f"irfen-v09-modelo-propio:v{MODEL_VERSION}", **GUARDS,
                 trained_at_utc=datetime.now(timezone.utc).isoformat(),
                 training_rain="PISCOp v2.1 diario (SENAMHI), tierra peruana en celdas de 0,25°",
                 training_period=[days[0].isoformat(), days[-1].isoformat()], l2=L2, enso_source=enso,
                 enso_note=("índices E y C del IGP" if enso == "ec" else
                            "Niño 1+2 y Niño 4 de CPC: el archivo E/C del IGP no está al día y no se mezclan fuentes"),
                 atmosphere_note="NCEP/NCAR R1 terminó el 17-03-2026: las variantes con atmósfera no aplican en operación",
                 climatologies=inp.clim, variants={})
    cv = dict(schema_version="0.1", **GUARDS, scheme="dejar fuera una temporada setiembre–agosto", results=[])
    import v09_fc_evaluate as ev

    for variant, feats in VARIANTS.items():
        model["variants"][variant] = dict(features=list(feats), models={})
        for lead in LEADS:
            X, meta = design(inp, issues, provinces, lead, feats, enso)
            if X.size == 0:
                continue
            mu, sd = X.mean(axis=0), X.std(axis=0)
            sd[sd == 0] = 1.0
            Z = (X - mu) / sd
            seasons = np.array([season_of(m[0]) for m in meta])
            for kind in KINDS:
                obs = np.array([m[2] if kind == "max" else m[3] for m in meta])
                for u in THRESHOLDS_MM:
                    y = (obs >= u).astype(float)
                    beta = fit_logistic(Z, y)
                    model["variants"][variant]["models"][f"{kind}|{u:g}|{lead}"] = dict(
                        beta=[round(float(b), 6) for b in beta], mean=mu.round(6).tolist(), sd=sd.round(6).tolist(),
                        n=int(y.size), events=int(y.sum()))
                    oof = np.full(y.size, np.nan)
                    for s in np.unique(seasons):
                        tr, te = seasons != s, seasons == s
                        if y[tr].sum() == 0:
                            oof[te] = 0.0
                            continue
                        oof[te] = predict_logistic(fit_logistic(Z[tr], y[tr]), Z[te])
                    block = ev.score_block(oof, y.astype(bool))
                    cv["results"].append(dict(variant=variant, kind=kind, threshold_mm=u, day=lead, **{
                        k: block[k] for k in ("pairs", "events", "brier", "bss", "roc_auc", "brier_decomposition",
                                              "reliability", "contingency")}))
                    print(f"::notice title=V09_OWN_MODEL_CV::{variant} {kind}≥{u:g} día {lead}: n={y.size} "
                          f"eventos={int(y.sum())} BSS={block['bss']} ROC={block['roc_auc']}")
    MODEL_JSON.parent.mkdir(parents=True, exist_ok=True)
    MODEL_JSON.write_text(json.dumps(model, ensure_ascii=False) + "\n", encoding="utf-8")
    CV_JSON.write_text(json.dumps(cv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


# =========================================================================== pronóstico en sombra
def forecast_record(model: dict, inp: Inputs, provinces: list[dict], issue_time: datetime) -> dict:
    """Mismo formato que el ledger ECMWF (``days``, ``provinces[...].days[...].p_max/p_mean``) para evaluarlos igual."""
    issue = issue_time.date()
    windows = ens.day_windows(issue_time.hour)
    run0 = issue_time.replace(minute=0, second=0, microsecond=0)
    days_meta = []
    for d, (s, e) in enumerate(windows, start=1):
        end = run0 + timedelta(hours=e)
        days_meta.append(dict(day=d, step_start_h=s, step_end_h=e, start_utc=(run0 + timedelta(hours=s)).isoformat(),
                              end_utc=end.isoformat(), valid_date_peru=(end - timedelta(hours=5)).date().isoformat()))
    provs, variants_used = {}, {}
    for p in provinces:
        pdays = []
        for meta in days_meta:
            lead = (date.fromisoformat(meta["valid_date_peru"]) - issue).days
            entry = dict(day=meta["day"], p_max={}, p_mean={})
            row = feature_row(inp, issue, lead, p["id"], atmos_max_age=3, ocean_max_age=3,
                              enso=model.get("enso_source", "nino"))
            variant = None
            if row is not None:
                variant = next((v for v, spec in model["variants"].items()
                                if spec.get("models") and all(f in row for f in spec["features"])), None)
            for kind in KINDS:
                for u in THRESHOLDS_MM:
                    m = model["variants"].get(variant or "", {}).get("models", {}).get(f"{kind}|{u:g}|{lead}")
                    if row is None or m is None:
                        entry[f"p_{kind}"][f"{u:g}"] = None  # sin insumos: faltante, nunca probabilidad cero
                        continue
                    feats = model["variants"][variant]["features"]
                    z = (np.array([row[f] for f in feats]) - np.array(m["mean"])) / np.array(m["sd"])
                    entry[f"p_{kind}"][f"{u:g}"] = round(float(predict_logistic(np.array(m["beta"]), z[None, :])[0]), 3)
            pdays.append(entry)
            variants_used[variant or "SIN_INSUMOS"] = variants_used.get(variant or "SIN_INSUMOS", 0) + 1
        provs[p["id"]] = dict(name=p["name"], department=p["department"], days=pdays)
    return dict(run_utc=run0.isoformat(), model_id=model["model_id"], processing_version=MODEL_VERSION,
                thresholds_mm=[float(u) for u in THRESHOLDS_MM], days=days_meta, provinces=provs,
                variants_used=variants_used, archived_at_utc=datetime.now(timezone.utc).isoformat())


def predict() -> int:
    if not MODEL_JSON.is_file():
        print("::notice title=V09_OWN_MODEL::modelo aún no entrenado; sin pronóstico")
        return 0
    model = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    inp = Inputs.load("imerg")
    inp.clim = model["climatologies"]
    provinces = ens.load_provinces(ens.boundaries_paths()[0])
    now = datetime.now(timezone.utc)
    issue_time = now.replace(hour=0 if now.hour < 12 else 12)  # alineado con la corrida ECMWF del mismo ciclo
    rec = forecast_record(model, inp, provinces, issue_time)
    appended = ens.append_ledger(rec, LEDGER)
    print(f"::notice title=V09_OWN_MODEL::emitido {rec['run_utc']} (nuevo={appended}); variantes {rec['variants_used']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("build-inputs", "refresh", "train", "predict"))
    args = parser.parse_args(argv)
    if args.command == "refresh":
        return build_inputs(live_only=True)
    return dict(build_inputs=build_inputs, train=train, predict=predict)[args.command.replace("-", "_")]()


if __name__ == "__main__":
    sys.exit(main())
