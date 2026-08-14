#!/usr/bin/env python3
"""Prueba el endpoint diario descubierto de GORE Piura y perfila el CSV más reciente.

Solo descubrimiento: no altera latest.json ni el modelo operativo.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv
import io
import json
import re

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "hydrology" / "gore_piura_probe.json"
BASE = "https://servicios.regionpiura.gob.pe"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; IRFEN-research/0.8)"}


def get_json(url):
    r = requests.get(url, timeout=45, headers=HEADERS)
    r.raise_for_status()
    return r.json(), r


def flatten_items(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("data", "items", "results", "result", "registros"):
            value = obj.get(key)
            if isinstance(value, list):
                return value
    return []


def extract_date(item):
    for key in ("fecha", "fdate", "date", "fecha_datos", "fecha_data", "fec"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def score_date(text):
    nums = re.findall(r"\d+", str(text))
    if len(nums) >= 3:
        try:
            if len(nums[0]) == 4:
                y, m, d = map(int, nums[:3])
            else:
                d, m, y = map(int, nums[:3])
            return y * 10000 + m * 100 + d
        except Exception:
            pass
    return 0


def decode_csv(content):
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            return content.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace"), "latin-1-replace"


def sniff(text):
    sample = text[:10000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = []
    for row in reader:
        rows.append(row)
        if len(rows) >= 12:
            break
    return delimiter, rows


def main():
    peru = timezone(timedelta(hours=-5))
    now = datetime.now(peru)
    months = [(now.year, now.month)]
    if now.month == 1:
        months.append((now.year - 1, 12))
    else:
        months.append((now.year, now.month - 1))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "institution": "Gobierno Regional Piura / Proyecto Especial Chira Piura",
        "production_use": False,
        "endpoint_template": f"{BASE}/datosh/data/{{year}}/{{month}}",
        "queries": [],
        "latest_item": None,
        "csv_profile": None,
    }

    all_items = []
    for year, month in months:
        url = f"{BASE}/datosh/data/{year}/{month:02d}"
        try:
            obj, r = get_json(url)
            items = flatten_items(obj)
            report["queries"].append({
                "url": url,
                "http_status": r.status_code,
                "response_type": type(obj).__name__,
                "top_level_keys": list(obj.keys())[:30] if isinstance(obj, dict) else None,
                "item_count": len(items),
                "sample_items": items[:3],
            })
            all_items.extend(items)
        except Exception as exc:
            report["queries"].append({"url": url, "error_type": type(exc).__name__, "error": str(exc)})

    candidates = []
    for item in all_items:
        if not isinstance(item, dict):
            continue
        fkey = item.get("fkey") or item.get("key") or item.get("id")
        if fkey:
            candidates.append((score_date(extract_date(item)), str(fkey), item))
    candidates.sort(reverse=True, key=lambda x: x[0])

    if candidates:
        _, fkey, item = candidates[0]
        report["latest_item"] = item
        csv_url = f"{BASE}/datosh/csv/{fkey}"
        try:
            r = requests.get(csv_url, timeout=60, headers=HEADERS)
            r.raise_for_status()
            text, encoding = decode_csv(r.content)
            delimiter, rows = sniff(text)
            report["csv_profile"] = {
                "url": csv_url,
                "http_status": r.status_code,
                "bytes": len(r.content),
                "content_type": r.headers.get("content-type"),
                "encoding": encoding,
                "delimiter": delimiter,
                "first_rows": rows,
                "first_line": text.splitlines()[0][:1000] if text.splitlines() else "",
                "keyword_hits": {
                    key: len(re.findall(key, text, flags=re.I))
                    for key in ("caudal", "precipit", "puente", "nacara", "ñacara", "piura", "tambogrande", "chulucanas", "nivel")
                },
            }
            report["status"] = "daily_csv_accessible"
            report["decision"] = "build_experimental_ingestor"
        except Exception as exc:
            report["csv_profile"] = {"url": csv_url, "error_type": type(exc).__name__, "error": str(exc)}
            report["status"] = "metadata_only"
            report["decision"] = "review_csv_download"
    else:
        report["status"] = "no_records"
        report["decision"] = "keep_discovery_only"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
