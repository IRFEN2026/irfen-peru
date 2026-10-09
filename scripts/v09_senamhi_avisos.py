#!/usr/bin/env python3
"""IRFEN v0.9 — captura TEST_ONLY de avisos meteorológicos de SENAMHI reproducidos por INDECI/COEN.

Canal: los hosts de SENAMHI (www, wis, idesep) rechazan el acceso automatizado de los agentes (robots), así
que este capturador NO los consulta. Usa el canal oficial secundario de INDECI/COEN, que publica por cada
aviso de SENAMHI un «Boletín informativo de aviso meteorológico» y, a diario, un «Boletín de monitoreo de
peligros y perspectivas» con la tabla de avisos vigentes. Se descubre por la API REST de medios de WordPress
de portal.indeci.gob.pe (JSON), se archivan los PDF con SHA-256 y se normalizan los campos.

Reglas:
* La fecha de descarga nunca sustituye a la emisión ni a la vigencia. Sin vigencia legible -> estado DESCONOCIDO.
* Un fallo de consulta nunca significa «no hay avisos»: se conserva la última captura válida y la fuente pasa
  a DESACTUALIZADA.
* Una revisión (mismo número y año, contenido distinto) se añade al historial sin borrar la anterior.
* El nivel oficial de SENAMHI se registra tal como lo reproduce INDECI; IRFEN no lo recalcula ni lo mezcla
  con prioridades internas.

  python scripts/v09_senamhi_avisos.py --capture     # red (runner)
  python scripts/v09_senamhi_avisos.py --status      # offline: recalcula estados con la hora actual
  python scripts/v09_senamhi_avisos.py               # offline: verifica archivo y guardas
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/v09_senamhi_avisos_contract_v0_1.json"
STORE = ROOT / "data/v09/senamhi_avisos"
REGISTRY = STORE / "registry_v0_1.json"
LIMA = ZoneInfo("America/Lima")
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
BULLETIN_NUMBER_RE = re.compile(r"N\s*[°º]?\s*(\d{1,4})\s*[-–]\s*(\d{4})\s*[-–]?\s*INDECI\s*/?\s*COEN")
DATELINE_RE = re.compile(r"(?:Chorrillos|Lima)\s*,\s*(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})", re.I)
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
MM_RE = re.compile(r"(?:acumulados?|valores?|alrededor|superiores?|cercanos?|entre)[^.\n]{0,60}?(\d{1,3}(?:[.,]\d)?)\s*(?:a\s*(\d{1,3}))?\s*mm(?:/d[ií]a)?", re.I)
CANCEL_RE = re.compile(r"(deja\s+sin\s+efecto|cancela(?:do|ci[oó]n)?\s+(?:el\s+)?aviso)", re.I)
UPDATE_RE = re.compile(r"(actualiza(?:ci[oó]n)?\s+(?:del?\s+)?aviso|ampl[ií]a(?:ci[oó]n)?\s+(?:del?\s+)?aviso)", re.I)


def month_number(word: str | None) -> int | None:
    return MONTHS.get(fold(word or "").lower()) if word else None


def lima_dt(y: int, m: int, d: int, hh: int | None, mm: int | None, end: bool) -> datetime:
    """Local Lima datetime. Without a stated hour the whole day is meant: start 00:00, end 23:59."""
    if hh is None:
        hh, mm = (23, 59) if end else (0, 0)
    return datetime(y, m, d, hh, mm or 0, tzinfo=LIMA)


def departments_in(text: str) -> list[str]:
    found = []
    folded = fold(text)
    for dep in DEPARTMENTS:
        if re.search(r"(?<![A-Z])" + dep + r"(?![A-Z])", folded):
            found.append(dep)
    return found


def parse_aviso_bulletin(text: str, reference_year: int | None = None) -> dict:
    """Fields of an INDECI 'Boletín informativo de aviso meteorológico'. Missing fields stay None."""
    t = text or ""
    folded = fold(t)
    out = dict(doc_type="INDECI_AVISO_BULLETIN", aviso_number=None, aviso_year=None, phenomenon=None,
               official_level=None, bulletin_date=None, validity_text=None, validity_start=None, validity_end=None,
               departments=[], precipitation_mm=[], cancellation_text=None, update_text=None, parse_notes=[])
    titles = [x for x in AVISO_TITLE_RE.finditer(folded) if not norm(x.group(3)).strip(" :-–").startswith(("INDECI", "COEN"))]
    m = titles[0] if titles else AVISO_TITLE_RE.search(folded)
    if m:
        out["aviso_number"] = int(m.group(1))
        out["aviso_year"] = int(m.group(2)) if m.group(2) else None
        title = norm(m.group(3)).strip(" :-–")
        out["phenomenon"] = title or None
    b = BULLETIN_NUMBER_RE.search(folded)
    if b:
        out["bulletin_number"] = f"{int(b.group(1)):03d}-{b.group(2)}-INDECI/COEN"
        out["aviso_year"] = out["aviso_year"] or int(b.group(2))
        if out["aviso_number"] is None:
            out["aviso_number"] = int(b.group(1))
            out["parse_notes"].append("aviso number taken from the INDECI bulletin number")
    d = DATELINE_RE.search(t)
    if d and month_number(d.group(2)):
        out["bulletin_date"] = date(int(d.group(3)), month_number(d.group(2)), int(d.group(1))).isoformat()
    year = out["aviso_year"] or (int(out["bulletin_date"][:4]) if out["bulletin_date"] else reference_year)
    for level in LEVELS:
        if re.search(r"NIVEL\s*(?:DE\s*(?:PELIGRO|AVISO)\s*)?[:\-]?\s*" + level, folded):
            out["official_level"] = level
            break
    r = RANGE_PROSE_RE.search(t)
    if r and year:
        d1, mo1, y1, h1, mi1, d2, mo2, y2, h2, mi2 = r.groups()
        m2 = month_number(mo2)
        m1 = month_number(mo1) or m2
        if m1 and m2:
            y_end = int(y2) if y2 else year
            y_start = int(y1) if y1 else (y_end - 1 if m1 > m2 else y_end)
            try:
                out["validity_start"] = iso(lima_dt(y_start, m1, int(d1), int(h1) if h1 else None, int(mi1) if mi1 else None, False))
                out["validity_end"] = iso(lima_dt(y_end, m2, int(d2), int(h2) if h2 else None, int(mi2) if mi2 else None, True))
                out["validity_text"] = norm(r.group(0))
                if not h1 or not h2:
                    out["parse_notes"].append("validity hours not stated: whole days assumed (start 00:00, end 23:59 Lima)")
            except ValueError as exc:
                out["parse_notes"].append(f"validity not parseable: {exc}")
    out["departments"] = departments_in(t)
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
        rows.append(dict(doc_type="INDECI_MONITORING_TABLE_ROW", aviso_number=int(n), aviso_year=int(y1) if int(m1) <= int(m2) or y1 == y2 else int(y1),
                         phenomenon=norm(phen), official_level=level, validity_start=iso(start), validity_end=iso(end),
                         validity_text=norm(m.group(0))[:220], source_flag=(flag or "").strip("()") or None,
                         parse_notes=["table gives dates only: whole days assumed (start 00:00, end 23:59 Lima)"]))
    return rows


def aviso_key(number: int, year: int | None) -> str:
    return f"SENAMHI-AVISO-{year if year else 'YEAR_UNKNOWN'}-{number:03d}"


def compute_status(fields: dict, now: datetime) -> tuple[str, str]:
    """Status from the documented validity only. Never inferred from the download time."""
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


FIELDS_TRACKED = ("phenomenon", "official_level", "validity_start", "validity_end", "departments", "precipitation_mm",
                  "cancellation_text", "update_text")


def merge_observation(registry: dict, obs: dict, document: dict, observed_at: datetime) -> dict | None:
    """Add one parsed observation of an aviso. Returns a change event, or None when nothing changed."""
    if obs.get("aviso_number") is None:
        return None
    key = aviso_key(obs["aviso_number"], obs.get("aviso_year"))
    avisos = registry.setdefault("avisos", {})
    entry = avisos.setdefault(key, dict(aviso_key=key, aviso_number=obs["aviso_number"], aviso_year=obs.get("aviso_year"),
                                        current={}, revisions=[], documents=[]))
    if document["sha256"] not in entry["documents"]:
        entry["documents"].append(document["sha256"])
    # A daily-table row only fills fields the dedicated bulletin did not give; it never overrides them.
    incoming = {k: obs.get(k) for k in FIELDS_TRACKED if obs.get(k) not in (None, [], "")}
    if obs["doc_type"] == "INDECI_MONITORING_TABLE_ROW":
        incoming = {k: v for k, v in incoming.items() if entry["current"].get(k) in (None, [], "")}
    changed = {k: v for k, v in incoming.items() if entry["current"].get(k) != v}
    if not changed:
        return None
    previous = {k: entry["current"].get(k) for k in changed}
    entry["current"].update(changed)
    entry["revisions"].append(dict(revision=len(entry["revisions"]) + 1, observed_at_utc=iso(observed_at),
                                   document_sha256=document["sha256"], document_type=obs["doc_type"],
                                   changed_fields=sorted(changed), previous_values=previous, new_values=changed))
    kind = "NEW_AVISO" if len(entry["revisions"]) == 1 else ("LEVEL_CHANGED" if "official_level" in changed else "AVISO_REVISED")
    return dict(event=kind, aviso_key=key, changed_fields=sorted(changed), observed_at_utc=iso(observed_at),
                document_sha256=document["sha256"])


def refresh_statuses(registry: dict, now: datetime) -> list[dict]:
    events = []
    for entry in registry.get("avisos", {}).values():
        status, basis = compute_status(entry["current"], now)
        if entry.get("status") != status:
            if entry.get("status") is not None:
                events.append(dict(event="STATUS_CHANGED", aviso_key=entry["aviso_key"], from_status=entry.get("status"),
                                   to_status=status, observed_at_utc=iso(now)))
            entry["status"] = status
        entry["status_basis"] = basis
        entry["status_computed_at_utc"] = iso(now)
        entry["status_computed_at_lima"] = iso(now.astimezone(LIMA))
        if entry["current"].get("validity_start"):
            s = datetime.fromisoformat(entry["current"]["validity_start"])
            e = datetime.fromisoformat(entry["current"]["validity_end"])
            entry["hours_to_start"] = round((s - now).total_seconds() / 3600, 1) if now < s else 0.0
            entry["hours_to_end"] = round((e - now).total_seconds() / 3600, 1) if now <= e else 0.0
        else:
            entry["hours_to_start"] = entry["hours_to_end"] = None
    return events


def empty_registry() -> dict:
    return dict(schema_version="0.1", registry_id="irfen-v09-senamhi-avisos-registry:v0.1", **GUARDS,
                map_publishable=False, source_channel="INDECI_COEN_REPRODUCTION_OF_SENAMHI_AVISOS",
                senamhi_direct_access="NOT_USED_AGENT_ACCESS_DECLINED_BY_ROBOTS",
                display_timezone="America/Lima", audit_timezone="UTC",
                rules=["download time is never emission or validity", "unknown validity -> DESCONOCIDO",
                       "a failed check never means 'no avisos'", "revisions are appended, never overwritten",
                       "SENAMHI official level is reproduced as published; IRFEN review priority is a separate vocabulary"],
                source_health=dict(last_check_utc=None, last_successful_check_utc=None, consecutive_failures=0,
                                   state="NEVER_CHECKED", minutes_since_last_success=None),
                documents={}, avisos={}, events=[])


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
    if not ok and registry.get("avisos"):
        h["note"] = "Last check failed: the avisos shown are the last valid capture, not an absence of avisos."


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


RSS_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)


def rss_items(xml: str) -> list[dict]:
    """Items of a WordPress RSS 2.0 feed (title, link, pubDate, guid). Pure: tested offline."""
    import html as htmlmod

    out = []
    for block in RSS_ITEM_RE.findall(xml or ""):
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
            if not m:
                return None
            v = m.group(1).strip()
            v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S)
            return htmlmod.unescape(v).strip()
        out.append(dict(title=norm(tag("title") or ""), link=tag("link"), pub_date=tag("pubDate"), guid=tag("guid")))
    return out


def classify_title(title: str, families: list[dict]) -> str | None:
    hay = fold(title)
    for fam in families:
        if re.search(fam["title_pattern"], hay):
            return fam["id"]
    return None


def html_main_text(raw_html: str) -> str:
    import html as htmlmod

    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html)
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", body) or re.search(r"(?is)<main[^>]*>(.*?)</main>", body)
    body = m.group(1) if m else body
    body = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h\d>", "\n", body)
    text = htmlmod.unescape(re.sub(r"<[^>]+>", " ", body))
    return "\n".join(norm(line) for line in text.splitlines() if norm(line))


def pdf_links(raw_html: str) -> list[str]:
    links = re.findall(r'href="(https://portal\.indeci\.gob\.pe/wp-content/uploads/[^"]+?\.pdf)"', raw_html, re.I)
    seen, out = set(), []
    for l in links:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return out


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


def observations_for(family: str, text: str, ref_year: int | None) -> list[dict]:
    if family == "MONITORING_BULLETIN":
        return parse_monitoring_table(text)
    obs = parse_aviso_bulletin(text, ref_year)
    obs["family"] = family
    return [obs]


def archive_bytes(data: bytes, suffix: str) -> tuple[str, Path]:
    digest = sha256_bytes(data)
    raw = STORE / "raw" / f"{digest}{suffix}"
    if not raw.exists():
        raw.write_bytes(data)
    return digest, raw


def capture() -> int:
    contract = load_contract()
    limits = contract["limits"]
    now = utc_now()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.is_file() else empty_registry()
    registry.setdefault("posts", {})
    (STORE / "raw").mkdir(parents=True, exist_ok=True)
    (STORE / "text").mkdir(parents=True, exist_ok=True)
    candidates, log = discover(contract)
    discovery_ok = any(m.get("http_status") == 200 and m.get("items_returned") for m in log)
    new_events, fetched = [], 0
    for item in candidates:
        prev = registry["posts"].get(item["link"])
        if prev and prev.get("pub_date") == item.get("pub_date"):
            continue  # already archived and unchanged in the feed
        page, meta = http_get(item["link"], limits["timeout_seconds"], 8_000_000)
        fetched += 1
        if page is None:
            log.append(dict(meta, error=meta.get("error") or "POST_UNREACHABLE"))
            continue
        page_sha, page_raw = archive_bytes(page, ".html")
        raw_html = page.decode("utf-8", "replace")
        texts = [html_main_text(raw_html)]
        doc_shas = [page_sha]
        for pdf_url in pdf_links(raw_html)[: limits["max_pdfs_per_post"]]:
            data, pmeta = http_get(pdf_url, limits["timeout_seconds"], limits["max_bytes_per_document"])
            if data is None or data[:5] != b"%PDF-":
                log.append(dict(pmeta, error=pmeta.get("error") or "NOT_A_PDF"))
                continue
            sha, raw = archive_bytes(data, ".pdf")
            text = pdf_text(data)
            txt = STORE / "text" / f"{sha}.txt"
            txt.write_text(text, encoding="utf-8")
            registry["documents"][sha] = dict(sha256=sha, url=pdf_url, kind="PDF", post_link=item["link"], retrieved_at_utc=iso(now),
                                              bytes=len(data), raw_path=str(raw.relative_to(ROOT)), text_path=str(txt.relative_to(ROOT)),
                                              text_sha256=sha256_bytes(txt.read_bytes()))
            texts.append(text)
            doc_shas.append(sha)
        page_txt = STORE / "text" / f"{page_sha}.txt"
        page_txt.write_text(texts[0], encoding="utf-8")
        registry["documents"][page_sha] = dict(sha256=page_sha, url=item["link"], kind="HTML_POST", post_link=item["link"],
                                               retrieved_at_utc=iso(now), bytes=len(page), raw_path=str(page_raw.relative_to(ROOT)),
                                               text_path=str(page_txt.relative_to(ROOT)), text_sha256=sha256_bytes(page_txt.read_bytes()))
        try:
            ref_year = parsedate_year(item.get("pub_date"))
        except Exception:  # noqa: BLE001
            ref_year = None
        combined = "\n".join(texts)
        observations = observations_for(item["family"], combined, ref_year)
        registry["posts"][item["link"]] = dict(link=item["link"], title=item["title"], pub_date=item.get("pub_date"), guid=item.get("guid"),
                                               family=item["family"], first_seen_utc=(prev or {}).get("first_seen_utc") or iso(now),
                                               last_archived_utc=iso(now), document_sha256=doc_shas,
                                               parsed=[dict(aviso_number=o.get("aviso_number"), aviso_year=o.get("aviso_year"),
                                                            doc_type=o["doc_type"], parse_notes=o.get("parse_notes", [])) for o in observations])
        document = dict(sha256=doc_shas[-1], post_link=item["link"])
        for obs in observations:
            obs.setdefault("indeci_post", item["link"])
            event = merge_observation(registry, obs, document, now)
            if event:
                new_events.append(event)
    new_events += refresh_statuses(registry, now)
    update_health(registry, discovery_ok, now, None if discovery_ok else "discovery failed: " + "; ".join(
        str(m.get("error")) for m in log if m.get("error"))[:400], contract["stale_after_minutes"])
    registry["events"] = (registry.get("events", []) + new_events)[-500:]
    registry["last_check"] = dict(checked_at_utc=iso(now), checked_at_lima=iso(now.astimezone(LIMA)), discovery_ok=discovery_ok,
                                  candidates=len(candidates), posts_archived=fetched, new_events=len(new_events), request_log=log[-40:])
    registry["contract_sha256"] = sha256_bytes(CONTRACT.read_bytes())
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(discovery_ok=discovery_ok, candidates=len(candidates), archived=fetched, avisos=len(registry["avisos"]),
                          events=[e["event"] + ":" + e["aviso_key"] for e in new_events][:20]), ensure_ascii=False))
    return 0  # a failed check is recorded in source_health; it does not fail the workflow


def parsedate_year(value: str | None) -> int | None:
    from email.utils import parsedate_to_datetime

    return parsedate_to_datetime(value).year if value else None


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
        txt = ROOT / doc["text_path"]
        if not txt.is_file() or sha256_bytes(txt.read_bytes()) != doc["text_sha256"]:
            errors.append(f"text missing or SHA-256 mismatch: {doc['text_path']}")
    for key, entry in reg.get("avisos", {}).items():
        if entry.get("status") not in STATUS_VOCABULARY:
            errors.append(f"{key}: status outside the vocabulary")
        if not entry.get("revisions"):
            errors.append(f"{key}: no revision history")
        for sha in entry.get("documents", []):
            if sha not in reg.get("documents", {}):
                errors.append(f"{key}: unknown document {sha}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.capture:
        return capture()
    if args.status:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        refresh_statuses(reg, utc_now())
        for e in sorted(reg["avisos"].values(), key=lambda x: x["aviso_key"]):
            c = e["current"]
            print(e["aviso_key"], e["status"], c.get("official_level"), c.get("validity_start"), c.get("validity_end"), (c.get("phenomenon") or "")[:60])
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
