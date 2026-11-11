#!/usr/bin/env python3
"""IRFEN v0.9 · instantánea de investigación para la vista privada de vigilancia (costa Tumbes–Tacna).
RESEARCH_ONLY / TEST_ONLY. No es una captura operativa: no toca las capturas meteorológicas de `main`.

Etapas (cada una deja registro; una sola pasada, sin reintentos en bucle):
* ``inei``: límites censales referenciales INEI servidos por SERFOR (mismo servicio ya usado en v0.9): departamentos y
  provincias de los 11 departamentos costeros, geometría simplificada por el propio servicio (maxAllowableOffset).
* ``imerg``: IMERG Early V07 (GPM_3IMERGHHE) de las últimas ~78 h disponibles en el catálogo sobre la costa
  (lon −81,5…−69,8; lat −18,6…−3,3). Se guardan las sumas por celda de 0,1° para 1, 3, 6, 24 y 72 h que terminan en la
  última media hora disponible; una ventana con alguna media hora ausente o celda sin dato queda NO_DISPONIBLE.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT_INEI = ROOT / "data/v09/sources/inei_coast_tumbes_tacna"
OUT_RAIN = ROOT / "data/v09/research/coast_rain/imerg_early_coast_snapshot_v0_1.json"
SERFOR = "https://geo.serfor.gob.pe/geoservicios/rest/services/Visor/Limites_Politicos_Administrativos/MapServer"
COAST = ["TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD", "ANCASH", "LIMA", "CALLAO", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"]
BOX = dict(lon_min=-81.5, lon_max=-69.8, lat_min=-18.6, lat_max=-3.3)
WINDOWS_H = [1, 3, 6, 24, 72]
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, operational_alerting_enabled=False,
              activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False)
UA = {"User-Agent": "IRFEN-research/0.9 (+https://github.com/IRFEN2026/irfen-peru)"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get(url: str, timeout=90) -> tuple[bytes | None, dict]:
    t0 = time.time()
    try:
        with urlopen(Request(url, headers=UA), timeout=timeout) as r:
            raw = r.read()
        return raw, dict(url=url, status="OK", bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), seconds=round(time.time() - t0, 1), at_utc=now())
    except Exception as e:  # noqa: BLE001
        return None, dict(url=url, status="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.time() - t0, 1), at_utc=now())


def stage_inei() -> dict:
    OUT_INEI.mkdir(parents=True, exist_ok=True)
    log = []
    raw, rec = get(SERFOR + "?f=pjson")
    log.append(rec)
    layers = {}
    if raw:
        meta = json.loads(raw)
        layers = {l["name"]: l["id"] for l in meta.get("layers", [])}
    res = dict(layers_seen=layers, requests=log)
    where = "NOMBDEP IN (" + ",".join(f"'{d}'" for d in COAST) + ")"
    for kind, guess in (("departamentos", ["Departamento_INEI", "Departamento", "Departamentos"]), ("provincias", ["Provincia_INEI", "Provincia"])):
        lid = next((layers[n] for n in guess if n in layers), 0 if kind == "departamentos" else 1)
        q = SERFOR + f"/{lid}/query?" + urlencode(dict(where=where, outFields="*", returnGeometry="true", outSR="4326",
                                                       maxAllowableOffset="0.002", geometryPrecision="5", f="geojson"))
        raw, rec = get(q, timeout=180)
        log.append(rec)
        if not raw:
            res[kind] = dict(status="ERROR", layer_id=lid)
            continue
        gj = json.loads(raw)
        if "error" in gj:
            res[kind] = dict(status="SERVICE_ERROR", layer_id=lid, error=gj["error"])
            continue
        (OUT_INEI / f"{kind}.geojson").write_bytes(raw)
        res[kind] = dict(status="OK", layer_id=lid, features=len(gj.get("features", [])), sha256=rec["sha256"],
                         departments=sorted({f["properties"].get("NOMBDEP") for f in gj.get("features", [])}))
    prov = dict(institution="INEI (límites censales referenciales), servidos por SERFOR", service_url=SERFOR,
                legal_status="REFERENTIAL_CENSUS_LIMITS_NOT_LEGAL_DEMARCATION", simplification="maxAllowableOffset=0.002° (servicio)",
                obtained_at_utc=now(), **res)
    (OUT_INEI / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return dict(status="OK" if all(res.get(k, {}).get("status") == "OK" for k in ("departamentos", "provincias")) else "PARCIAL",
                **{k: {x: v.get(x) for x in ("status", "features", "layer_id")} for k, v in res.items() if k in ("departamentos", "provincias")})


def _cap():
    spec = importlib.util.spec_from_file_location("cap", ROOT / "scripts/v09_imerg_final_daily_capture.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BOX = BOX
    return m


def stage_imerg() -> dict:
    import earthaccess
    import numpy as np
    if not os.getenv("EARTHDATA_TOKEN"):
        return dict(status="SIN_TOKEN")
    cap = _cap()
    earthaccess.login(strategy="environment")
    t_end = datetime.now(timezone.utc)
    found = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07",
                                    temporal=((t_end - timedelta(hours=100)).strftime("%Y-%m-%dT%H:%M:%S"), t_end.strftime("%Y-%m-%dT%H:%M:%S")), count=400)
    rows = {}
    for g in found:
        name = Path(g.data_links()[0].split("?", 1)[0]).name
        try:
            d, s = name.split(".3IMERG.")[1].split("-S")[0], name.split("-S")[1][:6]
            start = datetime.strptime(d + s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            continue
        if start not in rows or name > rows[start][0]:
            rows[start] = (name, g)
    if not rows:
        return dict(status="SIN_GRANULOS_EN_CATALOGO", catalog=len(found))
    last = max(rows)
    need = [last - timedelta(minutes=30 * k) for k in range(0, 72 * 2 + 6)]  # 72 h + margin
    todo = [rows[t] for t in need if t in rows]
    grids, names = {}, {}
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="irfen_coast_") as td:
        for i in range(0, len(todo), 30):
            chunk = todo[i:i + 30]
            try:
                paths = earthaccess.download([c[1] for c in chunk], local_path=td, threads=8, show_progress=False)
            except Exception as e:  # noqa: BLE001
                print(f"::warning::download chunk failed: {type(e).__name__}")
                continue
            by = {Path(p).name: p for p in paths}
            for name, _ in chunk:
                p = by.get(name)
                if not p:
                    continue
                try:
                    r = cap.read(p)
                except Exception:  # noqa: BLE001
                    continue
                st = datetime.fromisoformat(r["time_utc"])
                arr = np.array([[np.nan if v is None else v for v in row] for row in r["values_lon_by_lat"]], float)
                grids[st] = arr
                names[st.isoformat()] = dict(granule=name, sha256=cap.sha256_file(p))
                lon, lat = r["lon"], r["lat"]
                os.remove(p)
    if not grids:
        return dict(status="DESCARGA_FALLIDA", catalog=len(found))
    end = last + timedelta(minutes=30)
    windows = {}
    for h in WINDOWS_H:
        slots = [last - timedelta(minutes=30 * k) for k in range(h * 2)]
        present = [s for s in slots if s in grids]
        complete = len(present) == len(slots)
        if complete:
            tot = sum(grids[s] * 0.5 for s in slots)  # mm/hr × 0.5 h
            vals = [[None if v != v else round(float(v), 2) for v in row] for row in tot]
        else:
            vals = None
        windows[f"{h}h"] = dict(hours=h, start_utc=(end - timedelta(hours=h)).isoformat(), end_utc=end.isoformat(),
                                half_hours_required=len(slots), half_hours_present=len(present),
                                status="COMPLETA" if complete else "NO_DISPONIBLE_FALTAN_MEDIAS_HORAS", sum_mm_lon_by_lat=vals)
    doc = dict(schema_version="irfen_v09_imerg_early_coast_snapshot_v0_1", **GUARDS,
               source=dict(product="GPM_3IMERGHHE", version="07", provider="NASA GES DISC via earthaccess",
                           nature="estimación satelital Early (latencia de horas); no es observación en tiempo real ni pluviómetro"),
               captured_at_utc=now(), latest_half_hour_start_utc=last.isoformat(), windows_end_utc=end.isoformat(),
               latency_hours_at_capture=round((datetime.now(timezone.utc) - end).total_seconds() / 3600, 1),
               box=BOX, cell_deg=0.1, lon=lon, lat=lat, windows=windows, granules=dict(sorted(names.items())),
               download_seconds=round(time.time() - t0, 1), catalog_granules_searched=len(found))
    OUT_RAIN.parent.mkdir(parents=True, exist_ok=True)
    OUT_RAIN.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return dict(status="OK", latest=last.isoformat(), granules=len(grids),
                windows={k: (v["half_hours_present"], v["half_hours_required"], v["status"]) for k, v in windows.items()})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["inei", "imerg"])
    a = ap.parse_args(argv)
    t0 = time.time()
    try:
        res = dict(inei=stage_inei, imerg=stage_imerg)[a.stage]()
    except Exception as e:  # noqa: BLE001
        res = dict(status="ERROR", error=f"{type(e).__name__}: {str(e)[:300]}")
    print(f"::notice title={a.stage}::{json.dumps(res, ensure_ascii=False)[:900]} runtime_s={round(time.time() - t0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
