#!/usr/bin/env python3
"""IRFEN v0.9 · captura acotada para la viabilidad de la anticipación de crecidas. RESEARCH_ONLY / TEST_ONLY.

Etapas independientes (cada una deja registro aunque falle; nunca reintenta en bucle):
* ``hydrosheds``: HydroSHEDS v1 15″ DIR/ACC y HydroRIVERS recortados a las cuencas binacionales Puyango-Tumbes y
  Catamayo-Chira (lon −81,4…−78,8; lat −6,6…−3,0). Mismas URL que la captura de #459; se comprueba el SHA-256 del zip.
* ``ana_tumbes``: UNA consulta a la capa 2 del servicio ANA «Capas_Inundacion_Tumbes_04052023» (cuenca del río
  Tumbes) para saber si representa la cuenca binacional o solo el lado peruano.
* ``imerg_cmr``: recuento de gránulos IMERG V07 de 30 min (Final HH, Early HHE) y sus tamaños declarados en CMR para
  las ventanas 2017 y 2023. No descarga nada.
* ``imerg_pilot``: piloto de UN día UTC (2017-03-26: 48 gránulos Final HH y 48 Early HHE) para medir coste real
  (bytes, segundos) y comprobar la coherencia con el diario Final ya archivado. Guarda las celdas crudas del recuadro.

Sin SENAMHI, sin PECHP, sin GORE Piura (robots / prohibiciones). Sin umbrales.
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
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT_HS = ROOT / "data/v09/sources/hydrosheds_binational"
OUT_DIR = ROOT / "data/v09/research/anticipation"
BOX_BIN = (-81.4, -6.6, -78.8, -3.0)  # lon_min, lat_min, lon_max, lat_max
IMERG_BOX = dict(lon_min=-81.4, lon_max=-78.8, lat_min=-6.6, lat_max=-3.0)
WINDOWS = {"2017_avenida": ("2017-01-01", "2017-04-30"), "2023_avenida": ("2023-02-01", "2023-05-31")}
PILOT_DAY = "2017-03-26"
ANA_TUMBES = "https://geosnirh.ana.gob.pe/server/rest/services/Inundacion_Tumbes/Capas_Inundacion_Tumbes_04052023/MapServer/2"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, operational_alerting_enabled=False,
              activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None)
UA = {"User-Agent": "IRFEN-research/0.9 (+https://github.com/IRFEN2026/irfen-peru)"}


def _mod(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log_path(stage: str) -> Path:
    return OUT_DIR / f"capture_{stage}_v0_1.json"


def stage_hydrosheds() -> dict:
    hs = _mod("hs", "scripts/v09_hydrosheds_capture.py")
    hs.BOX = BOX_BIN
    hs.OUT = OUT_HS
    OUT_HS.mkdir(parents=True, exist_ok=True)
    prev = json.loads((ROOT / "data/v09/sources/hydrosheds_piura/provenance.json").read_text(encoding="utf-8"))
    res = dict(box=list(BOX_BIN), provenance="HydroSHEDS v1 (Lehner et al. 2008), derivado de SRTM; NO es cartografía oficial",
               licence_page="https://www.hydrosheds.org/terms-of-use")
    for key in ("dir15", "acc15", "rivers"):
        url = prev["chosen"][key]
        z = hs.fetch(url, timeout=900)
        if z is None:
            res[key] = dict(url=url, status="DESCARGA_FALLIDA")
            continue
        sha = hashlib.sha256(z).hexdigest()
        same = sha == prev[key]["zip_sha256"]
        if key == "rivers":
            meta = hs.crop_vector(z, key, ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "UPLAND_SKM", "DIS_AV_CMS", "ORD_STRA"])
        else:
            meta = hs.crop_raster(z, key)
        res[key] = dict(url=url, zip_sha256=sha, same_release_as_pr459=same, **meta)
        del z
    res["requests"] = hs.LOG
    (OUT_HS / "provenance.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return dict(status="OK" if all(res.get(k, {}).get("status") == "OK" for k in ("dir15", "acc15")) else "PARCIAL",
                files=sorted(p.name for p in OUT_HS.iterdir()))


def stage_ana_tumbes() -> dict:
    rec: dict = dict(url=ANA_TUMBES, at_utc=now())
    try:
        with urlopen(Request(ANA_TUMBES + "?f=pjson", headers=UA), timeout=60) as r:
            meta = json.loads(r.read().decode("utf-8", "replace"))
        rec["layer"] = {k: meta.get(k) for k in ("name", "type", "geometryType", "extent", "description", "copyrightText")}
        q = ANA_TUMBES + "/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson"
        with urlopen(Request(q, headers=UA), timeout=90) as r:
            raw = r.read()
        rec.update(query_url=q, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        gj = json.loads(raw.decode("utf-8", "replace"))
        if "error" in gj:
            rec["status"] = "SERVICE_ERROR"
            rec["error"] = gj["error"]
        else:
            rec["status"] = "OK"
            rec["features"] = len(gj.get("features", []))
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUT_DIR / "ana_tumbes_basin_layer2.geojson").write_bytes(raw)
    except Exception as e:  # noqa: BLE001
        rec.update(status="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}")
    return rec


def _granule_rows(found) -> list[dict]:
    rows = []
    for g in found:
        try:
            link = g.data_links()[0]
            name = Path(link.split("?", 1)[0]).name
        except Exception:  # noqa: BLE001
            continue
        try:
            mb = float(g.size())
        except Exception:  # noqa: BLE001
            mb = None
        rows.append(dict(name=name, size_mb=mb, link=link))
    return rows


def stage_imerg_cmr() -> dict:
    import earthaccess
    if not os.getenv("EARTHDATA_TOKEN"):
        return dict(status="SIN_TOKEN")
    earthaccess.login(strategy="environment")
    out = dict(at_utc=now(), products={})
    for short in ("GPM_3IMERGHH", "GPM_3IMERGHHE", "GPM_3IMERGHHL"):
        out["products"][short] = {}
        for wid, (a, b) in WINDOWS.items():
            t0 = time.time()
            try:
                found = earthaccess.search_data(short_name=short, version="07", temporal=(f"{a}T00:00:00", f"{b}T23:59:59"), count=-1)
                rows = _granule_rows(found)
                sizes = [r["size_mb"] for r in rows if r["size_mb"] is not None]
                from datetime import date
                exp = ((date.fromisoformat(b) - date.fromisoformat(a)).days + 1) * 48
                out["products"][short][wid] = dict(window=[a, b], granules=len(rows), expected_half_hours=exp,
                                                   total_mb_declared=round(sum(sizes), 1) if sizes else None,
                                                   median_mb=round(sorted(sizes)[len(sizes) // 2], 2) if sizes else None,
                                                   first=rows[0]["name"] if rows else None, last=rows[-1]["name"] if rows else None,
                                                   search_seconds=round(time.time() - t0, 1),
                                                   link_hosts=sorted({r["link"].split("/")[2] for r in rows})[:3])
            except Exception as e:  # noqa: BLE001
                out["products"][short][wid] = dict(status="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}")
    out["status"] = "OK"
    return out


def stage_imerg_pilot() -> dict:
    import earthaccess
    if not os.getenv("EARTHDATA_TOKEN"):
        return dict(status="SIN_TOKEN")
    cap = _mod("cap", "scripts/v09_imerg_final_daily_capture.py")
    cap.BOX = IMERG_BOX
    earthaccess.login(strategy="environment")
    res = dict(at_utc=now(), day=PILOT_DAY, box=IMERG_BOX, products={})
    for short in ("GPM_3IMERGHH", "GPM_3IMERGHHE"):
        t0 = time.time()
        found = earthaccess.search_data(short_name=short, version="07", temporal=(f"{PILOT_DAY}T00:00:00", f"{PILOT_DAY}T23:59:59"), count=100)
        found = [g for g in found if f".{PILOT_DAY.replace('-', '')}-S" in Path(g.data_links()[0].split("?", 1)[0]).name]
        slots, absent = {}, []
        nbytes = 0
        with tempfile.TemporaryDirectory(prefix="irfen_hh_") as td:
            try:
                paths = earthaccess.download(found, local_path=td, threads=6, show_progress=False)
            except Exception as e:  # noqa: BLE001
                paths = []
                res["products"][short] = dict(status="DESCARGA_FALLIDA", error=f"{type(e).__name__}: {str(e)[:200]}")
                continue
            dl_s = round(time.time() - t0, 1)
            for p in sorted(paths):
                name = Path(p).name
                try:
                    r = cap.read(p)
                except Exception as e:  # noqa: BLE001
                    absent.append(dict(name=name, reason=f"LECTURA_FALLIDA: {str(e)[:100]}"))
                    continue
                nbytes += os.path.getsize(p)
                start = name.split("-S")[1][:6]
                slots[start] = dict(granule=name, file_sha256=cap.sha256_file(p), file_bytes=os.path.getsize(p),
                                    units=r["units"], time_utc=r["time_utc"], lon=r["lon"], lat=r["lat"],
                                    values_lon_by_lat=r["values_lon_by_lat"])
        res["products"][short] = dict(status="OK", granules_found=len(found), slots_read=len(slots), absent=absent,
                                      download_seconds=dl_s, total_bytes=nbytes, slots=dict(sorted(slots.items())))
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["hydrosheds", "ana_tumbes", "imerg_cmr", "imerg_pilot"])
    a = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    fn = dict(hydrosheds=stage_hydrosheds, ana_tumbes=stage_ana_tumbes, imerg_cmr=stage_imerg_cmr, imerg_pilot=stage_imerg_pilot)[a.stage]
    try:
        res = fn()
    except Exception as e:  # noqa: BLE001
        res = dict(status="ERROR", error=f"{type(e).__name__}: {str(e)[:300]}")
    doc = dict(schema_version="irfen_v09_anticipation_capture_v0_1", stage=a.stage, **GUARDS, finished_at_utc=now(),
               runtime_s=round(time.time() - t0, 1), result=res)
    log_path(a.stage).write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=None, separators=(",", ":")) + "\n", encoding="utf-8")
    summary = {k: v for k, v in res.items() if k not in ("slots", "products", "layer", "requests")} if isinstance(res, dict) else res
    if a.stage == "imerg_cmr" and isinstance(res.get("products"), dict):
        summary = {s: {w: (v.get("granules"), v.get("total_mb_declared")) for w, v in d.items()} for s, d in res["products"].items()}
    if a.stage == "imerg_pilot" and isinstance(res.get("products"), dict):
        summary = {s: {k: v.get(k) for k in ("status", "granules_found", "slots_read", "download_seconds", "total_bytes")} for s, v in res["products"].items()}
    print(f"::notice title={a.stage}::{json.dumps(summary, ensure_ascii=False)[:900]} runtime_s={doc['runtime_s']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
