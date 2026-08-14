#!/usr/bin/env python3
"""Extrae evidencia trazable del PPRRD Catacaos 2026-2030 publicado en SIGRID.

Descarga temporalmente el PDF oficial, busca conceptos útiles para el modelo
fluvial y guarda solo metadatos/contextos breves con páginas. No republica el
PDF ni convierte automáticamente sus referencias en umbrales operativos.
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


def snippets(text, needles, limit=4, radius=220):
    low = text.lower()
    found = []
    seen = set()
    for needle in needles:
        start = 0
        n = needle.lower()
        while len(found) < limit:
            idx = low.find(n, start)
            if idx < 0:
                break
            a = max(0, idx - radius)
            b = min(len(text), idx + len(n) + radius)
            s = normalize(text[a:b])
            key = s[:120]
            if key not in seen:
                seen.add(key)
                found.append(s)
            start = idx + len(n)
    return found


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
        "evidence": {},
        "numeric_candidates": [],
        "warning": "Los extractos son evidencia documental para revisión; ningún número se convierte automáticamente en umbral o capacidad hidráulica.",
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
        evidence = {k: [] for k in TERMS}
        numeric = []

        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = normalize(page.extract_text() or "")
            except Exception as exc:
                continue
            if not text:
                continue
            low = text.lower()
            for category, needles in TERMS.items():
                if not any(n.lower() in low for n in needles):
                    continue
                for s in snippets(text, needles):
                    if len(evidence[category]) >= 12:
                        break
                    evidence[category].append({"page": idx, "context": s})

            # Candidatos numéricos de caudal: solo para revisión manual posterior.
            for m in re.finditer(r"(.{0,100})(\d{2,5}(?:[.,]\d+)?)\s*(?:m3/s|m³/s)(.{0,140})", text, flags=re.I):
                if len(numeric) >= 40:
                    break
                val = m.group(2).replace(",", ".")
                numeric.append({
                    "page": idx,
                    "value_text": m.group(2),
                    "unit": "m3/s",
                    "context": normalize(m.group(0)),
                    "validated_meaning": False,
                })

        report["evidence"] = {k: v for k, v in evidence.items() if v}
        report["numeric_candidates"] = numeric
        report["status"] = "extracted_for_scientific_review"
        report["categories_found"] = sorted(report["evidence"].keys())

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
