#!/usr/bin/env python3
"""Prueba el endpoint diario GORE Piura y diagnostica sus rutas de descarga.

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


def profile_response(r, body_limit=500):
    first = r.content[:body_limit]
    preview = first.decode("utf-8", errors="replace")
    return {
        "status": r.status_code,
        "url": r.url,
        "content_type": r.headers.get("content-type", ""),
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
    }


def main():
    peru = timezone(timedelta(hours=-5)); now = datetime.now(peru)
    months = [(now.year, now.month), (now.year if now.month > 1 else now.year-1, now.month-1 if now.month > 1 else 12)]
    session = requests.Session(); session.headers.update(HEADERS)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "institution": "Gobierno Regional Piura / Proyecto Especial Chira Piura",
        "production_use": False,
        "endpoint_template": f"{BASE}/datosh/data/{{year}}/{{month}}",
        "queries": [], "latest_item": None, "download_profiles": []
    }

    landing = session.get(f"{BASE}/datosh", timeout=45)
    report["landing"] = profile_response(landing, 120)
    session.headers.update({"Referer": f"{BASE}/datosh"})

    all_items = []
    for year, month in months:
        url = f"{BASE}/datosh/data/{year}/{month:02d}"
        try:
            r = session.get(url, timeout=45, headers={"Accept": "application/json,text/plain,*/*", "X-Requested-With": "XMLHttpRequest"})
            r.raise_for_status(); obj = r.json(); items = flatten_items(obj)
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

    if not candidates:
        report.update({"status":"no_records","decision":"keep_discovery_only"})
    else:
        _, fkey, item = candidates[0]; report["latest_item"] = item
        variants = []
        for kind, accept in (
            ("csv", "text/csv,text/plain,*/*"),
            ("xls", "application/vnd.ms-excel,application/octet-stream,*/*"),
            ("pdf", "application/pdf,application/octet-stream,*/*"),
        ):
            url = f"{BASE}/datosh/{kind}/{fkey}"
            for mode in ("follow", "no_redirect"):
                try:
                    r = session.get(url, timeout=60, headers={"Accept": accept}, allow_redirects=(mode=="follow"))
                    variants.append({"kind":kind,"mode":mode,**profile_response(r)})
                except Exception as exc:
                    variants.append({"kind":kind,"mode":mode,"url":url,"error_type":type(exc).__name__,"error":str(exc)})
        report["download_profiles"] = variants
        usable = [x for x in variants if x.get("status") == 200 and not x.get("looks_html") and x.get("bytes",0) > 100]
        report["status"] = "download_accessible" if usable else "download_route_returns_html"
        report["usable_downloads"] = usable
        report["decision"] = "build_experimental_ingestor" if usable else "inspect_server_routing_or_map_endpoint"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
