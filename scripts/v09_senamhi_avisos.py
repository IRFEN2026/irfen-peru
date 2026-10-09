#!/usr/bin/env python3
"""IRFEN v0.9 — captura TEST_ONLY de avisos de SENAMHI reproducidos por INDECI/COEN.

Canal: los hosts de SENAMHI (www, wis, idesep) rechazan el acceso automatizado de los agentes (robots), así
que este capturador NO los consulta. Usa el canal oficial secundario de INDECI/COEN: su feed RSS
«emergencias» (https://portal.indeci.gob.pe/emergencias/feed/) publica, por cada aviso de SENAMHI, un
«Boletín informativo de aviso de corto plazo ante lluvias intensas», «... ante posible activación de
quebradas» o «... de aviso meteorológico», con el PDF adjunto. Se archivan la página y el PDF con SHA-256,
se guardan el texto y las palabras con coordenadas (para reprocesar sin red) y se normalizan los campos.

Reglas:
* La fecha de descarga o de publicación en INDECI nunca sustituye a la emisión ni a la vigencia. Sin
  vigencia legible -> DESCONOCIDO. La hora de emisión de SENAMHI solo se registra si el documento la indica.
* Un fallo de consulta nunca significa «no hay avisos»: se conserva la última captura válida y la fuente
  pasa a ULTIMA_CONSULTA_FALLIDA o DESACTUALIZADA.
* Identidad del aviso = producto SENAMHI + año + número. «Aviso N°282» de lluvias y «Aviso N°282» de
  activación de quebradas son avisos distintos.
* Una revisión (misma identidad, contenido distinto) se añade al historial sin borrar la anterior.
* El nivel oficial solo se registra si el texto lo dice. En los boletines de corto plazo el nivel va
  codificado por colores en el mapa: queda null con su motivo; IRFEN no lo deduce ni lo mezcla con
  prioridades internas.
* Los eventos tienen identificador estable: reprocesar o repetir una consulta no duplica notificaciones.

  python scripts/v09_senamhi_avisos.py --capture     # red (runner)
  python scripts/v09_senamhi_avisos.py --reparse     # offline: reconstruye avisos desde el archivo
  python scripts/v09_senamhi_avisos.py --status      # offline: estados con la hora actual
  python scripts/v09_senamhi_avisos.py               # offline: verifica archivo y guardas
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmlmod
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/v09_senamhi_avisos_contract_v0_1.json"
STORE = ROOT / "data/v09/senamhi_avisos"
REGISTRY = STORE / "registry_v0_1.json"
LIMA = ZoneInfo("America/Lima")
PARSER_VERSION = "0.2"
USER_AGENT = "IRFEN-v0.9-research-aviso-archive/1.0 (+https://github.com/IRFEN2026/irfen-peru)"
GUARDS = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}
STATUS_VOCABULARY = ("FUTURO", "VIGENTE", "VENCIDO", "REEMPLAZADO", "CANCELADO", "DESCONOCIDO")
LEVELS = ("ROJO", "NARANJA", "AMARILLO", "VERDE")
DEPARTMENTS = (
    "AMAZONAS", "ANCASH", "APURIMAC", "AREQUIPA", "AYACUCHO", "CAJAMARCA", "CALLAO", "CUSCO", "HUANCAVELICA",
    "HUANUCO", "ICA", "JUNIN", "LA LIBERTAD", "LAMBAYEQUE", "LIMA", "LORETO", "MADRE DE DIOS", "MOQUEGUA",
    "PASCO", "PIURA", "PUNO", "SAN MARTIN", "TACNA", "TUMBES", "UCAYALI",
)
MONTHS = {m: i for i, m in enumerate(
    ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}
MONTHS["setiembre"] = 9
# INDECI bulletin family (RSS title) -> SENAMHI product code, phenomenon label, short-term flag.
PRODUCTS = {
    "AVISO_CORTO_PLAZO_LLUVIAS": ("ACP-LLUVIAS", "Lluvias intensas (aviso de corto plazo, 24 h)", True),
    "AVISO_CORTO_PLAZO_QUEBRADAS": ("ACP-QUEBRADAS", "Posible activación de quebradas (aviso de corto plazo, 24 h)", True),
    "AVISO_CORTO_PLAZO_OTRO": ("ACP-OTRO", None, True),
    "AVISO_METEOROLOGICO": ("AVISO-METEOROLOGICO", None, False),
}
LEVEL_NOT_IN_TEXT = ("NOT_STATED_IN_TEXT: the bulletin conveys the level by colour in its map; IRFEN does not "
                     "read colours or infer the level")


# --------------------------------------------------------------------------- utilities
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").upper()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def load_contract() -> dict:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if contract.get(key) != value:
            raise SystemExit(f"contract guard {key} must be {value!r}")
    return contract


# --------------------------------------------------------------------------- parsing (pure, tested offline)
AVISO_TITLE_RE = re.compile(r"AVISO\s*(?:METEOROLOGICO\s*)?N\s*[°ºO\.]*\s*(\d{1,4})\s*(?:[-–]\s*(\d{4}))?\s*[:\-–]?\s*([^\n]{0,160})")
SOURCE_AVISO_RE = re.compile(r"FUENTE\s*:\s*AVISO\s*N\s*[°º\.]*\s*(\d{1,4})(?:\s*[-–]\s*(\d{4}))?")
BULLETIN_NUMBER_RE = re.compile(r"N\s*[°º]?\s*(\d{1,4})\s*[-–]\s*(\d{4})\s*[-–]?\s*INDECI\s*/?\s*COEN")
DATELINE_RE = re.compile(r"(?:Chorrillos|Lima)\s*,\s*(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})", re.I)
VIGENCIA_RE = re.compile(
    r"VIGENCIA\s*:?\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*(?:\(\s*(\d{1,2})[:.](\d{2})\s*H?\s*\))?\s*"
    r"(?:AL|A|-|–)\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*(?:\(\s*(\d{1,2})[:.](\d{2})\s*H?\s*\))?")
TABLE_ROW_RE = re.compile(
    r"(?:AVISO|Aviso)\s*(?:N\s*[°º]?\s*)?(\d{1,4})\s+(.{3,120}?)\s+(ROJO|NARANJA|AMARILLO|VERDE)\s+"
    r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*(?:al|AL|-|–|a)\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*(\((?:Vigente|VIGENTE|Vencido|VENCIDO|Por iniciar|POR INICIAR)\))?",
    re.S)
RANGE_PROSE_RE = re.compile(
    r"desde\s+(?:el\s+)?(?:\w+\s+)?(\d{1,2})(?:\s+de\s+([a-záéíóú]+))?(?:\s+(?:de|del)\s+(\d{4}))?"
    r"(?:\s*(?:a\s+las|desde\s+las)\s+(\d{1,2})[:.]?(\d{2})?\s*(?:h|horas)?)?"
    r".{0,40}?hasta\s+(?:el\s+)?(?:\w+\s+)?(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+(?:de|del)\s+(\d{4}))?"
    r"(?:\s*(?:a\s+las|hasta\s+las)\s+(\d{1,2})[:.]?(\d{2})?\s*(?:h|horas)?)?",
    re.I | re.S)
# SENAMHI phrasing: "desde las 13:00 horas del martes 10 (de marzo) hasta las 23:59 horas del miércoles 11 de marzo (de 2025)"
RANGE_HOUR_FIRST_RE = re.compile(
    r"desde\s+las\s+(\d{1,2})[:.](\d{2})\s*(?:h|horas)?\s+del?\s+(?:[a-záéíóú]+\s+)?(\d{1,2})(?:\s+de\s+([a-záéíóú]+))?(?:\s+(?:de|del)\s+(\d{4}))?"
    r"\s*,?\s*hasta\s+las\s+(\d{1,2})[:.](\d{2})\s*(?:h|horas)?\s+del?\s+(?:[a-záéíóú]+\s+)?(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+(?:de|del)\s+(\d{4}))?",
    re.I)
MM_RE = re.compile(r"(?:acumulados?|valores?|alrededor|superiores?|cercanos?|entre)[^.\n]{0,60}?(\d{1,3}(?:[.,]\d)?)\s*(?:a\s*(\d{1,3}))?\s*mm(?:/d[ií]a)?", re.I)
CANCEL_RE = re.compile(r"(deja\s+sin\s+efecto|cancela(?:do|ci[oó]n)?\s+(?:el\s+)?aviso)", re.I)
UPDATE_RE = re.compile(r"(actualiza(?:ci[oó]n)?\s+(?:del?\s+)?aviso|ampl[ií]a(?:ci[oó]n)?\s+(?:del?\s+)?aviso)", re.I)
SUPERSEDES_RE = re.compile(r"(?:REEMPLAZA|SUSTITUYE)\s+(?:AL?\s+|EL\s+)?AVISO\s*N\s*[°º\.]*\s*(\d{1,4})")


def month_number(word: str | None) -> int | None:
    return MONTHS.get(fold(word or "").lower()) if word else None


def lima_dt(y: int, m: int, d: int, hh: int | None, mm: int | None, end: bool) -> datetime:
    """Local Lima datetime. Without a stated hour the whole day is meant: start 00:00, end 23:59."""
    if hh is None:
        hh, mm = (23, 59) if end else (0, 0)
    if hh == 24:  # '24:00 h' = end of that day
        hh, mm = 23, 59
    return datetime(y, m, d, hh, mm or 0, tzinfo=LIMA)


def departments_in(text: str) -> list[str]:
    folded = fold(text)
    return [dep for dep in DEPARTMENTS if re.search(r"(?<![A-Z])" + dep + r"(?![A-Z])", folded)]


def _lines(words: list[dict], tol: float = 3.0) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(w["top"] - out[-1][0]["top"]) <= tol:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in out]


def _first(words: list[dict], text: str, after: float = -1.0) -> dict | None:
    hits = [w for w in words if w["text"] == text and w["top"] > after]
    return min(hits, key=lambda w: w["top"]) if hits else None


def layout_from_words(words: list[dict] | None) -> dict | None:
    """Department/province table, 'Perspectivas' text and 'Fuente' line of an INDECI short-term bulletin.

    `words` are page-1 words with x0, x1, top (pdfplumber units). Returns None when the table header is not
    found (format change), and provinces=None when they cannot be assigned unambiguously.
    """
    if not words:
        return None
    hdr_d = _first(words, "DEPARTAMENTOS")
    hdr_p = next((w for w in sorted(words, key=lambda w: w["top"]) if w["text"].startswith("PROVINCIAS")
                  and hdr_d and abs(w["top"] - hdr_d["top"]) < 15), None)
    if not hdr_d or not hdr_p:
        return None
    notes = []
    split = (hdr_d["x0"] + hdr_p["x0"]) / 2
    left_edge = hdr_d["x0"] - 40
    top0 = hdr_d["top"] + 10
    stops = [w["top"] for w in words if w["top"] > top0 and (
        w["text"] in ("NIVELES", "INTERPRETACIÓN:", "DEPARTAMENTOS") or (w["text"] == "INDECI" and w["x0"] < left_edge))]
    bottom = min(stops) if stops else max(w["top"] for w in words) + 1
    dept_words = [w for w in words if left_edge <= w["x0"] < split and top0 < w["top"] < bottom
                  and re.fullmatch(r"[A-ZÁÉÍÓÚÑÜ]+", w["text"])]
    anchors = []
    for line in _lines(dept_words):
        name = fold(" ".join(w["text"] for w in line))
        if name in DEPARTMENTS:
            anchors.append(dict(department=name, top=line[0]["top"]))
    prov_words = [w for w in words if w["x0"] >= split and top0 < w["top"] < bottom]
    tokens = [w["text"] for line in _lines(prov_words) for w in line]
    groups, cur = [], []
    for tok in tokens:
        cur.append(tok)
        if tok.endswith("."):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    table = [dict(department=a["department"], provinces=None) for a in anchors]
    if anchors and len(groups) == len(anchors):
        for row, g in zip(table, groups):
            row["provinces"] = [p for p in (norm(x).rstrip(".") for x in " ".join(g).split(",")) if p]
    elif anchors:
        notes.append(f"provinces not assigned: {len(groups)} province groups for {len(anchors)} departments")
    persp = _first(words, "PERSPECTIVAS:")
    perspectives = None
    if persp:
        end = _first(words, "INDECI", after=persp["top"])
        right = min((w["x0"] for w in dept_words), default=left_edge) - 1
        pw = [w for w in words if persp["x0"] - 5 <= w["x0"] and w["x1"] <= right and persp["top"] < w["top"] < (end["top"] if end else 1e9)]
        perspectives = norm(" ".join(" ".join(w["text"] for w in line) for line in _lines(pw))) or None
    fuente = _first(words, "Fuente:")
    source_line = None
    if fuente:
        limit = min(left_edge, persp["x0"] if persp else 1e9) - 3
        fw = [w for w in words if fuente["x0"] - 5 <= w["x0"] < limit and fuente["top"] - 2 <= w["top"] <= fuente["top"] + 35]
        source_line = norm(" ".join(" ".join(w["text"] for w in line) for line in _lines(fw))) or None
    return dict(table=table, perspectives=perspectives, source_line=source_line, notes=notes)


def product_from_source_line(source_line: str | None) -> str | None:
    s = fold(source_line or "")
    if "QUEBRADA" in s:
        return "ACP-QUEBRADAS"
    if "CORTO PLAZO" in s and "LLUVIA" in s:
        return "ACP-LLUVIAS"
    return None


def parse_bulletin(text: str, words: list[dict] | None, family: str, reference_year: int | None = None) -> dict:
    """Fields of one INDECI aviso bulletin (short-term or meteorological). Missing fields stay None."""
    t = text or ""
    folded = fold(t)
    product, label, short_term = PRODUCTS.get(family, ("UNSPECIFIED", None, False))
    out = dict(doc_type="INDECI_AVISO_BULLETIN", family=family, product=product, aviso_number=None, aviso_year=None,
               aviso_year_basis=None, indeci_bulletin_id=None, phenomenon=label, official_level=None,
               official_level_note=None, senamhi_emission=None, bulletin_date=None, validity_text=None,
               validity_start=None, validity_end=None, validity_basis=None, departments=[], provinces_by_department=None,
               description=None, precipitation_mm=[], cancellation_text=None, update_text=None, supersedes_number=None,
               source_line=None, parser_version=PARSER_VERSION, parse_notes=[])
    notes = out["parse_notes"]
    layout = layout_from_words(words) if words is not None else None
    b = BULLETIN_NUMBER_RE.search(folded)
    if b:
        out["indeci_bulletin_id"] = f"{int(b.group(1)):03d}-{b.group(2)}-INDECI/COEN"
    src = SOURCE_AVISO_RE.search(folded)
    if src:
        out["aviso_number"] = int(src.group(1))
        if src.group(2):
            out["aviso_year"], out["aviso_year_basis"] = int(src.group(2)), "STATED_IN_SOURCE_LINE"
    elif not short_term:
        titles = [x for x in AVISO_TITLE_RE.finditer(folded) if not norm(x.group(3)).strip(" :-–").startswith(("INDECI", "COEN"))]
        if titles:
            m = titles[0]
            out["aviso_number"] = int(m.group(1))
            if m.group(2):
                out["aviso_year"], out["aviso_year_basis"] = int(m.group(2)), "STATED_IN_TITLE"
            out["phenomenon"] = out["phenomenon"] or (norm(m.group(3)).strip(" :-–") or None)
    if out["aviso_number"] is None:
        notes.append("SENAMHI aviso number not found: not merged into the aviso registry")
    if out["aviso_year"] is None and b:
        out["aviso_year"], out["aviso_year_basis"] = int(b.group(2)), "INDECI_BULLETIN_YEAR"
    if layout:
        out["source_line"] = layout["source_line"]
        notes.extend(layout["notes"])
        from_line = product_from_source_line(layout["source_line"])
        if from_line and from_line != product:
            notes.append(f"product from RSS title ({product}) differs from the 'Fuente' line ({from_line}); 'Fuente' line kept")
            out["product"] = from_line
    d = DATELINE_RE.search(t)
    if d and month_number(d.group(2)):
        out["bulletin_date"] = date(int(d.group(3)), month_number(d.group(2)), int(d.group(1))).isoformat()
    year = out["aviso_year"] or (int(out["bulletin_date"][:4]) if out["bulletin_date"] else reference_year)
    for level in LEVELS:
        if re.search(r"NIVEL\s*(?:DE\s*(?:PELIGRO|AVISO|ALERTA)\s*)?[:\-]?\s*" + level, folded):
            out["official_level"] = level
            break
    if out["official_level"] is None:
        out["official_level_note"] = LEVEL_NOT_IN_TEXT
    v = VIGENCIA_RE.search(folded)
    if v:
        d1, m1, y1, h1, mi1, d2, m2, y2, h2, mi2 = v.groups()
        try:
            out["validity_start"] = iso(lima_dt(int(y1), int(m1), int(d1), int(h1) if h1 else None, int(mi1) if mi1 else None, False))
            out["validity_end"] = iso(lima_dt(int(y2), int(m2), int(d2), int(h2) if h2 else None, int(mi2) if mi2 else None, True))
            out["validity_text"] = norm(v.group(0))
            out["validity_basis"] = "VIGENCIA_LINE_AS_REPRODUCED_BY_INDECI_COEN"
            if not h1 or not h2:
                notes.append("validity hours not stated: whole days assumed (start 00:00, end 23:59 Lima)")
        except ValueError as exc:
            notes.append(f"validity not parseable: {exc}")
    else:
        r = RANGE_HOUR_FIRST_RE.search(t)
        if r:
            h1, mi1, d1, mo1, y1, h2, mi2, d2, mo2, y2 = r.groups()
        else:
            r = RANGE_PROSE_RE.search(t)
            if r:
                d1, mo1, y1, h1, mi1, d2, mo2, y2, h2, mi2 = r.groups()
        if r and year:
            mo2n = month_number(mo2)
            mo1n = month_number(mo1) or mo2n
            if mo2n and not mo1 and int(d1) > int(d2):  # "del martes 30 hasta ... 01 de enero": start is the previous month
                mo1n = 12 if mo2n == 1 else mo2n - 1
            if mo1n and mo2n:
                y_end = int(y2) if y2 else year
                y_start = int(y1) if y1 else (y_end - 1 if mo1n > mo2n else y_end)
                try:
                    out["validity_start"] = iso(lima_dt(y_start, mo1n, int(d1), int(h1) if h1 else None, int(mi1) if mi1 else None, False))
                    out["validity_end"] = iso(lima_dt(y_end, mo2n, int(d2), int(h2) if h2 else None, int(mi2) if mi2 else None, True))
                    out["validity_text"] = norm(r.group(0))
                    out["validity_basis"] = "PROSE_RANGE_AS_REPRODUCED_BY_INDECI_COEN"
                    if not h1 or not h2:
                        notes.append("validity hours not stated: whole days assumed (start 00:00, end 23:59 Lima)")
                except ValueError as exc:
                    notes.append(f"validity not parseable: {exc}")
    if out["validity_start"] is None:
        notes.append("validity not found: status DESCONOCIDO")
    if layout and layout["table"]:
        out["departments"] = [row["department"] for row in layout["table"]]
        if all(row["provinces"] is not None for row in layout["table"]):
            out["provinces_by_department"] = {row["department"]: row["provinces"] for row in layout["table"]}
        out["description"] = layout["perspectives"]
    else:
        out["departments"] = departments_in(t)
        notes.append("department table not found in the page layout: departments taken from free text "
                     "(may include mentions outside the aviso scope)")
    notes.append("SENAMHI emission date/time not stated in the INDECI bulletin")
    for mm in MM_RE.finditer(t):
        hi = mm.group(2)
        out["precipitation_mm"].append(dict(value_mm=float(mm.group(1).replace(",", ".")), upper_mm=float(hi) if hi else None,
                                            text=norm(mm.group(0))[:200]))
    c = CANCEL_RE.search(t)
    if c:
        out["cancellation_text"] = norm(t[max(0, c.start() - 120):c.end() + 120])
    u = UPDATE_RE.search(t)
    if u:
        out["update_text"] = norm(t[max(0, u.start() - 120):u.end() + 120])
    s = SUPERSEDES_RE.search(folded)
    if s:
        out["supersedes_number"] = int(s.group(1))
    return out


def parse_monitoring_table(text: str) -> list[dict]:
    """Aviso rows of the INDECI daily monitoring bulletin table (number, phenomenon, level, validity range)."""
    rows = []
    for m in TABLE_ROW_RE.finditer(text or ""):
        n, phen, level, d1, m1, y1, d2, m2, y2, flag = m.groups()
        try:
            start = lima_dt(int(y1), int(m1), int(d1), None, None, False)
            end = lima_dt(int(y2), int(m2), int(d2), None, None, True)
        except ValueError:
            continue
        fp = fold(phen)
        product = "ACP-QUEBRADAS" if "QUEBRADA" in fp else ("ACP-LLUVIAS" if "CORTO PLAZO" in fp else "AVISO-METEOROLOGICO")
        rows.append(dict(doc_type="INDECI_MONITORING_TABLE_ROW", product=product, aviso_number=int(n), aviso_year=int(y1),
                         aviso_year_basis="TABLE_VALIDITY_START_YEAR", phenomenon=norm(phen), official_level=level,
                         validity_start=iso(start), validity_end=iso(end), validity_text=norm(m.group(0))[:220],
                         validity_basis="MONITORING_TABLE_DATES_ONLY", source_flag=(flag or "").strip("()") or None,
                         parse_notes=["table gives dates only: whole days assumed (start 00:00, end 23:59 Lima)",
                                      "product inferred from the table phenomenon text"]))
    return rows


def aviso_key(product: str, number: int, year: int | None) -> str:
    return f"SENAMHI-{product}-{year if year else 'YEAR_UNKNOWN'}-{number:03d}"


def compute_status(fields: dict, now: datetime) -> tuple[str, str]:
    """Status from the documented validity only. Never inferred from the download or publication time."""
    if fields.get("cancellation_text"):
        return "CANCELADO", "the source text announces a cancellation"
    if fields.get("superseded_by"):
        return "REEMPLAZADO", f"superseded by {fields['superseded_by']}"
    start, end = fields.get("validity_start"), fields.get("validity_end")
    if not start or not end:
        return "DESCONOCIDO", "validity not readable in the archived documents"
    s, e = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if e < s:
        return "DESCONOCIDO", "validity end precedes start in the parsed text"
    if now < s:
        return "FUTURO", f"starts {start}"
    if now <= e:
        return "VIGENTE", f"valid until {end}"
    return "VENCIDO", f"ended {end}"


FIELDS_TRACKED = ("phenomenon", "official_level", "official_level_note", "validity_start", "validity_end", "validity_text",
                  "validity_basis", "departments", "provinces_by_department", "description", "precipitation_mm",
                  "cancellation_text", "update_text", "supersedes_number", "indeci_bulletin_id", "source_line")


def event_id(event: dict) -> str:
    basis = {k: event.get(k) for k in ("event", "aviso_key", "revision", "to_status", "post_link", "document_sha256")}
    return sha256_bytes(json.dumps(basis, sort_keys=True).encode())[:20]


def add_events(registry: dict, events: list[dict], keep: int = 500) -> list[dict]:
    """Append events whose stable id was never seen. Repeated checks or a reparse never duplicate a notification."""
    seen = registry.setdefault("event_ids_seen", [])
    seen_set = set(seen)
    fresh = []
    for ev in events:
        ev["event_id"] = event_id(ev)
        if ev["event_id"] in seen_set:
            continue
        seen_set.add(ev["event_id"])
        seen.append(ev["event_id"])
        fresh.append(ev)
    registry["events"] = (registry.get("events", []) + fresh)[-keep:]
    registry["event_ids_seen"] = seen[-20000:]
    return fresh


def merge_observation(registry: dict, obs: dict, document: dict, observed_at: datetime, priority_regions=()) -> list[dict]:
    """Add one parsed observation of an aviso. Returns change events (empty when nothing changed)."""
    if obs.get("aviso_number") is None:
        return []
    key = aviso_key(obs.get("product", "UNSPECIFIED"), obs["aviso_number"], obs.get("aviso_year"))
    avisos = registry.setdefault("avisos", {})
    entry = avisos.setdefault(key, dict(aviso_key=key, product=obs.get("product"), aviso_number=obs["aviso_number"],
                                        aviso_year=obs.get("aviso_year"), aviso_year_basis=obs.get("aviso_year_basis"),
                                        official_url=None, indeci_posts=[], current={}, revisions=[], documents=[]))
    if document["sha256"] not in entry["documents"]:
        entry["documents"].append(document["sha256"])
    if document.get("post_link") and document["post_link"] not in entry["indeci_posts"]:
        entry["indeci_posts"].append(document["post_link"])
    incoming = {k: obs.get(k) for k in FIELDS_TRACKED if obs.get(k) not in (None, [], "")}
    # A daily-table row only fills fields a dedicated bulletin did not give; it never overrides them.
    if obs["doc_type"] == "INDECI_MONITORING_TABLE_ROW":
        incoming = {k: v for k, v in incoming.items() if entry["current"].get(k) in (None, [], "")}
    changed = {k: v for k, v in incoming.items() if entry["current"].get(k) != v}
    events = []
    if changed:
        previous = {k: entry["current"].get(k) for k in changed}
        entry["current"].update(changed)
        rev = len(entry["revisions"]) + 1
        entry["revisions"].append(dict(revision=rev, observed_at_utc=iso(observed_at), document_sha256=document["sha256"],
                                       document_type=obs["doc_type"], parser_version=obs.get("parser_version"),
                                       changed_fields=sorted(changed), previous_values=previous, new_values=changed,
                                       parse_notes=obs.get("parse_notes", [])))
        kind = "NEW_AVISO" if rev == 1 else ("LEVEL_CHANGED" if "official_level" in changed else "AVISO_REVISED")
        deps = entry["current"].get("departments") or []
        events.append(dict(event=kind, aviso_key=key, revision=rev, changed_fields=sorted(changed), observed_at_utc=iso(observed_at),
                           document_sha256=document["sha256"], post_link=document.get("post_link"),
                           priority_region_departments=[d for d in deps if d in priority_regions],
                           requires_human_review=True, public_communication="NOT_ALLOWED_WITHOUT_HUMAN_REVIEW"))
    target = obs.get("supersedes_number")
    if target:
        tkey = aviso_key(obs.get("product", "UNSPECIFIED"), target, obs.get("aviso_year"))
        if tkey in avisos and tkey != key and avisos[tkey]["current"].get("superseded_by") != key:
            avisos[tkey]["current"]["superseded_by"] = key
            avisos[tkey]["revisions"].append(dict(revision=len(avisos[tkey]["revisions"]) + 1, observed_at_utc=iso(observed_at),
                                                  document_sha256=document["sha256"], document_type=obs["doc_type"],
                                                  changed_fields=["superseded_by"], previous_values={"superseded_by": None},
                                                  new_values={"superseded_by": key}, parse_notes=["superseded per the text of " + key]))
    return events


def refresh_statuses(registry: dict, now: datetime) -> list[dict]:
    events = []
    for entry in registry.get("avisos", {}).values():
        status, basis = compute_status(entry["current"], now)
        if entry.get("status") != status:
            if entry.get("status") is not None:
                events.append(dict(event="STATUS_CHANGED", aviso_key=entry["aviso_key"], from_status=entry.get("status"),
                                   to_status=status, observed_at_utc=iso(now), requires_human_review=False))
            entry["status"] = status
        entry["status_basis"] = basis
        entry["status_computed_at_utc"] = iso(now)
        entry["status_computed_at_lima"] = iso(now.astimezone(LIMA))
        c = entry["current"]
        if c.get("validity_start") and c.get("validity_end"):
            s, e = datetime.fromisoformat(c["validity_start"]), datetime.fromisoformat(c["validity_end"])
            entry["hours_to_start"] = round((s - now).total_seconds() / 3600, 1) if now < s else 0.0
            entry["hours_to_end"] = round((e - now).total_seconds() / 3600, 1) if now <= e else 0.0
        else:
            entry["hours_to_start"] = entry["hours_to_end"] = None
        entry["georeference"] = dict(
            level_a_official_geometry=None, level_a_status="NOT_AVAILABLE_FROM_THIS_CHANNEL",
            level_b_administrative=("DEPARTMENTS_AND_PROVINCES_AS_LISTED" if c.get("provinces_by_department")
                                    else ("DEPARTMENTS_AS_LISTED" if c.get("departments") else "NONE")),
            note="Administrative units are a representation of the aviso scope, never its exact footprint.")
    return events


def empty_registry() -> dict:
    return dict(schema_version="0.2", registry_id="irfen-v09-senamhi-avisos-registry:v0.1", **GUARDS,
                map_publishable=False, source_channel="INDECI_COEN_REPRODUCTION_OF_SENAMHI_AVISOS",
                senamhi_direct_access="NOT_USED_AGENT_ACCESS_DECLINED_BY_ROBOTS",
                notification_channel="NOT_CONFIGURED_EVENTS_TRAY_ONLY",
                display_timezone="America/Lima", audit_timezone="UTC",
                rules=["download or INDECI publication time is never SENAMHI emission or validity",
                       "unknown validity -> DESCONOCIDO", "a failed check never means 'no avisos'",
                       "aviso identity = SENAMHI product + year + number", "revisions are appended, never overwritten",
                       "SENAMHI official level only when stated in text; IRFEN review priority is a separate vocabulary",
                       "events carry stable ids: a repeated check never duplicates a notification"],
                source_health=dict(last_check_utc=None, last_successful_check_utc=None, consecutive_failures=0,
                                   state="NEVER_CHECKED", minutes_since_last_success=None),
                posts={}, documents={}, avisos={}, events=[], event_ids_seen=[])


def update_health(registry: dict, ok: bool, now: datetime, error: str | None, stale_after_minutes: int) -> None:
    h = registry["source_health"]
    h["last_check_utc"] = iso(now)
    if ok:
        h["last_successful_check_utc"] = iso(now)
        h["consecutive_failures"] = 0
        h["last_error"] = None
    else:
        h["consecutive_failures"] = int(h.get("consecutive_failures") or 0) + 1
        h["last_error"] = error
    last = h.get("last_successful_check_utc")
    h["minutes_since_last_success"] = round((now - datetime.fromisoformat(last)).total_seconds() / 60, 1) if last else None
    if last is None:
        h["state"] = "NO_SUCCESSFUL_CHECK_YET"
    elif h["minutes_since_last_success"] > stale_after_minutes:
        h["state"] = "DESACTUALIZADA"
    else:
        h["state"] = "AL_DIA" if ok else "ULTIMA_CONSULTA_FALLIDA"
    h["note"] = (None if ok else
                 "Last check failed: the avisos shown are the last valid capture with its date; this is not an absence of avisos.")


def summary_view(registry: dict) -> dict:
    """What a dashboard may say. With a failed or stale source it never reports 'no avisos'."""
    h = registry["source_health"]
    active = [k for k, e in registry.get("avisos", {}).items() if e.get("status") in ("VIGENTE", "FUTURO")]
    if h.get("state") == "AL_DIA":
        headline = f"{len(active)} avisos vigentes o próximos en la última consulta correcta"
    elif h.get("state") in ("NEVER_CHECKED", "NO_SUCCESSFUL_CHECK_YET"):
        headline = "Fuente sin consulta correcta todavía: estado de avisos DESCONOCIDO"
    else:
        headline = (f"Fuente {h.get('state')}: última consulta correcta {h.get('last_successful_check_utc') or 'nunca'}; "
                    f"se muestran {len(active)} avisos de esa captura; puede haber avisos no capturados")
    return dict(source_state=h.get("state"), headline=headline, active_or_upcoming=sorted(active))


# --------------------------------------------------------------------------- feed and page parsing (pure)
RSS_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
POST_CONTENT_MARKER = 'class="post-content alerta-inside"'


def rss_items(xml: str) -> list[dict]:
    """Items of a WordPress RSS 2.0 feed (title, link, pubDate, guid)."""
    out = []
    for block in RSS_ITEM_RE.findall(xml or ""):
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
            if not m:
                return None
            v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", m.group(1).strip(), flags=re.S)
            return htmlmod.unescape(v).strip()
        out.append(dict(title=norm(tag("title") or ""), link=tag("link"), pub_date=tag("pubDate"), guid=tag("guid")))
    return out


def classify_title(title: str, families: list[dict]) -> str | None:
    hay = fold(title)
    for fam in families:
        if re.search(fam["title_pattern"], hay):
            return fam["id"]
    return None


def post_content(raw_html: str) -> tuple[str | None, list[str]]:
    """Text and PDF links of the INDECI post body. (None, []) when the portal layout marker is missing."""
    i = raw_html.find(POST_CONTENT_MARKER)
    if i < 0:
        return None, []
    ends = [j for j in (raw_html.find(m, i) for m in ("<aside", "<footer", 'class="content-padding-right')) if j > 0]
    i = raw_html.find(">", i) + 1
    body = raw_html[i:min(ends) if ends else i + 20000]
    links = []
    for link in re.findall(r'href="(https://portal\.indeci\.gob\.pe/wp-content/uploads/[^"]+?\.pdf)"', body, re.I):
        if link not in links:
            links.append(link)
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", body)
    body = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h\d>|</div>", "\n", body)
    text = htmlmod.unescape(re.sub(r"<[^>]+>", " ", body))
    return "\n".join(norm(x) for x in text.splitlines() if norm(x)), links


def parsedate_year(value: str | None) -> int | None:
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(value).year if value else None
    except (TypeError, ValueError):
        return None


def pubdate_utc(value: str | None) -> str | None:
    from email.utils import parsedate_to_datetime

    try:
        return iso(parsedate_to_datetime(value).astimezone(timezone.utc)) if value else None
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- network capture (runner only)
def http_get(url: str, timeout: int, max_bytes: int) -> tuple[bytes | None, dict]:
    from urllib.request import Request, urlopen

    meta = dict(url=url, requested_at_utc=iso(utc_now()))
    for attempt in range(3):
        try:
            with urlopen(Request(quote(url, safe=":/?#[]@!$&'()*+,;=%~"), headers={"User-Agent": USER_AGENT}), timeout=timeout) as r:
                data = r.read(max_bytes + 1)
                declared = r.headers.get("Content-Length")
                meta.update(http_status=r.status, content_type=r.headers.get("Content-Type"), content_length=declared, attempts=attempt + 1)
                if len(data) > max_bytes:
                    meta["error"] = "TOO_LARGE"
                    return None, meta
                if declared and declared.isdigit() and int(declared) != len(data):
                    meta["error"] = f"INCOMPLETE_BODY {len(data)}/{declared}"
                    time.sleep(3)
                    continue
                meta.pop("error", None)
                return data, meta
        except Exception as exc:  # noqa: BLE001 - recorded, retried a bounded number of times
            meta.update(error=f"{type(exc).__name__}: {str(exc)[:160]}", attempts=attempt + 1, http_status=getattr(exc, "code", None))
            time.sleep(2 * (attempt + 1))
    return None, meta


def pdf_text(data: bytes) -> str:
    if shutil.which("pdftotext"):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.pdf"
            src.write_bytes(data)
            out = subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True, timeout=300)
            if out.returncode == 0:
                return out.stdout.decode("utf-8", "replace")
    from io import BytesIO

    from pypdf import PdfReader

    return "\f".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)


def pdf_words(data: bytes) -> list[dict] | None:
    """Page-1 words with coordinates (pdfplumber). None when pdfplumber is unavailable or fails."""
    try:
        from io import BytesIO

        import pdfplumber
    except ImportError:
        return None
    try:
        with pdfplumber.open(BytesIO(data)) as pdf:
            return [dict(text=w["text"], x0=round(w["x0"], 1), x1=round(w["x1"], 1), top=round(w["top"], 1))
                    for w in pdf.pages[0].extract_words()]
    except Exception:  # noqa: BLE001 - a layout failure degrades to free-text parsing, recorded in parse_notes
        return None


def discover(contract: dict) -> tuple[list[dict], list[dict]]:
    """RSS items of the INDECI 'emergencias' feed whose title is an aviso or monitoring bulletin."""
    limits = contract["limits"]
    items, log = [], []
    for page in range(1, limits["feed_pages"] + 1):
        url = contract["feed_url"] + ("" if page == 1 else f"?paged={page}")
        data, meta = http_get(url, limits["timeout_seconds"], 5_000_000)
        meta["feed_page"] = page
        log.append(meta)
        if data is None:
            break
        parsed = rss_items(data.decode("utf-8", "replace"))
        meta["items_returned"] = len(parsed)
        for it in parsed:
            fam = classify_title(it["title"], contract["bulletin_families"])
            if fam:
                items.append(dict(it, family=fam))
    seen, unique = set(), []
    for it in items:
        if it["link"] and it["link"] not in seen:
            seen.add(it["link"])
            unique.append(it)
    return unique[: limits["max_items_per_check"]], log


def write_words(registry_doc: dict, digest: str, words: list[dict]) -> None:
    wp = STORE / "layout" / f"{digest}.words.json"
    wp.parent.mkdir(parents=True, exist_ok=True)
    wp.write_text(json.dumps(words, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    registry_doc.update(words_path=str(wp.relative_to(ROOT)), words_sha256=sha256_bytes(wp.read_bytes()))


def archive_document(registry: dict, data: bytes, suffix: str, kind: str, url: str, post_link: str, now: datetime,
                     text: str, words: list[dict] | None) -> str:
    digest = sha256_bytes(data)
    raw = STORE / "raw" / f"{digest}{suffix}"
    if not raw.exists():
        raw.write_bytes(data)
    txt = STORE / "text" / f"{digest}.txt"
    txt.write_text(text, encoding="utf-8")
    doc = registry["documents"].get(digest) or dict(sha256=digest, url=url, kind=kind, post_link=post_link,
                                                     retrieved_at_utc=iso(now), bytes=len(data))
    doc.update(raw_path=str(raw.relative_to(ROOT)), text_path=str(txt.relative_to(ROOT)), text_sha256=sha256_bytes(txt.read_bytes()))
    if words is not None:
        write_words(doc, digest, words)
    registry["documents"][digest] = doc
    return digest


def observations_for_post(registry: dict, post: dict) -> list[tuple[dict, dict]]:
    """(observation, document) pairs for one archived post, from archived text and layout only (no network)."""
    out = []
    ref_year = parsedate_year(post.get("pub_date"))
    docs = [registry["documents"][s] for s in post["document_sha256"]]
    pdfs = [d for d in docs if d["kind"] == "PDF"]
    if post["family"] == "MONITORING_BULLETIN":
        for doc in pdfs:
            for row in parse_monitoring_table((ROOT / doc["text_path"]).read_text(encoding="utf-8")):
                out.append((row, doc))
        return out
    for doc in pdfs or [d for d in docs if d["kind"] == "HTML_POST"]:
        words = json.loads((ROOT / doc["words_path"]).read_text(encoding="utf-8")) if doc.get("words_path") else None
        obs = parse_bulletin((ROOT / doc["text_path"]).read_text(encoding="utf-8"), words, post["family"], ref_year)
        if doc["kind"] == "HTML_POST":
            obs["parse_notes"].append("no PDF attached: fields parsed from the post page")
        out.append((obs, doc))
    return out


def apply_post(registry: dict, post: dict, observed_at: datetime, priority_regions) -> list[dict]:
    events, parsed = [], []
    for obs, doc in observations_for_post(registry, post):
        parsed.append(dict(aviso_key=aviso_key(obs.get("product", "UNSPECIFIED"), obs["aviso_number"], obs.get("aviso_year"))
                           if obs.get("aviso_number") is not None else None, doc_type=obs["doc_type"],
                           document_sha256=doc["sha256"], parse_notes=obs.get("parse_notes", [])))
        events += merge_observation(registry, obs, dict(sha256=doc["sha256"], post_link=post["link"]), observed_at, priority_regions)
        if obs.get("aviso_number") is None or not obs.get("validity_start"):
            events.append(dict(event="PARSE_INCOMPLETE", aviso_key=None, post_link=post["link"], document_sha256=doc["sha256"],
                               observed_at_utc=iso(observed_at), detail=obs.get("parse_notes", [])[:5], requires_human_review=True))
    if not parsed:
        events.append(dict(event="PARSE_INCOMPLETE", aviso_key=None, post_link=post["link"], document_sha256=None,
                           observed_at_utc=iso(observed_at), detail=["no parseable document in the post"], requires_human_review=True))
    post["parsed"] = parsed
    for entry in registry.get("avisos", {}).values():
        if post["link"] in entry.get("indeci_posts", []) and not entry.get("official_url"):
            entry["official_url"] = post["link"]
            entry["official_url_kind"] = "INDECI_COEN_POST_REPRODUCING_THE_SENAMHI_AVISO"
    return events


def capture() -> int:
    contract = load_contract()
    limits = contract["limits"]
    now = utc_now()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.is_file() else empty_registry()
    for k, v in empty_registry().items():
        registry.setdefault(k, v)
    (STORE / "raw").mkdir(parents=True, exist_ok=True)
    (STORE / "text").mkdir(parents=True, exist_ok=True)
    candidates, log = discover(contract)
    discovery_ok = any(m.get("http_status") == 200 and m.get("items_returned") for m in log)
    events, fetched = [], 0
    for item in candidates:
        prev = registry["posts"].get(item["link"])
        if prev and prev.get("pub_date") == item.get("pub_date") and prev.get("document_sha256"):
            continue  # already archived and unchanged in the feed
        page, meta = http_get(item["link"], limits["timeout_seconds"], 8_000_000)
        fetched += 1
        if page is None:
            log.append(dict(meta, error=meta.get("error") or "POST_UNREACHABLE"))
            continue
        raw_html = page.decode("utf-8", "replace")
        body_text, links = post_content(raw_html)
        if body_text is None:
            events.append(dict(event="PORTAL_FORMAT_CHANGED", aviso_key=None, post_link=item["link"], observed_at_utc=iso(now),
                               detail=["post-content marker missing in the INDECI page"], requires_human_review=True))
        doc_shas = [archive_document(registry, page, ".html", "HTML_POST", item["link"], item["link"], now, body_text or "", None)]
        for pdf_url in links[: limits["max_pdfs_per_post"]]:
            data, pmeta = http_get(pdf_url, limits["timeout_seconds"], limits["max_bytes_per_document"])
            if data is None or data[:5] != b"%PDF-":
                log.append(dict(pmeta, error=pmeta.get("error") or "NOT_A_PDF"))
                continue
            doc_shas.append(archive_document(registry, data, ".pdf", "PDF", pdf_url, item["link"], now, pdf_text(data), pdf_words(data)))
        post = dict(link=item["link"], title=item["title"], pub_date=item.get("pub_date"), indeci_published_utc=pubdate_utc(item.get("pub_date")),
                    guid=item.get("guid"), family=item["family"], first_seen_utc=(prev or {}).get("first_seen_utc") or iso(now),
                    last_archived_utc=iso(now), document_sha256=doc_shas)
        registry["posts"][item["link"]] = post
        events += apply_post(registry, post, now, contract["priority_regions"])
    events += refresh_statuses(registry, now)
    error = None if discovery_ok else "discovery failed: " + "; ".join(str(m.get("error")) for m in log if m.get("error"))[:400]
    update_health(registry, discovery_ok, now, error, contract["stale_after_minutes"])
    if not discovery_ok and any(e.get("status") == "VIGENTE" for e in registry["avisos"].values()):
        events.append(dict(event="SOURCE_LOST_DURING_ACTIVE_AVISO", aviso_key=None, observed_at_utc=iso(now),
                           post_link=f"health:{registry['source_health'].get('last_successful_check_utc')}", requires_human_review=True))
    fresh = add_events(registry, events)
    registry["parser_version"] = PARSER_VERSION
    registry["summary"] = summary_view(registry)
    registry["last_check"] = dict(checked_at_utc=iso(now), checked_at_lima=iso(now.astimezone(LIMA)), discovery_ok=discovery_ok,
                                  candidates=len(candidates), posts_archived=fetched, new_events=len(fresh), request_log=log[-40:])
    registry["contract_sha256"] = sha256_bytes(CONTRACT.read_bytes())
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(discovery_ok=discovery_ok, candidates=len(candidates), archived=fetched, avisos=len(registry["avisos"]),
                          source=registry["source_health"]["state"],
                          events=[e["event"] + ":" + str(e.get("aviso_key") or e.get("post_link")) for e in fresh][:20]), ensure_ascii=False))
    return 0  # a failed check is recorded in source_health; it does not fail the workflow


def reparse(now: datetime | None = None) -> dict:
    """Rebuild the aviso registry from archived documents only (no network). Event ids keep notifications unique."""
    contract = load_contract()
    now = now or utc_now()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for k, v in empty_registry().items():
        registry.setdefault(k, v)
    for doc in registry["documents"].values():
        if doc["kind"] == "PDF" and not doc.get("words_path"):
            words = pdf_words((ROOT / doc["raw_path"]).read_bytes())
            if words is not None:
                write_words(doc, doc["sha256"], words)
        if doc["kind"] == "HTML_POST":  # text is derived from the archived bytes; re-derive with the current extractor
            body, _ = post_content((ROOT / doc["raw_path"]).read_bytes().decode("utf-8", "replace"))
            txt = ROOT / doc["text_path"]
            txt.write_text(body or "", encoding="utf-8")
            doc["text_sha256"] = sha256_bytes(txt.read_bytes())
    registry["avisos"] = {}
    events = []
    for post in sorted(registry["posts"].values(), key=lambda p: (pubdate_utc(p.get("pub_date")) or "", p["link"])):
        post.setdefault("indeci_published_utc", pubdate_utc(post.get("pub_date")))
        events += apply_post(registry, post, datetime.fromisoformat(post["last_archived_utc"]), contract["priority_regions"])
    events += refresh_statuses(registry, now)
    add_events(registry, events)
    registry["parser_version"] = PARSER_VERSION
    registry["summary"] = summary_view(registry)
    registry["contract_sha256"] = sha256_bytes(CONTRACT.read_bytes())
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return registry


# --------------------------------------------------------------------------- offline verification
def verify() -> list[str]:
    errors = []
    load_contract()
    if not REGISTRY.is_file():
        return ["registry missing: run --capture"]
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if reg.get(key) != value:
            errors.append(f"registry guard {key} must be {value!r}")
    if reg.get("map_publishable") is not False:
        errors.append("registry map_publishable must be false")
    if STORE.resolve().is_relative_to((ROOT / "site").resolve()):
        errors.append("archive must stay outside site/")
    for digest, doc in reg.get("documents", {}).items():
        raw = ROOT / doc["raw_path"]
        if not raw.is_file() or sha256_bytes(raw.read_bytes()) != digest:
            errors.append(f"raw document missing or SHA-256 mismatch: {doc['raw_path']}")
        for path_key, sha_key in (("text_path", "text_sha256"), ("words_path", "words_sha256")):
            if doc.get(path_key):
                p = ROOT / doc[path_key]
                if not p.is_file() or sha256_bytes(p.read_bytes()) != doc.get(sha_key):
                    errors.append(f"{path_key} missing or SHA-256 mismatch: {doc[path_key]}")
    for key, entry in reg.get("avisos", {}).items():
        if entry.get("status") not in STATUS_VOCABULARY:
            errors.append(f"{key}: status outside the vocabulary")
        if not entry.get("revisions"):
            errors.append(f"{key}: no revision history")
        if entry["current"].get("official_level") not in (None, *LEVELS):
            errors.append(f"{key}: official level outside the SENAMHI vocabulary")
        for sha in entry.get("documents", []):
            if sha not in reg.get("documents", {}):
                errors.append(f"{key}: unknown document {sha}")
    ids = [e.get("event_id") for e in reg.get("events", []) if e.get("event_id")]
    if len(ids) != len(set(ids)):
        errors.append("duplicate event ids in the events tray")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--reparse", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.capture:
        return capture()
    if args.reparse:
        reg = reparse()
        print(f"reparsed {len(reg['posts'])} posts -> {len(reg['avisos'])} avisos")
        return 0
    if args.status:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        refresh_statuses(reg, utc_now())
        print(summary_view(reg)["headline"])
        for e in sorted(reg["avisos"].values(), key=lambda x: x["aviso_key"]):
            c = e["current"]
            print(e["aviso_key"], e["status"], c.get("official_level"), c.get("validity_start"), c.get("validity_end"),
                  ",".join(c.get("departments") or []))
        return 0
    errors = verify()
    if errors:
        print("FAIL:")
        for e in errors:
            print("  -", e)
        return 1
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    print(f"OK: {len(reg['documents'])} archived documents, {len(reg['avisos'])} avisos, source state {reg['source_health']['state']}; guards closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
