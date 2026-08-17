#!/usr/bin/env python3
"""Indexa evidencia del PPRRD Catacaos 2026-2030 publicado en SIGRID.

Descarga temporalmente el PDF oficial, identifica páginas útiles para el modelo
fluvial y guarda solo metadatos, páginas y candidatos numéricos sin párrafos del
documento. Ninguna referencia se convierte automáticamente en umbral operativo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/hydrology/catacaos_pprrd_2026_discovery.json"
URL = "https://sigrid.cenepred.gob.pe/sigridv3/documento/22172/descargar"
PAGE_URL = "https://sigrid.cenepred.gob.pe/sigridv3/documento/22172"
MAX_BYTES = 70 * 1024 * 1024
# El PDF oficial es escaneado. Se acota el OCR a los capítulos de diagnóstico
# hidráulico/riesgo y al anexo cartográfico de puntos críticos; no se necesita
# transcribir las 264 páginas para localizar evidencia de los bloqueos v0.8.
OCR_PAGE_RANGES = ((60, 140), (228, 240))

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


def index_page_texts(page_texts):
    """Build a bounded page index without persisting copyrighted page text."""
    page_hits = {key: set() for key in TERMS}
    match_counts = {key: 0 for key in TERMS}
    numeric = []
    extracted_chars = 0
    for idx, raw_text in enumerate(page_texts, start=1):
        text = normalize(raw_text)
        extracted_chars += len(text)
        if not text:
            continue
        low = text.lower()
        for category, needles in TERMS.items():
            hits = sum(low.count(needle.lower()) for needle in needles)
            if hits:
                page_hits[category].add(idx)
                match_counts[category] += hits
        for match in re.finditer(r"(\d{2,5}(?:[.,]\d+)?)\s*(?:m3/s|m³/s)", text, flags=re.I):
            if len(numeric) >= 80:
                break
            numeric.append({
                "page": idx,
                "value_text": match.group(1),
                "unit": "m3/s",
                "validated_meaning": False,
                "page_categories": sorted(
                    key for key, pages in page_hits.items() if idx in pages
                ),
            })
    page_index = {
        category: {
            "pages": sorted(pages)[:80],
            "page_count": len(pages),
            "match_count": match_counts[category],
        }
        for category, pages in page_hits.items() if pages
    }
    return page_index, numeric, extracted_chars


def ocr_page(image: Path, language: str):
    try:
        completed = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", language],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        return completed.stdout
    finally:
        image.unlink(missing_ok=True)


def ocr_image_only_pdf(pdf: Path, page_count: int, workdir: Path):
    if not shutil.which("pdftoppm") or not shutil.which("tesseract"):
        raise RuntimeError("Image-only PDF requires pdftoppm and tesseract")
    languages = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True, check=True
    ).stdout.split()
    language = "spa" if "spa" in languages else "eng"
    for start, end in OCR_PAGE_RANGES:
        start = max(1, start)
        end = min(page_count, end)
        if start > end:
            continue
        subprocess.run(
            [
                "pdftoppm", "-f", str(start), "-l", str(end),
                "-r", "100", "-png", str(pdf), str(workdir / "page"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
    images = sorted(workdir.glob("page-*.png"))
    expected_pages = sum(
        max(0, min(page_count, end) - max(1, start) + 1)
        for start, end in OCR_PAGE_RANGES
    )
    if len(images) != expected_pages:
        raise RuntimeError(f"Expected {expected_pages} OCR pages, found {len(images)}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        extracted = list(pool.map(lambda image: ocr_page(image, language), images))
    texts = [""] * page_count
    for image, text in zip(images, extracted):
        page_number = int(image.stem.rsplit("-", 1)[1])
        texts[page_number - 1] = text
    return texts, language, len(images)


def main():
    import requests
    from pypdf import PdfReader

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
        page_texts = []
        for page in reader.pages:
            try:
                page_texts.append(page.extract_text() or "")
            except Exception:
                page_texts.append("")
        page_index, numeric, extracted_chars = index_page_texts(page_texts)
        report["embedded_text_chars"] = extracted_chars
        report["extraction_method"] = "EMBEDDED_TEXT"
        if extracted_chars < 1_000:
            page_texts, language, processed_pages = ocr_image_only_pdf(
                pdf, len(reader.pages), Path(td)
            )
            page_index, numeric, ocr_chars = index_page_texts(page_texts)
            report["extraction_method"] = "OCR_IMAGE_ONLY_PDF"
            report["ocr_language"] = language
            report["ocr_pages_processed"] = processed_pages
            report["ocr_page_ranges"] = [list(row) for row in OCR_PAGE_RANGES]
            report["ocr_text_chars"] = ocr_chars

        report["page_index"] = page_index
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
