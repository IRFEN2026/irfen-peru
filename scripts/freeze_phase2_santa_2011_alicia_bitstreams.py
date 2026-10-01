#!/usr/bin/env python3
"""Freeze the ANA/ALICIA Santa 2011 study bitstreams (RESEARCH_ONLY / TEST_ONLY).

Downloads the public ORIGINAL PDF and EXTRACTED_TEXT bitstreams of
oai:repositorio.ana.gob.pe:20.500.12543/2362, verifies them against the
repository's own size + MD5 checksum metadata and computes a true SHA-256 of
the bytes actually received.  The repository checksum is MD5 and is never
relabelled as SHA-256.

Fail-closed rules:
  * Host unreachable / HTTP error -> SOURCE_ACCESS_UNAVAILABLE, no hash is
    produced.  Unavailability is not a negative.
  * Size or MD5 mismatch against the repository metadata -> INTEGRITY_MISMATCH,
    exit code 1, and no SHA-256 is offered for pinning.
  * The text probe only reports term counts in the repository's extracted
    text; absence of a term is not proof the datum was never declared (the
    extraction may miss map legends, scanned pages or figures).

The receipt is written to --out and summarised as GitHub ``::notice::``
annotations so it can be read from the check run without artifact download.
No geometry, capacity, discharge, threshold or map state is produced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

RECORD = "oai:repositorio.ana.gob.pe:20.500.12543/2362"
BASE = "https://repositorio.ana.gob.pe/bitstream/20.500.12543/2362"
TARGETS = {
    "ORIGINAL_PDF": {
        "url": f"{BASE}/1/ANA0001097.pdf",
        "expected_size_bytes": 5981714,
        "repository_md5": "b920108b7054aa77f164b979ea618ec0",
    },
    "EXTRACTED_TEXT": {
        "url": f"{BASE}/2/ANA0001097.pdf.txt",
        "expected_size_bytes": 178336,
        "repository_md5": "80a1625d1ba214efaf5c8ac9c2cec982",
    },
}
# Secondary public mirror registered in earlier Santa PRs (#334). Recorded for
# comparison only; it is not the institutional ORIGINAL bitstream.
MIRRORS = {
    "SIGRID_14534_PDF": "https://sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca/"
    "14534_tratamiento-de-cauce-del-rio-para-el-control-de-inundaciones-en-la-cuenca-del-santa.pdf",
}
TERMS = {
    "WGS": r"\bWGS\b",
    "WGS84": r"WGS\s*-?\s*84",
    "PSAD": r"\bPSAD\b",
    "PSAD56": r"PSAD\s*-?\s*56",
    "DATUM": r"\bdatum\b",
    "UTM": r"\bUTM\b",
    "ZONA_17": r"\bzona\s*17\b",
    "ZONA_18": r"\bzona\s*18\b",
    "HEC_RAS": r"HEC\s*-?\s*RAS",
    "HEC_GEORAS": r"HEC\s*-?\s*GEO\s*-?\s*RAS",
    "TIN": r"\bTIN\b",
    "DEM_MDE": r"\b(?:DEM|MDE|MDT)\b",
    "SECCIONES_TRANSVERSALES": r"secci[oó]n(?:es)?\s+transversal(?:es)?",
    "PROYECCION": r"proyecci[oó]n",
    "SISTEMA_DE_COORDENADAS": r"sistema\s+de\s+coordenadas",
}
# Native axis endpoints recorded by #318/#334 (UTM, datum unresolved).  The
# probe only checks whether these digit strings appear in the extracted text.
AXIS_ENDPOINT_DIGITS = ["758969", "9007565", "788881", "9038309"]

UA = "IRFEN-research-freezer/0.1 (+https://github.com/IRFEN2026/irfen-peru)"


def fetch(url: str, timeout: float) -> tuple[bytes | None, dict]:
    meta: dict = {"url": url}
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            meta.update(
                http_status=resp.status,
                final_url=resp.geturl(),
                content_type=resp.headers.get("Content-Type"),
            )
            return data, meta
    except urllib.error.HTTPError as exc:
        meta.update(access_status="SOURCE_ACCESS_UNAVAILABLE", error=f"HTTP_{exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        meta.update(access_status="SOURCE_ACCESS_UNAVAILABLE", error=f"{type(exc).__name__}: {reason}")
    return None, meta


def digits_only(text: str) -> str:
    return re.sub(r"[^0-9]", "", text)


def text_probe(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace")
    counts = {k: len(re.findall(p, text, flags=re.IGNORECASE)) for k, p in TERMS.items()}
    # Coordinates may be printed with thousand separators; search a digit-only
    # rendering of each line so "758 969" / "758,969" still match.
    lines_digits = [digits_only(line) for line in text.splitlines()]
    endpoints = {d: any(d in ld for ld in lines_digits) for d in AXIS_ENDPOINT_DIGITS}
    contexts = {}
    for key in ("WGS", "PSAD", "DATUM", "ZONA_17", "ZONA_18", "PROYECCION", "SISTEMA_DE_COORDENADAS"):
        hits = [m.start() for m in re.finditer(TERMS[key], text, flags=re.IGNORECASE)][:5]
        contexts[key] = [re.sub(r"\s+", " ", text[max(0, h - 80): h + 80]) for h in hits]
    return {
        "probe_scope": "REPOSITORY_EXTRACTED_TEXT_BITSTREAM_ONLY",
        "term_counts": counts,
        "axis_endpoint_digits_present": endpoints,
        "term_contexts_first5": contexts,
        "inference_limit": (
            "Term absence in the repository's extracted text is not proof that the study never declared "
            "a datum: map legends, figures and scanned pages may not be extracted."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    receipt: dict = {
        "schema_version": "0.1",
        "receipt_id": "santa_2011_alicia_bitstream_freeze_receipt_v0_1",
        "record": RECORD,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "bitstreams": {},
        "mirrors": {},
    }
    integrity_failure = False
    text_bytes = None
    for role, spec in TARGETS.items():
        data, meta = fetch(spec["url"], args.timeout)
        entry = {**meta, "expected_size_bytes": spec["expected_size_bytes"],
                 "repository_checksum_algorithm": "MD5", "repository_md5": spec["repository_md5"]}
        if data is None:
            entry["freeze_status"] = "SOURCE_ACCESS_UNAVAILABLE"
            entry["sha256"] = None
        else:
            md5 = hashlib.md5(data).hexdigest()
            sha = hashlib.sha256(data).hexdigest()
            size_ok = len(data) == spec["expected_size_bytes"]
            md5_ok = md5 == spec["repository_md5"]
            entry.update(received_size_bytes=len(data), received_md5=md5,
                         size_matches_repository=size_ok, md5_matches_repository=md5_ok)
            if size_ok and md5_ok:
                entry["freeze_status"] = "FROZEN_MD5_AND_SIZE_MATCH_REPOSITORY"
                entry["sha256"] = sha
                if role == "EXTRACTED_TEXT":
                    text_bytes = data
            else:
                integrity_failure = True
                entry["freeze_status"] = "INTEGRITY_MISMATCH_NOT_PINNABLE"
                entry["sha256_of_mismatched_bytes"] = sha
                entry["sha256"] = None
        receipt["bitstreams"][role] = entry
        print(f"::notice title=santa-freeze {role}::{json.dumps({k: entry.get(k) for k in ('freeze_status', 'received_size_bytes', 'received_md5', 'sha256', 'error')})}")

    for name, url in MIRRORS.items():
        data, meta = fetch(url, args.timeout)
        if data is not None:
            meta.update(received_size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                        md5=hashlib.md5(data).hexdigest(),
                        role="SECONDARY_MIRROR_COMPARISON_ONLY")
            pdf = receipt["bitstreams"]["ORIGINAL_PDF"]
            meta["byte_identical_to_ana_original"] = (
                pdf.get("sha256") is not None and pdf["sha256"] == meta["sha256"]
            )
        receipt["mirrors"][name] = meta
        print(f"::notice title=santa-freeze {name}::{json.dumps({k: meta.get(k) for k in ('access_status', 'received_size_bytes', 'sha256', 'byte_identical_to_ana_original', 'error')})}")

    if text_bytes is not None:
        receipt["text_probe"] = text_probe(text_bytes)
        tp = receipt["text_probe"]
        print(f"::notice title=santa-freeze TEXT_PROBE counts::{json.dumps(tp['term_counts'])}")
        print(f"::notice title=santa-freeze TEXT_PROBE axis endpoints::{json.dumps(tp['axis_endpoint_digits_present'])}")
        for key, ctx in tp["term_contexts_first5"].items():
            if ctx:
                print(f"::notice title=santa-freeze TEXT_CONTEXT {key}::{json.dumps(ctx, ensure_ascii=False)[:900]}")
    else:
        receipt["text_probe"] = {"probe_status": "NOT_RUN_TEXT_BITSTREAM_NOT_FROZEN"}

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    if integrity_failure:
        print("::error title=santa-freeze::Received bytes do not match repository size/MD5; nothing pinnable.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
