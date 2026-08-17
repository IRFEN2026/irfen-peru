#!/usr/bin/env python3
"""Archive post-day-close official-source evidence for shadow review.

This collector never assigns EVENT or NONE.  It preserves a bounded,
auditable snapshot of official pages while they are still current so a later
human review is not forced to rely on pages that have already rotated.
Missing or unreachable sources remain UNKNOWN_NOT_ZERO.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
RETRY_DELAYS_SECONDS = (2, 5)
SOURCES = (
    {
        "source_id": "senamhi_activation_quebradas",
        "url": "https://www.senamhi.gob.pe/?p=aviso-activacion-quebrada",
        "historical_date_parameter": "f",
    },
    {
        "source_id": "senamhi_piura_24h",
        "url": "https://www.senamhi.gob.pe/main.php?dp=piura&p=aviso-24H",
        "historical_date_parameter": "f",
    },
    {
        "source_id": "indeci_emergencies",
        "url": "https://portal.indeci.gob.pe/emergencias/",
    },
)
SUPPLEMENTAL_SOURCES = (
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


def normalized_text(raw: bytes, content_type: str | None = None):
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if match:
        charset = match.group(1)
    decoded = raw.decode(charset, errors="replace")
    parser = TextExtractor()
    parser.feed(decoded)
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


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
    return summary


def source_for_snapshot(source: dict, snapshot_date: str):
    """Return the exact historical SENAMHI page for the closed UTC day."""
    parameter = source.get("historical_date_parameter")
    if not parameter:
        return dict(source)
    snapshot_day = date.fromisoformat(snapshot_date)
    parts = urlsplit(source["url"])
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[parameter] = snapshot_day.strftime("%d-%m-%Y")
    resolved = dict(source)
    resolved["url"] = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    resolved.pop("historical_date_parameter", None)
    return resolved


def fetch_source(
    source: dict,
    captured_at: datetime,
    snapshot_date: str,
    sleep_fn=time.sleep,
):
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
                    source["source_id"], raw, content_type, snapshot_date
                )
                return {
                    **source,
                    "capture_status": "CAPTURED",
                    "http_status": response.status,
                    "captured_at": captured_at.isoformat(),
                    "content_type": content_type,
                    "content_length": len(raw),
                    "content_sha256": sha256(raw).hexdigest(),
                    "summary": summary,
                    "source_error": None,
                    "unknown_not_zero": False,
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
        "sources": [
            fetch_source(source, now, snapshot_day.isoformat())
            for source in SOURCES
        ],
        "supplemental_sources": [
            fetch_source(source, now, snapshot_day.isoformat())
            for source in SUPPLEMENTAL_SOURCES
        ],
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
