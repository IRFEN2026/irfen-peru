#!/usr/bin/env python3
"""Exploración técnica ACOTADA del acceso oficial ISAAC/SENAMHI.

Objetivo único: resolver el enlace oficial y comprobar si la página final expone
un canal estructurado obvio (JSON/CSV/GeoJSON/API). No rastrea sitios enteros,
no hace OCR, no cambia alertas y no convierte publicaciones sociales en datos.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import json
import re

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/stations/isaac_access_probe.json"
START_URLS = [
    "https://bit.ly/ISAAC_SENAMHI",
    "https://bit.ly/3uhJtjj",
]
TIMEOUT = (5, 12)
MAX_HTML_BYTES = 2_000_000


def safe_get(url, allow_redirects=True):
    return requests.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=allow_redirects,
        headers={"User-Agent": "IRFEN-v0.8-scientific-probe/1.0"},
    )


def classify_candidate(url):
    low = url.lower()
    if any(x in low for x in (".json", "geojson", "/api/", "?f=json", "format=json")):
        return "json_or_api_candidate"
    if any(x in low for x in (".csv", "format=csv")):
        return "csv_candidate"
    if any(x in low for x in ("featureserver", "mapserver", "arcgis", "geoserver", "wfs")):
        return "gis_service_candidate"
    return None


def main():
    generated = datetime.now(timezone.utc).isoformat()
    attempts = []
    final = None

    for start in START_URLS:
        row = {"start_url": start}
        try:
            r = safe_get(start)
            row.update({
                "status_code": r.status_code,
                "final_url": r.url,
                "content_type": r.headers.get("content-type"),
                "redirect_chain": [x.url for x in r.history] + [r.url],
            })
            attempts.append(row)
            if r.ok and "text/html" in (r.headers.get("content-type") or "").lower():
                final = r
                break
        except Exception as exc:
            row["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
            attempts.append(row)

    candidates = []
    html_meta = None
    if final is not None:
        raw = final.content[:MAX_HTML_BYTES]
        text = raw.decode(final.encoding or "utf-8", errors="ignore")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        html_meta = {
            "url": final.url,
            "title": re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None,
            "bytes_inspected": len(raw),
        }
        # Solo recursos referenciados por la propia página final. Máximo 25.
        urls = []
        for match in re.finditer(r"(?:src|href)=[\"']([^\"']+)[\"']", text, re.I):
            u = urljoin(final.url, match.group(1))
            if u.startswith("http") and u not in urls:
                urls.append(u)
        for u in urls[:100]:
            kind = classify_candidate(u)
            if kind:
                candidates.append({"url": u, "kind": kind})
                if len(candidates) >= 25:
                    break

    # Probar solo candidatos estructurados directos encontrados en la página.
    probed = []
    for c in candidates[:10]:
        try:
            r = safe_get(c["url"])
            ct = (r.headers.get("content-type") or "").lower()
            probed.append({
                **c,
                "http_status": r.status_code,
                "content_type": r.headers.get("content-type"),
                "final_url": r.url,
                "structured_response": any(x in ct for x in ("json", "csv", "geo+json")),
                "bytes": len(r.content),
            })
        except Exception as exc:
            probed.append({**c, "error": {"type": type(exc).__name__, "message": str(exc)[:300]}})

    usable = [x for x in probed if x.get("structured_response") and x.get("http_status") == 200]
    if usable:
        status = "STRUCTURED_CHANNEL_CANDIDATE_FOUND"
        next_action = "Review candidate schema and verify Pedregal Koica station before any integration."
    elif final is not None:
        status = "PUBLIC_PLATFORM_REACHED_NO_OBVIOUS_STRUCTURED_CHANNEL"
        next_action = "Stop endpoint exploration. Use ISAAC as official external/manual verification unless SENAMHI provides a documented data interface."
    else:
        status = "OFFICIAL_SHORTLINK_NOT_REACHABLE_FROM_GITHUB"
        next_action = "Stop endpoint exploration. Keep ISAAC as an official external/manual verification source."

    result = {
        "version": "0.8-experimental",
        "generated_at": generated,
        "production_use": False,
        "production_ready": False,
        "purpose": "Bounded technical check for a documented machine-readable ISAAC/SENAMHI rainfall channel.",
        "official_context": {
            "institution": "SENAMHI",
            "platform": "ISAAC - Monitoreo de lluvias intensas en la región Lima frente a la activación de quebradas",
            "official_news_url": "https://www.gob.pe/institucion/senamhi/noticias/1331936-plataforma-isaac-del-senamhi-monitorea-de-forma-continua-lluvias-que-puedan-activar-quebradas-en-chosica-y-chaclacayo",
            "target_station_named_by_senamhi": "Pedregal Koica",
            "regular_update_times_local": ["08:30", "19:30"],
            "event_update_frequency": "up to hourly during significant rainfall",
        },
        "status": status,
        "attempts": attempts,
        "page": html_meta,
        "structured_candidates_found": candidates,
        "candidate_probes": probed,
        "usable_structured_candidates": usable,
        "next_action": next_action,
        "stop_rule": "Do not continue blind endpoint enumeration after this bounded probe.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": status,
        "page": html_meta,
        "usable_count": len(usable),
        "next_action": next_action,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
