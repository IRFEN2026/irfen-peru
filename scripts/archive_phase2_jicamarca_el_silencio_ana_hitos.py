#!/usr/bin/env python3
"""Replay exact ANA El Silencio regulatory-faja hitos from an already frozen PDF.

The source bytes are the immutable RD 0525-2023 archive already committed for
Jicamarca provenance. Outputs are separate regulatory-context bank lines for
Qda. El Silencio, El Silencio 01 and El Silencio 02. They are never catchment
polygons, channel centrelines, outlets, event footprints, routing inputs, risk
states or alerts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config/phase2_jicamarca_el_silencio_ana_faja_contract_v0_1.json"
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


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guard(doc: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if doc.get(key) != expected:
            raise ArchiveError(f"UNSAFE_{label}_{key}")


def page_text(reader: PdfReader, first: int, last: int) -> str:
    if first < 0 or last < first or last >= len(reader.pages):
        raise ArchiveError(f"INVALID_PAGE_WINDOW {first}:{last} count={len(reader.pages)}")
    return "\n".join((reader.pages[i].extract_text() or "") for i in range(first, last + 1))


def slice_between(text: str, start: str | None, end: str | None) -> str:
    result = text
    if start:
        idx = result.find(start)
        if idx < 0:
            raise ArchiveError(f"START_HEADING_NOT_FOUND {start}")
        result = result[idx:]
    if end:
        idx = result.find(end, 1)
        if idx < 0:
            raise ArchiveError(f"END_HEADING_NOT_FOUND {end}")
        result = result[:idx]
    return result


def parse_codes(text: str, prefix: str, expected_count: int, segment_id: str) -> list[dict]:
    pattern = re.compile(
        rf"\b({re.escape(prefix)}\s*\d{{1,3}})\s+([0-9]{{6}}(?:\.[0-9]+)?)\s+([0-9]{{7}}(?:\.[0-9]+)?)\b",
        re.IGNORECASE,
    )
    first: dict[int, dict] = {}
    for match in pattern.finditer(text):
        code = re.sub(r"\s+", "", match.group(1).upper())
        number = int(code.split("-")[-1])
        if 1 <= number <= expected_count and number not in first:
            first[number] = {
                "segment_id": segment_id,
                "bank": "RIGHT" if prefix.upper() == "HMD-" else "LEFT",
                "hito_code": f"{prefix.upper()}{number:02d}" if number < 100 else f"{prefix.upper()}{number}",
                "source_order": number,
                "easting_m": float(match.group(2)),
                "northing_m": float(match.group(3)),
                "epsg": 32718,
            }
    expected = set(range(1, expected_count + 1))
    actual = set(first)
    if actual != expected:
        raise ArchiveError(
            f"HITO_CODE_SET_INCOMPLETE segment={segment_id} prefix={prefix} "
            f"count={len(actual)} missing={sorted(expected-actual)[:12]}"
        )
    return [first[i] for i in range(1, expected_count + 1)]


def validate_coordinates(rows: list[dict]) -> None:
    for row in rows:
        if not (299000.0 <= row["easting_m"] <= 305500.0):
            raise ArchiveError(f"EASTING_OUT_OF_BOUNDS {row['segment_id']} {row['hito_code']}")
        if not (8679000.0 <= row["northing_m"] <= 8687500.0):
            raise ArchiveError(f"NORTHING_OUT_OF_BOUNDS {row['segment_id']} {row['hito_code']}")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["segment_id", "bank", "hito_code", "source_order", "easting_m", "northing_m", "epsg"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "easting_m": f"{row['easting_m']:.4f}",
                "northing_m": f"{row['northing_m']:.4f}",
            })


def geojson(contract: dict, segment_rows: dict[str, dict[str, list[dict]]], source_sha: str, ledger_shas: dict[str, str]) -> dict:
    transformer = Transformer.from_crs(32718, 4326, always_xy=True)
    features = []
    segment_cfg = {row["segment_id"]: row for row in contract["segments"]}
    for segment_id in [row["segment_id"] for row in contract["segments"]]:
        cfg = segment_cfg[segment_id]
        for bank in ("RIGHT", "LEFT"):
            rows = segment_rows[segment_id][bank]
            coords = []
            for row in rows:
                lon, lat = transformer.transform(row["easting_m"], row["northing_m"])
                if not (-77.1 <= lon <= -76.6 and -12.2 <= lat <= -11.6):
                    raise ArchiveError(f"REPROJECTED_COORDINATE_OUT_OF_BOUNDS {segment_id} {row['hito_code']}")
                coords.append([round(lon, 8), round(lat, 8)])
            features.append({
                "type": "Feature",
                "properties": {
                    **SAFE,
                    "unit_id": f"jicamarca__el_silencio__{segment_id}__{bank.lower()}_bank",
                    "component_id": "el_silencio",
                    "segment_id": segment_id,
                    "source_label": cfg["source_summary_label"],
                    "bank": bank,
                    "geometry_role": "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY",
                    "source_institution": "Autoridad Nacional del Agua",
                    "source_resolution": contract["source"]["resolution"],
                    "source_epsg": 32718,
                    "source_pdf_sha256": source_sha,
                    "coordinate_ledger_sha256": ledger_shas[segment_id],
                    "activation_evidence": False,
                    "event_footprint": False,
                    "catchment_polygon": False,
                    "channel_centerline": False,
                    "outlet_or_confluence": False,
                    "historical_hydraulic_capacity": False,
                    "routing_parameter": False,
                    "risk_or_alert_layer": False,
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            })
    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "component_id": "el_silencio",
            "parent_context": "jicamarca",
            "geometry_role": "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY",
            "source_segments_union_performed": False,
            "event_footprint": False,
            "catchment_polygon": False,
            "channel_centerline": False,
            "outlet_or_confluence": False,
            "routing_enabled": False,
            "risk_or_alert_layer": False,
        },
        "features": features,
    }


def verify_existing(contract: dict) -> dict:
    manifest_path = ROOT / contract["manifest_path"]
    manifest = load(manifest_path)
    guard(manifest, "MANIFEST")
    if manifest.get("status") != "PASS_REPRODUCIBLE_ANA_EL_SILENCIO_FAJA_CONTEXT":
        raise ArchiveError(f"UNKNOWN_MANIFEST_STATUS {manifest.get('status')}")
    source_path = ROOT / contract["source"]["source_pdf_path"]
    if sha256_file(source_path) != contract["source"]["source_pdf_sha256"]:
        raise ArchiveError("SOURCE_PDF_HASH_DRIFT")
    if manifest.get("source_pdf_sha256") != contract["source"]["source_pdf_sha256"]:
        raise ArchiveError("MANIFEST_SOURCE_PDF_HASH_DRIFT")
    for segment in contract["segments"]:
        path = ROOT / segment["ledger_path"]
        if not path.is_file():
            raise ArchiveError(f"MISSING_LEDGER {segment['segment_id']}")
        expected = manifest["segments"][segment["segment_id"]]["coordinate_ledger_sha256"]
        if sha256_file(path) != expected:
            raise ArchiveError(f"LEDGER_HASH_DRIFT {segment['segment_id']}")
    geometry_path = ROOT / contract["geometry_path"]
    if not geometry_path.is_file() or sha256_file(geometry_path) != manifest["geometry_sha256"]:
        raise ArchiveError("GEOMETRY_HASH_DRIFT")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    guard(contract, "CONTRACT")
    if contract.get("component_id") != "el_silencio":
        raise ArchiveError("COMPONENT_MISMATCH")
    qa = contract["qa_rules"]
    required_false = (
        "faja_is_event_footprint", "faja_is_catchment_polygon", "faja_is_channel_centerline",
        "faja_is_outlet_or_confluence", "faja_is_historical_hydraulic_capacity",
        "map_eligible_as_activation_geometry", "may_enable_routing", "may_define_Q_i_t",
        "may_define_travel_time", "may_define_attenuation", "may_promote_parent_activation",
        "may_promote_receiver_overflow", "may_publish_risk_or_alert_semantics",
    )
    if any(qa.get(key) is not False for key in required_false):
        raise ArchiveError("UNSAFE_QA_POLICY")
    if qa.get("map_eligible_as_research_context") is not True or qa.get("segment_union_forbidden") is not True:
        raise ArchiveError("RESEARCH_CONTEXT_OR_SEPARATION_GUARD_MISSING")

    manifest_path = ROOT / contract["manifest_path"]
    if manifest_path.is_file() and not args.refresh:
        manifest = verify_existing(contract)
        print(canonical({"status": manifest["status"], "component_id": "el_silencio"}).strip())
        return
    if not args.refresh:
        raise ArchiveError("MISSING_MANIFEST_REFRESH_REQUIRED")

    source_path = ROOT / contract["source"]["source_pdf_path"]
    if not source_path.is_file():
        raise ArchiveError("MISSING_FROZEN_SOURCE_PDF")
    source_sha = sha256_file(source_path)
    if source_sha != contract["source"]["source_pdf_sha256"]:
        raise ArchiveError(f"SOURCE_PDF_HASH_DRIFT expected={contract['source']['source_pdf_sha256']} actual={source_sha}")
    archive_manifest = load(ROOT / contract["source"]["source_archive_manifest"])
    guard(archive_manifest, "SOURCE_ARCHIVE_MANIFEST")
    if archive_manifest.get("pdf_sha256") != source_sha or archive_manifest.get("source_bytes_archived") is not True:
        raise ArchiveError("SOURCE_ARCHIVE_NOT_IMMUTABLY_BOUND")

    reader = PdfReader(io.BytesIO(source_path.read_bytes()))
    if len(reader.pages) != 14:
        raise ArchiveError(f"UNEXPECTED_SOURCE_PAGE_COUNT {len(reader.pages)}")

    all_segments: dict[str, dict[str, list[dict]]] = {}
    ledger_shas: dict[str, str] = {}
    manifest_segments: dict[str, dict] = {}
    for segment in contract["segments"]:
        first, last = segment["pdf_page_window_zero_based"]
        text = page_text(reader, int(first), int(last))
        text = slice_between(text, segment.get("annex_heading"), segment.get("next_annex_heading"))
        right = parse_codes(text, segment["right_bank_prefix"], int(segment["right_bank_count"]), segment["segment_id"])
        left = parse_codes(text, segment["left_bank_prefix"], int(segment["left_bank_count"]), segment["segment_id"])
        validate_coordinates(right + left)
        if len(right) + len(left) != int(segment["total_hito_count"]):
            raise ArchiveError(f"TOTAL_HITO_COUNT_MISMATCH {segment['segment_id']}")
        ledger_path = ROOT / segment["ledger_path"]
        write_csv(ledger_path, right + left)
        ledger_sha = sha256_file(ledger_path)
        ledger_shas[segment["segment_id"]] = ledger_sha
        all_segments[segment["segment_id"]] = {"RIGHT": right, "LEFT": left}
        manifest_segments[segment["segment_id"]] = {
            "source_summary_label": segment["source_summary_label"],
            "right_bank_hito_count": len(right),
            "left_bank_hito_count": len(left),
            "total_hito_count": len(right) + len(left),
            "coordinate_ledger_path": segment["ledger_path"],
            "coordinate_ledger_sha256": ledger_sha,
            "segment_union_performed": False,
        }

    geometry_doc = geojson(contract, all_segments, source_sha, ledger_shas)
    geometry_path = ROOT / contract["geometry_path"]
    geometry_path.parent.mkdir(parents=True, exist_ok=True)
    geometry_path.write_text(canonical(geometry_doc), encoding="utf-8")
    geometry_sha = sha256_file(geometry_path)

    manifest = {
        "schema_version": "0.1",
        "status": "PASS_REPRODUCIBLE_ANA_EL_SILENCIO_FAJA_CONTEXT",
        **SAFE,
        "component_id": "el_silencio",
        "parent_context": "jicamarca",
        "source_pdf_path": contract["source"]["source_pdf_path"],
        "source_pdf_sha256": source_sha,
        "source_epsg": 32718,
        "output_epsg": 4326,
        "source_bytes_reused_from_existing_archive": True,
        "segments": manifest_segments,
        "geometry_path": contract["geometry_path"],
        "geometry_sha256": geometry_sha,
        "geometry_role": "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY",
        "source_segments_union_performed": False,
        "map_eligible_as_research_context": True,
        "map_eligible_as_activation_geometry": False,
        "faja_is_event_footprint": False,
        "faja_is_catchment_polygon": False,
        "faja_is_channel_centerline": False,
        "faja_is_outlet_or_confluence": False,
        "routing_enabled": False,
        "Q_i_t": None,
        "travel_time": None,
        "attenuation": None,
        "historical_hydraulic_capacity": None,
        "parent_activation_promoted": False,
        "receiver_overflow_inferred": False,
        "risk_or_alert_semantics": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(canonical(manifest), encoding="utf-8")
    verify_existing(contract)
    print(canonical({"status": manifest["status"], "segments": len(manifest_segments), "geometry_sha256": geometry_sha}).strip())


if __name__ == "__main__":
    main()
