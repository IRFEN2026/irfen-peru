#!/usr/bin/env python3
"""Sondeo acotado del canal oficial IGP/CENDEHUA para Huaycoloro.

El sondeo parte exclusivamente de URLs oficiales conocidas y solo inspecciona
recursos enlazados por la pagina obtenida. No enumera endpoints, no infiere
eventos y no cambia el estado operativo TEST_ONLY de IRFEN v0.8.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
import json
import re

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/stations/igp_cendehua_access_probe.json"
START_URLS = [
    "https://www.igp.gob.pe/servicios/centro-monitoreo-deslizamientos-huaicos/inicio",
    "https://grd.igp.gob.pe/lahares-huaicos/",
]
TIMEOUT = (5, 15)
MAX_HTML_BYTES = 2_000_000
MAX_REFERENCES = 120
MAX_CANDIDATES = 25
MAX_PROBES = 10


def safe_get(url: str):
    return requests.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={"User-Agent": "IRFEN-v0.8-scientific-probe/1.0"},
    )


def classify_candidate(url: str):
    """Clasifica unicamente referencias con senales estructuradas explicitas."""
    low = url.lower()
    if any(token in low for token in (".geojson", "geojson", "?f=geojson")):
        return "geojson_candidate"
    if any(token in low for token in (".json", "/api/", "?f=json", "format=json")):
        return "json_or_api_candidate"
    if any(token in low for token in (".csv", "format=csv")):
        return "csv_candidate"
    if any(token in low for token in ("featureserver", "mapserver", "geoserver", "/wfs")):
        return "gis_service_candidate"
    return None


def extract_candidates(html: str, base_url: str):
    """Extrae candidatos solo de href/src literales y con limites verificables."""
    references = []
    candidates = []
    for match in re.finditer(r"(?:src|href)=[\"']([^\"']+)[\"']", html, re.I):
        url = urljoin(base_url, unescape(match.group(1)).strip())
        if not url.startswith(("http://", "https://")) or url in references:
            continue
        references.append(url)
        kind = classify_candidate(url)
        if kind:
            candidates.append({"url": url, "kind": kind})
            if len(candidates) >= MAX_CANDIDATES:
                break
        if len(references) >= MAX_REFERENCES:
            break
    return references, candidates


def main():
    attempts = []
    final = None
    for start_url in START_URLS:
        row = {"start_url": start_url}
        try:
            response = safe_get(start_url)
            content_type = response.headers.get("content-type")
            row.update(
                {
                    "status_code": response.status_code,
                    "final_url": response.url,
                    "content_type": content_type,
                    "redirect_chain": [item.url for item in response.history] + [response.url],
                }
            )
            attempts.append(row)
            if response.ok and "text/html" in (content_type or "").lower():
                final = response
                break
        except Exception as exc:
            row["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
            attempts.append(row)

    page = None
    references = []
    candidates = []
    if final is not None:
        raw = final.content[:MAX_HTML_BYTES]
        text = raw.decode(final.encoding or "utf-8", errors="ignore")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        page = {
            "url": final.url,
            "title": re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None,
            "bytes_inspected": len(raw),
        }
        references, candidates = extract_candidates(text, final.url)

    probed = []
    for candidate in candidates[:MAX_PROBES]:
        try:
            response = safe_get(candidate["url"])
            content_type = (response.headers.get("content-type") or "").lower()
            probed.append(
                {
                    **candidate,
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "final_url": response.url,
                    "structured_response": any(
                        token in content_type for token in ("json", "csv", "geo+json")
                    ),
                    "bytes": len(response.content),
                }
            )
        except Exception as exc:
            probed.append(
                {**candidate, "error": {"type": type(exc).__name__, "message": str(exc)[:300]}}
            )

    usable = [
        item
        for item in probed
        if item.get("http_status") == 200 and item.get("structured_response") is True
    ]
    if usable:
        status = "STRUCTURED_CHANNEL_CANDIDATE_FOUND"
        next_action = (
            "Review schema, station identity and event semantics before adding any observation pair."
        )
    elif final is not None:
        status = "OFFICIAL_MONITOR_REACHED_NO_OBVIOUS_STRUCTURED_CHANNEL"
        next_action = (
            "Keep CENDEHUA as an authoritative external/manual outcome channel; stop endpoint exploration."
        )
    else:
        status = "OFFICIAL_MONITOR_NOT_REACHABLE_FROM_GITHUB"
        next_action = (
            "Retain the official IGP publications as documentary evidence and retry only the same URLs later."
        )

    result = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "purpose": (
            "Bounded check for a documented machine-readable IGP/CENDEHUA Huaycoloro monitoring channel."
        ),
        "official_context": {
            "institution": "Instituto Geofisico del Peru (IGP)",
            "platform": "CENDEHUA - monitoreo de deslizamientos y huaicos",
            "target_pilot": "Huaycoloro/Chosica",
            "official_service_url": "https://www.gob.pe/41855-centro-de-monitoreo-de-deslizamientos-y-huaicos-cendehua",
            "official_alerts_url": "https://www.gob.pe/8084-revisar-alertas-de-huaicos-en-lima",
            "official_monitoring_news_url": "https://www.gob.pe/institucion/igp/noticias/1343594-igp-refuerza-vigilancia-del-sistema-de-monitoreo-de-huaicos-en-las-quebradas-huaycoloro-y-rio-seco",
            "claimed_scope": "official 24/7 monitoring and alerts; not an IRFEN event label",
        },
        "status": status,
        "attempts": attempts,
        "page": page,
        "references_inspected": len(references),
        "structured_candidates_found": candidates,
        "candidate_probes": probed,
        "usable_structured_candidates": usable,
        "next_action": next_action,
        "stop_rule": (
            "Inspect only explicit page references; do not enumerate or guess undocumented endpoints."
        ),
        "validation_guard": (
            "This probe cannot classify an EVENT/NONE outcome or satisfy the Chosica validation contract by itself."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status,
                "page": page,
                "candidates": len(candidates),
                "usable_count": len(usable),
                "next_action": next_action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
