#!/usr/bin/env python3
"""Archive the documents checked for Quebrada Dos Barrios (Rímac corridor, Lurigancho-Chosica).

* ``--capture`` (network, run on the GitHub runner): fetch each seed document with
  ``capture: true``, keep the full body only (Content-Length checked, Range resume),
  store raw bytes, per-page text and term hits, and write the manifest.
* default (offline): re-hash every archived file against the manifest and the seeds.

Archive lives outside ``site/`` (GitHub Pages publishes only ``site/``). Documents with
``capture: false`` are listed in the manifest as not captured, with the reason.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "config/phase2_rimac_dos_barrios_capture_seeds_v0_1.json"
ARCHIVE = ROOT / "data/phase2/source_archive/rimac_dos_barrios"
MANIFEST = ARCHIVE / "archive_manifest_v0_1.json"
PUBLIC_ROOT = ROOT / "site"
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
TAG_RE = re.compile(r"<[^>]+>")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fold(text: str) -> str:
    """Lower-case and drop accents one character at a time, so offsets match the original."""
    return "".join((unicodedata.normalize("NFD", c.lower())[:1] or c) for c in text)


def load_seeds() -> dict:
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if seeds.get(key) != value:
            raise SystemExit(f"seed contract guard {key} must be {value!r}")
    if seeds.get("map_publishable") is not False:
        raise SystemExit("seed contract map_publishable must be false")
    return seeds


def safe_url(url: str) -> str:
    return quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def fetch_full(url: str, timeout: int, max_bytes: int, resumes: int = 4) -> dict:
    """Download with a Content-Length check; resume a short body with HTTP Range requests."""
    from urllib.request import Request, urlopen

    started = datetime.now(timezone.utc).isoformat()
    data, declared, meta, notes = b"", None, {}, []
    for attempt in range(resumes + 1):
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if data:
            headers["Range"] = f"bytes={len(data)}-"
        try:
            with urlopen(Request(safe_url(url), headers=headers), timeout=timeout) as response:
                if not meta:
                    meta = dict(final_url=response.geturl(), http_status=response.status,
                                content_type=response.headers.get("Content-Type"))
                    declared = response.headers.get("Content-Length")
                if data and response.status != 206:
                    notes.append(f"resume {attempt}: server ignored Range (HTTP {response.status}); restarting")
                    data = b""
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > max_bytes:
                        return dict(status="SKIPPED_TOO_LARGE", requested_url=url, retrieved_at_utc=started, bytes_read=len(data))
        except Exception as exc:  # noqa: BLE001 - recorded; a resume may follow
            code = getattr(exc, "code", None)
            notes.append(f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:160]} after {len(data)} bytes")
            if not meta and not data:
                return dict(status="HTTP_ERROR" if code else "UNREACHABLE", http_status=code, requested_url=url,
                            error=notes[-1], retrieved_at_utc=started)
        if not (declared and declared.isdigit()) or len(data) >= int(declared):
            break
        time.sleep(3)
    complete = not (declared and declared.isdigit() and len(data) != int(declared))
    return dict(status="CAPTURED" if complete else "INCOMPLETE_BODY", requested_url=url, **meta,
                content_length_header=declared, transfer_notes=notes, retrieved_at_utc=started, data=data, bytes_read=len(data))


def route_urls(item: dict) -> list[tuple[str, str]]:
    urls = []
    for route in item["routes"]:
        if route == "direct":
            urls.append(("direct", item["url"]))
        elif route == "wayback_latest":
            urls.append(("wayback_latest", "https://web.archive.org/web/2id_/" + item["url"]))
        else:
            raise SystemExit(f"unknown route {route!r} for {item['id']}")
    return urls


def pypdf_pages(data: bytes) -> list[str]:
    import logging

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pages = []
    for page in PdfReader(io.BytesIO(data)).pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - keep the bytes even if one page fails
            pages.append(f"[TEXT_EXTRACTION_FAILED: {type(exc).__name__}]")
    return pages


def poppler_pages(data: bytes) -> list[str] | None:
    if not shutil.which("pdftotext"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        src.write_bytes(data)
        out = subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True, timeout=600)
        if out.returncode != 0:
            return None
        pages = out.stdout.decode("utf-8", "replace").split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
        return pages


def html_text(data: bytes) -> str:
    raw = data.decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", raw))).strip()


def term_hits(pages: list[str], terms: list[dict], layer: str) -> list[dict]:
    hits = []
    for term in terms:
        rx = re.compile(term["pattern"])
        for number, text in enumerate(pages, start=1):
            for match in rx.finditer(fold(text)):
                start, end = max(0, match.start() - 220), min(len(text), match.end() + 220)
                hits.append(dict(term=term["term"], text_layer=layer, page=number,
                                 matched=text[match.start():match.end()],
                                 excerpt=re.sub(r"\s+", " ", text[start:end]).strip()))
    return hits


def text_layers(data: bytes, notes: dict) -> dict:
    layers = {}
    try:
        layers["pypdf_pages"] = pypdf_pages(data)
    except Exception as exc:  # noqa: BLE001 - poppler may still read a file pypdf cannot
        notes["pypdf_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    poppler = poppler_pages(data)
    if poppler is not None:
        layers["poppler_layout_pages"] = poppler
    return layers


def ingest_owner_copy(item: dict, base: dict, terms: list[dict]) -> dict:
    """A copy downloaded by the repository owner in a browser, committed under owner_supplied/.

    Its SHA-256 must equal the value fixed in the seeds; the agent never fetched it from the host.
    """
    copy = item["owner_supplied_copy"]
    path = ROOT / copy["path"]
    if not path.resolve().is_relative_to((ARCHIVE / "owner_supplied").resolve()):
        raise SystemExit(f"owner copy for {item['id']} must live under {ARCHIVE.relative_to(ROOT)}/owner_supplied/")
    data = path.read_bytes()
    if sha256_bytes(data) != copy["sha256"] or len(data) != copy["bytes"]:
        raise SystemExit(f"owner copy for {item['id']} does not match the SHA-256/bytes fixed in the seeds")
    notes: dict = {}
    layers = text_layers(data, notes)
    text_path = ARCHIVE / "text" / f"{item['id']}.pages.json"
    text_path.write_text(json.dumps(dict(document_id=item["id"], sha256_of_raw=sha256_bytes(data), **layers),
                                    ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    hits = [h for layer, pages in layers.items() for h in term_hits(pages, terms, layer)]
    return dict(base, status="ARCHIVED", acquisition="OWNER_SUPPLIED_COPY", owner_supplied_copy=copy,
                not_fetched_by_agent_reason=item.get("not_captured_reason"), media="pdf", bytes=len(data),
                sha256=sha256_bytes(data), page_count=len(next(iter(layers.values()))) if layers else 0,
                text_layers=sorted(layers), extraction_notes=notes, raw_path=copy["path"],
                text_path=str(text_path.relative_to(ROOT)), text_sha256=sha256_file(text_path),
                terms_found=sorted({h["term"] for h in hits}), term_hits=hits)


def capture() -> int:
    seeds = load_seeds()
    limits, terms = seeds["limits"], seeds["search_terms"]
    for sub in ("raw", "text"):
        if (ARCHIVE / sub).exists():
            shutil.rmtree(ARCHIVE / sub)  # a capture starts from empty raw/ and text/: nothing stale stays unlisted
        (ARCHIVE / sub).mkdir(parents=True)
    records = []
    for item in seeds["documents"]:
        base = dict(document_id=item["id"], institution=item["institution"], title_as_requested=item["title_as_requested"],
                    requested_url=item["url"], host_kind=item["host_kind"])
        if not item.get("capture") and item.get("owner_supplied_copy"):
            records.append(ingest_owner_copy(item, base, terms))
            continue
        if not item.get("capture"):
            records.append(dict(base, status="NOT_CAPTURED", not_captured_reason=item["not_captured_reason"],
                                not_captured_note=item["not_captured_note"]))
            continue
        attempts, record = [], None
        for how, url in route_urls(item):
            result = fetch_full(url, limits["timeout_seconds"], limits["max_bytes_per_document"])
            attempts.append({**{k: v for k, v in result.items() if k != "data"}, "route": how})
            data = result.get("data") or b""
            if result["status"] != "CAPTURED" or not data:
                time.sleep(limits["pause_seconds"])
                continue
            is_pdf = data[:5] == b"%PDF-"
            if item["expect_pdf"] and not is_pdf:
                attempts[-1]["rejected"] = "EXPECTED_PDF_GOT_OTHER_BYTES"
                continue
            ext = ".pdf" if is_pdf else ".html"
            raw_path = ARCHIVE / "raw" / f"{item['id']}{ext}"
            raw_path.write_bytes(data)
            layers = {}
            if is_pdf:
                try:
                    layers["pypdf_pages"] = pypdf_pages(data)
                except Exception as exc:  # noqa: BLE001 - a broken page tree must not lose the bytes; poppler may still read it
                    attempts[-1]["pypdf_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                poppler = poppler_pages(data)
                if poppler is not None:
                    layers["poppler_layout_pages"] = poppler
            else:
                layers["html_text_pages"] = [html_text(data)]
            text_path = ARCHIVE / "text" / f"{item['id']}.pages.json"
            text_path.write_text(json.dumps(dict(document_id=item["id"], sha256_of_raw=sha256_bytes(data), **layers),
                                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            hits = [h for layer, pages in layers.items() for h in term_hits(pages, terms, layer)]
            record = dict(base, status="ARCHIVED", served_by_route=how, served_url=url,
                          final_url=result.get("final_url"), http_status=result.get("http_status"),
                          content_type=result.get("content_type"), content_length_header=result.get("content_length_header"),
                          retrieved_at_utc=result["retrieved_at_utc"], media=ext[1:], bytes=len(data), sha256=sha256_bytes(data),
                          page_count=len(next(iter(layers.values()))) if layers else 0, text_layers=sorted(layers),
                          raw_path=str(raw_path.relative_to(ROOT)), text_path=str(text_path.relative_to(ROOT)),
                          text_sha256=sha256_file(text_path), terms_found=sorted({h["term"] for h in hits}),
                          term_hits=hits, route_attempts=attempts)
            break
        if record is None:
            record = dict(base, status="UNREACHABLE_ALL_ROUTES", route_attempts=attempts)
        records.append(record)
    manifest = dict(schema_version="0.1", status="SOURCE_CAPTURE_IDENTITY_NOT_ADJUDICATED_HERE", **GUARDS,
                    map_publishable=False, seeds_path=str(SEEDS.relative_to(ROOT)), seeds_sha256=sha256_file(SEEDS),
                    captured_at_utc=datetime.now(timezone.utc).isoformat(),
                    capture_environment="GitHub Actions runner (pull_request workflow phase2-rimac-dos-barrios-source-archive)",
                    rule="Hits are verbatim text matches only. A hit is not an identity, alias, event, works or geometry decision.",
                    records=records)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("capture:", json.dumps([{k: r.get(k) for k in ("document_id", "status", "served_by_route", "bytes", "terms_found")}
                                  for r in records], ensure_ascii=False))
    return 0


def verify() -> list[str]:
    errors: list[str] = []
    seeds = load_seeds()
    if ARCHIVE.resolve().is_relative_to(PUBLIC_ROOT.resolve()):
        errors.append("ARCHIVE points inside site/, which GitHub Pages publishes")
    if not MANIFEST.is_file():
        return errors + [f"missing {MANIFEST.relative_to(ROOT)}"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if manifest.get(key) != value:
            errors.append(f"manifest guard {key} must be {value!r}")
    if manifest.get("map_publishable") is not False:
        errors.append("manifest map_publishable must be false")
    if manifest.get("seeds_sha256") != sha256_file(SEEDS):
        errors.append("seed contract changed since capture: run --capture")
    seed_ids = [d["id"] for d in seeds["documents"]]
    if [r["document_id"] for r in manifest.get("records", [])] != seed_ids:
        errors.append("manifest records do not match the seed documents one to one")
    listed = set()
    for record in manifest.get("records", []):
        for key, digest in (("raw_path", "sha256"), ("text_path", "text_sha256")):
            rel = record.get(key)
            if not rel:
                continue
            path = ROOT / rel
            listed.add(path.resolve())
            if path.resolve().is_relative_to(PUBLIC_ROOT.resolve()):
                errors.append(f"archived file inside the published site/: {rel}")
            if not path.is_file() or sha256_file(path) != record.get(digest):
                errors.append(f"missing or SHA-256 mismatch: {rel}")
        if record.get("status") == "ARCHIVED" and record.get("text_path"):
            text = json.loads((ROOT / record["text_path"]).read_text(encoding="utf-8"))
            if text.get("sha256_of_raw") != record.get("sha256"):
                errors.append(f"text extraction does not point at the archived bytes: {record['document_id']}")
    for sub in ("raw", "text", "owner_supplied"):
        folder = ARCHIVE / sub
        for path in folder.glob("*") if folder.is_dir() else []:
            if path.resolve() not in listed:
                errors.append(f"unlisted file in archive: {path.relative_to(ROOT)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
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
    print(f"OK: {sum(1 for r in manifest['records'] if r.get('raw_path'))} archived files match their SHA-256; seeds unchanged; map_publishable=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
