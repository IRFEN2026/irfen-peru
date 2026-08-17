#!/usr/bin/env python3
"""Archive post-day-close official-source evidence for shadow review.

This collector never assigns EVENT or NONE.  It preserves a bounded,
auditable snapshot of official pages while they are still current so a later
human review is not forced to rely on pages that have already rotated.
Missing or unreachable sources remain UNKNOWN_NOT_ZERO.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import argparse
import json
import re
import time


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/validation/official_outcome_evidence.json"
MAX_RECORDS = 400
MAX_CAPTURES_PER_DAY = 5
MAX_BYTES = 2_000_000
MAX_FETCH_ATTEMPTS = 3
MAX_FETCH_WORKERS = 3
RETRY_DELAYS_SECONDS = (2, 5)
SOURCES = (
    {
        "source_id": "senamhi_activation_quebradas",
        "url": "https://www.senamhi.gob.pe/servicios/?p=aviso-activacion-quebrada",
        "historical_date_parameter": "f",
    },
    {
        "source_id": "senamhi_piura_24h",
        "url": "https://www.senamhi.gob.pe/servicios/main.php?dp=piura&p=aviso-24H",
        "historical_date_parameter": "f",
    },
    {
        "source_id": "indeci_emergencies",
        "url": "https://portal.indeci.gob.pe/emergencias/",
        "historical_search_parameter": "s",
    },
)
SUPPLEMENTAL_SOURCES = (
    {
        "source_id": "anin_san_ildefonso_news",
        "url": "https://www.gob.pe/institucion/anin/noticias",
        "scope": "San Ildefonso external manual outcome evidence",
    },
    {
        "source_id": "igp_cendehua_huaycoloro_monitor",
        "url": "https://www.igp.gob.pe/servicios/centro-monitoreo-deslizamientos-huaicos/inicio",
        "scope": "Huaycoloro/Chosica external manual outcome evidence",
    },
    {
        "source_id": "pechp_piura_news",
        "url": "https://www.gob.pe/que/pechp",
        "scope": "Catacaos/Bajo Piura external manual outcome evidence",
    },
)
PILOT_TERMS = (
    "San Ildefonso",
    "San Idelfonso",
    "Huaycoloro",
    "Chosica",
    "Río Seco",
    "Rio Seco",
    "Catacaos",
    "Bajo Piura",
    "Piura",
    "La Libertad",
    "Lima",
)


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        self.current_href = dict(attrs).get("href")
        self.current_parts = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self.current_href is None:
            return
        self.links.append({
            "href": self.current_href,
            "title": re.sub(r"\s+", " ", unescape(" ".join(self.current_parts))).strip(),
        })
        self.current_href = None
        self.current_parts = []


def decoded_html(raw: bytes, content_type: str | None = None):
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="replace")


def normalized_text(raw: bytes, content_type: str | None = None):
    decoded = decoded_html(raw, content_type)
    parser = TextExtractor()
    parser.feed(decoded)
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


def indeci_report_links(
    raw: bytes,
    content_type: str | None,
    source_url: str,
    snapshot_date: str,
):
    """Extract dated INDECI result links without trusting the echoed search query."""
    snapshot_day = date.fromisoformat(snapshot_date)
    date_tokens = {
        snapshot_day.isoformat(),
        f"{snapshot_day.day}/{snapshot_day.month}/{snapshot_day.year}",
        snapshot_day.strftime("%d/%m/%Y"),
        f"{snapshot_day.day}-{snapshot_day.month}-{snapshot_day.year}",
        snapshot_day.strftime("%d-%m-%Y"),
        f"{snapshot_day.day}.{snapshot_day.month}.{snapshot_day.year}",
        snapshot_day.strftime("%d.%m.%Y"),
    }
    parser = LinkExtractor()
    parser.feed(decoded_html(raw, content_type))
    reports = []
    seen_urls = set()
    for link in parser.links:
        resolved_url = urljoin(source_url, link["href"])
        parts = urlsplit(resolved_url)
        if (
            parts.netloc.lower() != "portal.indeci.gob.pe"
            or not parts.path.startswith("/emergencias/")
            or parts.path.rstrip("/") == "/emergencias"
        ):
            continue
        searchable = f'{link["title"]} {resolved_url}'.lower()
        if not any(token.lower() in searchable for token in date_tokens):
            continue
        canonical_url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        pilot_terms = [
            term for term in PILOT_TERMS if re.search(re.escape(term), searchable, re.I)
        ]
        reports.append({
            "title": link["title"],
            "url": canonical_url,
            "pilot_terms_found": pilot_terms,
        })
    return reports[:30]


def excerpt_around(text: str, pattern: str, radius: int = 260):
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return text[start:end].strip()


def date_marker_alignment(date_markers: list[str], snapshot_date: str):
    expected = date.fromisoformat(snapshot_date)
    parsed = []
    for marker in date_markers:
        try:
            if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", marker):
                parsed.append(date.fromisoformat(marker))
            else:
                day, month, year = [int(part) for part in re.split(r"[/.-]", marker)]
                parsed.append(date(year, month, day))
        except (TypeError, ValueError):
            continue
    if expected in parsed:
        return "TARGET_DATE_PRESENT"
    if parsed:
        return "TARGET_DATE_NOT_PRESENT"
    return "UNKNOWN_NO_DATE_MARKER"


def summarize_content(
    source_id: str,
    raw: bytes,
    content_type: str | None,
    snapshot_date: str | None = None,
    source_url: str | None = None,
):
    text = normalized_text(raw, content_type)
    day_first_dates = re.findall(
        r"\b(?:0?[1-9]|[12]\d|3[01])[/.-](?:0?[1-9]|1[0-2])[/.-]20\d{2}\b",
        text,
    )
    iso_dates = re.findall(r"\b20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b", text)
    dates = sorted(set(day_first_dates + iso_dates))
    terms = [term for term in PILOT_TERMS if re.search(re.escape(term), text, re.I)]
    term_excerpts = [
        {
            "term": term,
            "excerpt": excerpt_around(text, re.escape(term)),
        }
        for term in terms
    ]
    no_activation_excerpt = None
    if source_id == "senamhi_activation_quebradas":
        no_activation_excerpt = excerpt_around(
            text,
            r"no se consideran condiciones favorables.{0,220}activaci[oó]n de quebradas",
        )
    summary = {
        "date_markers": dates[:30],
        "pilot_terms_found": terms,
        "pilot_term_excerpts": term_excerpts,
        "explicit_no_activation_conditions_excerpt": no_activation_excerpt,
        "interpretation": (
            "Source text captured for later review; forecast wording alone does not prove a NONE outcome."
            if no_activation_excerpt
            else "Source text captured for later review; absence of pilot terms is not evidence of no event."
        ),
    }
    if snapshot_date:
        # Alignment must inspect the complete marker set.  The persisted list
        # remains bounded because SENAMHI pages also expose long archive tables.
        summary["snapshot_date_alignment"] = date_marker_alignment(dates, snapshot_date)
    if source_id == "indeci_emergencies" and snapshot_date and source_url:
        report_links = indeci_report_links(
            raw, content_type, source_url, snapshot_date
        )
        pilot_links = [row for row in report_links if row["pilot_terms_found"]]
        summary["official_report_links_for_snapshot_date"] = report_links
        summary["pilot_report_links_for_snapshot_date"] = pilot_links
        # The WordPress search page echoes the query date in its title.  Only a
        # dated report anchor can prove that the returned page covers the day.
        summary["snapshot_date_alignment"] = (
            "TARGET_DATE_PRESENT" if report_links else "TARGET_DATE_NOT_PRESENT"
        )
        summary["interpretation"] = (
            "Official dated report links captured for human review; a link is not an "
            "automatic EVENT label and absence of a link is not evidence of NONE."
        )
    return summary


def source_for_snapshot(source: dict, snapshot_date: str):
    """Return a date-specific official-source page for the closed UTC day."""
    date_parameter = source.get("historical_date_parameter")
    search_parameter = source.get("historical_search_parameter")
    parameter = date_parameter or search_parameter
    if not parameter:
        return dict(source)
    snapshot_day = date.fromisoformat(snapshot_date)
    parts = urlsplit(source["url"])
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[parameter] = (
        snapshot_day.strftime("%d-%m-%Y")
        if date_parameter
        else f"{snapshot_day.day}/{snapshot_day.month}/{snapshot_day.year}"
    )
    resolved = dict(source)
    resolved["url"] = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    resolved.pop("historical_date_parameter", None)
    resolved.pop("historical_search_parameter", None)
    return resolved


def fetch_source(
    source: dict,
    captured_at: datetime,
    snapshot_date: str,
    sleep_fn=time.sleep,
):
    requires_target_date_alignment = bool(
        source.get("historical_date_parameter")
        or source.get("historical_search_parameter")
    )
    source = source_for_snapshot(source, snapshot_date)
    attempts = []
    last_error = None
    for attempt_number in range(1, MAX_FETCH_ATTEMPTS + 1):
        request = Request(
            source["url"],
            headers={"User-Agent": "IRFEN-v0.8-shadow-evidence/1.0"},
        )
        try:
            with urlopen(request, timeout=35) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError(f"official response exceeds {MAX_BYTES} bytes")
                content_type = response.headers.get("Content-Type")
                attempts.append({
                    "attempt": attempt_number,
                    "status": "CAPTURED",
                    "http_status": response.status,
                    "error": None,
                })
                summary = summarize_content(
                    source["source_id"], raw, content_type, snapshot_date, source["url"]
                )
                date_alignment = summary.get("snapshot_date_alignment")
                date_aligned = (
                    not requires_target_date_alignment
                    or date_alignment == "TARGET_DATE_PRESENT"
                )
                return {
                    **source,
                    "capture_status": (
                        "CAPTURED"
                        if date_aligned
                        else "CAPTURED_TARGET_DATE_UNVERIFIED"
                    ),
                    "http_status": response.status,
                    "captured_at": captured_at.isoformat(),
                    "content_type": content_type,
                    "content_length": len(raw),
                    "content_sha256": sha256(raw).hexdigest(),
                    "summary": summary,
                    "source_error": None,
                    "unknown_not_zero": not date_aligned,
                    "attempt_count": len(attempts),
                    "attempts": attempts,
                }
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            last_error = {"type": type(exc).__name__, "message": str(exc)[:500]}
            attempts.append({
                "attempt": attempt_number,
                "status": "SOURCE_UNREACHABLE",
                "http_status": getattr(exc, "code", None),
                "error": last_error,
            })
            if attempt_number < MAX_FETCH_ATTEMPTS:
                sleep_fn(RETRY_DELAYS_SECONDS[attempt_number - 1])
    return {
        **source,
        "capture_status": "SOURCE_UNREACHABLE",
        "http_status": attempts[-1]["http_status"],
        "captured_at": captured_at.isoformat(),
        "content_type": None,
        "content_length": None,
        "content_sha256": None,
        "summary": None,
        "source_error": last_error,
        "unknown_not_zero": True,
        "attempt_count": len(attempts),
        "attempts": attempts,
    }


def fetch_sources(sources: tuple[dict, ...], captured_at: datetime, snapshot_date: str):
    """Fetch independent official sources concurrently, preserving manifest order."""
    if not sources:
        return []
    worker_count = min(MAX_FETCH_WORKERS, len(sources))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(
            executor.map(
                lambda source: fetch_source(source, captured_at, snapshot_date),
                sources,
            )
        )


def load_archive():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {
            "version": "0.8-official-outcome-evidence-v1",
            "production_use": False,
            "production_ready": False,
            "status": "OFFICIAL_SOURCE_SNAPSHOT_ARCHIVE",
            "decision_use": "HUMAN_REVIEW_INPUT_ONLY",
            "records": [],
        }


def add_capture(archive: dict, snapshot_date: str, capture: dict):
    records = archive.get("records") or []
    record = next((row for row in records if row.get("snapshot_date_utc") == snapshot_date), None)
    if record is None:
        record = {"snapshot_date_utc": snapshot_date, "captures": []}
        records.append(record)
    record["captures"] = (record.get("captures") or [])[-(MAX_CAPTURES_PER_DAY - 1):] + [capture]
    records.sort(key=lambda row: row.get("snapshot_date_utc", ""))
    archive["records"] = records[-MAX_RECORDS:]
    archive["record_count"] = len(archive["records"])
    archive["updated_at"] = capture["captured_at"]
    archive["production_use"] = False
    archive["production_ready"] = False
    archive["decision_use"] = "HUMAN_REVIEW_INPUT_ONLY"
    return archive


def resolve_snapshot_day(snapshot_date: str | None, now: datetime):
    """Resolve a closed UTC day; current or future days are never reviewable."""
    snapshot_day = (
        date.fromisoformat(snapshot_date)
        if snapshot_date
        else now.date() - timedelta(days=1)
    )
    if snapshot_day >= now.date():
        raise ValueError("snapshot date must be a closed UTC day before today")
    return snapshot_day


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-date", help="Closed UTC day, YYYY-MM-DD; defaults to yesterday UTC")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        snapshot_day = resolve_snapshot_day(args.snapshot_date, now)
    except ValueError as exc:
        parser.error(str(exc))
    capture = {
        "captured_at": now.isoformat(),
        "capture_status": "EVIDENCE_CAPTURED_NOT_CLASSIFIED",
        "outcome_label": None,
        "counts_toward_closeout": False,
        "production_use": False,
        "safety_rule": "No automatic EVENT/NONE classification; missing evidence remains UNKNOWN_NOT_ZERO.",
        "sources": fetch_sources(SOURCES, now, snapshot_day.isoformat()),
        "supplemental_sources": fetch_sources(
            SUPPLEMENTAL_SOURCES, now, snapshot_day.isoformat()
        ),
    }
    archive = add_capture(load_archive(), snapshot_day.isoformat(), capture)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "snapshot_date_utc": snapshot_day.isoformat(),
        "captured_at": now.isoformat(),
        "source_statuses": {
            row["source_id"]: row["capture_status"]
            for row in capture["sources"] + capture["supplemental_sources"]
        },
        "counts_toward_closeout": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
