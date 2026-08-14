#!/usr/bin/env python3
"""Inspecciona la interfaz pública del hidrograma SENAMHI Puente Ñacara.

Solo genera metadatos de descubrimiento. No altera el modelo Catacaos ni trata
HTML de presentación como una API estable hasta identificar el origen real de
datos.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import html
import json
import re

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "hydrology" / "senamhi_piura_discovery.json"
URL = "https://www.senamhi.gob.pe/mapas/mapa-monitoreohidro/include/mnt-grafica-new.php"
STATION = "47E0415A"


def compact(value, limit=420):
    text = re.sub(r"\s+", " ", html.unescape(str(value))).strip()
    return text[:limit]


def unique(seq, limit=100):
    out = []
    seen = set()
    for x in seq:
        x = compact(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
            if len(out) >= limit:
                break
    return out


def inspect_page(date_text):
    params = {
        "fecha_hora": date_text,
        "id": STATION,
        "variable": "CAUDAL",
        "variable_opcion": "C",
    }
    response = requests.get(
        URL,
        params=params,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0 IRFEN-research/0.8",
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://www.senamhi.gob.pe/?dp=piura&p=monitoreo-piura",
        },
    )
    text = response.text

    quoted_urls = re.findall(r"https?://[^\"'<>\s]+", text, flags=re.I)
    php_refs = re.findall(r"[A-Za-z0-9_./-]+\.php(?:\?[^\"'<>\s]*)?", text, flags=re.I)
    url_assignments = re.findall(r"(?:url|href|src)\s*[:=]\s*[\"']([^\"']+)[\"']", text, flags=re.I)
    ajax_calls = re.findall(r"\$\.(?:ajax|get|getJSON|post)\s*\((.{0,700}?)\);", text, flags=re.I | re.S)
    fetch_calls = re.findall(r"fetch\s*\((.{0,500}?)\)", text, flags=re.I | re.S)

    keyword_snippets = []
    for match in re.finditer(
        r"highcharts|series\s*:|data\s*:|json|ajax|fetch|php|caudal|47E0415A|umbral|navigator",
        text,
        flags=re.I,
    ):
        a = max(0, match.start() - 180)
        b = min(len(text), match.end() + 300)
        keyword_snippets.append(text[a:b])

    date_utc_count = len(re.findall(r"Date\.UTC\s*\(", text, flags=re.I))
    unix_ms = re.findall(r"\b1[4-9]\d{11}\b", text)
    array_like = re.findall(r"\[\s*(?:\[|\{)[\s\S]{20,1500}?\]\s*[,;]", text)

    return {
        "requested_url": response.url,
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "response_bytes": len(response.content),
        "contains_station_name": "ÑACARA" in text.upper() or "NACARA" in text.upper(),
        "contains_highcharts": "highcharts" in text.lower(),
        "date_utc_occurrences": date_utc_count,
        "unix_millisecond_candidates": unique(unix_ms, 20),
        "absolute_urls": unique(quoted_urls, 60),
        "php_references": unique(php_refs, 80),
        "url_assignments": unique(url_assignments, 80),
        "ajax_calls": unique(ajax_calls, 30),
        "fetch_calls": unique(fetch_calls, 30),
        "keyword_snippets": unique(keyword_snippets, 60),
        "array_like_snippets": unique(array_like, 20),
    }


def main():
    peru = timezone(timedelta(hours=-5))
    now = datetime.now(peru)
    probes = [
        now.strftime("%Y-%m-%d %H:00:00"),
        "2025-03-21 12:00:00",
        "2024-09-06 19:00:00",
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "institution": "SENAMHI Perú",
        "station": {
            "name": "Puente Ñacara",
            "id": STATION,
            "river": "Río Piura",
            "variable": "CAUDAL",
        },
        "purpose": "Descubrir una interfaz reutilizable de datos hidrológicos antes de integrar Catacaos/Bajo Piura.",
        "production_use": False,
        "probes": [],
    }
    for date in probes:
        try:
            result = inspect_page(date)
            report["probes"].append({"date": date, **result})
        except Exception as exc:
            report["probes"].append({
                "date": date,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    successful = [p for p in report["probes"] if p.get("http_status") == 200]
    refs = []
    for p in successful:
        refs.extend(p.get("php_references", []))
        refs.extend(p.get("url_assignments", []))
    likely = [
        x for x in unique(refs, 150)
        if any(k in x.lower() for k in ("json", "data", "ajax", "graf", "hidro", "estacion", "serie"))
    ]
    report["candidate_data_references"] = likely
    report["status"] = "html_accessible" if successful else "access_failed"
    report["decision"] = (
        "inspect_candidate_references" if likely
        else "inspect_embedded_highcharts_data" if any(p.get("contains_highcharts") for p in successful)
        else "review_interface"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
