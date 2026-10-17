#!/usr/bin/env python3
"""IRFEN — inventory completeness review (documentary QA tool, RESEARCH_ONLY / TEST_ONLY).

Cross-checks institutional sources that are already archived byte-for-byte (SHA-256) in the repository's
source archives against the national quebrada inventory: main plus the open inventory lanes (#365 on #364,
#366, #363), without editing any inventory row. It writes one review ledger:

    config/phase2_inventory_completeness_review_v0_1.json

What it does:
  * verifies every archived source file against its expected SHA-256 before reading it (fails closed);
  * re-reads the ANA 2016 tables (SIGRID 3743 Tumbes, SIGRID 3741 Piura) from the archived map PDFs and checks
    each existing ANA-2016 inventory row (row number, UTM reference point, quebrada and centro poblado);
  * parses ANA DU 015-2023 Anexo II (all sections, by word position) and Anexo III, and the INGEMMET A6764
    Tumbes 2017 control-point table, and classifies each named quebrada against the inventory;
  * lists the "Q."/"Quebrada" labels of the ANA 2016 Tumbes map that the inventory does not hold;
  * adjudicates the owner's named candidates with literal quotes.

It never infers aliases, parent basins, outlets or geometry. A same-name match in another district stays a
separate candidate; a partial-name match is a possible relation, UNRESOLVED. Nothing here is map-eligible.

Usage (sources are the archived raw files, e.g. from the #364/#365 branch archive):
    python scripts/phase2_inventory_completeness_review.py --sources DIR --lanes DIR [--out PATH]
    python scripts/phase2_inventory_completeness_review.py --check      # structural check of the committed ledger
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json"
OUT = ROOT / "config/phase2_inventory_completeness_review_v0_1.json"
ARCHIVE = "data/phase2/source_archive/tumbes_capitana_hualaca_higueron"
ARCHIVE_BRANCH = "inventory/tumbes-anexo-ii-gap-v0-1 (PR #365, stacked on #364; the archive itself comes from #364)"

GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None, map_publishable=False)

SOURCES = {
    "ANA-DU015-2023-ANEXO-II": dict(
        file="raw/ana-du-015-2023-anexo-ii.pdf", sha256="c00095672208cb0afbd368aa02fe8172c2661d0df629385fb91b9f464db883b9",
        institution="ANA (publicado por MEF/gob.pe)", title="DU 015-2023, Anexo II: Listado de puntos críticos para limpieza y descolmatación",
        url="https://cdn.www.gob.pe/uploads/document/file/4704868/Anexo_II_DU015_2023.pdf", evidence_kind="CRITICAL_POINT_WORKS_LIST"),
    "ANA-DU015-2023-ANEXO-III": dict(
        file="raw/ana-du-015-2023-anexo-iii.pdf", sha256="5963b140cd49b8ee6599044ab094e7a511a77d5ad0d9efdebcad35f633ac1cad",
        institution="ANA (publicado por MEF/gob.pe)", title="DU 015-2023, Anexo III: Listado de quebradas a ser intervenidas",
        url="https://cdn.www.gob.pe/uploads/document/file/4704869/Anexo_III_DU015_2023.pdf", evidence_kind="VULNERABLE_POPULATION_WORKS_LIST"),
    "ANA-2016-MAPA-TUMBES-SIGRID-3743": dict(
        file="raw/sigrid-3743.pdf", text="text/sigrid-3743.pages.json",
        sha256="3b63261930a7e908722c8109b4818908e08cdb28591d96edc7a54171d165f8c8",
        institution="ANA (vía SIGRID/CENEPRED)", title="Mapa de ubicación de poblaciones vulnerables por activación de quebradas, Tumbes 2016",
        url="https://sigrid.cenepred.gob.pe/sigridv3/documento/3743/descargar", evidence_kind="CRITICAL_POINT_TABLE_AND_MAP_LABELS"),
    "ANA-2016-MAPA-PIURA-SIGRID-3741": dict(
        file="raw/sigrid-3741.pdf", text="text/sigrid-3741.pages.json",
        sha256="c246b48b3f94ec72cecdd6531da35073c1102bf9ce8f1a694adc321577bb4004",
        institution="ANA (vía SIGRID/CENEPRED)", title="Mapa de ubicación de poblaciones vulnerables por activación de quebradas, Piura 2016",
        url="https://sigrid.cenepred.gob.pe/sigridv3/documento/3741/descargar", evidence_kind="CRITICAL_POINT_TABLE"),
    "INGEMMET-A6764-TUMBES-2017": dict(
        file="raw/sigrid-3708-ingemmet-a6764-tumbes-2017.pdf", text="text/sigrid-3708-ingemmet-a6764-tumbes-2017.pages.json",
        sha256="e32e0c506300368351e54d5d190219c764995b913f3604e466f8185edd7b5231",
        institution="INGEMMET (vía SIGRID)", title="Informe técnico A6764: evaluación geológica de las zonas afectadas por El Niño Costero, Tumbes 2017",
        url="https://sigrid.cenepred.gob.pe/sigridv3/documento/3708/descargar", evidence_kind="GEOLOGICAL_CONTROL_POINTS"),
    "INDECI-RC-3755-2025-TUMBES": dict(
        file="raw/indeci-rc-3755-2025-03-18-tumbes.pdf", text="text/indeci-rc-3755-2025-03-18-tumbes.pages.json",
        sha256="a0eb6ecac12b3c8577170c735b62d08893ea2fc454cdc6e10dd7c21b83bcf460",
        institution="INDECI / COEN", title="Reporte complementario N.º 3755, 18-03-2025: lluvias intensas en el departamento de Tumbes",
        url="https://portal.indeci.gob.pe/wp-content/uploads/2025/03/REPORTE-COMPLEMENTARIO-N.%C2%BA-3755-18MAR2025-LLUVIAS-INTENSAS-EN-EL-DEPARTAMENTO-DE-TUMBES-29.pdf",
        evidence_kind="EMERGENCY_REPORT"),
}

SOURCE_CODE = {"ANA-DU015-2023-ANEXO-II": "a2", "ANA-DU015-2023-ANEXO-III": "a3", "INGEMMET-A6764-TUMBES-2017": "ing",
               "ANA-2016-MAPA-TUMBES-SIGRID-3743": "map"}
REGION_PENDING_ES = {
    "Tumbes": ["Rótulos del mapa ANA 2016 sin distrito: lectura visual del mapa y cruce con los mapas por quebrada SIGRID 3745–3770 (carril #364/#365).",
               "SIGRID 11733 (ANA puntos críticos Tumbes 2015) archivado pero no leído en esta revisión.",
               "Distrito de Las Gardenias (Tumbes vs La Cruz) sin adjudicar."],
    "Piura": ["Homónimos del anexo (Atahualpa ×2, San Francisco ×3 en Tambogrande, 9 de Diciembre, Cementerio, Paccha) sin adjudicar.",
              "Informes INGEMMET de Piura y fichas GORE Piura no barridos.",
              "Rótulos del mapa ANA 2016 de Piura no usados: el mapa incluye Lambayeque y Cajamarca y no permite asignar departamento."],
    "Lambayeque": ["Cuadro 17 (ANA 2016) aún sin copia archivada para verificar byte a byte las 46 filas.",
                   "«El Hualtacal» (Oyotún) no se equipara con Hualtacal de Tumbes."],
    "La Libertad": ["Cuadro 19 (ANA 2016) no recuperado.", "22 de los 26 candidatos del anexo están en la sierra (Pataz, Bolívar, Sánchez Carrión), fuera del ámbito costero del piloto, pero se conservan."],
    "Rímac": ["QA independiente del carril #363 pendiente.", "Anexo III: 11 etiquetas no inventariadas; relación «Cóndores 1/2» con «Los Cóndores» y «Milagros» con «Señor de los Milagros» sin adjudicar.",
              "PPRRD municipales de Chaclacayo, Ricardo Palma y Santa Eulalia no barridos."],
    "Pisco/Ica": ["Cuadro 41 (ANA 2016) no recuperado.", "Río Seco: homónimos Salas/Llipata (contrato de homónimos en main).", "Topará: ¿uno o dos cauces a ambos lados del límite Ica–Lima?"],
    "Santa/Casma": ["Cuadro 23 (ANA 2016) no recuperado.", "Relación «Bombon-Poctao» / «Bombon Matua» sin adjudicar.", "El carril #371 trata geometría de Casma, no inventario."],
}
ANEXO_II_READING_FIXES = {
    ("II", 77): dict(distrito="Colan", sector="9 de Diciembre - Parte alta"),
    ("IV", 79): dict(distrito="Condomarca", sector="San Agustin De Chuquique"),
}
REGIONS = ["Tumbes", "Piura", "Lambayeque", "La Libertad", "Rímac", "Pisco/Ica", "Santa/Casma"]
RIMAC_CORRIDOR = "CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA"
RIMAC_DISTRICTS = ("lurigancho", "chaclacayo", "ricardo palma", "santa eulalia", "ate", "san mateo", "matucana", "surco",
                   "callahuanca", "chicla", "san bartolome", "cocachacra", "antioquia")
LABEL_STOP = {"q", "qda", "quebrada", "quebradas"}
ARTICLES = {"el", "la", "los", "las", "de", "del"}


# --------------------------------------------------------------------------- text helpers (pure)
def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def norm_label(text: str) -> str:
    words = re.sub(r"[^a-z0-9ñ ]+", " ", fold(text).replace("ñ", "n")).split()
    return " ".join(w for w in words if w not in LABEL_STOP)


def core(label_norm: str) -> str:
    return " ".join(w for w in label_norm.split() if w not in ARTICLES)


def slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", fold(text))).strip("_")


def same_district(a: str | None, b: str | None) -> bool | None:
    if not a or not b:
        return None
    a, b = norm_label(a), norm_label(b)
    return a == b or a.startswith(b) or b.startswith(a)


def region_of(department: str | None, province: str | None = None, district: str | None = None, corridor: str | None = None,
              basin: str | None = None) -> str | None:
    dep = fold(department or "")
    if corridor == RIMAC_CORRIDOR:
        return "Rímac"
    if corridor == "SANTA_CASMA":
        return "Santa/Casma"
    if dep == "tumbes":
        return "Tumbes"
    if dep == "piura":
        return "Piura"
    if dep == "lambayeque":
        return "Lambayeque"
    if dep == "la libertad":
        return "La Libertad"
    if dep == "ica":
        return "Pisco/Ica"
    if dep == "lima" and district and any(norm_label(district).startswith(d) for d in RIMAC_DISTRICTS) and corridor is None:
        return "Rímac"
    if dep == "ancash" and corridor is None and (fold(province or "") in ("santa", "casma") or fold(basin or "") in ("santa", "casma")):
        return "Santa/Casma"
    return None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- inventory index (pure)
def name_parts(row: dict) -> list[str]:
    names = [row["documentary_name"], *row.get("name_variants_observed", [])]
    return [n["label"] if isinstance(n, dict) else n for n in names if n]


class Index:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.full = defaultdict(list)       # exact normalized full name -> rows
        self.component = defaultdict(list)  # component of a compound label -> rows
        self.cores = defaultdict(list)      # name without articles -> rows
        for r in rows:
            for n in name_parts(r):
                k = norm_label(n)
                self.full[k].append(r)
                self.cores[core(k)].append(r)
                for part in re.split(r"\s*(?:/|–|—|\(|\)|,|;| - | o | y )\s*", n):
                    pk = norm_label(part)
                    if pk and pk != k:
                        self.component[pk].append(r)

    def classify(self, label: str, department: str, district: str | None) -> dict:
        """Relation of a source label to the inventory. Same department only; nothing is equated."""
        k = norm_label(label)
        dep = fold(department)
        in_dep = lambda rows: [r for r in rows if fold(r["department"]) == dep]
        exact = in_dep(self.full.get(k, []))
        if exact:
            same = [r for r in exact if same_district(r.get("district"), district)]
            if same:
                return dict(relation="REGISTERED_SAME_NAME_SAME_DISTRICT", rows=[r["inventory_id"] for r in same])
            unknown = [r for r in exact if not r.get("district") or not district]
            if unknown:
                return dict(relation="REGISTERED_SAME_NAME_DISTRICT_NOT_COMPARABLE", rows=[r["inventory_id"] for r in unknown])
            return dict(relation="SAME_NAME_OTHER_DISTRICT_SEPARATE_CANDIDATE", rows=[r["inventory_id"] for r in exact])
        possible = {r["inventory_id"]: r for r in in_dep(self.component.get(k, []) + self.cores.get(core(k), []))}
        # same district only: one label's words contained in the other's ("Condores 1" / "Los Cóndores",
        # "Milagros" / "Señor de los Milagros"). A possible relation, never an equivalence.
        src = set(re.sub(r"\b\d+\b", " ", core(k)).split())
        if src and district:
            for r in in_dep(self.rows):
                if same_district(r.get("district"), district):
                    for n in name_parts(r):
                        tok = set(re.sub(r"\b\d+\b", " ", core(norm_label(n))).split())
                        if tok and (src <= tok or tok <= src):
                            possible[r["inventory_id"]] = r
        if possible:
            return dict(relation="POSSIBLE_RELATION_UNRESOLVED", rows=sorted(possible))
        return dict(relation="NOT_IN_INVENTORY", rows=[])


# --------------------------------------------------------------------------- source parsers
def words_bbox(pdf: Path) -> list[list[tuple]]:
    from xml.etree import ElementTree as ET

    xml = subprocess.check_output(["pdftotext", "-bbox", str(pdf), "-"]).decode("utf-8")
    xml = re.sub(r'xmlns="[^"]+"', "", re.sub(r"<!DOCTYPE[^>]*>", "", xml)).replace("&nbsp;", " ")
    root = ET.fromstring(xml)
    return [[(float(w.get("xMin")), float(w.get("yMin")), float(w.get("xMax")), w.text or "") for w in p.iter("word")] for p in root.iter("page")]


def parse_anexo_ii(pdf: Path) -> list[dict]:
    """Rows of Anexo II with columns assigned by word position (multi-line cells joined)."""
    header_keys = {"CUENCA": "cuenca", "FUENTE": "fuente", "RIO_Qda.": "rio_qda", "AAA": "aaa", "ALA": "ala",
                   "DEPARTAMENTO": "departamento", "PROVINCIA": "provincia", "DISTRITO": "distrito", "SECTOR": "sector", "N°": "n"}
    rows, section = [], None
    for page_no, words in enumerate(words_bbox(pdf), start=1):
        hdr = {}
        for x0, y0, x1, t in words:
            if t in header_keys and header_keys[t] not in hdr:
                hdr[header_keys[t]] = ((x0 + x1) / 2, y0)
        if len(hdr) < 9:
            continue
        hdr_y = max(v[1] for v in hdr.values()) + 4
        centers = sorted((v[0], k) for k, v in hdr.items())
        bounds = [(centers[i][0] + centers[i + 1][0]) / 2 for i in range(len(centers) - 1)]
        col = lambda xc: next((centers[i][1] for i, b in enumerate(bounds) if xc < b), centers[-1][1])
        body = [w for w in words if w[1] > hdr_y]
        lines = defaultdict(list)
        for w in body:
            lines[round(w[1])].append(w)
        anchors = []
        for y, ws in sorted(lines.items()):
            text = " ".join(t for *_, t in sorted(ws))
            m = re.match(r"^(?:\d+\s+)?([IVX]+)\s*-\s*([A-ZÁÉÍÓÚÑ ]+)$", text)
            if m:
                anchors.append(("S", y, m.group(1), m.group(2).strip()))
                continue
            for x0, y0, x1, t in ws:
                if col((x0 + x1) / 2) == "n" and re.fullmatch(r"\d+", t):
                    anchors.append(("R", y0, int(t), None))
        anchors.sort(key=lambda a: a[1])
        row_anchors = [a for a in anchors if a[0] == "R"]
        cells = {id(a): defaultdict(list) for a in row_anchors}
        for x0, y0, x1, t in body:
            c = col((x0 + x1) / 2)
            if c == "n" or any(a[0] == "S" and abs(a[1] - y0) < 2 for a in anchors) or not row_anchors:
                continue
            near = min(row_anchors, key=lambda a: abs(a[1] - y0))
            if abs(near[1] - y0) < 14:
                cells[id(near)][c].append((y0, x0, t))
        for a in anchors:
            if a[0] == "S":
                section = (a[2], a[3])
                continue
            c = cells[id(a)]
            rec = {k: " ".join(t for _, _, t in sorted(c.get(k, []))) for k in header_keys.values() if k != "n"}
            if not rec["fuente"]:
                continue  # page numbers and other stray digits in the N° column
            rows.append(dict(page=page_no, section=section[0], section_name=section[1], n=a[2], **rec))
    return rows


def parse_anexo_iii(pdf: Path) -> list[dict]:
    text = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"]).decode("utf-8")
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d{1,2})\s{2,}(.*)$", line)
        if not m:
            continue
        f = re.split(r"\s{2,}", m.group(2).strip())
        if len(f) < 12:
            continue
        # cuenca, quebrada (may be glued to the AAA column by one space), ..., este, norte, fuente, susceptibilidad, observación
        num = [i for i, x in enumerate(f) if re.fullmatch(r"\d{6,7}", x)]
        if len(num) < 2:
            continue
        e_i = num[0]
        quebrada = re.sub(r"\s+(Cañete Fortaleza|Chaparra‐Chincha|Chaparra-Chincha)$", "", f[1])
        rows.append(dict(n=int(m.group(1)), cuenca=f[0], quebrada=quebrada, departamento=f[e_i - 4], provincia=f[e_i - 3],
                         distrito=f[e_i - 2], sector=f[e_i - 1], este=int(f[e_i]), norte=int(f[e_i + 1]), fuente=f[e_i + 2],
                         susceptibilidad=f[e_i + 3] if len(f) > e_i + 3 else None, line=" ".join(line.split())))
    return rows


def page_texts(path: Path) -> list[str]:
    d = json.loads(path.read_text(encoding="utf-8"))
    pages = d["pages"] if isinstance(d, dict) else d
    return [p["text"] if isinstance(p, dict) else p for p in pages]


def ana2016_table_rows(text: str) -> dict[int, dict]:
    out = {}
    for m in re.finditer(r"(?m)^\s*(\d{1,2}) (\d{6}) (\d{7}) (.+?)\s*$", text):
        out.setdefault(int(m.group(1)), dict(e=int(m.group(2)), n=int(m.group(3)), rest=m.group(4)))
    return out


def map_labels(text: str) -> list[str]:
    labels = []
    for line in text.split("\n"):
        line = " ".join(line.split())
        for part in re.split(r"(?=\b(?:Q\.|Qda\.|Quebrada)\s*)", line):
            m = re.match(r"^(?:Q\.|Qda\.|Quebrada)\s*(.+)$", part.strip())
            if m:
                labels.append(m.group(1).strip())
    return labels


def ingemmet_points(text: str) -> list[dict]:
    flat = " ".join(text.split())
    out = []
    for m in re.finditer(r"\b(P-\d{2})\s+(Quebrada (?:(?!P-\d)[^/]){1,40}?)(?:/[^ ]+(?: [^ ]+)?)?\s+(Zarumilla|Tumbes|Contralmirante Villar|Constralmirante Villar)\s+(?:\d+\s+)?(Rehabilitación|Reubicación|Reconstrucción)", flat):
        out.append(dict(point=m.group(1), label=m.group(2).replace("Quebrada ", "", 1).strip(), province=m.group(3).replace("Constralmirante", "Contralmirante"),
                        action=m.group(4), quote=m.group(0)))
    return out


# --------------------------------------------------------------------------- review
def load_union(lanes_dir: Path) -> tuple[list[dict], dict]:
    main = json.loads(INVENTORY.read_text(encoding="utf-8"))
    rows = {r["inventory_id"]: dict(r, _lane="main") for r in main["candidates"]}
    lanes_meta = json.loads((lanes_dir / "lanes.json").read_text(encoding="utf-8"))
    lanes = []
    for lane in lanes_meta:
        doc = json.loads((lanes_dir / lane["file"]).read_text(encoding="utf-8"))
        added = []
        for r in doc["candidates"]:
            if r["inventory_id"] not in rows:
                rows[r["inventory_id"]] = dict(r, _lane=f"#{lane['pr']}")
                added.append(r["inventory_id"])
        lanes.append(dict(pr=lane["pr"], branch=lane["branch"], head=lane["head"], rows_in_file=len(doc["candidates"]), rows_added=sorted(added)))
    return list(rows.values()), dict(main_rows=len(main["candidates"]), lanes=lanes, union_rows=len(rows))


def review(sources_dir: Path, lanes_dir: Path, main_commit: str) -> dict:
    for sid, s in SOURCES.items():
        got = sha256(sources_dir / s["file"])
        if got != s["sha256"]:
            raise SystemExit(f"SHA-256 mismatch for {sid}: {got}")  # fail closed: never read an unverified file
    union, baseline = load_union(lanes_dir)
    idx = Index(union)
    by_id = {r["inventory_id"]: r for r in union}
    entries = []  # every named quebrada reference found in a source

    # --- ANA 2016 tables: verify existing rows, list rows the inventory lacks
    verification = {}
    for sid, dep, table in (("ANA-2016-MAPA-TUMBES-SIGRID-3743", "Tumbes", "Cuadro 9"), ("ANA-2016-MAPA-PIURA-SIGRID-3741", "Piura", "Cuadro 11")):
        text = page_texts(sources_dir / SOURCES[sid]["text"])[0]
        table_rows = ana2016_table_rows(text)
        inv = [r for r in union if r["department"] == dep and any(e.get("source_id") == "ANA-2016-COMPLEMENTACION-NACIONAL" and e.get("table") == table for e in r["evidence"])]
        verified, mismatches, used = [], [], set()
        for r in inv:
            for e in r["evidence"]:
                if e.get("source_id") != "ANA-2016-COMPLEMENTACION-NACIONAL" or e.get("table") != table:
                    continue
                n, pt = e.get("row_number_as_read"), e.get("source_reference_point") or {}
                tr = table_rows.get(n)
                name_ok = tr is not None and all(w in norm_label(tr["rest"]) for w in norm_label(r["documentary_name"]).split())
                coord_ok = tr is not None and (tr["e"], tr["n"]) == (pt.get("easting_m"), pt.get("northing_m"))
                used.add(n)
                (verified if name_ok and coord_ok else mismatches).append(dict(
                    inventory_id=r["inventory_id"], row=n, name_in_map_table=name_ok, reference_point_equal=coord_ok,
                    map_table_row=(f"{n} {tr['e']} {tr['n']} {tr['rest']}" if tr else None)))
        missing = [dict(row=n, map_table_row=f"{n} {t['e']} {t['n']} {t['rest']}") for n, t in sorted(table_rows.items()) if n not in used]
        verification[sid] = dict(department=dep, table=table, map_table_rows=len(table_rows), inventory_rows_citing_table=len(inv),
                                 verified=len(verified), mismatches=mismatches, table_rows_not_in_inventory=missing,
                                 verified_inventory_ids=sorted({v["inventory_id"] for v in verified}))

    # --- ANA DU 015-2023 Anexo II (Quebrada rows)
    a2 = parse_anexo_ii(sources_dir / SOURCES["ANA-DU015-2023-ANEXO-II"]["file"])
    for r in a2:
        fix = ANEXO_II_READING_FIXES.get((r["section"], r["n"]))
        if fix:
            r.update(fix, reading_fix="column boundary corrected by eye on the rendered page (also in the 09-10 gap report)")
    a2_counts = Counter((r["section"], r["section_name"], r["fuente"]) for r in a2)
    for r in a2:
        if r["fuente"] != "Quebrada":
            continue
        label = re.sub(r"^Qda\.?\s*", "", r["rio_qda"]).strip()
        entries.append(dict(source_id="ANA-DU015-2023-ANEXO-II", locator=f"sección {r['section']} ({r['section_name']}), fila {r['n']}, p. {r['page']}",
                            label=label, department=r["departamento"], province=r["provincia"], district=r["distrito"], sector=r["sector"],
                            basin=r["cuenca"], quote=" | ".join(r[k] for k in ("cuenca", "fuente", "rio_qda", "aaa", "ala", "departamento", "provincia", "distrito", "sector")),
                            unnamed=norm_label(label) in ("s n", "sn", "")))

    # --- ANA DU 015-2023 Anexo III
    a3 = parse_anexo_iii(sources_dir / SOURCES["ANA-DU015-2023-ANEXO-III"]["file"])
    for r in a3:
        label = re.sub(r"^Qda\.?\s*", "", r["quebrada"]).strip()
        entries.append(dict(source_id="ANA-DU015-2023-ANEXO-III", locator=f"fila {r['n']}", label=label, department=r["departamento"],
                            province=r["provincia"], district=r["distrito"], sector=r["sector"], basin=r["cuenca"], quote=r["line"],
                            source_reference_point=dict(easting_m=r["este"], northing_m=r["norte"], datum_note="UTM as printed; zone not stated in the row"),
                            unnamed=False))

    # --- INGEMMET A6764 control points named "Quebrada ..."
    ing_pages = page_texts(sources_dir / SOURCES["INGEMMET-A6764-TUMBES-2017"]["text"])
    seen_pts = set()
    # the map's summary table (columns: punto, centro poblado, provincia, acción) is the only page with a single
    # province column; the body tables add a district column that a text parser cannot separate reliably
    summary = [(i, t) for i, t in enumerate(ing_pages, start=1) if "CENTROS POBLADOS PROVINCIA NUMERO ACCIÓN" in " ".join(t.split())]
    for i, t in summary:
        for p in ingemmet_points(t):
            if p["point"] in seen_pts:
                continue
            seen_pts.add(p["point"])
            entries.append(dict(source_id="INGEMMET-A6764-TUMBES-2017", locator=f"punto {p['point']}, p. {i}", label=p["label"], department="Tumbes",
                                province=p["province"], district=None, sector=None, basin=None, quote=p["quote"], unnamed=False))

    # --- ANA 2016 Tumbes map labels ("Q." / "Quebrada")
    labels_3743 = map_labels(page_texts(sources_dir / SOURCES["ANA-2016-MAPA-TUMBES-SIGRID-3743"]["text"])[0])
    truncated, excluded = [], []
    for lab in dict.fromkeys(labels_3743):
        nl = norm_label(lab)
        if len(nl.replace(" ", "")) < 4 or re.search(r"\b[a-z]$", nl) or lab.endswith(("Zarum", "Ánim")):
            truncated.append(lab)
            continue
        if re.search(r"N°|Viviendas", lab):
            excluded.append(dict(label=lab, reason="table header text, not a label"))
            continue
        if nl in ("tumbes", "zarumilla"):
            excluded.append(dict(label=lab, reason="same name as the main river; not entered as a quebrada"))
            continue
        entries.append(dict(source_id="ANA-2016-MAPA-TUMBES-SIGRID-3743", locator="rótulo del mapa", label=lab, department="Tumbes",
                            province=None, district=None, sector=None, basin=None, quote=f"rótulo «{lab}» (ortografía tal como se lee; el departamento sale solo del título del mapa)", unnamed=False, map_label=True))

    # --- classify and group into candidates
    for e in entries:
        e["region"] = region_of(e["department"], e.get("province"), e.get("district"), None, e.get("basin"))
        e["classification"] = dict(relation="UNNAMED_IN_SOURCE", rows=[]) if e["unnamed"] else idx.classify(e["label"], e["department"], e.get("district"))
    candidates = {}
    rank = {"NOT_IN_INVENTORY": 0, "POSSIBLE_RELATION_UNRESOLVED": 1, "SAME_NAME_OTHER_DISTRICT_SEPARATE_CANDIDATE": 2}
    for e in entries:
        rel = e["classification"]["relation"]
        if rel in ("REGISTERED_SAME_NAME_SAME_DISTRICT", "REGISTERED_SAME_NAME_DISTRICT_NOT_COMPARABLE", "UNNAMED_IN_SOURCE"):
            continue
        # one candidate per source, label and district: the same label in another source, or in another district, is a
        # separate candidate linked as "same label", never merged
        src = SOURCE_CODE[e["source_id"]]
        key = (src, fold(e["department"]), core(norm_label(e["label"])), norm_label(e.get("district") or ""))
        c = candidates.get(key)
        if c is None:
            dist = e.get("district")
            cid = f"rev20261014_{src}_" + slug(e["department"]) + "_" + (slug(dist) + "_" if dist else "") + slug(core(norm_label(e["label"])) or e["label"])
            c = candidates[key] = dict(
                candidate_id=cid, documentary_label=e["label"], region=e["region"], department=e["department"],
                province=e.get("province"), district=e.get("district"), basin_as_printed=e.get("basin"), sources=[],
                relation_to_inventory=rel, related_inventory_rows=[],
                status=dict(inventariado="CANDIDATO_NO_INTEGRADO", geometria_reproducible="NO", publicable_en_mapa=False),
                evidence_scale="MAP_LABEL_ONLY" if e.get("map_label") else "NAMED_IN_INSTITUTIONAL_LIST")
        c["sources"].append({k: e[k] for k in ("source_id", "locator", "quote", "sector") if e.get(k)}
                            | ({"source_reference_point": e["source_reference_point"]} if e.get("source_reference_point") else {}))
        c["related_inventory_rows"] = sorted(set(c["related_inventory_rows"]) | set(e["classification"]["rows"]))
        if rank[rel] > rank[c["relation_to_inventory"]]:
            c["relation_to_inventory"] = rel
    for c in candidates.values():
        if len(c["sources"]) > 1:
            c["repeated_in_source_note"] = ("La misma etiqueta aparece en varias filas o puntos de la fuente; si es un cauce o varios queda "
                                            "UNRESOLVED (no se fusiona ni se separa por inferencia).")
    by_label = defaultdict(list)
    for c in candidates.values():
        by_label[(fold(c["department"]), core(norm_label(c["documentary_label"])))].append(c["candidate_id"])
    for c in candidates.values():
        c["same_label_other_candidates_not_merged"] = [x for x in by_label[(fold(c["department"]), core(norm_label(c["documentary_label"])))] if x != c["candidate_id"]]
    cand_list = sorted(candidates.values(), key=lambda c: (REGIONS.index(c["region"]) if c["region"] in REGIONS else 99, c["candidate_id"]))

    coverage = Counter((e["source_id"], e["classification"]["relation"]) for e in entries)
    region_table = []
    for reg in REGIONS:
        rows_r = [r for r in union if region_of(r["department"], r.get("province"), r.get("district"), r.get("corridor")) == reg]
        cands = [c for c in cand_list if c["region"] == reg]
        ver_src = [sid for sid, v in verification.items() if v["department"] == reg]
        srcs = sorted({x["source_id"] for c in cands for x in c["sources"]} | {e["source_id"] for e in entries if e["region"] == reg} | set(ver_src)
                      | ({"INDECI-RC-3755-2025-TUMBES"} if reg == "Tumbes" else set()))
        ver = sum(len(verification[sid]["verified_inventory_ids"]) for sid in ver_src)
        region_table.append(dict(
            region=reg,
            inventariado=dict(main=sum(1 for r in rows_r if r["_lane"] == "main"),
                              carriles_abiertos={lane: n for lane, n in sorted(Counter(r["_lane"] for r in rows_r if r["_lane"] != "main").items())},
                              total=len(rows_r)),
            geometria_reproducible=sum(1 for r in rows_r if (r.get("reproducible_geometry") or {}).get("exists")),
            publicable_en_mapa=sum(1 for r in rows_r if r.get("map_eligible")),
            candidatos_nuevos=dict(listas_institucionales=sum(1 for c in cands if c["evidence_scale"] == "NAMED_IN_INSTITUTIONAL_LIST"),
                                   solo_rotulo_de_mapa=sum(1 for c in cands if c["evidence_scale"] == "MAP_LABEL_ONLY"),
                                   posibles_relaciones_o_homonimos=sum(1 for c in cands if c["relation_to_inventory"] != "NOT_IN_INVENTORY")),
            fuentes_verificadas=srcs, filas_existentes_verificadas_byte_a_byte=ver,
            pendientes_es=REGION_PENDING_ES[reg]))
    return dict(
        schema_version="0.1", review_id="irfen-phase2-inventory-completeness-review:2026-10-14", **GUARDS,
        role="DOCUMENTARY_COMPLETENESS_REVIEW_NOT_INTEGRATOR_NOT_ALERT_GENERATOR",
        rules=dict(inventory_rows_edited=0, aliases_inferred=False, same_name_other_district_merged=False, parent_basin_inferred=False,
                   critical_point_converted_to_event=False, geometry_or_outlet_created=False, map_promotions=0,
                   missing_gis_is_not_a_reason_to_drop=True),
        state_separation_es=dict(
            INVENTARIADO="Fila en el inventario nacional (main o carril abierto). Un candidato de esta revisión aún NO está inventariado.",
            GEOMETRIA_REPRODUCIBLE="Geometría reproducible en main con SHA-256 (reproducible_geometry.exists=true).",
            PUBLICABLE_EN_MAPA="Admitida por el catálogo canónico map_semantics y QA. Ningún candidato lo es."),
        main_commit=main_commit, baseline=baseline,
        source_archive=dict(path=ARCHIVE, branch=ARCHIVE_BRANCH, note="Archived bytes verified against the SHA-256 below before reading; nothing was downloaded for this review."),
        sources_checked=[dict(source_id=k, **{x: v[x] for x in ("institution", "title", "url", "sha256", "evidence_kind")}, archived_file=f"{ARCHIVE}/{v['file']}") for k, v in SOURCES.items()],
        anexo_ii_row_counts=[dict(section=s, name=n, fuente=f, rows=c) for (s, n, f), c in sorted(a2_counts.items())],
        anexo_iii_rows=len(a3),
        ana2016_table_verification=verification,
        tumbes_map_labels=dict(labels_read=len(labels_3743), unique=len(dict.fromkeys(labels_3743)), truncated_not_used=truncated, excluded=excluded,
                               caution_es="Rótulos del mapa ANA 2016 leídos del texto del PDF: sin distrito, con la ortografía impresa y sin comprobar que cada "
                                          "rótulo esté dentro de Tumbes (el marco del mapa puede incluir bordes de Piura o Ecuador). Requieren lectura visual."),
        regions=region_table,
        coverage_by_source=[dict(source_id=s, relation=r, entries=n) for (s, r), n in sorted(coverage.items())],
        distinct_labels_by_region=dict(Counter(r or "Otras zonas" for r, _ in {(c["region"], (fold(c["department"]), core(norm_label(c["documentary_label"])))) for c in cand_list})),
        new_candidates=cand_list,
    )


def check(doc: dict) -> list[str]:
    errors = []
    for k, v in GUARDS.items():
        if doc.get(k) != v:
            errors.append(f"guard {k}")
    ids = [c["candidate_id"] for c in doc["new_candidates"]]
    if len(ids) != len(set(ids)):
        errors.append("duplicate candidate ids")
    inv_ids = {r["inventory_id"] for r in json.loads(INVENTORY.read_text(encoding="utf-8"))["candidates"]}
    for c in doc["new_candidates"]:
        if c["status"] != dict(inventariado="CANDIDATO_NO_INTEGRADO", geometria_reproducible="NO", publicable_en_mapa=False):
            errors.append(f"{c['candidate_id']}: status")
        if not c["sources"] or any(s["source_id"] not in {x["source_id"] for x in doc["sources_checked"]} for s in c["sources"]):
            errors.append(f"{c['candidate_id']}: sources")
        if c["candidate_id"] in inv_ids:
            errors.append(f"{c['candidate_id']}: collides with an inventory id")
    for n in doc.get("named_candidates", []):
        if n["verdict"] not in NAMED_VERDICTS:
            errors.append(f"named {n['name']}: verdict")
        for e in n["evidence"]:
            if e.get("quote_found_in_archived_text") is False:
                errors.append(f"named {n['name']}: quote not found in {e['source_id']}")
    return errors


def verify_named_quotes(named: list[dict], sources_dir: Path) -> None:
    """Mark each quoted passage as found (or not) in the archived text of its source. Anexo rows quoted cell by
    cell ("a | b | c") are checked cell by cell."""
    texts = {}
    for sid, s in SOURCES.items():
        if s.get("text"):
            texts[sid] = " ".join(" ".join(page_texts(sources_dir / s["text"])).split())
        else:
            texts[sid] = " ".join(subprocess.check_output(["pdftotext", "-raw", str(sources_dir / s["file"]), "-"]).decode("utf-8").split())
    for n in named:
        for e in n["evidence"]:
            hay = fold(texts[e["source_id"]])
            parts = [p.strip() for p in e["quote"].split("|")] if "|" in e["quote"] else [e["quote"]]
            e["quote_found_in_archived_text"] = all(fold(" ".join(p.split())) in hay for p in parts if p)


NAMED_VERDICTS = ("NEW_CANDIDATE_NAMED_AS_QUEBRADA", "NAMED_ON_MAIN_OUTSIDE_INVENTORY", "ALREADY_IN_INVENTORY",
                  "NOT_A_QUEBRADA_IN_SOURCES_READ", "NO_SOURCE_FOUND")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources")
    ap.add_argument("--lanes")
    ap.add_argument("--named", help="JSON with the adjudicated named candidates (kept in the ledger)")
    ap.add_argument("--main-commit", default="")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        errs = check(json.loads(Path(a.out).read_text(encoding="utf-8")))
        print("OK" if not errs else "\n".join(errs))
        return 1 if errs else 0
    doc = review(Path(a.sources), Path(a.lanes), a.main_commit)
    if a.named:
        doc["named_candidates"] = json.loads(Path(a.named).read_text(encoding="utf-8"))
    if a.named:
        verify_named_quotes(doc["named_candidates"], Path(a.sources))
    errs = check(doc)
    if errs:
        print("\n".join(errs))
        return 1
    Path(a.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {a.out}: {len(doc['new_candidates'])} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
