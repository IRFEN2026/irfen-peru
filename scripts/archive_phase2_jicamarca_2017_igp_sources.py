#!/usr/bin/env python3
"""Freeze exact bytes for three preregistered official IGP 2017 pages.

This is a provenance-only archive. It does not reinterpret event outcomes, create
negative evidence, resolve geometry/outlets, or parameterize collector routing.
A source-access failure remains UNKNOWN/BLOCKED and partial bytes are discarded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/phase2_jicamarca_2017_igp_source_archive_contract_v0_1.json"
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


class ArchiveError(RuntimeError):
    pass


class SourceUnavailable(ArchiveError):
    pass


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_bytes(data: bytes):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path):
    return sha256_bytes(path.read_bytes())


def guards(obj, label):
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise ArchiveError(f"UNSAFE_{label}_{key}")


def validate_contract_binding(contract, metadata):
    guards(contract, "ARCHIVE_CONTRACT")
    guards(metadata, "EVENT_METADATA")
    meta_by = {row["source_id"]: row for row in metadata.get("sources", [])}
    expected_ids = [row["source_id"] for row in contract["sources"]]
    if len(expected_ids) != len(set(expected_ids)):
        raise ArchiveError("DUPLICATE_SOURCE_ID")
    if len(expected_ids) != 3:
        raise ArchiveError("UNEXPECTED_SOURCE_COUNT")
    for source in contract["sources"]:
        if not source["url"].startswith("https://"):
            raise ArchiveError(f"NON_HTTPS_SOURCE {source['source_id']}")
        meta = meta_by.get(source["source_id"])
        if meta is None:
            raise ArchiveError(f"SOURCE_NOT_IN_EVENT_METADATA {source['source_id']}")
        if meta.get("url") != source["url"]:
            raise ArchiveError(f"SOURCE_URL_MISMATCH {source['source_id']}")
        if meta.get("source_role") != source["source_role"]:
            raise ArchiveError(f"SOURCE_ROLE_MISMATCH {source['source_id']}")
        if meta.get("source_bytes_sha256") is not None:
            raise ArchiveError(f"FROZEN_BASE_MUTATION_REQUIRED_FORBIDDEN {source['source_id']}")
    return meta_by


def download(source, max_bytes):
    request = Request(
        source["url"],
        headers={
            "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with urlopen(request, timeout=90) as response:
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise SourceUnavailable(
                    f"SOURCE_TOO_LARGE declared={length} source_id={source['source_id']}"
                )
            data = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise SourceUnavailable(
            f"SOURCE_FETCH_FAILED {type(exc).__name__} source_id={source['source_id']}"
        ) from exc

    if len(data) > max_bytes:
        raise SourceUnavailable(
            f"SOURCE_TOO_LARGE actual>{max_bytes} source_id={source['source_id']}"
        )
    if not data:
        raise SourceUnavailable(f"EMPTY_SOURCE source_id={source['source_id']}")

    host = (urlparse(final_url).hostname or "").lower()
    if not (host == "gob.pe" or host.endswith(".gob.pe")):
        raise SourceUnavailable(
            f"UNEXPECTED_FINAL_HOST host={host} source_id={source['source_id']}"
        )
    prefix = data[:4096].lower()
    if content_type not in {"text/html", "application/xhtml+xml"} and not (
        b"<html" in prefix or b"<!doctype html" in prefix
    ):
        raise SourceUnavailable(
            f"NOT_HTML content_type={content_type} source_id={source['source_id']}"
        )
    return data, final_url, content_type


def provenance_hashes(contract_path, contract):
    metadata_path = ROOT / contract["metadata_contract"]
    discovery_path = ROOT / contract["effective_discovery_contract"]
    return {
        "archive_contract_sha256": file_sha256(contract_path),
        "metadata_contract_sha256": file_sha256(metadata_path),
        "effective_discovery_contract_sha256": file_sha256(discovery_path),
    }


def verify_existing(contract_path, contract, archive_root, manifest):
    guards(manifest, "MANIFEST")
    if manifest.get("status") != "PASS_REPRODUCIBLE_IGP_2017_BYTE_ARCHIVE":
        raise ArchiveError(f"UNEXPECTED_PASS_STATUS {manifest.get('status')}")
    expected_hashes = provenance_hashes(contract_path, contract)
    for key, expected in expected_hashes.items():
        if manifest.get(key) != expected:
            raise ArchiveError(f"PROVENANCE_HASH_DRIFT {key}")
    rows = manifest.get("sources", [])
    if len(rows) != len(contract["sources"]):
        raise ArchiveError("ARCHIVE_COUNT_MISMATCH")
    rows_by_id = {row["source_id"]: row for row in rows}
    for source in contract["sources"]:
        row = rows_by_id.get(source["source_id"])
        if row is None:
            raise ArchiveError(f"MISSING_MANIFEST_SOURCE {source['source_id']}")
        if row.get("source_url") != source["url"]:
            raise ArchiveError(f"MANIFEST_URL_DRIFT {source['source_id']}")
        path = archive_root / source["archive_filename"]
        if not path.is_file():
            raise ArchiveError(f"MISSING_ARCHIVE {path}")
        data = path.read_bytes()
        actual = sha256_bytes(data)
        if row.get("sha256") != actual:
            raise ArchiveError(f"ARCHIVE_HASH_DRIFT {source['source_id']}")
        if row.get("bytes") != len(data):
            raise ArchiveError(f"ARCHIVE_SIZE_DRIFT {source['source_id']}")
        if row.get("archive_path") != path.relative_to(ROOT).as_posix():
            raise ArchiveError(f"ARCHIVE_PATH_DRIFT {source['source_id']}")


def blocked_manifest(contract_path, contract, failures):
    return {
        "schema_version": "0.1",
        "status": "BLOCKED_PUBLIC_OFFICIAL_SOURCE_BYTES_NOT_REPRODUCIBLE",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        **provenance_hashes(contract_path, contract),
        "content_interpreted": False,
        "event_attribution_modified": False,
        "negative_evidence_created": False,
        "geometry_modified": False,
        "outlet_or_confluence_inferred": False,
        "Q_i_t_inferred": False,
        "travel_time_inferred": False,
        "attenuation_inferred": False,
        "hydraulic_capacity_inferred": False,
        "thresholds_imported": False,
        "routing_enabled": False,
        "alerting_enabled": False,
        "source_count": 0,
        "partial_archive_retained": False,
        "source_probe_failures": failures,
        "rule": "Official-source access failure remains UNKNOWN/BLOCKED; it is not negative evidence and cannot promote geometry, routing, thresholds, capacity, risk or alerting.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    metadata = load(ROOT / contract["metadata_contract"])
    validate_contract_binding(contract, metadata)

    discovery = load(ROOT / contract["effective_discovery_contract"])
    guards(discovery, "EFFECTIVE_DISCOVERY")
    if discovery.get("collector_coupling_effect", {}).get("routing_status") != "BLOCKED_PENDING_REPRODUCIBLE_OUTLETS_AND_ROUTING":
        raise ArchiveError("ROUTING_GATE_NOT_BLOCKED")

    archive_root = ROOT / contract["archive_root"]
    manifest_path = ROOT / contract["manifest_path"]
    archive_root.mkdir(parents=True, exist_ok=True)

    if manifest_path.is_file() and not args.refresh:
        manifest = load(manifest_path)
        guards(manifest, "MANIFEST")
        if manifest.get("status") == "PASS_REPRODUCIBLE_IGP_2017_BYTE_ARCHIVE":
            verify_existing(contract_path, contract, archive_root, manifest)
        elif manifest.get("status") == "BLOCKED_PUBLIC_OFFICIAL_SOURCE_BYTES_NOT_REPRODUCIBLE":
            if manifest.get("source_count") != 0 or manifest.get("partial_archive_retained") is not False:
                raise ArchiveError("UNSAFE_BLOCKED_MANIFEST")
            for source in contract["sources"]:
                if (archive_root / source["archive_filename"]).exists():
                    raise ArchiveError(f"PARTIAL_ARCHIVE_PRESENT {source['source_id']}")
        else:
            raise ArchiveError(f"UNKNOWN_MANIFEST_STATUS {manifest.get('status')}")
        print(json.dumps({"status": manifest["status"], "source_count": manifest.get("source_count", 0)}, sort_keys=True))
        return

    if not args.refresh:
        raise ArchiveError("MISSING_MANIFEST_REFRESH_REQUIRED")

    max_bytes = int(contract["max_bytes_per_source"])
    staged = []
    failures = []
    for source in contract["sources"]:
        try:
            data, final_url, content_type = download(source, max_bytes)
            staged.append((source, data, final_url, content_type))
        except SourceUnavailable as exc:
            failures.append(
                {
                    "source_id": source["source_id"],
                    "source_url": source["url"],
                    "error": str(exc),
                }
            )
            break

    if failures:
        for source in contract["sources"]:
            path = archive_root / source["archive_filename"]
            if path.exists():
                path.unlink()
        manifest = blocked_manifest(contract_path, contract, failures)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(canonical(manifest), encoding="utf-8")
        print(json.dumps({"status": manifest["status"], "failures": failures}, ensure_ascii=False, sort_keys=True))
        return

    rows = []
    for source, data, final_url, content_type in staged:
        path = archive_root / source["archive_filename"]
        path.write_bytes(data)
        rows.append(
            {
                "source_id": source["source_id"],
                "source_role": source["source_role"],
                "source_url": source["url"],
                "final_url": final_url,
                "content_type": content_type,
                "archive_path": path.relative_to(ROOT).as_posix(),
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
        )

    manifest = {
        "schema_version": "0.1",
        "status": "PASS_REPRODUCIBLE_IGP_2017_BYTE_ARCHIVE",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        **provenance_hashes(contract_path, contract),
        "content_interpreted": False,
        "event_attribution_modified": False,
        "negative_evidence_created": False,
        "geometry_modified": False,
        "outlet_or_confluence_inferred": False,
        "Q_i_t_inferred": False,
        "travel_time_inferred": False,
        "attenuation_inferred": False,
        "hydraulic_capacity_inferred": False,
        "thresholds_imported": False,
        "routing_enabled": False,
        "alerting_enabled": False,
        "source_count": len(rows),
        "partial_archive_retained": False,
        "sources": rows,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(canonical(manifest), encoding="utf-8")
    verify_existing(contract_path, contract, archive_root, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "source_count": len(rows),
                "sha256": {row["source_id"]: row["sha256"] for row in rows},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
