#!/usr/bin/env python3
"""IRFEN v0.9 — Lluvia observada IMERG Late por provincia y día pluviométrico de Perú, TEST_ONLY.

Fuente de verificación independiente del pronóstico: no lee nada de ECMWF ni del modelo propio.

Correspondencia temporal
  Día pluviométrico ``D`` = de las 12:00 UTC de D−1 a las 12:00 UTC de D (07:00 a 07:00 en Perú), el mismo cierre que
  las estaciones convencionales de SENAMHI y que las ventanas del pronóstico ECMWF. Se suman los 48 gránulos
  medio-horarios de IMERG Late V07 (``GPM_3IMERGHHL``) cuyo inicio cae en ``[D−1 12:00, D 12:00)``; cada gránulo aporta
  tasa (mm/h) × 0,5 h. Un día con menos de 48 gránulos queda incompleto y no se usa para verificar: un dato faltante
  no es lluvia cero.

Correspondencia espacial (por provincia INEI, mismas celdas que el pronóstico)
  * ``lluvia_max_mm`` / ``lluvia_media_mm``: IMERG promediado por área sobre la tierra peruana de cada celda de 0,25°
    de la grilla de ECMWF (misma máscara que PISCO en el entrenamiento del modelo propio) y luego máximo / media sobre
    las celdas que el pronóstico asigna a la provincia. Es el soporte de ``p_max`` /
    ``p_mean``: compara lo que el modelo puede representar (~27 km), no un punto.
  * ``lluvia_max_nativo_mm``: máximo sobre las celdas IMERG de 0,1° (~11 km) de la provincia. Más cercano a un
    chubasco local, pero todavía no es la lluvia puntual de una quebrada ni de un pluviómetro.

  python scripts/v09_imerg_late_province_daily.py      # runner con EARTHDATA_TOKEN
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import v09_ecmwf_ens_north as ens  # noqa: E402 - solo geometría y grilla; ningún dato de pronóstico

DATA_ROOT = Path(os.environ.get("IRFEN_FC_DATA") or ROOT)
OBS_DIR = DATA_ROOT / "data/v09/obs_imerg"
FIELDS_DIR = OBS_DIR / "fields"
PARTIAL_DIR = OBS_DIR / "partial"
OBS_CSV = OBS_DIR / "imerg_late_provincias_v0_1.csv"
STATUS_JSON = OBS_DIR / "imerg_late_status_v0_1.json"

PRODUCT, VERSION = "GPM_3IMERGHHL", "07"
SLOTS_PER_DAY = 48
LOOKBACK_DAYS = 6          # días pluviométricos que se intentan completar en cada corrida
MAX_DOWNLOADS = 150        # gránulos por corrida (acotado)
IMERG_STEP = 0.1
CSV_COLUMNS = ("fecha_peru", "idprov", "lluvia_max_mm", "lluvia_media_mm", "fuente", "n", "lluvia_max_nativo_mm",
               "celdas_025", "celdas_01", "medias_horas")
SOURCE_LABEL = "IMERG Late V07 (soporte 0,25° ECMWF)"
GUARDS = ens.GUARDS


# --------------------------------------------------------------------------- tiempo
def rain_day_slots(valid: date) -> list[datetime]:
    start = datetime(valid.year, valid.month, valid.day, 12, tzinfo=timezone.utc) - timedelta(days=1)
    return [start + timedelta(minutes=30 * i) for i in range(SLOTS_PER_DAY)]


def rain_day_of(slot_start: datetime) -> date:
    """Día pluviométrico al que pertenece un gránulo que empieza en ``slot_start`` (UTC)."""
    t = slot_start.astimezone(timezone.utc)
    return (t + timedelta(hours=12)).date()


def candidate_days(now: datetime, lookback: int = LOOKBACK_DAYS) -> list[date]:
    """Días pluviométricos ya cerrados (fin ≤ ahora) dentro de la ventana de búsqueda, del más antiguo al más nuevo."""
    last_closed = (now.astimezone(timezone.utc) - timedelta(hours=12)).date()
    return [last_closed - timedelta(days=k) for k in range(lookback - 1, -1, -1)]


# --------------------------------------------------------------------------- remuestreo 0,1° → 0,25° por área
def overlap_matrix(src_centres: np.ndarray, src_step: float, dst_centres: np.ndarray, dst_step: float) -> np.ndarray:
    """W[j, i] = fracción de la celda destino j cubierta por la celda origen i (1 dimensión)."""
    s_lo, s_hi = src_centres - src_step / 2, src_centres + src_step / 2
    d_lo, d_hi = dst_centres - dst_step / 2, dst_centres + dst_step / 2
    lo = np.maximum(d_lo[:, None], s_lo[None, :])
    hi = np.minimum(d_hi[:, None], s_hi[None, :])
    return np.clip(hi - lo, 0.0, None) / dst_step


MIN_LAND_FRAC = 0.2   # una celda de 0,25° cuenta si al menos el 20 % de su área es tierra peruana


def regrid_area_mean(field: np.ndarray, src_lat, src_lon, dst_lat, dst_lon,
                     src_step: float = IMERG_STEP, dst_step: float = 0.25, land: np.ndarray | None = None,
                     min_land_frac: float = MIN_LAND_FRAC) -> np.ndarray:
    """Media por área de ``field`` [lat, lon] sobre cada celda destino.

    Sin ``land``: NaN si falta más del 10 % del área. Con ``land`` (máscara booleana en la grilla de origen): media
    solo sobre la tierra; NaN si la tierra cubre menos de ``min_land_frac`` de la celda o si falta más del 10 % de la
    tierra. Así PISCO (solo tierra) e IMERG (tierra y mar) se comparan sobre el mismo soporte.
    """
    wl = overlap_matrix(np.asarray(src_lat), src_step, np.asarray(dst_lat), dst_step)
    wo = overlap_matrix(np.asarray(src_lon), src_step, np.asarray(dst_lon), dst_step)
    base = np.ones(field.shape, dtype=bool) if land is None else np.asarray(land, dtype=bool)
    valid = np.isfinite(field) & base
    num = wl @ np.where(valid, field, 0.0) @ wo.T
    den = wl @ valid.astype(float) @ wo.T
    cover = wl.sum(axis=1)[:, None] * wo.sum(axis=1)[None, :]
    support = wl @ base.astype(float) @ wo.T
    out = np.full(num.shape, np.nan)
    need = (0.0 if land is None else min_land_frac) * cover
    ok = (cover > 0) & (support > 0) & (support >= need) & (den >= 0.9 * support)
    out[ok] = num[ok] / den[ok]
    return out


_LAND_CACHE: dict = {}


def land_mask(lat, lon) -> np.ndarray:
    """Tierra = centro de celda dentro de alguna provincia INEI del archivo archivado (todas sus provincias)."""
    key = (tuple(np.round(lat, 4)), tuple(np.round(lon, 4)))
    if key not in _LAND_CACHE:
        provinces = ens.load_provinces(ens.boundaries_paths()[0], departments=None)
        glon, glat = np.meshgrid(np.asarray(lon, float), np.asarray(lat, float))
        px, py = glon.ravel(), glat.ravel()
        mask = np.zeros(px.size, dtype=bool)
        for prov in provinces:
            for poly in prov["polygons"]:
                ext = poly[0]
                box = ((px >= ext[:, 0].min()) & (px <= ext[:, 0].max()) &
                       (py >= ext[:, 1].min()) & (py <= ext[:, 1].max()))
                if box.any():
                    sub = np.zeros(px.size, dtype=bool)
                    sub[box] = ens.points_in_polygon(px[box], py[box], poly)
                    mask |= sub
        _LAND_CACHE[key] = mask.reshape(glat.shape)
    return _LAND_CACHE[key]


# --------------------------------------------------------------------------- acumulación
def subset_imerg(lat: np.ndarray, lon: np.ndarray, rate: np.ndarray):
    ri, ci, la, lo = ens.subset_bbox(np.asarray(lat, float), np.asarray(lon, float), ens.BBOX)
    return la, lo, np.asarray(rate, float)[np.ix_(ri, ci)]


class DayAccumulator:
    """Suma de un día pluviométrico; cada celda lleva cuántas medias horas válidas tiene."""

    def __init__(self, lat, lon, total=None, valid=None, granules=None):
        self.lat, self.lon = np.asarray(lat, float), np.asarray(lon, float)
        shape = (self.lat.size, self.lon.size)
        self.total = np.zeros(shape) if total is None else np.asarray(total, float)
        self.valid = np.zeros(shape, dtype=np.int16) if valid is None else np.asarray(valid, np.int16)
        self.granules = list(granules or [])

    def add(self, slot: str, lat, lon, rate_mm_h) -> bool:
        """Suma una media hora identificada por su inicio UTC (ISO); repetirla no cambia nada."""
        if slot in self.granules:
            return False
        if not (np.allclose(lat, self.lat) and np.allclose(lon, self.lon)):
            raise ValueError("grilla IMERG distinta dentro del mismo día")
        ok = np.isfinite(rate_mm_h) & (rate_mm_h >= 0)
        self.total += np.where(ok, rate_mm_h, 0.0) * 0.5
        self.valid += ok.astype(np.int16)
        self.granules.append(slot)
        return True

    @property
    def complete(self) -> bool:
        return len(self.granules) >= SLOTS_PER_DAY

    def field(self) -> np.ndarray:
        """Total diario (mm); NaN en celdas sin las 48 medias horas válidas."""
        out = self.total.copy()
        out[self.valid < SLOTS_PER_DAY] = np.nan
        return out

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        np.savez_compressed(buf, lat=self.lat, lon=self.lon, total=self.total.astype(np.float32), valid=self.valid,
                            granules=np.array(self.granules))
        path.write_bytes(buf.getvalue())

    @classmethod
    def load(cls, path: Path):
        with np.load(path, allow_pickle=False) as z:
            return cls(z["lat"], z["lon"], z["total"], z["valid"], [str(g) for g in z["granules"]])


# --------------------------------------------------------------------------- estadísticas por provincia
def province_rows(valid: date, field: np.ndarray, lat, lon, provinces: list[dict], land: np.ndarray | None = None
                  ) -> list[dict]:
    ela, elo = ens.ens_grid()
    land = land_mask(lat, lon) if land is None else land
    coarse = regrid_area_mean(field, lat, lon, ela, elo, land=land)
    a025 = ens.assign_cells(provinces, ela, elo)
    a01 = ens.assign_cells(provinces, np.asarray(lat), np.asarray(lon))
    cflat, fflat = coarse.ravel(), field.ravel()
    rows = []
    for p in provinces:
        c = cflat[a025[p["id"]]["idx"]]
        f = fflat[a01[p["id"]]["idx"]]
        complete = np.isfinite(c).all() and np.isfinite(f).all()
        fmt = lambda v: "" if not complete else f"{v:.2f}"  # noqa: E731 - incompleto = faltante, nunca cero
        rows.append(dict(fecha_peru=valid.isoformat(), idprov=p["id"], lluvia_max_mm=fmt(np.max(c)),
                         lluvia_media_mm=fmt(np.mean(c)), fuente=SOURCE_LABEL, n=str(c.size),
                         lluvia_max_nativo_mm=fmt(np.max(f)), celdas_025=str(c.size), celdas_01=str(f.size),
                         medias_horas=str(SLOTS_PER_DAY)))
    return rows


def write_csv(rows: list[dict], path: Path = OBS_CSV):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["fecha_peru"], r["idprov"]))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue()
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def rebuild_csv(provinces: list[dict]):
    rows = []
    for f in sorted(FIELDS_DIR.glob("*.npz")):
        acc = DayAccumulator.load(f)
        rows.extend(province_rows(date.fromisoformat(f.stem), acc.field(), acc.lat, acc.lon, provinces))
    write_csv(rows)
    return rows


# --------------------------------------------------------------------------- E/S (solo en el runner)
def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lookback", type=int, default=LOOKBACK_DAYS, help="días pluviométricos cerrados a completar")
    parser.add_argument("--max-downloads", type=int, default=MAX_DOWNLOADS)
    args = parser.parse_args(argv)
    geo_path, _ = ens.boundaries_paths()
    provinces = ens.load_provinces(geo_path)
    now = datetime.now(timezone.utc)
    if not os.getenv("EARTHDATA_TOKEN"):
        print("::warning title=V09_IMERG_LATE::sin EARTHDATA_TOKEN: nada capturado (no es lluvia cero)")
        return 0
    import earthaccess

    import probe_imerg_early_live as probe

    days = [d for d in candidate_days(now, args.lookback) if not (FIELDS_DIR / f"{d.isoformat()}.npz").is_file()]
    status = dict(state="AVAILABLE", checked_at_utc=now.isoformat(), product=f"{PRODUCT} v{VERSION}", days_pending=[])
    if days:
        start = rain_day_slots(days[0])[0]
        end = rain_day_slots(days[-1])[-1] + timedelta(minutes=30)
        try:
            import time

            for attempt, wait in enumerate((20, 60, None), start=1):  # contacto acotado con Earthdata
                try:
                    earthaccess.login(strategy="environment")
                    found = earthaccess.search_data(short_name=PRODUCT, version=VERSION,
                                                    temporal=(start.isoformat(), end.isoformat()))
                    status["contact_attempts"] = attempt
                    break
                except Exception:  # noqa: BLE001
                    if wait is None:
                        raise
                    time.sleep(wait)
        except Exception as exc:  # noqa: BLE001 - fuente no disponible, nunca lluvia cero
            status.update(state="SOURCE_UNREACHABLE", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
            STATUS_JSON.write_text(json.dumps(dict(**GUARDS, status=status), ensure_ascii=False, indent=1) + "\n",
                                   encoding="utf-8")
            print(f"::warning title=V09_IMERG_LATE::{status['error']}")
            return 0
        wanted = set(days)
        accs = {d: (DayAccumulator.load(PARTIAL_DIR / f"{d}.npz") if (PARTIAL_DIR / f"{d}.npz").is_file() else None)
                for d in days}
        by_slot = {}
        for ts, name, granule in probe.index_granules(found):
            d = rain_day_of(ts)
            slot = ts.isoformat()  # identidad = media hora, no nombre: dos versiones del mismo gránulo no suman dos veces
            if d in wanted and (accs[d] is None or slot not in accs[d].granules):
                by_slot[slot] = (ts, name, granule, d)  # el catálogo viene ordenado: queda la última versión listada
        todo = sorted(by_slot.values(), key=lambda r: r[0])[:args.max_downloads]  # el más antiguo primero: cierra días
        with tempfile.TemporaryDirectory(prefix="irfen_imerg_late_") as td:
            paths = earthaccess.download([r[2] for r in todo], local_path=td, threads=4, show_progress=False) if todo else []
            by_name = {Path(p).name: p for p in paths}
            for ts, name, _, d in todo:
                path = by_name.get(name)
                if path is None:
                    continue
                lat, lon, values, units = probe.read_grid(path)
                if not any(u in units.lower() for u in ("mm/hr", "mm h-1", "mm/hour")):
                    print(f"::warning title=V09_IMERG_LATE::{name}: unidades inesperadas {units!r}; descartado")
                    continue
                la, lo, sub = subset_imerg(lat, lon, values)
                if accs[d] is None:
                    accs[d] = DayAccumulator(la, lo)
                accs[d].add(ts.isoformat(), la, lo, sub)
        for d, acc in accs.items():
            if acc is None:
                status["days_pending"].append(dict(fecha_peru=d.isoformat(), medias_horas=0))
                continue
            if acc.complete:
                acc.save(FIELDS_DIR / f"{d}.npz")
                (PARTIAL_DIR / f"{d}.npz").unlink(missing_ok=True)
            else:
                acc.save(PARTIAL_DIR / f"{d}.npz")
                status["days_pending"].append(dict(fecha_peru=d.isoformat(), medias_horas=len(acc.granules)))
    rows = rebuild_csv(provinces)
    status["days_complete"] = sorted({r["fecha_peru"] for r in rows})
    STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(json.dumps(dict(schema_version="0.1", archive_id="irfen-v09-imerg-late-provinces:v0.1",
                                           **GUARDS, map_publishable=False, status=status,
                                           method=dict(rain_day="12:00 UTC D−1 → 12:00 UTC D (07:00–07:00 Perú)",
                                                       lluvia_max_mm="máximo de celdas 0,25° (media por área de IMERG)",
                                                       lluvia_max_nativo_mm="máximo de celdas IMERG 0,1°")),
                                      ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=V09_IMERG_LATE::días completos {len(status['days_complete'])}; "
          f"pendientes {[(x['fecha_peru'], x['medias_horas']) for x in status['days_pending']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
