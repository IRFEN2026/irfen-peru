#!/usr/bin/env python3
"""Extrae, sin modificarlas, las imágenes incrustadas de los cuadros «Centros poblados vulnerables por activación de
quebradas» de los departamentos costeros del documento ANA 2016-2017 (SIGRID 2799). En el PDF estos cuadros son
imágenes: su contenido se transcribe aparte (OCR + verificación visual). RESEARCH_ONLY / TEST_ONLY."""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana2017_complementacion_quebradas"
URL = "https://sigrid.cenepred.gob.pe/sigridv3/documento/2799/descargar"
# PDF page -> (cuadro, departamento) for the coastal departments (page numbers of the PDF file, not the printed ones)
TABLES = {25: (9, "Tumbes"), 27: (11, "Piura"), 32: (17, "Lambayeque"), 35: (19, "La Libertad"), 39: (23, "Ancash"),
          45: (29, "Lima"), 59: (41, "Ica"), 62: (43, "Arequipa"), 68: (47, "Moquegua"), 70: (49, "Tacna")}


def main() -> int:
    from pypdf import PdfReader
    record = json.loads((SRC / "source_record.json").read_text(encoding="utf-8"))
    with urlopen(Request(URL, headers={"User-Agent": "Mozilla/5.0 (IRFEN research TEST_ONLY)"}), timeout=240) as r:
        data = r.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != record["sha256"]:
        print(f"::error title=ANA2017_SHA::downloaded {digest} != recorded {record['sha256']}")
        return 1
    reader = PdfReader(io.BytesIO(data))
    out = SRC / "table_images"
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for page_no, (cuadro, dept) in TABLES.items():
        page = reader.pages[page_no - 1]
        for k, img in enumerate(page.images):
            raw = img.data
            ext = Path(img.name).suffix or ".bin"
            name = f"p{page_no:02d}_cuadro{cuadro}_{dept.lower().replace(' ', '_')}_{k}{ext}"
            (out / name).write_bytes(raw)
            w = h = None
            try:
                w, h = img.image.size
            except Exception:  # noqa: BLE001
                pass
            index.append(dict(file=name, pdf_page=page_no, cuadro=cuadro, department=dept, image_index=k, bytes=len(raw),
                              sha256=hashlib.sha256(raw).hexdigest(), width=w, height=h))
    (SRC / "table_images_index.json").write_text(json.dumps(dict(pdf_sha256=digest, images=index), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=ANA2017_IMAGES::{[(i['file'], i['width'], i['height'], i['bytes']) for i in index]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
