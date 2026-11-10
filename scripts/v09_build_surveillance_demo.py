#!/usr/bin/env python3
"""IRFEN v0.9 · versión de un solo archivo de la vista privada de vigilancia, para abrirla en un alojamiento privado
(p. ej. una página privada de claude.ai) o directamente desde el disco. RESEARCH_ONLY / TEST_ONLY.

Toma site/v09/vigilancia.html y site/data/v09/surveillance_view_v0_1.json y escribe
research/v09/private_demo/irfen_vigilancia_privada.html con:
* el paquete de datos incrustado (<script id="bundle" type="application/json">), sin peticiones a la carpeta de datos;
* la hoja de estilos de Leaflet 1.9.4 incrustada solo si se pasa `--leaflet-css` y su SHA-256 coincide con el hash SRI
  publicado (los alojamientos con CSP estricta no admiten hojas de estilo externas);
* sin mapa base externo (la página lo omite en modo de un solo archivo) y sin enrutamiento por fragmento.
No está en site/: la puerta de Pages no lo necesita y nunca se publica desde aquí.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site/v09/vigilancia.html"
BUNDLE = ROOT / "site/data/v09/surveillance_view_v0_1.json"
OUT = ROOT / "research/v09/private_demo/irfen_vigilancia_privada.html"
LEAFLET_CSS_SRI = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="


def build(leaflet_css: Path | None, fragment: bool) -> str:
    html = PAGE.read_text(encoding="utf-8")
    data = BUNDLE.read_text(encoding="utf-8").strip().replace("</", "<\\/")
    link = re.search(r'<link rel="stylesheet" href="https://unpkg\.com/leaflet@1\.9\.4/dist/leaflet\.css"[^>]*>', html).group(0)
    css = ""
    if leaflet_css:
        raw = leaflet_css.read_bytes()
        sri = "sha256-" + base64.b64encode(hashlib.sha256(raw).digest()).decode()
        if sri != LEAFLET_CSS_SRI:
            raise SystemExit(f"leaflet.css does not match the published SRI hash ({sri})")
        css = "<style>/* Leaflet 1.9.4 (BSD-2-Clause), verified against " + LEAFLET_CSS_SRI + " */\n" + raw.decode("utf-8") + "</style>"
    html = html.replace(link, css)
    html = html.replace('<script id="app">', '<script id="bundle" type="application/json">' + data + '</script>\n<script id="app">', 1)
    if fragment:  # hosts that add their own document skeleton: keep only title, styles, scripts and body content
        head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
        body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
        head = re.sub(r'<meta charset="utf-8">|<meta name="viewport"[^>]*>', "", head)
        html = head + "\n" + body
    return html


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--leaflet-css", type=Path)
    ap.add_argument("--fragment", action="store_true", help="omit doctype/html/head/body wrappers")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    text = build(a.leaflet_css, a.fragment)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    print(f"{a.out} · {len(text.encode()) / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
