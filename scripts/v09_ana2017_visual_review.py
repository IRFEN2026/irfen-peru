#!/usr/bin/env python3
"""Revisión visual trazable de las filas que el OCR celda a celda no pudo leer y de las celdas sin consenso
(ANA 2016-2017, cuadros costeros). RESEARCH_ONLY / TEST_ONLY. Sin red.

Por qué hace falta: las filas que el documento resalta en gris (centros poblados con mayor exposición) pierden las
líneas de la rejilla al binarizar, y el OCR no las separa. No se corrige nada en silencio:

1. REVIEWS contiene la transcripción que una persona hace de la página renderizada a 300 ppp (valor tal como está
   impreso, sin redondear ni completar).
2. Para cada fila revisada se recorta la franja de la página (entre la fila anterior y la siguiente que sí se leyeron),
   se guarda el recorte con su SHA-256 y se vuelve a leer cada celda numérica con las mismas tres lecturas Tesseract del
   OCR original, ahora sobre la franja aislada (el fondo gris deja de interferir con la detección de la rejilla).
3. Un valor de Este/Norte revisado solo vale como coordenada si al menos dos de esas tres lecturas coinciden con la
   transcripción (dos lecturas independientes, como en el OCR general). Si no, queda pendiente.

Salida: data/v09/sources/ana2017_complementacion_quebradas/visual_review_v0_1.json y recortes en visual_review/.
    python scripts/v09_ana2017_visual_review.py           # escribe
    python scripts/v09_ana2017_visual_review.py --check   # rehace y compara (requiere tesseract)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/v09/sources/ana2017_complementacion_quebradas"
OCR = SRC / "ocr_tables.json"
PAGES = SRC / "table_pages_300dpi"
CROPS = SRC / "visual_review"
OUT = SRC / "visual_review_v0_1.json"
_spec = importlib.util.spec_from_file_location("ocr", ROOT / "scripts/v09_ana2017_table_ocr.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

SHADED = "Fila resaltada en gris en el original: la rejilla no se detecta al binarizar y el OCR no la separó."
# (cuadro, n) -> transcription of the printed row (strings exactly as printed; numbers without thousands separators)
ROWS = {
    (11, 12): dict(este="563435", norte="9471428", prov="Sullana", distrito="Tambogrande", centro="Somate Alto",
                   quebrada="El Ereo", viviendas="500", hab_directos="2500", hab_indirectos="3325", hab_total="5825"),
    (11, 13): dict(este="587557", norte="9445864", prov="Morropón", distrito="Tambogrande", centro="Paccha",
                   quebrada="Paccha", viviendas="600", hab_directos="3000", hab_indirectos="3990", hab_total="6990"),
    (19, 1): dict(este="694176", norte="9153288", prov="Ascope", distrito="Casa Grande", centro="Mocan",
                  quebrada="La Culebra - El Higueron (San José Alto)", viviendas="400", hab_directos="2000",
                  hab_indirectos="2660", hab_total="4660"),
    (43, 11): dict(este="747403", norte="8161997", prov="Camana", distrito="Samuel Pastor",
                   centro="El Asentamiento Habitad, Asentamiento Pueblo Nuevo", quebrada="Pastor", viviendas="600",
                   hab_directos="2500", hab_indirectos="3325", hab_total="5825"),
    (43, 14): dict(este="745385", norte="8165014", prov="Camana", distrito="Nicolás de Piérola",
                   centro="Los AA. HH. Chávez de la Cadena, AA. HH Murillo Motta I. II. III y CPM. Hacienda El Molino",
                   quebrada="Bandurrias", viviendas="430", hab_directos="2150", hab_indirectos="2860", hab_total="5010"),
    (43, 22): dict(este="802475", norte="8197659", prov="Caylloma", distrito="Majes", centro="Hospicio",
                   quebrada="Hospicio", viviendas="1300", hab_directos="6500", hab_indirectos="8645", hab_total="15145"),
    (43, 70): dict(este="674486", norte="8255199", prov="Caraveli", distrito="Caraveli",
                   centro="Urb. Jose Pedro Tordoya, P.J. Virgencita del Buen Paso y Pueblo Caraveli",
                   quebrada="Sector La Yesera", viviendas="350", hab_directos="2000", hab_indirectos="2660", hab_total="4660"),
    (47, 1): dict(este="296728", norte="8097713", prov="Mariscal Nieto", distrito="Moquegua", centro="El Cementerio",
                  quebrada="El Cementerio", viviendas="100", hab_directos="300", hab_indirectos="399", hab_total="699"),
}
# single cells of rows that WERE read: (cuadro, n) -> {field: printed value}, with the reason
CELLS = {
    (47, 10): (dict(prov="General Sanchez Cerro"),
               "Nombre de provincia en dos líneas («General Sanchez / Cerro»); el OCR de una línea leyó «a ocancnez»."),
    (49, 10): (dict(este="390651.3"),
               "El cuadro imprime el Este con un decimal («390651.3»); el OCR solo de dígitos leyó «3906513» (7 cifras)."),
}
# Control sample of coordinates ADMITTED by the OCR (2 of 3 reads) outside Tumbes, Piura and Lambayeque (the master
# already cross-checks those three): the first 4 admitted points per department in sha256(id) order. Each Este/Norte
# cell is compared by eye with the dataset value. Verdict COINCIDE = identical digits.
CONTROL_SAMPLE = {
    "ANA2017-C19-021": "COINCIDE",
    "ANA2017-C19-041": "COINCIDE",
    "ANA2017-C19-061": "COINCIDE",
    "ANA2017-C19-016": "COINCIDE",
    "ANA2017-C23-047": "COINCIDE",
    "ANA2017-C23-020": "COINCIDE",
    "ANA2017-C23-066": "COINCIDE",
    "ANA2017-C23-005": "COINCIDE",
    "ANA2017-C29-087": "COINCIDE",
    "ANA2017-C29-044": "COINCIDE",
    "ANA2017-C29-010": "COINCIDE",
    "ANA2017-C29-070": "COINCIDE",
    "ANA2017-C41-020": "COINCIDE",
    "ANA2017-C41-017": "COINCIDE",
    "ANA2017-C41-044": "COINCIDE",
    "ANA2017-C41-022": "COINCIDE",
    "ANA2017-C43-041": "COINCIDE",
    "ANA2017-C43-020": "COINCIDE",
    "ANA2017-C43-100": "COINCIDE",
    "ANA2017-C43-032": "COINCIDE",
    "ANA2017-C47-013": "COINCIDE",
    "ANA2017-C47-023": "COINCIDE",
    "ANA2017-C47-016": "COINCIDE",
    "ANA2017-C47-026": "COINCIDE",
    "ANA2017-C49-012": "COINCIDE",
    "ANA2017-C49-001": "COINCIDE",
    "ANA2017-C49-014": "COINCIDE",
    "ANA2017-C49-018": "COINCIDE",
}
NUMERIC = ("este", "norte", "viviendas", "hab_directos", "hab_indirectos", "hab_total")


def table_geometry(t: dict):
    xs, ys = t["grid"]["xs"], t["grid"]["ys"]
    cols = [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > 15]
    return cols, ys


def local_lines(gray, t: dict, ya: int, yb: int) -> list[int]:
    """Horizontal rule positions in a band: rows where >60 % of the table width is darker than the grey shading."""
    cols, _ = table_geometry(t)
    band = gray[ya:yb, cols[0][0] + 5:cols[-1][1] - 5]
    idx = [ya + i for i, f in enumerate((band < 90).mean(axis=1)) if f > 0.6]
    out: list[list[int]] = []
    for i in idx:
        if out and i - out[-1][-1] <= 3:
            out[-1].append(i)
        else:
            out.append([i])
    return [round(sum(o) / len(o)) for o in out]


def row_band(gray, t: dict, n: int, numbered: dict) -> tuple[int, int]:
    """Vertical band of an unread row n: the k-th ruled row below the last row read above it (or below the header)."""
    above = max((k for k in numbered if k < n), default=None)
    _, ys = table_geometry(t)
    ref = numbered[above][0] if above else ys[t["header_row"] + 1]
    k = n - (above or 0)  # segments to skip below the reference line (the row above itself counts as one)
    found = local_lines(gray, t, ref + 4, ref + 80 * (k + 1))
    rules = [ref] + found
    if above is None:
        k -= 1
    return rules[k], rules[k + 1]


def reread(gray, cols, colmap, y0, y1) -> dict:
    out = {}
    for key in NUMERIC:
        ci = colmap.get(key)
        if ci is None or ci >= len(cols):
            continue
        a, b, c = T.read_numeric(T.cell(gray, cols[ci][0], cols[ci][1], y0, y1))
        out[key] = dict(read_a=a, read_b=b, read_c=c)
    return out


def agrees(reads: dict, printed: str) -> int:
    want = re.sub(r"[^0-9]", "", printed)
    return sum(1 for k in ("read_a", "read_b", "read_c") if re.sub(r"[^0-9]", "", reads.get(k, "")) == want)


def build() -> dict:
    ocr = json.loads(OCR.read_text(encoding="utf-8"))
    tabs = {int(re.search(r"cuadro(\d+)", t["file"]).group(1)): t for t in ocr["tables"]}
    CROPS.mkdir(parents=True, exist_ok=True)
    entries = []
    for (cu, n), printed in sorted(ROWS.items()) + [(k, v[0]) for k, v in sorted(CELLS.items())]:
        t = tabs[cu]
        cols, _ = table_geometry(t)
        colmap = dict(t["columns"])
        for k, key in enumerate(("viviendas", "hab_directos", "hab_indirectos", "hab_total"), start=1):
            colmap.setdefault(key, colmap["quebrada"] + k)
        numbered = {}
        for r in t["rows"]:
            v = r["cells"].get("n", {}).get("consensus")
            if v:
                numbered.setdefault(int(v), r["y"])
        whole_row = (cu, n) in ROWS
        gray = cv2.imread(str(PAGES / t["file"]), cv2.IMREAD_GRAYSCALE)
        y0, y1 = row_band(gray, t, n, numbered) if whole_row else numbered[n]
        crop = gray[max(0, y0 - 2):y1 + 2, cols[0][0]:cols[-1][1]]
        name = f"c{cu:02d}_r{n:03d}.png"
        ok, buf = cv2.imencode(".png", crop)
        (CROPS / name).write_bytes(buf.tobytes())
        reads = reread(gray, cols, colmap, y0, y1)
        checks = {k: dict(printed=v, ocr_reads_agreeing=agrees(reads[k], v), **reads[k]) for k, v in printed.items() if k in reads}
        coords_ok = all(checks[k]["ocr_reads_agreeing"] >= 2 for k in ("este", "norte") if k in checks)
        entries.append(dict(
            cuadro=cu, row=n, kind="FILA_NO_LEIDA_TRANSCRITA" if whole_row else "CELDA_CORREGIDA",
            pdf_page=int(re.match(r"p(\d+)_", t["file"]).group(1)), page_file=t["file"], band_y=[y0, y1],
            crop=f"visual_review/{name}", crop_sha256=hashlib.sha256(buf.tobytes()).hexdigest(),
            printed=printed, reason=SHADED if whole_row else CELLS[(cu, n)][1],
            ocr_recheck=checks, coordinates_confirmed_by_two_reads=coords_ok if ("este" in printed or "norte" in printed) else None))
    points = {p["id"]: p for p in json.loads((ROOT / "site/data/v09/ana2017_coastal_points_v0_1.json").read_text(encoding="utf-8"))["points"]}
    control = []
    for pid, verdict in CONTROL_SAMPLE.items():
        p = points[pid]
        t = tabs[p["cuadro"]]
        cols, _ = table_geometry(t)
        r = next(r for r in t["rows"] if r["row_index"] == p["ocr_row_index"])
        gray = cv2.imread(str(PAGES / t["file"]), cv2.IMREAD_GRAYSCALE)
        ok, buf = cv2.imencode(".png", gray[r["y"][0]:r["y"][1], cols[0][0]:cols[2][1]])
        name = f"control_{pid[8:].lower()}.png"
        (CROPS / name).write_bytes(buf.tobytes())
        control.append(dict(id=pid, department=p["department"], easting_m=p["utm"]["easting_m"], northing_m=p["utm"]["northing_m"],
                            crop=f"visual_review/{name}", crop_sha256=hashlib.sha256(buf.tobytes()).hexdigest(), visual_verdict=verdict))
    return dict(schema_version="irfen_v09_ana2017_visual_review_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                method=("Transcripción visual de la página renderizada a 300 ppp + tres relecturas Tesseract de cada celda "
                        "numérica sobre la franja aislada. Una coordenada revisada solo se usa si dos relecturas coinciden "
                        "con lo impreso. Los valores se copian tal como están impresos (sin redondear)."),
                reviewer="revisión visual asistida (sesión de QA IRFEN, 30-10-2026)", tesseract=T.subprocess.run(
                    ["tesseract", "--version"], capture_output=True, text=True).stdout.splitlines()[0], entries=entries,
                control_sample=dict(rule="4 puntos admitidos por OCR 2 de 3 por departamento (La Libertad, Áncash, Lima, Ica, "
                                         "Arequipa, Moquegua, Tacna), orden sha256(id); comparación visual de Este y Norte",
                                    points=control, coincide=sum(c["visual_verdict"] == "COINCIDE" for c in control)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    for e in json.loads(text)["entries"]:
        print(e["cuadro"], e["row"], e["kind"], "coords two reads:", e["coordinates_confirmed_by_two_reads"],
              {k: v["ocr_reads_agreeing"] for k, v in e["ocr_recheck"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
