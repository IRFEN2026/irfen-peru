#!/usr/bin/env python3
"""Indexa evidencia del PPRRD Catacaos 2026-2030 publicado en SIGRID.

Descarga temporalmente el PDF oficial, identifica páginas útiles para el modelo
fluvial y guarda solo metadatos, páginas y candidatos numéricos sin párrafos del
documento. Ninguna referencia se convierte automáticamente en umbral operativo.
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
OUT = ROOT / "site/data/hydrology/catacaos_pprrd_2026_discovery.json"
URL = "https://sigrid.cenepred.gob.pe/sigridv3/documento/22172/descargar"
PAGE_URL = "https://sigrid.cenepred.gob.pe/sigridv3/documento/22172"
MAX_BYTES = 70 * 1024 * 1024

TERMS = {
    "river_flood": ["desborde del río piura", "desborde del rio piura", "inundación fluvial", "inundacion fluvial"],
    "pluvial_flood": ["inundación pluvial", "inundacion pluvial", "drenaje pluvial"],
    "exposure": ["población expuesta", "poblacion expuesta", "elementos expuestos", "viviendas expuestas"],
    "critical_points": ["puntos críticos", "puntos criticos", "sector crítico", "sector critico"],
    "risk_levels": ["riesgo muy alto", "riesgo alto", "peligro muy alto", "peligro alto"],
    "river_flow": ["m3/s", "m³/s", "caudal"],
    "evacuation": ["evacuación", "evacuacion", "refugio"],
    "defenses": ["defensa ribereña", "defensa riberena", "dique", "enrocado"],
}


def normalize(text):
    return re.sub(r"\s+", " ", text or " ").strip()


def main():
    headers = {"User-Agent": "Mozilla/5.0 IRFEN-research/0.8"}
    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "source": {
            "title": "Plan de prevención y reducción del riesgo de desastres del distrito de Catacaos 2026-2030",
            "publisher": "Municipalidad Distrital de Catacaos / SIGRID-CENEPRED",
            "year": 2026,
            "document_page": PAGE_URL,
            "download_url": URL,
        },
        "status": "starting",
        "page_index": {},
        "numeric_candidates": [],
        "warning": "Índice documental para revisión científica. No contiene extractos extensos y ningún número se convierte automáticamente en umbral o capacidad hidráulica.",
    }

    with tempfile.TemporaryDirectory(prefix="irfen_pprrd_") as td:
        pdf = Path(td) / "catacaos_pprrd_2026.pdf"
        with requests.get(URL, stream=True, timeout=(20, 180), headers=headers) as r:
            r.raise_for_status()
            total = 0
            with pdf.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise RuntimeError(f"PPRRD excede límite seguro de {MAX_BYTES} bytes")
                    f.write(chunk)
        report["download_bytes"] = total

        reader = PdfReader(str(pdf))
        report["page_count"] = len(reader.pages)
        page_hits = {k: set() for k in TERMS}
        match_counts = {k: 0 for k in TERMS}
        numeric = []

        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = normalize(page.extract_text() or "")
            except Exception:
                continue
            if not text:
                continue
            low = text.lower()
            for category, needles in TERMS.items():
                hits = sum(low.count(n.lower()) for n in needles)
                if hits:
                    page_hits[category].add(idx)
                    match_counts[category] += hits

            # Candidatos numéricos de caudal: valor y página, sin copiar contexto.
            for m in re.finditer(r"(\d{2,5}(?:[.,]\d+)?)\s*(?:m3/s|m³/s)", text, flags=re.I):
                if len(numeric) >= 80:
                    break
                value_text = m.group(1)
                numeric.append({
                    "page": idx,
                    "value_text": value_text,
                    "unit": "m3/s",
                    "validated_meaning": False,
                    "page_categories": sorted(k for k, pages in page_hits.items() if idx in pages),
                })

        report["page_index"] = {
            category: {
                "pages": sorted(pages)[:80],
                "page_count": len(pages),
                "match_count": match_counts[category],
            }
            for category, pages in page_hits.items() if pages
        }
        report["numeric_candidates"] = numeric
        report["status"] = "indexed_for_scientific_review"
        report["categories_found"] = sorted(report["page_index"].keys())

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "download_bytes": report.get("download_bytes"),
        "page_count": report.get("page_count"),
        "categories_found": report.get("categories_found"),
        "numeric_candidates": len(report.get("numeric_candidates", [])),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
