#!/usr/bin/env python3
"""Bounded, fail-closed capture of official sources for La Capitana, Hualaca and Higuerón (Tumbes).

Two modes:

* ``--capture`` (network): reads the seed contract, queries the listed official
  search endpoints, follows result pages on allowed hosts one level deep, keeps
  only documents whose text names a search term (plus every explicit seed),
  stores the original bytes, their real SHA-256, a per-page text extraction and
  the exact term hits, and writes ``archive_manifest_v0_1.json``.
* default (offline): re-hashes every archived file and checks it against the
  manifest, the seed contract digest and the fail-closed guards. Nothing is
  downloaded.

The script never interprets a hit. Identity decisions live in
``config/phase2_tumbes_capitana_hualaca_higueron_identity_v0_1.json`` and must
quote archived text only.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "config/phase2_tumbes_capitana_hualaca_higueron_capture_seeds_v0_1.json"
ARCHIVE = ROOT / "site/data/phase2/sources/tumbes_capitana_hualaca_higueron"
MANIFEST = ARCHIVE / "archive_manifest_v0_1.json"
USER_AGENT = "IRFEN-phase2-research-source-archive/1.0 (+https://github.com/IRFEN2026/irfen-peru)"
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
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
DOC_URL_RE = re.compile(r"(/sigridv3/documento/\d+|/handle/\d+/\d+|/items/[0-9a-f-]{36}|/bitstream|\.pdf(\?|$))", re.I)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fold(text: str) -> str:
    """Lower-case and strip accents so 'Higuerón' and 'HIGUERON' both match."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def seeds_digest() -> str:
    return sha256_bytes(SEEDS.read_bytes())


def load_seeds() -> dict:
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if seeds.get(key) != value:
            raise SystemExit(f"seed contract guard {key} must be {value!r}")
    return seeds


def slug(text: str, limit: int = 80) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")
    return s[:limit] or "document"


