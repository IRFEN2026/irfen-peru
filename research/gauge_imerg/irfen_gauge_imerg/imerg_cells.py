"""Extracción offline de la celda IMERG (0,1°) que contiene cada estación, desde archivos HDF5 ya descargados.

No descarga nada. Lee gránulos medio-horarios locales (V07, Early/Late/Final), comprueba la malla, las unidades, el
tiempo interno y el valor de relleno, y escribe una «serie de celdas» con linaje (SHA-256 de cada archivo).

* ``precipitation`` de IMERG HHR es una **tasa** en mm/h promediada en la media hora; el acumulado de la media hora es
  ``tasa × 0,5 h``. Cualquier otra unidad se rechaza (no se convierte por suposición).
* Valores negativos o iguales a ``_FillValue`` son FALTANTES (``None``), nunca cero.
* El orden de dimensiones se toma del atributo ``DimensionNames`` si existe; si no, se deduce solo cuando no es ambiguo.

Uso::

    python -m irfen_gauge_imerg.imerg_cells --stations estaciones.json --out celdas.json gránulos/*.HDF5
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import GUARDS, SCHEMA_VERSION
from .granules import iso, parse
from .grid import GridError, locate, neighbourhood, verify_axis

ACCEPTED_UNITS = {"mm/hr", "mm/h", "mm hr-1", "mm h-1", "mm/hour"}


class UnitError(ValueError):
    pass


class GranuleContentError(ValueError):
    pass


def normalise_units(raw) -> str:
    u = raw.decode(errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
    u = u.strip().lower()
    if u not in ACCEPTED_UNITS:
        raise UnitError(f"unidades {u!r} no aceptadas para IMERG HHR (se esperaba tasa en mm/h)")
    return "mm/hr"


def attr_str(v) -> str:
    """Atributo HDF5 como texto (bytes, numpy.bytes_, arreglos de un elemento o None)."""
    if v is None:
        return ""
    try:
        import numpy as np  # noqa: PLC0415 — opcional: solo existe cuando se leen HDF5 reales
        if isinstance(v, np.ndarray):
            v = v.ravel()[0] if v.size else ""
    except ImportError:
        pass
    return v.decode(errors="ignore") if isinstance(v, (bytes, bytearray)) else str(v)


_EPOCH_RE = re.compile(r"^\s*(seconds?|minutes?|hours?)\s+since\s+(\d{4}-\d{2}-\d{2})[ T]?(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?",
                       re.IGNORECASE)


def decode_time(value: float, units: str) -> datetime | None:
    """``<unidad> since <época>`` (CF) → datetime UTC; ``None`` si las unidades no se reconocen (no se adivina)."""
    m = _EPOCH_RE.match(units or "")
    if not m:
        return None
    epoch = datetime.fromisoformat(f"{m[2]}T{m[3] or '00:00:00'}").replace(tzinfo=timezone.utc)
    mult = {"s": 1, "m": 60, "h": 3600}[m[1][0].lower()]
    return epoch + timedelta(seconds=float(value) * mult)


def file_header_start(header: str) -> datetime | None:
    """``StartGranuleDateTime=…`` del atributo ``FileHeader`` de los HDF5 GPM; ``None`` si no está."""
    m = re.search(r"StartGranuleDateTime=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", header or "")
    return datetime.fromisoformat(m[1]).replace(tzinfo=timezone.utc) if m else None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def station_cells(stations: dict) -> dict:
    """``{id: {lat, lon, coordinate_verified, ...}}`` → celda, banderas y vecindad 3×3 de cada estación."""
    out = {}
    for sid, st in stations.items():
        cell, flags = locate(st["lat"], st["lon"])
        out[sid] = {"lat": float(st["lat"]), "lon": float(st["lon"]),
                    "coordinate_verified": bool(st.get("coordinate_verified", False)),
                    "coordinate_source": st.get("coordinate_source"),
                    "cell": cell.as_dict(), "location_flags": flags,
                    "neighbourhood": [[c.i, c.j] for c in neighbourhood(cell)]}
    return out


def _clean(v, fill) -> float | None:
    v = float(v)
    if not math.isfinite(v) or v < 0 or (fill is not None and abs(v - fill) < 1e-6):
        return None
    return v


def values_for_cells(getter, cells: dict, fill) -> dict:
    """``getter(i, j)`` → tasa cruda; devuelve centro y vecindad por estación con faltantes explícitos."""
    out = {}
    for sid, c in cells.items():
        center = _clean(getter(c["cell"]["i_lon"], c["cell"]["j_lat"]), fill)
        nb = [_clean(getter(i, j), fill) for i, j in c["neighbourhood"]]
        out[sid] = {"center_mm_hr": center, "nbhd_mm_hr": nb}
    return out


def extract_from_arrays(granule_name: str, lat, lon, field_lonlat, units_raw, fill, cells: dict,
                        internal_start_utc: datetime | None = None, sha256: str | None = None) -> dict:
    """Núcleo comprobable sin h5py: ``field_lonlat[n_lon][n_lat]`` sobre ejes (posiblemente recortados) lat/lon."""
    gid = parse(granule_name)
    units = normalise_units(units_raw)
    ax_lon, ax_lat = verify_axis(lon, "lon"), verify_axis(lat, "lat")
    flags = []
    if internal_start_utc is None:
        flags.append("INTERNAL_TIME_NOT_CHECKED")
    elif internal_start_utc != gid.start_utc:
        raise GranuleContentError(f"{gid.name}: tiempo interno {iso(internal_start_utc)} ≠ nombre {iso(gid.start_utc)}")

    def getter(i, j):
        li, lj = i - ax_lon["offset"], j - ax_lat["offset"]
        if not (0 <= li < ax_lon["size"] and 0 <= lj < ax_lat["size"]):
            raise GridError(f"celda ({i},{j}) fuera del recorte del archivo")
        return field_lonlat[li][lj]

    return {**gid.as_dict(), "family": gid.family, "units": units, "units_raw": str(units_raw),
            "sha256": sha256, "content_flags": flags, "values": values_for_cells(getter, cells, fill)}


def read_granule(path: Path, cells: dict) -> dict:
    import h5py  # dependencia solo para leer archivos reales
    import numpy as np

    with h5py.File(path, "r") as f:
        g = f["Grid"] if "Grid" in f else f
        for k in ("lat", "lon", "precipitation"):
            if k not in g:
                raise GranuleContentError(f"{path.name}: falta Grid/{k}")
        lat = np.asarray(g["lat"][:], dtype=float)
        lon = np.asarray(g["lon"][:], dtype=float)
        pd = g["precipitation"]
        dims = pd.attrs.get("DimensionNames")
        dims = dims.decode() if isinstance(dims, (bytes, bytearray)) else (str(dims) if dims is not None else None)
        shape = pd.shape
        if dims:
            names = [d.strip() for d in dims.split(",")]
            if len(names) != len(shape) or {"lat", "lon"} - set(names):
                raise GranuleContentError(f"{path.name}: DimensionNames {dims!r} incompatible con forma {shape}")
        elif shape[-2:] == (lon.size, lat.size) and lon.size != lat.size:
            names = (["time"] if len(shape) == 3 else []) + ["lon", "lat"]
        elif shape[-2:] == (lat.size, lon.size) and lon.size != lat.size:
            names = (["time"] if len(shape) == 3 else []) + ["lat", "lon"]
        else:
            raise GranuleContentError(f"{path.name}: no se puede determinar el orden de dimensiones {shape}")
        if "time" in names and shape[names.index("time")] != 1:
            raise GranuleContentError(f"{path.name}: se esperaba una sola media hora por archivo")
        fill = pd.attrs.get("_FillValue")
        fill = float(np.asarray(fill).ravel()[0]) if fill is not None else None
        units_raw = pd.attrs.get("units", "")
        internal = None
        if "time" in g:
            internal = decode_time(float(np.asarray(g["time"][:]).ravel()[0]), attr_str(g["time"].attrs.get("units")))
        if internal is None:
            internal = file_header_start(attr_str(f.attrs.get("FileHeader")))
        il, ia = names.index("lon"), names.index("lat")

        def raw(i_local, j_local):
            idx = [0] * len(shape)
            idx[il], idx[ia] = i_local, j_local
            return float(pd[tuple(idx)])

        class _Field:  # acceso perezoso: solo se leen las celdas necesarias
            def __getitem__(self, li):
                return _Row(li)

        class _Row:
            def __init__(self, li):
                self.li = li

            def __getitem__(self, lj):
                return raw(self.li, lj)

        return extract_from_arrays(path.name, lat, lon, _Field(), units_raw, fill, cells,
                                   internal_start_utc=internal, sha256=sha256_file(path))


def build_series(paths: list[Path], stations: dict, retrieval: dict | None = None) -> dict:
    cells = station_cells(stations)
    granules, errors = [], []
    for p in sorted(paths, key=lambda x: x.name):
        try:
            rec = read_granule(p, cells)
            if retrieval and p.name in retrieval:
                rec["retrieved_at_utc"] = retrieval[p.name]
            granules.append(rec)
        except Exception as exc:  # noqa: BLE001 — cada archivo defectuoso queda registrado, no se rellena
            errors.append({"file": p.name, "error": f"{type(exc).__name__}: {exc}"})
    return {"schema": "irfen.gauge_imerg.cell_series", "schema_version": SCHEMA_VERSION, "guards": GUARDS,
            "data_nature": "SATELLITE_ESTIMATE_NOT_GAUGE_OBSERVATION",
            "stations": cells, "granules": granules, "read_errors": errors,
            "provenance": {"tool": "irfen_gauge_imerg.imerg_cells", "files_seen": len(paths),
                           "extracted_at_utc": iso(datetime.now(timezone.utc))}}


def build_series_from_block(block_doc: dict, stations: dict) -> dict:
    """Serie de celdas a partir de un bloque regional ya extraído (``irfen.gauge_imerg.imerg_block``).

    Permite recuperar los gránulos una sola vez antes de conocer las coordenadas exactas: cada estación toma su celda
    y su vecindad del bloque. Una estación cuya vecindad sale del bloque se rechaza (no se rellena).
    """
    if block_doc.get("schema") != "irfen.gauge_imerg.imerg_block":
        raise GranuleContentError("documento no es un imerg_block")
    b = block_doc["block_global_indices"]
    cells = station_cells(stations)
    for sid, c in cells.items():
        for i, j in c["neighbourhood"]:
            if not (b["i0"] <= i < b["i1"] and b["j0"] <= j < b["j1"]):
                raise GridError(f"estación {sid}: celda ({i},{j}) fuera del bloque recuperado")
    lon = [round(-179.95 + 0.1 * i, 4) for i in range(b["i0"], b["i1"])]
    lat = [round(-89.95 + 0.1 * j, 4) for j in range(b["j0"], b["j1"])]
    granules, errors = [], []
    for g in block_doc.get("granules", []):
        try:
            internal = g.get("internal_start_utc")
            internal = datetime.fromisoformat(internal.replace("Z", "+00:00")) if internal else None
            field = [[-1.0 if v is None else v for v in row] for row in g["rates_mm_hr_lon_lat"]]
            rec = extract_from_arrays(g["granule"], lat, lon, field, g["units"], g.get("fill_value"), cells,
                                      internal_start_utc=internal, sha256=g.get("sha256"))
            for k in ("retrieved_at_utc", "url"):
                if g.get(k):
                    rec[k] = g[k]
            granules.append(rec)
        except Exception as exc:  # noqa: BLE001
            errors.append({"file": g.get("granule"), "error": f"{type(exc).__name__}: {exc}"})
    return {"schema": "irfen.gauge_imerg.cell_series", "schema_version": SCHEMA_VERSION, "guards": GUARDS,
            "data_nature": "SATELLITE_ESTIMATE_NOT_GAUGE_OBSERVATION",
            "stations": cells, "granules": granules, "read_errors": errors,
            "provenance": {"tool": "irfen_gauge_imerg.imerg_cells.build_series_from_block",
                           "block_granules": len(block_doc.get("granules", []))}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--block", type=Path, help="bloque regional ya extraído (en lugar de archivos HDF5)")
    ap.add_argument("--stations", required=True, type=Path, help="JSON {id: {lat, lon, coordinate_verified, ...}}")
    ap.add_argument("--retrieval", type=Path, help="JSON opcional {archivo: retrieved_at_utc} para medir latencia")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    stations = json.loads(a.stations.read_text(encoding="utf-8"))
    retrieval = json.loads(a.retrieval.read_text(encoding="utf-8")) if a.retrieval else None
    if a.block:
        doc = build_series_from_block(json.loads(a.block.read_text(encoding="utf-8")), stations)
    elif a.files:
        doc = build_series(a.files, stations, retrieval)
    else:
        ap.error("se requieren archivos HDF5 o --block")
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(doc['granules'])} gránulos leídos, {len(doc['read_errors'])} con error → {a.out}")


if __name__ == "__main__":
    main()
