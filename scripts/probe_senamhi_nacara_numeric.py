#!/usr/bin/env python3
"""Prueba acceso numérico oficial SENAMHI/PHISIS para Puente Ñácara.

No integra valores al modelo. Intenta únicamente descubrir si el HTML oficial
de monitoreo expone series numéricas que puedan extraerse de forma estable
desde GitHub Actions. Todo resultado se guarda como evidencia experimental.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import html
import json
import re

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/hydrology/senamhi_nacara_numeric_probe.json"
STATION_ID = "47E0415A"
BASE = "https://www.senamhi.gob.pe"


def get(url, timeout=35):
    headers = {
        "User-Agent": "IRFEN-v0.8-scientific-probe/1.0 (+https://github.com/IRFEN2026/irfen-peru)",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    return r


def compact(text, n=1200):
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n]


def extract_candidates(text):
    """Extrae candidatos numéricos sin asumir cuál representa el caudal actual."""
    decoded = html.unescape(text or "")
    out = []

    # Frases explícitas con caudal y unidades.
    patterns = [
        r"(?:CAUDAL|Caudal|caudal)[^0-9]{0,80}([0-9]+(?:[\.,][0-9]+)?)\s*(?:m3/s|m³/s|m3\/s)",
        r"([0-9]+(?:[\.,][0-9]+)?)\s*(?:m3/s|m³/s|m3\/s)[^<\n]{0,80}",
    ]
    for pat in patterns:
        for m in re.finditer(pat, decoded, flags=re.I):
            raw = m.group(1).replace(",", ".")
            try:
                value = float(raw)
            except Exception:
                continue
            ctx = compact(decoded[max(0, m.start()-120):m.end()+120], 360)
            out.append({"value": value, "unit": "m3/s", "context": ctx, "method": "explicit_unit_regex"})

    # Estructuras JS típicas Highcharts / arrays de series.
    for m in re.finditer(r"(?:data|series)\s*[:=]\s*(\[[^;]{20,5000}\])", decoded, flags=re.I|re.S):
        chunk = m.group(1)
        if "Date.UTC" in chunk or "timestamp" in chunk.lower() or "caudal" in decoded[max(0,m.start()-400):m.start()].lower():
            out.append({"method": "javascript_series_fragment", "fragment": compact(chunk, 1400)})
            if len(out) >= 25:
                break

    # Deduplicar valores explícitos.
    seen = set(); dedup = []
    for item in out:
        key = (item.get("method"), item.get("value"), item.get("context"), item.get("fragment"))
        if key in seen:
            continue
        seen.add(key); dedup.append(item)
    return dedup[:30]


def main():
    now = datetime.now(timezone.utc)
    local_guess = now - timedelta(hours=5)  # Perú UTC-5, solo para formar fecha de consulta.
    fecha_hora = local_guess.strftime("%Y-%m-%d %H:00:00")

    urls = [
        (
            "station_chart_current",
            BASE + "/mapas/mapa-monitoreohidro/include/mnt-grafica-new.php"
            + f"?fecha_hora={requests.utils.quote(fecha_hora)}&id={STATION_ID}&variable=CAUDAL&variable_opcion=C",
        ),
        (
            "piura_monitoring",
            BASE + "/servicios/main.php?dp=piura&p=monitoreo-piura",
        ),
        (
            "daily_hydrology",
            BASE + "/servicios/main.php?dp=piura&p=monitoreo-informacion-diaria",
        ),
    ]

    probes = []
    for name, url in urls:
        row = {"name": name, "url": url}
        try:
            r = get(url)
            row.update({
                "http_status": r.status_code,
                "final_url": r.url,
                "content_type": r.headers.get("content-type"),
                "content_length": len(r.content),
                "contains_station_id": STATION_ID in r.text,
                "contains_nacara": bool(re.search(r"[ÑNn]acara|[ÑNn]ácara", r.text, flags=re.I)),
                "contains_caudal": "caudal" in r.text.lower(),
                "candidate_count": len(extract_candidates(r.text)),
                "candidates": extract_candidates(r.text),
                "html_excerpt": compact(r.text, 1800),
            })
        except Exception as exc:
            row.update({
                "http_status": None,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
        probes.append(row)

    explicit = []
    for p in probes:
        for c in p.get("candidates", []):
            if c.get("method") == "explicit_unit_regex" and c.get("value") is not None:
                explicit.append({"source_probe": p["name"], **c})

    # Importante: no asumir que un valor hallado es el último caudal solo porque
    # aparece en el HTML. Esa homologación requiere timestamp/serie inequívocos.
    result = {
        "version": "0.8-experimental",
        "generated_at": now.isoformat(),
        "production_use": False,
        "production_ready": False,
        "station": "Puente Ñácara",
        "station_id": STATION_ID,
        "river": "Río Piura",
        "query_local_time_assumption": "UTC-5",
        "query_fecha_hora": fecha_hora,
        "status": "NUMERIC_CANDIDATES_FOUND_NEED_SEMANTIC_VALIDATION" if explicit else "NO_UNAMBIGUOUS_NUMERIC_VALUE_FOUND",
        "numeric_river_state_available": False,
        "explicit_numeric_candidates": explicit,
        "probes": probes,
        "scientific_gate": {
            "status": "AUTOMATIC_NUMERIC_ACCESS_UNRESOLVED",
            "rule": "No marcar numeric_river_state_available=true hasta asociar de forma inequívoca valor, timestamp, estación y variable desde una respuesta oficial estable.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "explicit_numeric_candidates": explicit[:8],
        "probes": [
            {k: p.get(k) for k in ("name","http_status","content_length","candidate_count","error_type")}
            for p in probes
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
