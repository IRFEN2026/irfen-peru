#!/usr/bin/env python3
"""IRFEN v0.9.1 · carpeta desplegable de la vista privada conectada a la rama de datos (RESEARCH_ONLY; NO se despliega aquí).

Genera una carpeta estática (index.html + _headers) que, una vez subida a un alojamiento con control de acceso
(propuesta: Cloudflare Pages + Cloudflare Access, pendiente de autorización), carga el paquete validado de
`research/v091-live-data` y consulta su manifest.json cada 5 min; cuando aparece un ciclo nuevo, el mapa se recarga
solo. La página no necesita volver a desplegarse para cada ciclo: solo cuando cambie su propio código.

    python3 scripts/v091_build_private_site.py --out dist/irfen_v091_private
    python3 scripts/v091_build_private_site.py --out DIR --data-base http://127.0.0.1:PORT/current/   # prueba local

Base por defecto: https://raw.githubusercontent.com/IRFEN2026/irfen-peru/research/v091-live-data/current/
(repositorio público; el control de acceso protege la interfaz, no los datos, que ya son públicos en el repositorio).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://raw.githubusercontent.com/IRFEN2026/irfen-peru/research/v091-live-data/current/"
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; "
       "img-src 'self' data: https://*.basemaps.cartocdn.com https://tile.openstreetmap.org https://unpkg.com; "
       "connect-src 'self' https://raw.githubusercontent.com; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
HEADERS = f"""/*
  X-Robots-Tag: noindex, nofollow
  Referrer-Policy: no-referrer
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Cache-Control: no-store
  Content-Security-Policy: {CSP}
"""


def build(out: Path, base: str) -> dict:
    if not (base.startswith("https://") or re.match(r"^http://127\.0\.0\.1(:\d+)?/", base)):
        raise SystemExit("data base must be https:// (or http://127.0.0.1 for the local test)")
    base = base if base.endswith("/") else base + "/"
    page = (ROOT / "site/v09/vigilancia.html").read_text(encoding="utf-8")
    meta = f'<meta name="irfen-live" content="{html.escape(base, quote=True)}">'
    page = page.replace('<meta name="robots" content="noindex,nofollow">', '<meta name="robots" content="noindex,nofollow">' + meta, 1)
    assert meta in page
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    info = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", public_alerting=False, notifications_enabled=False,
                deployed=False, data_base=base, files=["index.html", "_headers"],
                note_es="Carpeta preparada, no desplegada. Requiere autorización y control de acceso (ver docs/V091_LIVE_REFRESH.md §5).")
    (out / "BUILD_INFO.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-base", default=DEFAULT_BASE)
    a = ap.parse_args(argv)
    print(json.dumps(build(a.out, a.data_base), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
