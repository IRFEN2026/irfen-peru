#!/usr/bin/env python3
"""IRFEN v0.9 · validación histórica: IMERG Final V07 diario (GPM_3IMERGDF) sobre el norte del Perú.
RESEARCH_ONLY / TEST_ONLY. Runner con EARTHDATA_TOKEN. No toca capturas operativas ni el motor.

Para cada día UTC de los periodos pedidos guarda, de forma compacta y verificable:
* nombre, versión, SHA-256 y tamaño del gránulo; día declarado en el nombre y marca interna (`Grid/time` con la época
  que declaren sus unidades);
* unidades de `precipitation` y de `precipitation_cnt` (número de medias horas válidas por celda);
* los valores CRUDOS de todas las celdas de 0,1° del recuadro de Piura–Chira (lon −81,3…−79,1; lat −6,5…−3,3), para que
  cualquier media por polígono (UH ANA o cuenca hasta una estación) se pueda recalcular sin volver a descargar.
Un día que no se descarga o no se lee queda AUSENTE con su motivo (nunca 0 mm).

    EARTHDATA_TOKEN=… python scripts/v09_imerg_final_daily_capture.py --period 2017-01-01:2017-04-30 --period …
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/research/historical/imerg_final_daily_piura_chira_v0_1.json"
BOX = dict(lon_min=-81.3, lon_max=-79.1, lat_min=-6.5, lat_max=-3.3)
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None, map_publishable=False, used_by_rain_engine_or_priority=False)
NAME_RE = re.compile(r"3IMERG\.(\d{8})-S(\d{6})-E(\d{6})\.(V\d+[A-Z]?)\.nc4|3IMERG\.(\d{8})-S(\d{6})-E(\d{6})\.(V\d+[A-Z]?)", re.I)


def day_from_name(name: str) -> tuple[str | None, str | None]:
    m = re.search(r"3IMERG\.(\d{8})-S\d{6}-E\d{6}\.(V\d+[A-Z]?)", name, re.I)
    if not m:
        return None, None
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}", m.group(2).upper()


def epoch_value(units: str, value: float) -> str | None:
    m = re.match(r"(seconds|days) since (\d{4}-\d{2}-\d{2})[ T]?(\d{2}:\d{2}:\d{2})?", units or "")
    if not m:
        return None
    base = datetime.fromisoformat(f"{m.group(2)}T{m.group(3) or '00:00:00'}+00:00")
    return (base + (timedelta(seconds=float(value)) if m.group(1) == "seconds" else timedelta(days=float(value)))).isoformat()


def read(path: str) -> dict:
    import h5py
    import numpy as np
    with h5py.File(path, "r") as f:
        g = f["Grid"] if "Grid" in f else f
        p, cnt = g["precipitation"], g.get("precipitation_cnt")
        lat, lon = np.asarray(g["lat"][:]), np.asarray(g["lon"][:])
        dims = p.attrs.get("DimensionNames", b"")
        dims = dims.decode() if isinstance(dims, bytes) else str(dims)
        units = p.attrs.get("units", b"")
        units = units.decode() if isinstance(units, bytes) else str(units)
        t = g["time"]
        tu = t.attrs.get("units", b"")
        tu = tu.decode() if isinstance(tu, bytes) else str(tu)
        tval = float(np.asarray(t[:]).ravel()[0])
        i0, i1 = int(np.searchsorted(lon, BOX["lon_min"])), int(np.searchsorted(lon, BOX["lon_max"]))
        j0, j1 = int(np.searchsorted(lat, BOX["lat_min"])), int(np.searchsorted(lat, BOX["lat_max"]))
        shape = list(p.shape)
        if dims.startswith("time,lon,lat") or (len(shape) == 3 and shape[1] == lon.size):
            block = np.asarray(p[0, i0:i1, j0:j1], dtype=float)
            cblock = np.asarray(cnt[0, i0:i1, j0:j1], dtype=float) if cnt is not None else None
        else:
            raise RuntimeError(f"unexpected dims {dims} {shape}")
        cu = cnt.attrs.get("units", b"") if cnt is not None else b""
        return dict(units=units, dims=dims, shape=shape, time_units=tu, time_value=tval, time_utc=epoch_value(tu, tval),
                    fill_value=float(np.asarray(p.attrs.get("_FillValue", [np.nan])).ravel()[0]),
                    cnt_units=cu.decode() if isinstance(cu, bytes) else str(cu),
                    lon=[round(float(x), 3) for x in lon[i0:i1]], lat=[round(float(y), 3) for y in lat[j0:j1]],
                    values_lon_by_lat=[[None if (v != v or v < 0) else round(float(v), 3) for v in row] for row in block],
                    cnt_lon_by_lat=None if cblock is None else [[None if c != c else int(c) for c in row] for row in cblock])


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", action="append", required=True, help="YYYY-MM-DD:YYYY-MM-DD (inclusive, UTC days)")
    ap.add_argument("--budget-s", type=int, default=2400)
    a = ap.parse_args(argv)
    if not os.getenv("EARTHDATA_TOKEN"):
        print("::warning::EARTHDATA_TOKEN missing: nothing captured (not a zero-rain result)")
        return 0
    import earthaccess
    t0 = time.time()
    earthaccess.login(strategy="environment")
    doc = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else dict(
        schema_version="irfen_v09_imerg_final_daily_v0_1", **GUARDS, box=BOX,
        source=dict(product="GPM_3IMERGDF", version="07", provider="NASA GES DISC via earthaccess",
                    note="IMERG Final Run diario: día UTC 00:00–23:59:59; `precipitation` en mm/día; "
                         "`precipitation_cnt` = medias horas válidas por celda"),
        days={}, absent={}, searches=[])
    for per in a.period:
        start, end = per.split(":")
        found = earthaccess.search_data(short_name="GPM_3IMERGDF", version="07", temporal=(f"{start}T00:00:00", f"{end}T23:59:59"),
                                        count=400)
        rows = []
        for g in found:
            try:
                name = Path(g.data_links()[0].split("?", 1)[0]).name
            except Exception:  # noqa: BLE001
                continue
            day, ver = day_from_name(name)
            if day and start <= day <= end:
                rows.append((day, ver, name, g))
        by = {}
        dups = []
        for r in sorted(rows):
            if r[0] in by:
                dups.append(dict(day=r[0], kept=max(by[r[0]], r, key=lambda x: x[1])[2], dropped=min(by[r[0]], r, key=lambda x: x[1])[2]))
                by[r[0]] = max(by[r[0]], r, key=lambda x: x[1])
            else:
                by[r[0]] = r
        expected = [(date.fromisoformat(start) + timedelta(days=k)).isoformat()
                    for k in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
        doc["searches"].append(dict(period=per, catalog=len(found), in_period=len(rows), unique_days=len(by), expected_days=len(expected),
                                    duplicates=dups))
        for d in expected:
            if d not in by and d not in doc["days"]:
                doc["absent"][d] = "NO_EN_EL_CATALOGO"
        todo = [by[d] for d in expected if d in by and d not in doc["days"]]
        for i in range(0, len(todo), 15):
            if time.time() - t0 > a.budget_s:
                for r in todo[i:]:
                    doc["absent"][r[0]] = "PRESUPUESTO_DE_TIEMPO_AGOTADO"
                break
            chunk = todo[i:i + 15]
            with tempfile.TemporaryDirectory(prefix="irfen_imergdf_") as td:
                try:
                    paths = earthaccess.download([r[3] for r in chunk], local_path=td, threads=6, show_progress=False)
                except Exception as exc:  # noqa: BLE001
                    paths = []
                    print(f"::warning::download failed: {type(exc).__name__}: {str(exc)[:150]}")
                names = {Path(p).name: p for p in paths}
                for day, ver, name, _ in chunk:
                    path = names.get(name)
                    if not path:
                        doc["absent"][day] = "DESCARGA_FALLIDA"
                        continue
                    try:
                        r = read(path)
                    except Exception as exc:  # noqa: BLE001
                        doc["absent"][day] = f"LECTURA_FALLIDA: {str(exc)[:120]}"
                        continue
                    doc["days"][day] = dict(granule=name, version=ver, file_sha256=sha256_file(path), file_bytes=os.path.getsize(path), **r)
                    doc["absent"].pop(day, None)
            print(f"{per}: {min(i + 15, len(todo))}/{len(todo)} in {time.time() - t0:.0f}s", flush=True)
    doc["days"] = dict(sorted(doc["days"].items()))
    doc["absent"] = dict(sorted(doc["absent"].items()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    units = sorted({d["units"] for d in doc["days"].values()})
    vers = sorted({d["version"] for d in doc["days"].values()})
    print(f"::notice title=imerg_final_daily::days={len(doc['days'])} absent={len(doc['absent'])} units={units} versions={vers} "
          f"searches={json.dumps(doc['searches'])[:900]} runtime_s={round(time.time() - t0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
