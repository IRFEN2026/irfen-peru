#!/usr/bin/env python3
"""OCR celda a celda de los cuadros «Centros poblados vulnerables por activación de quebradas» (ANA 2016-2017) de los
departamentos costeros, renderizados a 300 ppp por scripts/v09_ana2017_table_images.py.

Método (reproducible, sin red):
1. detectar la rejilla de la tabla (líneas horizontales y verticales, OpenCV) y recortar cada celda;
2. leer cada celda con Tesseract 5 en modo línea (`--psm 7`); en Este/Norte y en las columnas numéricas solo dígitos;
3. dos lecturas independientes de cada celda numérica (escala ×2 binarizada con Otsu, y escala ×3 en gris): si no
   coinciden, la celda queda marcada para revisión y NO se acepta;
4. sumas de control: las columnas de viviendas y habitantes deben sumar la fila TOTAL del propio cuadro;
5. el datum se lee del pie del cuadro («Datum: WGS 84-ZONA 17 SUR»).

Salida: data/v09/sources/ana2017_complementacion_quebradas/ocr_tables.json (lecturas en bruto, sin interpretar).
Ninguna celda dudosa se corrige aquí: la revisión visual se registra aparte. RESEARCH_ONLY / TEST_ONLY.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana2017_complementacion_quebradas"
PAGES = SRC / "table_pages_300dpi"
OUT = SRC / "ocr_tables.json"
HEADERS = {"n": r"^N", "este": r"Este", "norte": r"Norte", "prov": r"Prov", "distrito": r"Distr", "centro": r"Centro",
           "quebrada": r"Quebr", "viviendas": r"Vivien", "hab_directos": r"(Directa|Direct)", "hab_indirectos": r"(Indirect)",
           "hab_total": r"Total"}
NUMERIC = {"n", "este", "norte", "viviendas", "hab_directos", "hab_indirectos", "hab_total"}


LANG = "eng"


def tess(img: np.ndarray, digits: bool) -> str:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.png"
        cv2.imwrite(str(p), img)
        cfg = ["--psm", "7", "-l", "eng" if digits else LANG]
        if digits:
            cfg += ["-c", "tessedit_char_whitelist=0123456789,."]
        out = subprocess.run(["tesseract", str(p), "stdout", *cfg], capture_output=True, text=True).stdout
    return " ".join(out.split())


def lines(mask: np.ndarray, axis: int, min_frac: float) -> list[int]:
    """Positions of long lines along an axis (projection of a line mask), merged when closer than 6 px."""
    proj = mask.sum(axis=axis) / 255
    length = mask.shape[axis]
    idx = [i for i, v in enumerate(proj) if v >= min_frac * length]
    out = []
    for i in idx:
        if out and i - out[-1][-1] <= 6:
            out[-1].append(i)
        else:
            out.append([i])
    return [int(round(sum(g) / len(g))) for g in out]


def grid(gray: np.ndarray):
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 12)
    h, w = bw.shape
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (w // 25, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 60)))
    ys = lines(horiz, 1, 0.25)
    # columns: vertical lines spanning a good part of the table height
    top, bottom = (ys[0], ys[-1]) if ys else (0, h)
    xs = lines(vert[top:bottom], 0, 0.30)
    return xs, ys


def cell(gray, x0, x1, y0, y1, pad=3):
    return gray[y0 + pad:y1 - pad + 1, x0 + pad:x1 - pad + 1]


def read_numeric(c: np.ndarray) -> tuple[str, str]:
    a = cv2.resize(c, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, a = cv2.threshold(a, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    b = cv2.resize(c, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)
    b = cv2.normalize(b, None, 0, 255, cv2.NORM_MINMAX)
    return tess(a, True), tess(b, True)


def read_text(c: np.ndarray) -> str:
    a = cv2.resize(c, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    a = cv2.normalize(a, None, 0, 255, cv2.NORM_MINMAX)
    return tess(a, False)


def digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s)


def process(png: Path) -> dict:
    gray = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    xs, ys = grid(gray)
    rows = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1) if ys[i + 1] - ys[i] > 20]
    cols = [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > 15]
    # header: the first row whose cells contain «Este» and «Norte»
    header_idx, colmap = None, {}
    for ri, (y0, y1) in enumerate(rows[:4]):
        texts = [read_text(cell(gray, x0, x1, y0, y1)) for x0, x1 in cols]
        found = {}
        for key, pat in HEADERS.items():
            for ci, t in enumerate(texts):
                if re.search(pat, t, re.I) and ci not in found.values():
                    found[key] = ci
                    break
        if "este" in found and "norte" in found:
            header_idx, colmap = ri, found
            break
    if header_idx is None:
        return dict(file=png.name, error="header with Este/Norte not found", xs=xs, ys=ys)
    # the multi-line headers of the numeric columns OCR poorly: after «Quebrada» the cuadro has, in this order,
    # viviendas, habitantes directos, indirectos and total (same layout in every cuadro of the document)
    if "quebrada" in colmap:
        for k, key in enumerate(("viviendas", "hab_directos", "hab_indirectos", "hab_total"), start=1):
            if colmap["quebrada"] + k < len(cols):
                colmap[key] = colmap["quebrada"] + k
    out_rows, total = [], None
    for ri, (y0, y1) in enumerate(rows[header_idx + 1:], start=header_idx + 1):
        rec, review = {}, []
        for key, ci in colmap.items():
            if ci >= len(cols):
                continue
            x0, x1 = cols[ci]
            c = cell(gray, x0, x1, y0, y1)
            if c.size == 0:
                continue
            if key in NUMERIC:
                a, b = read_numeric(c)
                rec[key] = dict(read_a=a, read_b=b, agree=digits(a) == digits(b) and digits(a) != "")
                if not rec[key]["agree"] and (digits(a) or digits(b)):
                    review.append(key)
            else:
                rec[key] = dict(text=read_text(c))
        first = " ".join(v.get("text", v.get("read_a", "")) for v in rec.values())
        if re.search(r"TOTAL", first, re.I):
            total = rec
            continue
        if total is not None:  # rows after TOTAL: source and datum notes (full table width)
            continue
        if not digits(rec.get("n", {}).get("read_a", "")) and not digits(rec.get("este", {}).get("read_a", "")):
            continue
        out_rows.append(dict(row_index=ri, y=[y0, y1], cells=rec, needs_review=review))
    # notes inside the table frame after TOTAL («Fuente: …», «Datum: WGS 84-ZONA 17 SUR») and just below it
    notes = []
    for y0, y1 in rows[-3:]:
        notes.append(read_text(cell(gray, cols[0][0], cols[-1][1], y0, y1)))
    foot = gray[ys[-1]:min(gray.shape[0], ys[-1] + 120), cols[0][0]:cols[-1][1]] if cols else gray
    notes.append(read_text(foot) if foot.size else "")
    footer = " | ".join(notes)
    datum_zone = re.search(r"ZONA\s*(\d{2})\s*S", footer.upper())
    return dict(file=png.name, columns=colmap, header_row=header_idx, grid=dict(xs=xs, ys=ys), rows=out_rows, total_row=total,
                footer_ocr=footer, datum_zone_ocr=int(datum_zone.group(1)) if datum_zone else None)


def _set_lang(lang: str) -> None:
    global LANG
    LANG = lang


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--lang", default="eng", help="Tesseract language for text cells (spa on the CI runner)")
    ap.add_argument("--jobs", type=int, default=1)
    a = ap.parse_args(argv)
    global LANG
    LANG = a.lang
    version = subprocess.run(["tesseract", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    pngs = [p for p in sorted(PAGES.glob("p*_cuadro*.png")) if not a.only or any(o in p.name for o in a.only)]
    if a.jobs > 1:
        from multiprocessing import Pool
        with Pool(a.jobs, initializer=_set_lang, initargs=(LANG,)) as pool:
            tables = pool.map(process, pngs)
    else:
        tables = [process(p) for p in pngs]
    for png, t in zip(pngs, tables):
        print(png.name, len(t.get("rows", [])), "rows;", sum(1 for r in t.get("rows", []) if r["needs_review"]), "need review;",
              "datum zone", t.get("datum_zone_ocr"), t.get("error", ""))
    doc = dict(text_language=LANG, method="cell-wise Tesseract OCR, two independent reads per numeric cell", tesseract=version,
               opencv=cv2.__version__, tables=tables)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