def safe_url(url: str) -> str:
    """Percent-encode spaces and non-ASCII characters without touching reserved URL syntax."""
    return quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def fetch(url: str, timeout: int, max_bytes: int) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    try:
        request = Request(safe_url(url), headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        with urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                return dict(status="SKIPPED_TOO_LARGE", requested_url=url, retrieved_at_utc=started, bytes_read=len(data))
            return dict(status="CAPTURED", requested_url=url, final_url=response.geturl(), http_status=response.status,
                        content_type=response.headers.get("Content-Type"), retrieved_at_utc=started, data=data)
    except HTTPError as exc:
        return dict(status="HTTP_ERROR", requested_url=url, http_status=exc.code, retrieved_at_utc=started)
    except (URLError, TimeoutError, OSError) as exc:
        return dict(status="UNREACHABLE", requested_url=url, error=type(exc).__name__ + ": " + str(exc)[:200], retrieved_at_utc=started)
    except Exception as exc:  # noqa: BLE001 - invalid URL or protocol error is recorded, never fatal
        return dict(status="FETCH_ERROR", requested_url=url, error=type(exc).__name__ + ": " + str(exc)[:200], retrieved_at_utc=started)


def is_pdf(result: dict) -> bool:
    data = result.get("data") or b""
    return data[:5] == b"%PDF-" or "pdf" in (result.get("content_type") or "").lower()


def pdf_pages(data: bytes) -> list[str]:
    from pypdf import PdfReader  # imported lazily: offline verification needs no PDF parser

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - keep the bytes even if one page fails
            pages.append(f"[TEXT_EXTRACTION_FAILED: {type(exc).__name__}]")
    return pages


def html_text(data: bytes) -> str:
    raw = data.decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", raw))).strip()


def term_hits(pages: list[str], terms: list[dict]) -> list[dict]:
    hits = []
    for term in terms:
        rx = re.compile(fold(term["pattern"]))
        for number, text in enumerate(pages, start=1):
            folded = fold(text)
            for match in rx.finditer(folded):
                start, end = max(0, match.start() - 220), min(len(text), match.end() + 220)
                hits.append(dict(term=term["term"], page=number, excerpt=re.sub(r"\s+", " ", text[start:end]).strip()))
    return hits


def allowed(url: str, hosts: set[str]) -> bool:
    return urlparse(url).netloc.lower() in hosts


def links(data: bytes, base: str) -> list[tuple[str, str]]:
    raw = data.decode("utf-8", "replace")
    found = []
    for href, label in HREF_RE.findall(raw):
        found.append((urljoin(base, html.unescape(href.strip())), re.sub(r"\s+", " ", TAG_RE.sub(" ", html.unescape(label))).strip()))
    return found


def capture() -> int:
    seeds = load_seeds()
    limits = seeds["limits"]
    hosts = {h.lower() for h in seeds["allowed_hosts"]}
    terms = seeds["search_terms"]
    term_rx = re.compile("|".join(fold(t["pattern"]) for t in terms))
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    (ARCHIVE / "raw").mkdir(exist_ok=True)
    (ARCHIVE / "text").mkdir(exist_ok=True)
    for old in list((ARCHIVE / "raw").iterdir()) + list((ARCHIVE / "text").iterdir()):
        old.unlink()
    records, queue, seen, total = [], [], set(), 0

    def store(doc_id: str, result: dict, origin: dict, keep_without_hits: bool) -> None:
        nonlocal total
        record = dict(document_id=doc_id, origin=origin, **{k: v for k, v in result.items() if k != "data"})
        if result["status"] != "CAPTURED":
            records.append(record)
            return
        data = result["data"]
        pdf = is_pdf(result)
        try:
            pages = pdf_pages(data) if pdf else [html_text(data)]
            record["text_extraction"] = "PYPDF_PER_PAGE" if pdf else "HTML_TAGS_STRIPPED"
        except Exception as exc:  # noqa: BLE001
            pages = []
            record["text_extraction"] = f"FAILED: {type(exc).__name__}"
        if not pdf and origin.get("kind") in {"seed", "discovery_result"}:
            for url, label in links(data, result.get("final_url") or result["requested_url"]):
                lower = url.lower()
                looks_doc = lower.endswith(".pdf") or "/descargar" in lower or "/bitstream" in lower or "/bitstreams/" in lower
                if looks_doc and allowed(url, hosts) and url not in seen:
                    attachment = origin["kind"] == "seed" and "/wp-content/uploads/" in lower and "descargar" in fold(label)
                    queue.append((url, dict(kind="link_from_archived_page" if attachment else "link_from_page", parent=doc_id,
                                            anchor_text=label[:200], retained_as_seed_attachment=attachment), attachment))
        hits = term_hits(pages, terms)
        record.update(media="pdf" if pdf else "html", bytes=len(data), sha256=sha256_bytes(data), page_count=len(pages),
                      text_characters=sum(len(p) for p in pages), term_hits=hits,
                      terms_found=sorted({h["term"] for h in hits}))
        if not hits and not keep_without_hits:
            record["status"] = "CAPTURED_NOT_RETAINED_NO_TERM_HIT"
            records.append(record)
            return
        context = [fold(c) for c in limits.get("retain_discovered_only_if_text_contains_any", [])]
        if not keep_without_hits and context and not any(c in fold(" ".join(pages)) for c in context):
            record["status"] = "CAPTURED_NOT_RETAINED_OUTSIDE_TUMBES_CONTEXT"
            records.append(record)
            return
        if total + len(data) > limits["max_total_bytes"]:
            record["status"] = "SKIPPED_TOTAL_BYTE_LIMIT"
            records.append(record)
            return
        total += len(data)
        ext = ".pdf" if pdf else ".html"
        raw_path = ARCHIVE / "raw" / f"{doc_id}{ext}"
        raw_path.write_bytes(data)
        text_path = ARCHIVE / "text" / f"{doc_id}.pages.json"
        text_path.write_text(json.dumps(dict(document_id=doc_id, sha256_of_raw=record["sha256"], pages=pages), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        record.update(status="ARCHIVED", raw_path=str(raw_path.relative_to(ROOT)), text_path=str(text_path.relative_to(ROOT)),
                      text_sha256=sha256_bytes(text_path.read_bytes()))
        records.append(record)

    for query in seeds["discovery_queries"]:
        result = fetch(query["url"], limits["timeout_seconds"], 3_000_000)
        seen.add(query["url"])
        record = dict(document_id=query["id"], origin=dict(kind="discovery_query", query_kind=query["kind"]), **{k: v for k, v in result.items() if k != "data"})
        if result["status"] == "CAPTURED":
            data = result["data"]
            record.update(bytes=len(data), sha256=sha256_bytes(data))
            path = ARCHIVE / "raw" / f"{query['id']}.{'json' if query['kind'].startswith('wp_') else 'html'}"
            path.write_bytes(data)
            record.update(status="ARCHIVED_DISCOVERY_RESPONSE", raw_path=str(path.relative_to(ROOT)))
            total += len(data)
            candidates = []
            if query["kind"].startswith("wp_"):
                try:
                    payload = json.loads(data.decode("utf-8", "replace"))
                    if not isinstance(payload, list):
                        record["parse_error"] = "JSON_NOT_A_RESULT_LIST"
                        payload = []
                    for item in payload:
                        if not isinstance(item, dict):
                            continue
                        url = item.get("source_url") or item.get("url") or item.get("link")
                        title = item.get("title")
                        title = title.get("rendered") if isinstance(title, dict) else title
                        if url:
                            candidates.append((url, str(title or "")))
                except ValueError:
                    record["parse_error"] = "NOT_JSON"
            elif query["kind"] == "html_site_search":
                found = [(u, t) for u, t in links(data, result.get("final_url") or query["url"]) if "/emergencias/" in u]
                unique = list(dict.fromkeys(found))
                candidates = unique[: limits.get("max_site_search_results_per_query", 15)]
            else:
                candidates = [(u, t) for u, t in links(data, result.get("final_url") or query["url"])
                              if term_rx.search(fold(t)) and DOC_URL_RE.search(u)]
            record["candidate_links"] = [dict(url=u, title=t[:200]) for u, t in candidates]
            for url, title in candidates:
                if allowed(url, hosts) and url not in seen:
                    if re.search(r"/sigridv3/documento/\d+/?$", url):
                        url = url.rstrip("/") + "/descargar"
                    queue.append((url, dict(kind="discovery_result", query=query["id"], title=title[:200]), False))
        records.append(record)
        time.sleep(1)

    front = [(seed["url"], dict(kind="seed", seed_id=seed["id"], institution=seed["institution"], why=seed["why"]), True)
             for seed in seeds["seed_documents"]]
    front += [(probe["url"], dict(kind="probe", seed_id=probe["id"], institution=probe["institution"], why=probe["why"]), False)
              for probe in seeds.get("probe_documents", [])]
    sweep = seeds.get("sigrid_id_sweep")
    if sweep:
        front += [(sweep["url_template"].format(id=i), dict(kind="sigrid_id_sweep", seed_id=f"sigrid-{i}"), False)
                  for i in range(sweep["from"], sweep["to"] + 1)]
    queue[:0] = front

    count = 0
    while queue and count < limits["max_documents"]:
        url, origin, keep = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        count += 1
        doc_id = origin.get("seed_id") or f"d{count:02d}-{slug(origin.get('title') or origin.get('anchor_text') or urlparse(url).path.rsplit('/', 1)[-1])}"
        store(doc_id, fetch(url, limits["timeout_seconds"], limits["max_bytes_per_document"]), origin, keep)
        time.sleep(1)
    manifest = dict(
        schema_version="0.1",
        status="SOURCE_CAPTURE_COMPLETED_IDENTITY_NOT_ADJUDICATED_HERE",
        **GUARDS,
        seeds_path=str(SEEDS.relative_to(ROOT)),
        seeds_sha256=seeds_digest(),
        captured_at_utc=datetime.now(timezone.utc).isoformat(),
        capture_environment="GitHub Actions runner (pull_request workflow phase2-tumbes-capitana-hualaca-higueron-source-archive)",
        documents_attempted=count,
        documents_left_in_queue=len(queue),
        records=records,
        rule="Hits are verbatim text matches only. A hit is not an identity, alias, event or geometry decision.",
        map_publishable=False,
    )
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    archived = sum(r["status"].startswith("ARCHIVED") for r in records)
    print(f"capture complete: {archived} archived files, {count} documents attempted, {len(queue)} left in queue")
    return 0


def verify() -> list[str]:
    errors: list[str] = []
    load_seeds()
    if not MANIFEST.is_file():
        return [f"missing {MANIFEST.relative_to(ROOT)}"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if manifest.get(key) != value:
            errors.append(f"manifest guard {key} must be {value!r}")
    if manifest.get("map_publishable") is not False:
        errors.append("manifest map_publishable must be false")
    if manifest.get("seeds_sha256") != seeds_digest():
        errors.append("seed contract changed since capture: run the capture again")
    listed = set()
    for record in manifest.get("records", []):
        raw = record.get("raw_path")
        if not raw:
            continue
        path = ROOT / raw
        listed.add(path.resolve())
        if not path.is_file():
            errors.append(f"archived file missing: {raw}")
        elif sha256_bytes(path.read_bytes()) != record.get("sha256"):
            errors.append(f"SHA-256 mismatch: {raw}")
        text = record.get("text_path")
        if text:
            tpath = ROOT / text
            listed.add(tpath.resolve())
            if not tpath.is_file() or sha256_bytes(tpath.read_bytes()) != record.get("text_sha256"):
                errors.append(f"text extraction missing or changed: {text}")
    for sub in ("raw", "text"):
        for path in (ARCHIVE / sub).glob("*") if (ARCHIVE / sub).is_dir() else []:
            if path.resolve() not in listed:
                errors.append(f"unlisted file in archive: {path.relative_to(ROOT)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="download from the network and rewrite the archive")
    args = parser.parse_args(argv)
    if args.capture:
        return capture()
    errors = verify()
    if errors:
        print("FAIL:")
        for error in errors:
            print("  -", error)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    archived = [r for r in manifest["records"] if r.get("raw_path")]
    print(f"OK: {len(archived)} archived files match their SHA-256; seed contract unchanged; map_publishable=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
