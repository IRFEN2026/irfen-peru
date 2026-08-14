#!/usr/bin/env python3
"""Descubre fichas ANA 2026 de puntos críticos relevantes para Catacaos/Bajo Piura.

Descarga temporalmente paquetes oficiales SIGRID, lista sus archivos y usa solo
la capa de texto ya existente en PDFs para localizar referencias territoriales.
No usa OCR, no republica archivos y no convierte fichas en alertas o umbrales.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import re
import tempfile
import zipfile

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/hydrology/ana_piura_critical_points_2026.json"
MAX_DOWNLOAD = 120 * 1024 * 1024

DOCUMENTS = [
    {"id": 21411, "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/21411/descargar?boletin=578", "office": "0127-2026-ANA-J"},
    {"id": 22176, "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/22176/descargar", "office": "0774-2026-ANA-J"},
    {"id": 22191, "url": "https://sigrid.cenepred.gob.pe/sigridv3/documento/22191/descargar", "office": "0788-2026-ANA-J"},
]

TERRITORY = {
    "catacaos": ["catacaos"],
    "la_legua": ["la legua"],
    "simbila": ["simbilá", "simbila"],
    "pedregal_grande": ["pedregal grande"],
    "cura_mori": ["cura mori"],
    "bajo_piura": ["bajo piura"],
    "rio_piura": ["río piura", "rio piura"],
}


def clean_name(name):
    return name.replace("\\", "/").split("/")[-1]


def download(url, headers):
    r = requests.get(url, timeout=(20, 150), headers=headers)
    r.raise_for_status()
    data = r.content
    if len(data) > MAX_DOWNLOAD:
        raise RuntimeError(f"Descarga excede límite de {MAX_DOWNLOAD} bytes")
    return data, r.headers.get("content-type", "")


def page_hits(pdf_path):
    hits = {k: [] for k in TERRITORY}
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return hits, 0, False
    had_text = False
    for pageno, page in enumerate(reader.pages, start=1):
        try:
            text = re.sub(r"\s+", " ", page.extract_text() or " ").lower()
        except Exception:
            continue
        if not text.strip():
            continue
        had_text = True
        for key, needles in TERRITORY.items():
            if any(n in text for n in needles):
                hits[key].append(pageno)
    return {k: v for k, v in hits.items() if v}, len(reader.pages), had_text


def relevant_from_name(name):
    low = name.lower()
    return sorted(k for k, needles in TERRITORY.items() if any(n in low for n in needles))


def process_pdf(path, source_doc, member_name=None):
    hits, pages, text_layer = page_hits(path)
    name = member_name or path.name
    name_hits = relevant_from_name(name)
    relevant = bool(hits or name_hits)
    return {
        "source_document_id": source_doc["id"],
        "office": source_doc["office"],
        "source_page": f"https://sigrid.cenepred.gob.pe/sigridv3/documento/{source_doc['id']}",
        "file_name": clean_name(name),
        "page_count": pages,
        "text_layer_available": text_layer,
        "territory_hits_from_filename": name_hits,
        "territory_page_hits": hits,
        "relevant_to_catacaos_model": relevant,
        "production_use": False,
    }


def main():
    headers = {"User-Agent": "Mozilla/5.0 IRFEN-research/0.8"}
    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "status": "starting",
        "purpose": "Descubrir fichas ANA 2026 relacionadas con Catacaos/Bajo Piura sin asumir que todo punto crítico de Piura afecta Catacaos.",
        "documents": [],
        "relevant_files": [],
        "warning": "Los resultados son un índice de documentos. Una coincidencia territorial no equivale a un polígono de peligro ni a un umbral operativo."
    }

    with tempfile.TemporaryDirectory(prefix="irfen_ana_piura_") as td:
        work = Path(td)
        for doc in DOCUMENTS:
            item = {"document_id": doc["id"], "office": doc["office"], "download_url": doc["url"]}
            try:
                data, content_type = download(doc["url"], headers)
                item["download_bytes"] = len(data)
                item["content_type"] = content_type
                item["files"] = []

                if zipfile.is_zipfile(BytesIO(data)):
                    item["container"] = "zip"
                    with zipfile.ZipFile(BytesIO(data)) as z:
                        members = [m for m in z.namelist() if not m.endswith("/")]
                        item["member_count"] = len(members)
                        for idx, member in enumerate(members):
                            name = clean_name(member)
                            meta = {"file_name": name, "extension": Path(name).suffix.lower(), "territory_hits_from_filename": relevant_from_name(name)}
                            item["files"].append(meta)
                            if Path(name).suffix.lower() != ".pdf":
                                continue
                            raw = z.read(member)
                            p = work / f"{doc['id']}_{idx}.pdf"
                            p.write_bytes(raw)
                            result = process_pdf(p, doc, member)
                            if result["relevant_to_catacaos_model"]:
                                report["relevant_files"].append(result)
                elif data[:4] == b"%PDF":
                    item["container"] = "pdf"
                    p = work / f"{doc['id']}.pdf"
                    p.write_bytes(data)
                    result = process_pdf(p, doc)
                    item["files"].append({"file_name": p.name, "extension": ".pdf"})
                    if result["relevant_to_catacaos_model"]:
                        report["relevant_files"].append(result)
                else:
                    item["container"] = "unknown"
                    item["error"] = "Formato descargado no reconocido como ZIP/PDF"
            except Exception as exc:
                item["status"] = "error"
                item["error_type"] = type(exc).__name__
                item["error"] = str(exc)
            else:
                item["status"] = "processed"
            report["documents"].append(item)

    report["status"] = "discovered" if report["relevant_files"] else "processed_no_catacaos_match_yet"
    report["relevant_file_count"] = len(report["relevant_files"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "documents": [{"id": x["document_id"], "status": x.get("status"), "container": x.get("container"), "members": x.get("member_count")} for x in report["documents"]],
        "relevant_file_count": report["relevant_file_count"],
        "relevant_files": report["relevant_files"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
