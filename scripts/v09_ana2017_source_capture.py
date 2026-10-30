#!/usr/bin/env python3
"""Captura reproducible del documento ANA 2016-2017 «Complementación de identificación de poblaciones vulnerables por
activación de quebradas» (SINIA/MINAM). Guarda el registro de la descarga (URL, cabeceras, tamaño, SHA-256, fecha) y el
texto de cada página extraído con pypdf (modo «layout», que conserva las columnas de los cuadros). No interpreta nada:
el análisis de los cuadros lo hace scripts/v09_ana2017_coastal_points.py sobre este texto. RESEARCH_ONLY / TEST_ONLY.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/ana2017_complementacion_quebradas"
URL = "https://sinia.minam.gob.pe/sites/default/files/sial-sialtrujillo/archivos/public/docs/ana2017.pdf"


def main() -> int:
    from pypdf import PdfReader
    req = Request(URL, headers={"User-Agent": "IRFEN-research/0.9 (+https://github.com/IRFEN2026/irfen-peru; TEST_ONLY)"})
    with urlopen(req, timeout=180) as r:
        data = r.read()
        headers = {k.lower(): v for k, v in r.headers.items() if k.lower() in ("content-type", "content-length", "last-modified", "etag", "date")}
        final_url = r.geturl()
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text(extraction_mode="layout")
        except Exception as exc:  # noqa: BLE001 - recorded, never silently skipped
            text, err = "", f"{type(exc).__name__}: {exc}"
        else:
            err = None
        pages.append(dict(page=i, chars=len(text), text=text, error=err))
    OUT.mkdir(parents=True, exist_ok=True)
    record = dict(source_id="ANA-2016-COMPLEMENTACION-NACIONAL", url=URL, final_url=final_url, http_headers=headers,
                  size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  retrieved_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                  pdf_pages=len(reader.pages), extractor="pypdf extract_text(extraction_mode='layout')",
                  pdf_metadata={k: str(v) for k, v in (reader.metadata or {}).items()},
                  pages_with_text=sum(1 for p in pages if p["chars"] > 50),
                  note="The PDF itself is not committed (public source); its SHA-256 identifies the exact bytes read.")
    (OUT / "source_record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "pages_text.json").write_text(json.dumps(pages, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"::notice title=ANA2017::pages={len(pages)} with_text={record['pages_with_text']} sha256={record['sha256']} bytes={len(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
