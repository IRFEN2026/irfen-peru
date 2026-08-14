#!/usr/bin/env python3
"""Indexa evidencia del IGP 2023 sobre precipitación histórica en Chosica/Huaycoloro.

Busca tanto la brecha del evento Chosica 23/03/2015 como una posible fecha
exacta documentada para Huaycoloro/Jicamarca 2012. Guarda páginas, términos y
candidatos numéricos; no republica el PDF ni ajusta umbrales automáticamente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import tempfile

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/calibration/chosica_igp_precip_2023_index.json"
URL = "https://repositorio.igp.gob.pe/bitstreams/7ab825b4-0aca-4275-95a8-4243998bbe4c/download"
ITEM = "https://repositorio.igp.gob.pe/items/58daab07-5d95-49d2-9d8b-e1fc0bd57111"
MAX_BYTES = 25 * 1024 * 1024

CATEGORIES = {
    "event_2015": ["2015", "23 de marzo", "23/03/2015", "23-03-2015"],
    "event_2012": ["2012", "05/04/2012", "5/04/2012", "5 de abril de 2012", "05 de abril de 2012"],
    "chosica": ["chosica", "lurigancho"],
    "chaclacayo": ["chaclacayo"],
    "huaycoloro": ["huaycoloro"],
    "jicamarca": ["jicamarca"],
    "cajamarquilla": ["cajamarquilla"],
    "matucana": ["matucana"],
    "santa_eulalia": ["santa eulalia"],
    "nana": ["ñaña", "nana"],
    "rainfall": ["precipitación", "precipitacion", "lluvia"],
    "station": ["estación", "estacion", "pluviómetro", "pluviometro"],
    "debris_flow": ["flujo de detritos", "huaico", "huayco", "quebrada"],
    "pedregal": ["pedregal"],
    "quiro": ["quirio"],
    "corrales": ["corrales"],
    "libertad": ["la libertad"],
}


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def rainfall_tokens(text):
    out = []
    patterns = [
        r"(?<!\d)(\d{1,4}(?:[.,]\d{1,3})?)\s*mm\b",
        r"(?<!\d)(\d{1,4}(?:[.,]\d{1,3})?)\s*mm\s*/\s*(?:h|hora|día|dia)",
        r"(?<!\d)(\d{1,4}(?:[.,]\d{1,3})?)\s*mil[ií]metros?",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            token = m.group(1)
            if token not in out:
                out.append(token)
    return out[:80]


def date_tokens(text):
    values = []
    patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}\b",
        r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(?:19|20)\d{2}\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            value = norm(m.group(0))
            if value not in values:
                values.append(value)
    return values[:80]


def main():
    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "source": {
            "title": "Análisis y evaluación histórica de precipitaciones en Chaclacayo, Chosica y áreas aledañas",
            "publisher": "Instituto Geofísico del Perú",
            "year": 2023,
            "item_url": ITEM,
            "download_url": URL,
        },
        "purpose": "Investigar la baja captura IMERG del evento 23/03/2015 y resolver, si la evidencia lo permite, una fecha exacta del evento Huaycoloro/Jicamarca 2012.",
        "status": "starting",
        "page_index": {},
        "pages_with_2015_and_rainfall": [],
        "pages_with_2012_huaycoloro_context": [],
        "date_candidates_2012_huaycoloro_context": [],
        "pages_with_station_and_rainfall": [],
        "rainfall_value_candidates": [],
        "date_candidates": [],
        "warning": "Índice documental. Una fecha candidata solo puede pasar al catálogo histórico si coincide en la misma página con Huaycoloro/Jicamarca/Cajamarquilla y el contexto de evento; los valores de lluvia requieren validar estación y periodo.",
    }

    headers = {"User-Agent": "Mozilla/5.0 IRFEN-research/0.8"}
    try:
        r = requests.get(URL, headers=headers, timeout=(20, 180), stream=True)
        r.raise_for_status()
        with tempfile.TemporaryDirectory(prefix="irfen_igp_chosica_") as td:
            pdf = Path(td) / "igp_chosica_2023.pdf"
            total = 0
            with pdf.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise RuntimeError(f"PDF excede límite seguro de {MAX_BYTES} bytes")
                    f.write(chunk)
            report["download_bytes"] = total
            reader = PdfReader(str(pdf))
            report["page_count"] = len(reader.pages)
            pages = {k: [] for k in CATEGORIES}
            rain_candidates = []
            dates = []
            page_dates = {}
            page_categories = {}
            text_pages = 0

            for pageno, page in enumerate(reader.pages, start=1):
                try:
                    raw = page.extract_text() or ""
                except Exception:
                    raw = ""
                if not raw.strip():
                    continue
                text_pages += 1
                low = raw.lower()
                hit_categories = []
                for key, needles in CATEGORIES.items():
                    if any(n.lower() in low for n in needles):
                        pages[key].append(pageno)
                        hit_categories.append(key)
                page_categories[pageno] = sorted(hit_categories)
                tokens = rainfall_tokens(raw)
                for token in tokens:
                    rain_candidates.append({
                        "page": pageno,
                        "value_text": token,
                        "unit": "mm_or_mm_rate_unresolved",
                        "page_categories": sorted(hit_categories),
                        "validated_period": False,
                        "validated_station": False,
                    })
                pd = date_tokens(raw)
                page_dates[pageno] = pd
                for value in pd:
                    dates.append({"page": pageno, "date_text": value, "page_categories": sorted(hit_categories)})

            report["text_layer_pages"] = text_pages
            report["page_index"] = {k: {"pages": v, "page_count": len(v)} for k, v in pages.items() if v}

            s2015 = set(pages.get("event_2015", []))
            s2012 = set(pages.get("event_2012", []))
            srain = set(pages.get("rainfall", []))
            sstation = set(pages.get("station", []))
            shuay = set(pages.get("huaycoloro", [])) | set(pages.get("jicamarca", [])) | set(pages.get("cajamarquilla", []))
            sdebris = set(pages.get("debris_flow", []))

            report["pages_with_2015_and_rainfall"] = sorted(s2015 & srain)
            report["pages_with_station_and_rainfall"] = sorted(sstation & srain)
            candidate_pages = sorted(s2012 & shuay & sdebris)
            report["pages_with_2012_huaycoloro_context"] = candidate_pages
            report["date_candidates_2012_huaycoloro_context"] = [
                {
                    "page": p,
                    "dates": [d for d in page_dates.get(p, []) if "2012" in d],
                    "page_categories": page_categories.get(p, []),
                    "same_page_huaycoloro_or_jicamarca": True,
                    "same_page_debris_flow_context": True,
                    "validated_event_date": False,
                }
                for p in candidate_pages
                if any("2012" in d for d in page_dates.get(p, []))
            ]
            report["rainfall_value_candidates"] = rain_candidates[:250]
            report["date_candidates"] = dates[:250]
            report["status"] = "indexed_for_calibration_review" if text_pages else "downloaded_without_text_layer"
    except Exception as exc:
        report["status"] = "download_or_parse_error"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "page_count": report.get("page_count"),
        "pages_with_2015_and_rainfall": report.get("pages_with_2015_and_rainfall"),
        "pages_with_2012_huaycoloro_context": report.get("pages_with_2012_huaycoloro_context"),
        "date_candidates_2012_huaycoloro_context": report.get("date_candidates_2012_huaycoloro_context"),
        "rainfall_value_candidate_count": len(report.get("rainfall_value_candidates", [])),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
