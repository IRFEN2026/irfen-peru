#!/usr/bin/env python3
"""IRFEN v0.9 — Probabilidad de lluvia por provincia con el ensamble ECMWF (datos abiertos), TEST_ONLY.

Fase 0 del modelo predictivo a 72 h para El Niño 2026–2027 (costa norte). Corre en modo sombra: calcula y
archiva pronósticos para verificarlos después contra lluvia observada; no alimenta alertas ni el sitio público.

Qué hace, en cada corrida del ensamble (51 miembros: control + 50 perturbados):
* Descarga solo la precipitación total (``tp``) de ECMWF Open Data (licencia CC-BY-4.0) en los pasos necesarios.
* Arma tres ventanas de 24 h que cierran a las 12 UTC (07:00 hora de Perú), el mismo cierre del día pluviométrico
  de las estaciones convencionales de SENAMHI, para que pronóstico y observación sean comparables.
* Asigna las celdas de la grilla a cada provincia INEI (límites archivados en ``data/v09/admin_boundaries``): celdas
  cuyo centro cae dentro del polígono; si una provincia tiene menos de ``MIN_CELLS`` celdas, se usan las ``K_NEAREST``
  celdas más cercanas a su centroide y se declara el método. Nada de esto inventa precisión: se publica el número de
  celdas y el método por provincia.
* Para cada provincia, día y umbral calcula dos probabilidades (fracción de miembros):
    - ``p_mean``: la lluvia media de la provincia supera el umbral;
    - ``p_max``: alguna celda de la provincia supera el umbral (más cercano a "lluvia fuerte en algún punto").
* Lee el GRIB con eccodes, mensaje por mensaje.
* Archiva cada corrida en un registro JSONL de solo agregado y deja la última en un JSON con guardas TEST_ONLY.

Si la descarga falla, el estado queda ``UNAVAILABLE`` y no se escriben probabilidades: un dato faltante no es lluvia
cero (``missing_data_rule = UNKNOWN_NOT_LOW_RISK``).

  python scripts/v09_ecmwf_ens_north.py                 # corrida más reciente disponible
  python scripts/v09_ecmwf_ens_north.py --grib f.grib2  # procesar un archivo ya descargado
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data/v09/forecast"
LATEST_OUT = OUT_DIR / "ecmwf_ens_provinces_north_v0_1.json"
LEDGER_OUT = OUT_DIR / "ecmwf_ens_provinces_ledger_v0_1.jsonl"
BOUNDARIES_POINTER = ROOT / "data/v09/admin_boundaries/latest.json"

PROCESSING_VERSION = "0.1"
DEPARTMENTS = ("TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD")
THRESHOLDS_MM = (10.0, 25.0, 50.0)
N_DAYS = 3
CLOSE_HOUR_UTC = 12  # 07:00 en Perú (UTC−5): cierre del día pluviométrico de SENAMHI
BBOX = dict(lat_min=-9.6, lat_max=-3.0, lon_min=-81.7, lon_max=-76.6)  # 4 departamentos con margen de 1 celda
MIN_CELLS = 3
K_NEAREST = 4
SOURCES = ("azure", "aws", "ecmwf")  # réplicas en la nube primero (Azure fue la más rápida en la primera prueba)
SOURCE_TIMEOUT_S = 360
ATTRIBUTION = "Adaptado de ECMWF Open Data (IFS ENS), ECMWF, licencia CC BY 4.0, https://data.ecmwf.int/forecasts/"

GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)


# --------------------------------------------------------------------------- utilidades
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


def norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.upper().split())


# --------------------------------------------------------------------------- geometría (solo numpy)
def _rings_of(geometry: dict) -> list[list[np.ndarray]]:
    """Lista de polígonos; cada polígono es [anillo exterior, huecos...] como arrays (n, 2) lon/lat."""
    kind, coords = geometry["type"], geometry["coordinates"]
    polys = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else None
    if polys is None:
        raise ValueError(f"geometría no soportada: {kind}")
    return [[np.asarray(ring, dtype=float)[:, :2] for ring in poly] for poly in polys]


def ring_area_centroid(ring: np.ndarray) -> tuple[float, float, float]:
    x, y = ring[:, 0], ring[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    a = cross.sum() / 2.0
    if abs(a) < 1e-15:
        return 0.0, float(x.mean()), float(y.mean())
    return abs(a), float(((x + x1) * cross).sum() / (6 * a)), float(((y + y1) * cross).sum() / (6 * a))


def points_in_polygon(px: np.ndarray, py: np.ndarray, polygon: list[np.ndarray]) -> np.ndarray:
    """Regla par-impar sobre todos los anillos de un polígono (los huecos se excluyen solos)."""
    inside = np.zeros(px.shape, dtype=bool)
    for ring in polygon:
        xs, ys = ring[:, 0], ring[:, 1]
        xj, yj = np.roll(xs, 1), np.roll(ys, 1)
        for xa, ya, xb, yb in zip(xs, ys, xj, yj):
            if ya == yb:
                continue
            crosses = (ya > py) != (yb > py)
            x_cut = (xb - xa) * (py - ya) / (yb - ya) + xa
            inside ^= crosses & (px < x_cut)
    return inside


def load_provinces(geojson_path: Path, departments=DEPARTMENTS) -> list[dict]:
    data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
    wanted = {norm(d) for d in departments}
    out = []
    for feat in data["features"]:
        props = feat.get("properties") or {}
        dept = norm(props.get("NOMBDEP"))
        if dept not in wanted:
            continue
        polygons = _rings_of(feat["geometry"])
        area, cx, cy = max(ring_area_centroid(p[0]) for p in polygons)
        out.append(dict(id=str(props.get("IDPROV") or f"{dept}|{norm(props.get('NOMBPROV'))}"),
                        name=norm(props.get("NOMBPROV")), department=dept, polygons=polygons,
                        centroid=(cx, cy), area_deg2=area))
    if not out:
        raise ValueError("ninguna provincia de los departamentos pedidos en el archivo de límites")
    ids = [p["id"] for p in out]
    if len(set(ids)) != len(ids):
        raise ValueError("IDPROV duplicado en los límites provinciales")
    return sorted(out, key=lambda p: p["id"])


def assign_cells(provinces: list[dict], lats: np.ndarray, lons: np.ndarray,
                 min_cells: int = MIN_CELLS, k_nearest: int = K_NEAREST) -> dict[str, dict]:
    """Índices planos (fila-lat, columna-lon) de las celdas de cada provincia y el método usado."""
    glon, glat = np.meshgrid(lons, lats)
    px, py = glon.ravel(), glat.ravel()
    masks = {}
    for prov in provinces:
        mask = np.zeros(px.shape, dtype=bool)
        for poly in prov["polygons"]:
            ext = poly[0]
            box = ((px >= ext[:, 0].min()) & (px <= ext[:, 0].max()) &
                   (py >= ext[:, 1].min()) & (py <= ext[:, 1].max()))
            if box.any():
                sub = np.zeros(px.shape, dtype=bool)
                sub[box] = points_in_polygon(px[box], py[box], poly)
                mask |= sub
        masks[prov["id"]] = mask
    # Para el respaldo se prefieren celdas en tierra (dentro de alguna provincia cargada): en provincias costeras
    # pequeñas las celdas más cercanas pueden caer sobre el mar, cuya lluvia con mar cálido no es la de la provincia.
    land = np.zeros(px.shape, dtype=bool)
    for mask in masks.values():
        land |= mask
    out = {}
    for prov in provinces:
        idx = np.flatnonzero(masks[prov["id"]])
        method = "CELL_CENTRE_IN_POLYGON"
        if idx.size < min_cells:
            cx, cy = prov["centroid"]
            d2 = ((px - cx) * math.cos(math.radians(cy))) ** 2 + (py - cy) ** 2
            candidates = np.flatnonzero(land) if land.sum() >= k_nearest else np.arange(px.size)
            nearest = candidates[np.argsort(d2[candidates], kind="stable")[:k_nearest]]
            idx = np.unique(np.concatenate([idx, nearest]))
            method = f"NEAREST_{k_nearest}_LAND_CELLS_TO_CENTROID (provincia con menos de {min_cells} celdas)"
        out[prov["id"]] = dict(idx=idx, method=method)
    return out


# --------------------------------------------------------------------------- ventanas y probabilidades
def day_windows(run_hour: int, n_days: int = N_DAYS, close_hour: int = CLOSE_HOUR_UTC) -> list[tuple[int, int]]:
    """Pasos (h) de inicio y fin de cada ventana de 24 h que cierra a ``close_hour`` UTC.

    La primera ventana cierra en el primer ``close_hour`` que esté al menos 24 h después de la corrida, para que
    el día 1 sea un pronóstico completo: corrida 12 UTC → (0,24); 00 UTC → (12,36); 06 UTC → (6,30); 18 UTC → (18,42).
    """
    first_end = 24 + (close_hour - run_hour) % 24
    return [(first_end - 24 + 24 * i, first_end + 24 * i) for i in range(n_days)]


def daily_totals_mm(tp_m: np.ndarray, steps_h, windows) -> list[np.ndarray]:
    """Acumulado de cada ventana en mm, por miembro y celda. ``tp_m`` es acumulado desde el inicio, en metros."""
    pos = {int(s): i for i, s in enumerate(steps_h)}
    zeros = np.zeros(tp_m.shape[:1] + tp_m.shape[2:])
    out = []
    for start, end in windows:
        if end not in pos or (start != 0 and start not in pos):
            raise ValueError(f"faltan pasos {start}/{end} h en el pronóstico")
        a = zeros if start == 0 else tp_m[:, pos[start]]
        out.append(np.clip((tp_m[:, pos[end]] - a) * 1000.0, 0.0, None))
    return out


def province_stats(day_mm: np.ndarray, assignment: dict[str, dict], thresholds=THRESHOLDS_MM) -> dict[str, dict]:
    """``day_mm`` [miembro, lat, lon] → probabilidades por provincia (fracción de miembros, 3 decimales)."""
    flat = day_mm.reshape(day_mm.shape[0], -1)
    stats = {}
    for pid, a in assignment.items():
        vals = flat[:, a["idx"]]
        areal_mean, areal_max = vals.mean(axis=1), vals.max(axis=1)
        stats[pid] = dict(
            p_mean={f"{u:g}": round(float((areal_mean >= u).mean()), 3) for u in thresholds},
            p_max={f"{u:g}": round(float((areal_max >= u).mean()), 3) for u in thresholds},
            q50_mean_mm=round(float(np.median(areal_mean)), 1),
            q90_max_mm=round(float(np.percentile(areal_max, 90)), 1),
        )
    return stats


def subset_bbox(lats: np.ndarray, lons: np.ndarray, bbox: dict = BBOX):
    lons = np.where(lons > 180, lons - 360, lons)
    ri = np.flatnonzero((lats >= bbox["lat_min"]) & (lats <= bbox["lat_max"]))
    ci = np.flatnonzero((lons >= bbox["lon_min"]) & (lons <= bbox["lon_max"]))
    if ri.size == 0 or ci.size == 0:
        raise ValueError("la grilla no cubre la caja de la costa norte")
    return ri, ci, lats[ri], lons[ci]


def build_run_record(run_utc: datetime, tp_m: np.ndarray, steps_h, lats, lons, provinces: list[dict],
                     n_days: int = N_DAYS, thresholds=THRESHOLDS_MM) -> dict:
    """Registro completo de una corrida. ``tp_m`` [miembro, paso, lat, lon] ya recortado a ``lats``/``lons``."""
    windows = day_windows(run_utc.hour, n_days)
    totals = daily_totals_mm(tp_m, steps_h, windows)
    assignment = assign_cells(provinces, np.asarray(lats), np.asarray(lons))
    grid = float(np.median(np.abs(np.diff(lats)))) if len(lats) > 1 else None
    days_meta, per_day = [], []
    for d, ((s, e), mm) in enumerate(zip(windows, totals), start=1):
        end = run_utc + timedelta(hours=e)
        days_meta.append(dict(day=d, step_start_h=s, step_end_h=e,
                              start_utc=(run_utc + timedelta(hours=s)).isoformat(), end_utc=end.isoformat(),
                              valid_date_peru=(end - timedelta(hours=5)).date().isoformat()))
        per_day.append(province_stats(mm, assignment, thresholds))
    provs = {}
    for prov in provinces:
        pid = prov["id"]
        provs[pid] = dict(name=prov["name"], department=prov["department"], cells=int(assignment[pid]["idx"].size),
                          method=assignment[pid]["method"],
                          days=[dict(day=d + 1, **per_day[d][pid]) for d in range(n_days)])
    return dict(run_utc=run_utc.isoformat(), processing_version=PROCESSING_VERSION, members=int(tp_m.shape[0]),
                grid_deg=grid, thresholds_mm=[float(u) for u in thresholds], days=days_meta, provinces=provs)


# --------------------------------------------------------------------------- E/S de ECMWF (solo en el runner)
def _alarm(seconds: int):
    import signal

    def handler(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"réplica sin respuesta completa en {seconds} s")

    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)


def latest_run_and_download(target: Path, sources=SOURCES, n_days: int = N_DAYS,
                            timeout_s: int = SOURCE_TIMEOUT_S) -> tuple[datetime, str]:
    import signal

    from ecmwf.opendata import Client

    errors = []
    for source in sources:
        try:
            Path(target).unlink(missing_ok=True)  # nunca mezclar restos de una réplica fallida
            _alarm(timeout_s)
            client = Client(source=source)
            run = client.latest(stream="enfo", type="pf", param="tp", step=96)
            steps = sorted({s for w in day_windows(run.hour, n_days) for s in w if s > 0})
            client.retrieve(date=run.strftime("%Y%m%d"), time=run.hour, stream="enfo", type=["cf", "pf"],
                            param="tp", step=steps, target=str(target))
            return run.replace(tzinfo=timezone.utc), source
        except Exception as exc:  # noqa: BLE001 - se prueba la siguiente réplica y se reporta todo
            errors.append(f"{source}: {type(exc).__name__}: {str(exc)[:160]}")
            print(f"::warning title=V09_ECMWF_ENS::réplica {errors[-1]}")
        finally:
            signal.alarm(0)
    raise RuntimeError("; ".join(errors))


def assemble_members(fields: dict) -> tuple[np.ndarray, list[int], list[int]]:
    """{(miembro, paso_h): campo 2D} → array [miembro, paso, lat, lon]; exige la malla completa miembro × paso."""
    members = sorted({m for m, _ in fields})
    steps = sorted({s for _, s in fields})
    missing = [(m, s) for m in members for s in steps if (m, s) not in fields]
    if missing:
        raise ValueError(f"faltan {len(missing)} campos miembro×paso, p. ej. {missing[:3]}")
    return np.stack([np.stack([fields[(m, s)] for s in steps]) for m in members]).astype(float), members, steps


def read_grib(path: Path, bbox: dict = BBOX):
    """Lee ``tp`` de control y perturbados con eccodes → (corrida UTC, tp_m [miembro, paso, lat, lon], pasos_h, lats, lons).

    Se recorren los mensajes uno a uno; la latitud y longitud de cada punto se toman del propio mensaje, en el mismo
    orden que los valores, para no depender de la dirección de barrido de la grilla.
    """
    import eccodes

    fields, inventory, run, ri, ci, lats, lons, shape = {}, [], None, None, None, None, None, None
    with open(path, "rb") as fh:
        while True:
            gid = eccodes.codes_grib_new_from_file(fh)
            if gid is None:
                break
            try:
                short = eccodes.codes_get(gid, "shortName")
                if len(inventory) < 6:
                    inventory.append(f"{eccodes.codes_get(gid, 'dataType')}/{short}/{eccodes.codes_get(gid, 'stepRange')}")
                if short != "tp":
                    continue
                if shape is None:
                    shape = (eccodes.codes_get(gid, "Nj"), eccodes.codes_get(gid, "Ni"))
                    lat2 = np.asarray(eccodes.codes_get_array(gid, "latitudes"), float).reshape(shape)
                    lon2 = np.asarray(eccodes.codes_get_array(gid, "longitudes"), float).reshape(shape)
                    ri, ci, lats, lons = subset_bbox(lat2[:, 0], lon2[0, :], bbox)
                    date, hhmm = eccodes.codes_get(gid, "dataDate"), eccodes.codes_get(gid, "dataTime")
                    run = datetime.strptime(f"{date}{int(hhmm):04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                values = np.asarray(eccodes.codes_get_values(gid), float).reshape(shape)
                key = (int(eccodes.codes_get(gid, "number")), int(eccodes.codes_get(gid, "endStep")))
                fields[key] = values[np.ix_(ri, ci)]
            finally:
                eccodes.codes_release(gid)
    if not fields:
        raise ValueError(f"el GRIB no contiene 'tp'; primeros mensajes: {inventory}")
    tp_m, members, steps = assemble_members(fields)
    return run, tp_m, steps, lats, lons


# --------------------------------------------------------------------------- archivo
def append_ledger(record: dict, path: Path = LEDGER_OUT) -> bool:
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("run_utc") == record["run_utc"]:
                return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    return True


def boundaries_paths() -> tuple[Path, dict]:
    ptr = load(BOUNDARIES_POINTER)
    if not ptr:
        raise FileNotFoundError("falta data/v09/admin_boundaries/latest.json")
    return ROOT / ptr["path"], dict(sha256=ptr["sha256"], provenance=ptr["provenance"])


def latest_document(status: dict, record: dict | None, boundaries: dict) -> dict:
    return dict(schema_version="0.1", archive_id="irfen-v09-ecmwf-ens-provinces-north:v0.1", **GUARDS,
                map_publishable=False,
                source=dict(product="ECMWF IFS ENS, precipitación total (tp), datos abiertos",
                            members="control + 50 perturbados", attribution=ATTRIBUTION,
                            nature="pronóstico numérico crudo, sin calibrar con observaciones peruanas"),
                method=dict(windows=f"3 ventanas de 24 h que cierran a las {CLOSE_HOUR_UTC} UTC (07:00 Perú)",
                            p_mean="fracción de miembros con lluvia media provincial ≥ umbral",
                            p_max="fracción de miembros con alguna celda de la provincia ≥ umbral",
                            cell_assignment=f"centro de celda dentro del polígono; < {MIN_CELLS} celdas → "
                                            f"{K_NEAREST} celdas en tierra más cercanas al centroide"),
                boundaries=boundaries, status=status, latest_run=record,
                generated_at_utc=datetime.now(timezone.utc).isoformat())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--grib", type=Path, help="procesar un GRIB ya descargado en lugar de descargar")
    parser.add_argument("--workdir", type=Path, default=Path("."), help="carpeta temporal para el GRIB")
    args = parser.parse_args(argv)

    geo_path, boundaries = boundaries_paths()
    provinces = load_provinces(geo_path)
    previous = load(LATEST_OUT)
    try:
        source = "archivo local"
        grib = args.grib
        if grib is None:
            grib = args.workdir / "ecmwf_ens_tp.grib2"
            _, source = latest_run_and_download(grib)
        run, tp_m, steps, lats, lons = read_grib(grib)
        if previous and (previous.get("latest_run") or {}).get("run_utc") == run.isoformat() \
                and (previous.get("latest_run") or {}).get("processing_version") == PROCESSING_VERSION:
            print(f"::notice title=V09_ECMWF_ENS::corrida {run.isoformat()} ya procesada")
            return 0
        record = build_run_record(run, tp_m, steps, lats, lons, provinces)
    except Exception as exc:  # noqa: BLE001 - la falla se archiva como UNAVAILABLE, nunca como lluvia cero
        msg = f"{type(exc).__name__}: {str(exc)[:400]}"
        status = dict(state="UNAVAILABLE", error=msg, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                      last_good_run_utc=(previous or {}).get("status", {}).get("last_good_run_utc"))
        write_if_changed(LATEST_OUT, latest_document(status, None, boundaries),
                         volatile=("generated_at_utc",))
        print(f"::warning title=V09_ECMWF_ENS::sin pronóstico: {msg}")
        return 1
    appended = append_ledger(record)
    status = dict(state="AVAILABLE", source_mirror=source, last_good_run_utc=record["run_utc"],
                  provinces=len(record["provinces"]), appended_to_ledger=appended)
    write_if_changed(LATEST_OUT, latest_document(status, record, boundaries), volatile=("generated_at_utc",))
    top = sorted(((p["days"][-1]["p_max"]["10"], p["name"]) for p in record["provinces"].values()), reverse=True)[:5]
    print(f"::notice title=V09_ECMWF_ENS::corrida {record['run_utc']}; {len(record['provinces'])} provincias; "
          f"mayor P(≥10 mm en alguna celda, día 3): " + ", ".join(f"{n} {p:.0%}" for p, n in top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
