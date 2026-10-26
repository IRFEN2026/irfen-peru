#!/usr/bin/env python3
"""Recuperación ÚNICA y acotada autorizada el 26-oct-2026 (RESEARCH_ONLY / TEST_ONLY). No es un sondeo.

Autorización del propietario (issue #400, PR #419):
1. Consulta puntual de coordenadas y metadatos de 10 estaciones de Tumbes (WMO OSCAR/Surface o fuentes públicas
   SENAMHI, consultas manuales limitadas).
2. Registros pluviométricos instrumentales oficiales (SENAMHI, PECHP o acceso WIS2 permitido), sin eludir
   autenticación ni restricciones y sin sondeo permanente.
3. Recuperación única de los 192 gránulos IMERG Early V07C del 21-oct 12Z al 25-oct 12Z del manifiesto, con las
   credenciales Earthdata del repositorio, extrayendo solo un bloque regional de celdas sobre Tumbes.

Este script corre una vez en un runner (el flujo se niega a repetir si ya existe el resultado). Los HDF5 se borran
después de extraer el bloque; en el repositorio solo quedan metadatos, hashes y el bloque de celdas.
Cada solicitud queda registrada con URL, hora, estado HTTP, bytes y SHA-256 de la respuesta. Un error o un 401/403
se registra como bloqueo: no se reintenta por otras vías.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
PKG_ROOT = HERE.parent
sys.path.insert(0, str(PKG_ROOT))
from irfen_gauge_imerg.granules import iso, parse  # noqa: E402
from irfen_gauge_imerg.grid import verify_axis  # noqa: E402
from irfen_gauge_imerg.imerg_cells import normalise_units, sha256_file  # noqa: E402

UA = {"User-Agent": "IRFEN-research/0.9 one-shot authorized retrieval (+https://github.com/IRFEN2026/irfen-peru/issues/400)"}
TIMEOUT = (10, 60)
MANIFEST = PKG_ROOT / "evidence/imerg_early_granule_manifest_2026-10-21_26_v1.json"
WINDOWS = ("rainday_2026-10-22_PET", "rainday_2026-10-23_PET", "rainday_2026-10-24_PET", "rainday_2026-10-25_PET")
# Bloque regional sobre Tumbes con margen para la vecindad 3×3 (índices globales V07, fin exclusivo)
BLOCK = {"i0": 990, "i1": 1001, "j0": 857, "j1": 868}   # lon −81,0…−79,9; lat −4,3…−3,2
STATIONS = ["La Cruz", "Matapalo", "Papayal", "Puerto Pizarro", "Campamento SEDA", "Puente Tumbes", "Cañaveral",
            "Huasimal", "Rica Playa", "Cabo Inga"]
SENAMHI_CODES = {"LA CRUZ": "100072", "MATAPALO": "103008", "PAPAYAL": "103040", "PUERTO PIZARRO": "103038",
                 "CAÑAVERAL": "103042", "RICA PLAYA": "103036", "CABO INGA": "103043"}  # Anexo 1, Atlas climático


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url, params=None, method="GET", data=None, save_dir: Path | None = None, tag: str = "") -> dict:
    rec = {"tag": tag, "url": url, "params": params, "method": method, "requested_at_utc": now()}
    t0 = time.monotonic()
    try:
        r = requests.request(method, url, params=params, data=data, headers=UA, timeout=TIMEOUT)
        body = r.content
        rec.update(http_status=r.status_code, final_url=r.url, content_type=r.headers.get("content-type"),
                   bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), seconds=round(time.monotonic() - t0, 2))
        if save_dir is not None and body and r.status_code == 200:
            ext = ".json" if "json" in (r.headers.get("content-type") or "") else ".html"
            p = save_dir / f"{tag}{ext}"
            p.write_bytes(body[:5_000_000])
            rec["saved_as"] = p.name
        rec["_body"] = body
    except Exception as exc:  # noqa: BLE001 — se registra tal cual; no se reintenta por otras vías
        rec.update(http_status=None, error=f"{type(exc).__name__}: {exc}"[:400], seconds=round(time.monotonic() - t0, 2))
    return rec


def strip(rec):
    return {k: v for k, v in rec.items() if not k.startswith("_")}


# ------------------------------------------------------------------------------------------------- 1. metadatos
def oscar(out: Path) -> dict:
    """WMO OSCAR/Surface: estaciones del Perú (una consulta) y filtro local por nombre. No asume equivalencias."""
    res = {"requests": [], "candidates": []}
    for tag, params in (("oscar_search_PER", {"territoryName": "PER"}),
                        ("oscar_search_Peru", {"territoryName": "Peru"})):
        r = get("https://oscar.wmo.int/surface/rest/api/search/station", params, save_dir=out, tag=tag)
        res["requests"].append(strip(r))
        if r.get("http_status") == 200:
            try:
                js = json.loads(r["_body"])
            except ValueError:
                continue
            items = js if isinstance(js, list) else js.get("stationSearchResults") or js.get("results") or []
            res["n_items"] = len(items)
            keys = [s.upper().replace("Ñ", "N") for s in STATIONS] + ["TUMBES", "HUASIMO", "CAMPAMENTO", "PUENTE"]
            for it in items:
                name = str(it.get("name", "")).upper().replace("Ñ", "N")
                if any(k.split()[0] in name for k in keys):
                    res["candidates"].append(it)
            break
    return res


def senamhi_public(out: Path) -> dict:
    """Páginas públicas SENAMHI (catálogo de estaciones y WIS2). Consultas puntuales; sin autenticación."""
    reqs = []
    reqs.append(strip(get("https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/", save_dir=out, tag="senamhi_mapa_estaciones")))
    reqs.append(strip(get("https://wis.senamhi.gob.pe/oapi/collections/stations/items",
                          {"f": "json", "limit": 500}, save_dir=out, tag="senamhi_wis2_stations")))
    return {"requests": reqs}


# --------------------------------------------------------------------------------------- 2. registros de estación
def senamhi_records(out: Path, wis2_ids: list[str]) -> dict:
    reqs = []
    for code in sorted(set(SENAMHI_CODES.values())):
        reqs.append(strip(get("https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/_dato_esta_tipo02.php",
                              {"estaciones": code, "CBOFiltro": "202610", "t_e": "M", "estado": "REAL"},
                              save_dir=out, tag=f"senamhi_dato_{code}_202610")))
    for wid in wis2_ids[:10]:
        reqs.append(strip(get("https://wis.senamhi.gob.pe/oapi/collections/urn:wmo:md:pe-senamhi:synop-hourly/items",
                              {"f": "json", "wigos_station_identifier": wid, "limit": 1000,
                               "datetime": "2026-10-21T00:00:00Z/2026-10-26T18:00:00Z"},
                              save_dir=out, tag=f"senamhi_wis2_obs_{wid}")))
    return {"requests": reqs}


# ----------------------------------------------------------------------------------------------------- 3. IMERG
def manifest_names() -> list[str]:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    names = []
    for w in m["windows"]:
        if w["id"] in WINDOWS:
            names += [g["granule"] for g in w["granules"]]
    names = sorted(set(names))
    assert len(names) == 192, len(names)
    return names


def cmr(names: list[str]) -> dict:
    r = get("https://cmr.earthdata.nasa.gov/search/granules.umm_json",
            {"short_name": "GPM_3IMERGHHE", "version": "07", "page_size": 250, "sort_key": "start_date",
             "temporal": "2026-10-21T12:00:00Z,2026-10-25T11:59:59Z"}, tag="cmr_GPM_3IMERGHHE_07")
    out = {"request": strip(r), "items": {}, "discrepancies": []}
    if r.get("http_status") != 200:
        out["discrepancies"].append({"issue": "CMR_UNREACHABLE"})
        return out
    js = json.loads(r["_body"])
    for it in js.get("items", []):
        umm, meta = it.get("umm", {}), it.get("meta", {})
        gname = umm.get("GranuleUR", "")
        fname = gname.split(":")[-1]
        urls = [u.get("URL") for u in umm.get("RelatedUrls", []) if u.get("Type") == "GET DATA"]
        info = (umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation") or [{}])[0]
        out["items"][fname] = {"granule_ur": gname, "concept_id": meta.get("concept-id"),
                               "revision_id": meta.get("revision-id"), "revision_date": meta.get("revision-date"),
                               "production_datetime": umm.get("DataGranule", {}).get("ProductionDateTime"),
                               "size": info.get("Size"), "size_unit": info.get("SizeUnit"),
                               "checksum": info.get("Checksum"), "get_data_urls": urls}
    found = set(out["items"])
    for n in names:
        if n not in found:
            gid = parse(n)
            alt = [f for f in found if parse(f).start_utc == gid.start_utc]
            out["discrepancies"].append({"granule": n, "issue": "NOT_IN_CMR_WITH_SAME_NAME",
                                         "same_slot_in_cmr": alt})
    extra = sorted(found - set(names))
    if extra:
        out["discrepancies"].append({"issue": "CMR_HAS_GRANULES_NOT_IN_MANIFEST", "granules": extra})
    return out


def read_block(path: Path) -> dict:
    import h5py
    import numpy as np
    with h5py.File(path, "r") as f:
        g = f["Grid"]
        lat = np.asarray(g["lat"][:], dtype=float)
        lon = np.asarray(g["lon"][:], dtype=float)
        ax_lon, ax_lat = verify_axis(lon, "lon"), verify_axis(lat, "lat")
        if ax_lon["offset"] != 0 or ax_lat["offset"] != 0 or ax_lon["size"] != 3600 or ax_lat["size"] != 1800:
            raise ValueError("se esperaba la malla global completa")
        pd = g["precipitation"]
        dims = pd.attrs.get("DimensionNames")
        dims = dims.decode() if isinstance(dims, (bytes, bytearray)) else str(dims)
        if [d.strip() for d in dims.split(",")] != ["time", "lon", "lat"]:
            raise ValueError(f"DimensionNames inesperado {dims!r}")
        units = normalise_units(pd.attrs.get("units", ""))
        fill = float(np.asarray(pd.attrs.get("_FillValue")).ravel()[0])
        sub = np.asarray(pd[0, BLOCK["i0"]:BLOCK["i1"], BLOCK["j0"]:BLOCK["j1"]], dtype=float)
        secs = float(np.asarray(g["time"][:]).ravel()[0])
        tunits = g["time"].attrs.get("units", b"")
        tunits = tunits.decode() if isinstance(tunits, (bytes, bytearray)) else str(tunits)
    internal = datetime.fromtimestamp(secs, tz=timezone.utc) if "1970-01-01" in tunits else None
    vals = [[None if (not np.isfinite(v) or v < 0 or abs(v - fill) < 1e-3) else round(float(v), 5) for v in row]
            for row in sub]
    return {"units": units, "fill_value": fill, "internal_start_utc": iso(internal) if internal else None,
            "rates_mm_hr_lon_lat": vals}


def imerg(out: Path, names: list[str], cmr_info: dict) -> dict:
    import earthaccess
    res = {"login": None, "granules": [], "errors": []}
    if not os.getenv("EARTHDATA_TOKEN"):
        res["login"] = "BLOCKED_NO_TOKEN"
        return res
    try:
        earthaccess.login(strategy="environment")
        res["login"] = "OK"
        found = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07",
                                        temporal=("2026-10-21T12:00:00Z", "2026-10-25T11:59:59Z"), count=250)
    except Exception as exc:  # noqa: BLE001
        res["login"] = f"ERROR {type(exc).__name__}: {exc}"[:300]
        return res
    stop = {d["granule"] for d in cmr_info.get("discrepancies", []) if d.get("granule")}
    by_name = {}
    for g in found:
        links = g.data_links()
        for link in links:
            fname = link.rsplit("/", 1)[-1]
            if fname in names and fname not in stop:
                by_name[fname] = (g, link)
    res["search_matches"] = len(by_name)
    with tempfile.TemporaryDirectory(prefix="irfen_imerg_once_") as td:
        for fname in names:
            if fname in stop:
                res["errors"].append({"granule": fname, "error": "STOPPED_CMR_DISCREPANCY"})
                continue
            if fname not in by_name:
                res["errors"].append({"granule": fname, "error": "NOT_FOUND_IN_EARTHACCESS_SEARCH"})
                continue
            g, link = by_name[fname]
            t0 = time.monotonic()
            try:
                paths = earthaccess.download([g], local_path=td, threads=1, show_progress=False)
                p = Path([x for x in paths if str(x).endswith(fname)][0])
                rec = {"granule": fname, "url": link, "retrieved_at_utc": now(), "bytes": p.stat().st_size,
                       "sha256": sha256_file(p), "cmr": cmr_info.get("items", {}).get(fname),
                       "download_seconds": round(time.monotonic() - t0, 1)}
                gid = parse(fname)
                block = read_block(p)
                if block["internal_start_utc"] != iso(gid.start_utc):
                    raise ValueError(f"hora interna {block['internal_start_utc']} ≠ nombre {iso(gid.start_utc)}")
                rec.update(gid.as_dict(), family=gid.family, **block)
                res["granules"].append(rec)
            except Exception as exc:  # noqa: BLE001
                res["errors"].append({"granule": fname, "error": f"{type(exc).__name__}: {exc}"[:300]})
            finally:
                for x in Path(td).iterdir():
                    x.unlink()
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    out = a.out
    raw = out / "raw_metadata"
    raw.mkdir(parents=True, exist_ok=True)
    started = now()
    names = manifest_names()
    meta = {"oscar": oscar(raw), "senamhi_public": senamhi_public(raw)}
    wis2_ids = []
    p = raw / "senamhi_wis2_stations.json"
    if p.is_file():
        try:
            feats = json.loads(p.read_text()).get("features", [])
            for f in feats:
                pr = f.get("properties", {})
                if "TUMBES" in json.dumps(pr, ensure_ascii=False).upper():
                    wid = pr.get("wigos_station_identifier") or f.get("id")
                    if wid:
                        wis2_ids.append(str(wid))
        except ValueError:
            pass
    records = senamhi_records(raw, wis2_ids)
    cmr_info = cmr(names)
    im = imerg(out, names, cmr_info)
    block_doc = {"schema": "irfen.gauge_imerg.imerg_block", "schema_version": "1.0.0",
                 "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
                 "data_nature": "SATELLITE_ESTIMATE_NOT_GAUGE_OBSERVATION",
                 "block_global_indices": BLOCK, "short_name": "GPM_3IMERGHHE", "version_requested": "07",
                 "granules": im["granules"]}
    (out / "imerg_early_tumbes_block_2026-10-21T12_25T12.json").write_text(json.dumps(block_doc, ensure_ascii=False))
    log = {"schema": "irfen.gauge_imerg.retrieval_log", "schema_version": "1.0.0", "one_shot": True,
           "authorization": "Propietario IRFEN, 26-oct-2026 (puntos 1–3); ver docstring",
           "started_at_utc": started, "finished_at_utc": now(),
           "metadata": meta, "station_records": records, "wis2_tumbes_ids_found": wis2_ids,
           "cmr": {k: v for k, v in cmr_info.items() if k != "items"}, "cmr_items": cmr_info.get("items"),
           "imerg": {"login": im["login"], "search_matches": im.get("search_matches"),
                     "retrieved": len(im["granules"]), "expected": len(names), "errors": im["errors"]}}
    (out / "retrieval_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(log["imerg"], ensure_ascii=False)[:2000])
    print("oscar candidates:", len(meta["oscar"]["candidates"]), "wis2 ids:", wis2_ids)


if __name__ == "__main__":
    main()
