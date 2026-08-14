#!/usr/bin/env python3
"""Prueba el endpoint diario GORE Piura y diagnostica sus rutas de descarga/mapa.

Solo descubrimiento: no altera latest.json ni el modelo operativo.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "hydrology" / "gore_piura_probe.json"
BASE = "https://servicios.regionpiura.gob.pe"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.7",
}


def flatten_items(obj):
    if isinstance(obj, list): return obj
    if isinstance(obj, dict):
        for key in ("data", "items", "results", "result", "registros"):
            if isinstance(obj.get(key), list): return obj[key]
    return []


def extract_date(item):
    for key in ("fecha", "fdate", "date", "fecha_datos", "fecha_data", "fec"):
        if item.get(key): return str(item[key])
    return ""


def score_date(text):
    nums = re.findall(r"\d+", str(text))
    if len(nums) >= 3:
        try:
            if len(nums[0]) == 4: y, m, d = map(int, nums[:3])
            else:
                d, m, y = map(int, nums[:3]); y += 2000 if y < 100 else 0
            return y * 10000 + m * 100 + d
        except Exception: pass
    return 0


def profile_response(r, body_limit=650):
    first = r.content[:body_limit]
    preview = first.decode("utf-8", errors="replace")
    ctype = r.headers.get("content-type", "")
    return {
        "status": r.status_code,
        "url": r.url,
        "content_type": ctype,
        "content_disposition": r.headers.get("content-disposition", ""),
        "content_length_header": r.headers.get("content-length"),
        "bytes": len(r.content),
        "location": r.headers.get("location"),
        "history": [{"status": h.status_code, "url": h.url, "location": h.headers.get("location")} for h in r.history],
        "first_bytes_hex": first[:40].hex(),
        "preview": preview,
        "looks_html": b"<html" in r.content[:1000].lower() or b"<!doctype html" in r.content[:1000].lower(),
        "looks_pdf": r.content.startswith(b"%PDF"),
        "looks_zip": r.content.startswith(b"PK\x03\x04"),
        "looks_image": ctype.lower().startswith("image/") or r.content.startswith((b"\x89PNG", b"\xff\xd8\xff")),
    }


def request_profile(session, url, accept="*/*", redirects=True):
    try:
        r = session.get(url, timeout=60, headers={"Accept": accept}, allow_redirects=redirects)
        return profile_response(r)
    except Exception as exc:
        return {"url":url,"error_type":type(exc).__name__,"error":str(exc)}


def main():
    peru = timezone(timedelta(hours=-5)); now = datetime.now(peru)
    months = [(now.year, now.month), (now.year if now.month > 1 else now.year-1, now.month-1 if now.month > 1 else 12)]
    # Añadir un mes histórico conocido para distinguir fallo de rutas vs. falta de archivos recientes.
    historic_month = (2025, 7)
    if historic_month not in months: months.append(historic_month)
    session = requests.Session(); session.headers.update(HEADERS)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "institution": "Gobierno Regional Piura / Proyecto Especial Chira Piura",
        "production_use": False,
        "endpoint_template": f"{BASE}/datosh/data/{{year}}/{{month}}",
        "queries": [], "latest_item": None, "route_tests": [], "map_profile": None
    }

    landing = session.get(f"{BASE}/datosh", timeout=45)
    report["landing"] = profile_response(landing, 120)
    session.headers.update({"Referer": f"{BASE}/datosh"})
    report["map_profile"] = request_profile(session, f"{BASE}/datosh/mapa", "image/*,text/html,*/*")

    all_items = []
    per_month = {}
    for year, month in months:
        url = f"{BASE}/datosh/data/{year}/{month:02d}"
        try:
            r = session.get(url, timeout=45, headers={"Accept": "application/json,text/plain,*/*", "X-Requested-With": "XMLHttpRequest"})
            r.raise_for_status(); obj = r.json(); items = flatten_items(obj)
            key=f"{year}-{month:02d}"; per_month[key]=items
            report["queries"].append({"url": url, "http_status": r.status_code, "item_count": len(items), "sample_items": items[:3]})
            all_items.extend(items)
        except Exception as exc:
            report["queries"].append({"url": url, "error_type": type(exc).__name__, "error": str(exc)})

    candidates = []
    for item in all_items:
        if not isinstance(item, dict): continue
        fkey = item.get("fkey") or item.get("key") or item.get("id")
        if fkey: candidates.append((score_date(extract_date(item)), str(fkey), item))
    candidates.sort(reverse=True, key=lambda x: x[0])
    report["latest_item"] = candidates[0][2] if candidates else None

    keys_to_test=[]
    if candidates: keys_to_test.append(candidates[0][1])
    hist_items=per_month.get("2025-07",[])
    if hist_items:
        hist_key=hist_items[0].get("fkey") or hist_items[0].get("id")
        if hist_key and str(hist_key) not in keys_to_test: keys_to_test.append(str(hist_key))

    route_tests=[]
    for fkey in keys_to_test:
        for kind, accept in (
            ("csv", "text/csv,text/plain,*/*"),
            ("xls", "application/vnd.ms-excel,application/octet-stream,*/*"),
            ("pdf", "application/pdf,application/octet-stream,*/*"),
        ):
            base_url=f"{BASE}/datosh/{kind}/{fkey}"
            variants=[base_url,base_url+"/",base_url+"?download=1"]
            for url in variants:
                route_tests.append({"fkey":fkey,"kind":kind,"variant":url,**request_profile(session,url,accept)})
    report["route_tests"]=route_tests
    usable=[x for x in route_tests if x.get("status")==200 and not x.get("looks_html") and x.get("bytes",0)>100]
    map_ok=report["map_profile"] and not report["map_profile"].get("looks_html",True)
    report["usable_downloads"]=usable
    if usable:
        report["status"]="download_accessible"; report["decision"]="build_experimental_ingestor"
    elif map_ok:
        report["status"]="map_asset_accessible"; report["decision"]="inspect_map_asset"
    else:
        report["status"]="metadata_endpoint_only"; report["decision"]="use_daily_availability_metadata_and_seek_alternate_data_route"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status":report["status"],"decision":report["decision"],"latest_item":report["latest_item"],
        "map_profile":report["map_profile"],"usable_download_count":len(usable)
    },ensure_ascii=False,indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
