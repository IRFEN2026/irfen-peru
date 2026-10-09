#!/usr/bin/env python3
"""Archive the extra official sources for the Tumbes inventory gap closure (DU 015-2023 names).

Reuses the fetch/route/text helpers of
``scripts/archive_phase2_tumbes_capitana_hualaca_higueron_sources.py`` (PR #364) and
writes to its own archive outside ``site/``. Documents already archived by PR #364
are referenced, not downloaded again.

* ``--capture-supplements`` (network): fetch the supplements the manifest does not hold.
* default (offline): re-hash every archived file against the manifest and the seeds.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT / "config/phase2_tumbes_inventory_anexo_ii_gap_capture_seeds_v0_1.json"
ARCHIVE = ROOT / "data/phase2/source_archive/tumbes_inventory_anexo_ii_gap"
MANIFEST = ARCHIVE / "archive_manifest_v0_1.json"
PUBLIC_ROOT = ROOT / "site"

_spec = importlib.util.spec_from_file_location(
    "irfen_tumbes_capitana_archiver", ROOT / "scripts/archive_phase2_tumbes_capitana_hualaca_higueron_sources.py")
BASE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BASE)
GUARDS = BASE.GUARDS


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_full(url: str, timeout: int, max_bytes: int, resumes: int = 6) -> dict:
    """Download with Content-Length check; resume a short body with HTTP Range requests."""
    from urllib.request import Request, urlopen

    started = datetime.now(timezone.utc).isoformat()
    data, declared, meta, notes = b"", None, {}, []
    for attempt in range(resumes + 1):
        headers = {"User-Agent": BASE.USER_AGENT, "Accept": "*/*"}
        if data:
            headers["Range"] = f"bytes={len(data)}-"
        try:
            with urlopen(Request(BASE.safe_url(url), headers=headers), timeout=timeout) as response:
                if not meta:
                    meta = dict(final_url=response.geturl(), http_status=response.status, content_type=response.headers.get("Content-Type"))
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
            notes.append(f"attempt {attempt}: {type(exc).__name__}: {str(exc)[:120]} after {len(data)} bytes")
            if not meta and not data:
                return dict(status="UNREACHABLE", requested_url=url, error=notes[-1], retrieved_at_utc=started)
        if declared and declared.isdigit() and len(data) >= int(declared):
            break
        if not declared:
            break
        time.sleep(3)
    complete = not (declared and declared.isdigit() and len(data) != int(declared))
    return dict(status="CAPTURED" if complete else "INCOMPLETE_BODY", requested_url=url, **meta,
                content_length_header=declared, transfer_notes=notes, retrieved_at_utc=started, data=data, bytes_read=len(data))


def extract_pages(data: bytes) -> tuple[list[str], str]:
    """pypdf per page; if pypdf fails, fall back to poppler pdftotext (one page per form feed)."""
    try:
        return BASE.pdf_pages(data), "PYPDF_PER_PAGE"
    except Exception as exc:  # noqa: BLE001
        first_error = f"{type(exc).__name__}: {str(exc)[:120]}"
    if shutil.which("pdftotext"):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.pdf"
            src.write_bytes(data)
            out = subprocess.run(["pdftotext", "-layout", str(src), "-"], capture_output=True, timeout=300)
            if out.returncode == 0 and out.stdout.strip():
                pages = out.stdout.decode("utf-8", "replace").split("\f")
                if pages and not pages[-1].strip():
                    pages = pages[:-1]
                return pages, f"POPPLER_PDFTOTEXT_LAYOUT_AFTER_PYPDF_FAILED ({first_error})"
    return [], f"FAILED ({first_error})"


def load_seeds() -> dict:
    seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
    for key, value in GUARDS.items():
        if seeds.get(key) != value:
            raise SystemExit(f"seed contract guard {key} must be {value!r}")
    return seeds


def capture_supplements() -> int:
    seeds = load_seeds()
    limits, terms = seeds["limits"], seeds["search_terms"]
    (ARCHIVE / "raw").mkdir(parents=True, exist_ok=True)
    (ARCHIVE / "text").mkdir(parents=True, exist_ok=True)
    if MANIFEST.is_file():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    else:
        manifest = dict(schema_version="0.1", status="SOURCE_CAPTURE_IDENTITY_NOT_ADJUDICATED_HERE", **GUARDS,
                        seeds_path=str(SEEDS.relative_to(ROOT)), reused_archive=seeds["reused_archive"], records=[],
                        rule="Hits are verbatim text matches only. A hit is not an identity, alias, event or geometry decision.",
                        map_publishable=False)
    held = {r["document_id"] for r in manifest["records"] if r.get("status") == "ARCHIVED" and not r.get("possibly_truncated")}
    added = []
    for item in seeds.get("supplement_documents", []):
        doc_id = item["id"]
        if doc_id in held:
            continue
        manifest["records"] = [r for r in manifest["records"] if r["document_id"] != doc_id]
        for stale in list((ARCHIVE / "raw").glob(f"{doc_id}.*")) + list((ARCHIVE / "text").glob(f"{doc_id}.*")):
            stale.unlink()  # a superseded (e.g. truncated) copy is replaced, never kept unlisted
        attempts, record = [], None
        for url, how, accept in BASE.expand_routes(item["routes"], limits, attempts):
            result = fetch_full(url, limits["timeout_seconds"], limits["max_bytes_per_document"])
            attempt = {k: v for k, v in result.items() if k in ("requested_url", "status", "http_status", "error", "final_url", "retrieved_at_utc", "bytes_read", "content_length_header", "transfer_notes")}
            attempt["route"] = how
            attempts.append(attempt)
            data = result.get("data") or b""
            if result["status"] != "CAPTURED" or (item.get("expect_pdf") and data[:5] != b"%PDF-"):
                time.sleep(2)
                continue
            attempt.update(bytes=len(data), sha256=BASE.sha256_bytes(data))
            if BASE.is_pdf(result):
                pages, extraction = extract_pages(data)
            else:
                pages, extraction = [BASE.html_text(data)], "HTML_TAGS_STRIPPED"
            declared = result.get("content_length_header")
            truncated = bool(declared and declared.isdigit() and int(declared) != len(data))
            hits = BASE.term_hits(pages, terms)
            if accept and not any(a in BASE.fold(" ".join(pages)) for a in accept):
                attempt["rejected"] = "TEXT_LACKS_REQUIRED_TOKEN"
                continue
            ext = ".pdf" if BASE.is_pdf(result) else ".html"
            raw_path = ARCHIVE / "raw" / f"{doc_id}{ext}"
            raw_path.write_bytes(data)
            text_path = ARCHIVE / "text" / f"{doc_id}.pages.json"
            text_path.write_text(json.dumps(dict(document_id=doc_id, sha256_of_raw=BASE.sha256_bytes(data), pages=pages), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            record = {k: v for k, v in result.items() if k not in ("data", "status")}
            record.update(document_id=doc_id, origin=dict(kind="supplement", institution=item["institution"], why=item["why"]),
                          official_url=item["official_url"], served_by_route=how, route_attempts=attempts,
                          text_extraction=extraction, possibly_truncated=truncated,
                          media=ext[1:], bytes=len(data), sha256=BASE.sha256_bytes(data), page_count=len(pages),
                          text_characters=sum(len(p) for p in pages), term_hits=hits, terms_found=sorted({h["term"] for h in hits}),
                          status="ARCHIVED", raw_path=str(raw_path.relative_to(ROOT)), text_path=str(text_path.relative_to(ROOT)),
                          text_sha256=sha256_file(text_path))
            break
        if record is None:
            record = dict(document_id=doc_id, origin=dict(kind="supplement", institution=item["institution"], why=item["why"]),
                          official_url=item["official_url"], status="UNREACHABLE_ALL_ROUTES", route_attempts=attempts)
        manifest["records"].append(record)
        added.append(dict(document_id=doc_id, status=record["status"], served_by_route=record.get("served_by_route")))
    manifest.setdefault("supplement_captures", []).append(dict(
        captured_at_utc=datetime.now(timezone.utc).isoformat(), seeds_sha256_before=manifest.get("seeds_sha256"),
        seeds_sha256_after=sha256_file(SEEDS), documents=added, earlier_records_untouched=True,
        capture_environment="GitHub Actions runner (pull_request workflow phase2-tumbes-inventory-anexo-ii-gap-source-archive)"))
    manifest["seeds_sha256"] = sha256_file(SEEDS)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("supplement capture:", json.dumps(added, ensure_ascii=False))
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
        errors.append("seed contract changed since capture: run --capture-supplements")
    reused = ROOT / seeds["reused_archive"]
    if not reused.is_file():
        errors.append(f"reused archive manifest missing: {seeds['reused_archive']}")
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
    for sub in ("raw", "text"):
        folder = ARCHIVE / sub
        for path in folder.glob("*") if folder.is_dir() else []:
            if path.resolve() not in listed:
                errors.append(f"unlisted file in archive: {path.relative_to(ROOT)}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-supplements", action="store_true")
    args = parser.parse_args(argv)
    if args.capture_supplements:
        return capture_supplements()
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
