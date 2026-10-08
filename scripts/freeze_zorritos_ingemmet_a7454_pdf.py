#!/usr/bin/env python3
"""Fail-closed raw-byte capture of INGEMMET A7454 (Tumbes, 2023-2024).

The report contains the Tucillal 24-050 and Leoncio Prado/Tiburón 24-051
references, but capturing the report never adjudicates a child, geometry,
outlet, event, hydraulic capacity, or hazard threshold.

Live access: --capture --out-dir PATH
Offline bytes: --from-file PDF --out-dir PATH (origin remains unverified)
Replay: --verify --out-dir PATH
Contract check: --self-test (offline, no official source claims)
"""
import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SOURCE_URL = (
    "https://sigrid.cenepred.gob.pe/sigridv3/storage/biblioteca/"
    "16827_informe-tecnico-n0-a7454-evaluacion-de-zonas-criticas-por-"
    "peligros-geologicos-ante-el-fenomeno-el-nino-2023-2024-"
    "departamento-de-tumbes.pdf"
)
PDF_NAME = "ingemmet_a7454.raw.pdf"
MANIFEST_NAME = "manifest_v0_1.json"
MAX_BYTES = 64 * 1024 * 1024
SAFE = {
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


class SourceFreezeError(RuntimeError):
    pass


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_pdf(raw):
    if not raw.startswith(b"%PDF-"):
        raise SourceFreezeError("NOT_PDF_MAGIC")
    if b"%%EOF" not in raw[-2048:]:
        raise SourceFreezeError("PDF_EOF_NOT_PRESENT")
    if len(raw) > MAX_BYTES:
        raise SourceFreezeError("PDF_EXCEEDS_CAPTURE_LIMIT")
    if len(raw) < 64:
        raise SourceFreezeError("PDF_IMPLAUSIBLY_SHORT")


def fetch_source():
    request = Request(SOURCE_URL, headers={"User-Agent": "IRFEN-RESEARCH-ONLY-A7454-raw-freeze/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            if response.status != 200:
                raise SourceFreezeError(f"HTTP_{response.status}")
            final_url = response.geturl()
            if urlsplit(final_url).scheme != "https" or urlsplit(final_url).hostname != "sigrid.cenepred.gob.pe":
                raise SourceFreezeError("UNEXPECTED_REDIRECT_ORIGIN")
            raw = response.read(MAX_BYTES + 1)
            metadata = {"final_url": final_url, "content_type": response.headers.get("Content-Type"),
                        "etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SourceFreezeError(f"SOURCE_ACCESS_UNAVAILABLE_{type(exc).__name__}") from exc
    validate_pdf(raw)
    return raw, metadata


def make_manifest(raw, mode, metadata):
    if mode not in ("OFFICIAL_URL_HTTP_RESPONSE", "LOCAL_FILE_ORIGIN_UNVERIFIED"):
        raise SourceFreezeError("INVALID_ACQUISITION_MODE")
    validate_pdf(raw)
    return {
        "schema_version": "0.1", **SAFE,
        "source_id": "INGEMMET-A7454-TUMBES-2023-2024",
        "official_source_url": SOURCE_URL,
        "acquisition_mode": mode,
        "source_origin_verified": mode == "OFFICIAL_URL_HTTP_RESPONSE",
        "source_bytes_sha256": sha256(raw),
        "source_bytes_size": len(raw),
        "raw_file": PDF_NAME,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_response_metadata": metadata if mode == "OFFICIAL_URL_HTTP_RESPONSE" else None,
        "claim_level": "REPORT_RAW_BYTES_ONLY_NOT_CHILD_LEVEL_ADJUDICATION",
        "feature_references_for_later_review": ["24-050 TUCILLAL", "24-051 LEONCIO_PRADO_TIBURON_PAIRED"],
        "feature_text_independently_verified": False,
        "geometries_inferred": False,
        "outlets_verified": False,
        "events_promoted": False,
        "map_publishable": False,
        "marine_and_fluvial_hazards_combined": False,
        "child_event_transfer_allowed": False,
        "interpretation": "Raw report byte freeze only. A PDF is not a channel line, outlet, flood footprint, dated child event, capacity, or threshold."
    }


def write_capture(raw, manifest, out_dir):
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise SourceFreezeError("OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".a7454_capture_", dir=out_dir.parent) as temp:
        staged = Path(temp) / "capture"
        staged.mkdir()
        (staged / PDF_NAME).write_bytes(raw)
        (staged / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        verify_capture(staged)
        os.replace(staged, out_dir)


def verify_capture(out_dir):
    out_dir = Path(out_dir)
    manifest = json.loads((out_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        if manifest.get(key, "MISSING") != expected:
            raise SourceFreezeError(f"UNSAFE_GUARD_{key}")
    if manifest.get("source_id") != "INGEMMET-A7454-TUMBES-2023-2024":
        raise SourceFreezeError("SOURCE_ID_MISMATCH")
    if manifest.get("official_source_url") != SOURCE_URL:
        raise SourceFreezeError("SOURCE_URL_MISMATCH")
    mode = manifest.get("acquisition_mode")
    if mode not in ("OFFICIAL_URL_HTTP_RESPONSE", "LOCAL_FILE_ORIGIN_UNVERIFIED"):
        raise SourceFreezeError("INVALID_ACQUISITION_MODE")
    if manifest.get("source_origin_verified") is not (mode == "OFFICIAL_URL_HTTP_RESPONSE"):
        raise SourceFreezeError("ORIGIN_VERIFICATION_MISMATCH")
    if mode == "OFFICIAL_URL_HTTP_RESPONSE":
        meta = manifest.get("http_response_metadata") or {}
        final_url = meta.get("final_url", "")
        if urlsplit(final_url).scheme != "https" or urlsplit(final_url).hostname != "sigrid.cenepred.gob.pe":
            raise SourceFreezeError("INVALID_OFFICIAL_HTTP_ORIGIN")
    if manifest.get("raw_file") != PDF_NAME:
        raise SourceFreezeError("UNEXPECTED_RAW_FILENAME")
    for key in ("feature_text_independently_verified", "geometries_inferred", "outlets_verified",
                "events_promoted", "map_publishable", "marine_and_fluvial_hazards_combined", "child_event_transfer_allowed"):
        if manifest.get(key) is not False:
            raise SourceFreezeError(f"PROMOTION_FLAG_SET_{key}")
    if manifest.get("claim_level") != "REPORT_RAW_BYTES_ONLY_NOT_CHILD_LEVEL_ADJUDICATION":
        raise SourceFreezeError("CLAIM_LEVEL_PROMOTED")
    raw = (out_dir / PDF_NAME).read_bytes()
    validate_pdf(raw)
    if sha256(raw) != manifest.get("source_bytes_sha256") or len(raw) != manifest.get("source_bytes_size"):
        raise SourceFreezeError("RAW_BYTES_HASH_OR_SIZE_MISMATCH")
    return "PASS_RAW_REPORT_BYTES_HASH_MATCH_NO_PROMOTION"


def self_test():
    sample = b"%PDF-1.4\n" + b"% IRFEN SYNTHETIC TEST BYTES NOT AN OFFICIAL PDF\n" + b"0" * 70 + b"\n%%EOF\n"
    try:
        validate_pdf(b"not a pdf")
    except SourceFreezeError as exc:
        assert str(exc) == "NOT_PDF_MAGIC"
    else:
        raise AssertionError("Non-PDF accepted")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        manifest = make_manifest(sample, "LOCAL_FILE_ORIGIN_UNVERIFIED", None)
        assert manifest["source_origin_verified"] is False
        assert manifest["map_publishable"] is False
        write_capture(sample, manifest, root / "capture")
        assert verify_capture(root / "capture").startswith("PASS_")
        tampered = (root / "capture" / PDF_NAME)
        tampered.write_bytes(sample + b"\nTAMPER")
        try:
            verify_capture(root / "capture")
        except SourceFreezeError as exc:
            assert str(exc) == "RAW_BYTES_HASH_OR_SIZE_MISMATCH"
        else:
            raise AssertionError("Tampered bytes accepted")
        try:
            write_capture(sample, manifest, root / "capture")
        except SourceFreezeError as exc:
            assert str(exc) == "OUTPUT_ALREADY_EXISTS_NO_OVERWRITE"
        else:
            raise AssertionError("Existing capture overwritten")
    return "PASS_A7454_OFFLINE_SELF_TEST_NO_OFFICIAL_SOURCE_CLAIMS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--capture", action="store_true")
    action.add_argument("--from-file", type=Path)
    action.add_argument("--verify", action="store_true")
    action.add_argument("--self-test", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    if args.self_test:
        print(self_test())
        return
    if args.out_dir is None:
        parser.error("--out-dir required except with --self-test")
    if args.verify:
        print(verify_capture(args.out_dir))
        return
    if args.capture:
        raw, metadata = fetch_source()
        mode = "OFFICIAL_URL_HTTP_RESPONSE"
    else:
        raw, metadata = args.from_file.read_bytes(), None
        mode = "LOCAL_FILE_ORIGIN_UNVERIFIED"
    manifest = make_manifest(raw, mode, metadata)
    write_capture(raw, manifest, args.out_dir)
    print(json.dumps({"status": "CAPTURED_REPORT_BYTES_NOT_ADJUDICATED", "source_origin_verified": manifest["source_origin_verified"],
                      "sha256": manifest["source_bytes_sha256"], "map_publishable": False}, sort_keys=True))


if __name__ == "__main__":
    main()
