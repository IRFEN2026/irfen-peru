#!/usr/bin/env python3
"""Freeze official ANA Río Seco faja bytes and exact hito coordinates.

This script is deliberately bounded to RD 0525-2023-ANA-AAA.CF. It produces
regulatory-context geometry only. It never treats a faja marginal as an event
footprint, drainage polygon, channel centreline, outlet, confluence, hydraulic
capacity or routing input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pypdf import PdfReader
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/phase2_jicamarca_rio_seco_ana_hito_archive_contract_v0_1.json"
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


class SourceBlocked(ArchiveError):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def guard(doc: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if doc.get(key) != expected:
            raise ArchiveError(f"UNSAFE_{label}_{key}")


def download_pdf(url: str, max_bytes: int) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
            "Accept": "application/pdf,*/*;q=0.5",
        },
    )
    try:
        with urlopen(req, timeout=120) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > max_bytes:
                raise SourceBlocked(f"PDF_TOO_LARGE declared={declared}")
            data = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SourceBlocked(f"SOURCE_FETCH_FAILED {type(exc).__name__}") from exc
    if not data:
        raise SourceBlocked("EMPTY_PDF")
    if len(data) > max_bytes:
        raise SourceBlocked(f"PDF_TOO_LARGE actual>{max_bytes}")
    if not data.startswith(b"%PDF-"):
        raise SourceBlocked("NOT_PDF_MAGIC")
    return data


def extract_window_text(pdf_bytes: bytes, first_page: int, last_page: int) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:  # pragma: no cover - dependency/parser boundary
        raise SourceBlocked(f"PDF_PARSE_FAILED {type(exc).__name__}") from exc
    if len(reader.pages) <= last_page:
        raise SourceBlocked(f"PDF_PAGE_COUNT_TOO_SMALL {len(reader.pages)}")
    text_parts: list[str] = []
    for index in range(first_page, last_page + 1):
        try:
            text_parts.append(reader.pages[index].extract_text() or "")
        except Exception as exc:  # pragma: no cover
            raise SourceBlocked(f"PDF_TEXT_EXTRACTION_FAILED page={index} {type(exc).__name__}") from exc
    return "\n".join(text_parts), len(reader.pages)


def extract_header_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((reader.pages[i].extract_text() or "") for i in range(min(4, len(reader.pages))))


def _parse_first_occurrences(text: str, prefix: str, expected_count: int) -> list[dict]:
    # PDF text extraction may interleave the two bank columns. Capture every
    # explicit code/easting/northing triple and keep only the first occurrence
    # for each code. The main Río Seco table precedes the tributary tables.
    pattern = re.compile(
        rf"\b({re.escape(prefix)}\s*\d{{1,3}})\s+([0-9]{{6}}(?:\.[0-9]+)?)\s+([0-9]{{7}}(?:\.[0-9]+)?)\b",
        re.IGNORECASE,
    )
    first: dict[int, dict] = {}
    for match in pattern.finditer(text):
        raw_code = re.sub(r"\s+", "", match.group(1).upper())
        number = int(raw_code.split("-")[-1])
        if 1 <= number <= expected_count and number not in first:
            first[number] = {
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
        missing = sorted(expected - actual)
        raise SourceBlocked(f"HITO_CODE_SET_INCOMPLETE prefix={prefix} count={len(actual)} missing={missing[:12]}")
    return [first[i] for i in range(1, expected_count + 1)]


def validate_coordinates(rows: list[dict]) -> None:
    for row in rows:
        e = row["easting_m"]
        n = row["northing_m"]
        if not (294000.0 <= e <= 313000.0):
            raise SourceBlocked(f"EASTING_OUT_OF_BOUNDS {row['hito_code']}={e}")
        if not (8677000.0 <= n <= 8688000.0):
            raise SourceBlocked(f"NORTHING_OUT_OF_BOUNDS {row['hito_code']}={n}")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["bank", "hito_code", "source_order", "easting_m", "northing_m", "epsg"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "easting_m": f"{row['easting_m']:.4f}",
                    "northing_m": f"{row['northing_m']:.4f}",
                }
            )


def make_geojson(right: list[dict], left: list[dict], source_sha: str, ledger_sha: str) -> dict:
    transformer = Transformer.from_crs(32718, 4326, always_xy=True)

    def feature(bank: str, rows: list[dict]) -> dict:
        coords = []
        for row in rows:
            lon, lat = transformer.transform(row["easting_m"], row["northing_m"])
            if not (-77.1 <= lon <= -76.6 and -12.2 <= lat <= -11.6):
                raise SourceBlocked(f"REPROJECTED_COORDINATE_OUT_OF_BOUNDS {row['hito_code']}={lon},{lat}")
            coords.append([round(lon, 8), round(lat, 8)])
        suffix = "right_bank" if bank == "RIGHT" else "left_bank"
        return {
            "type": "Feature",
            "properties": {
                **SAFE,
                "unit_id": f"jicamarca__rio_seco__ana_faja_{suffix}",
                "component_id": "rio_seco",
                "bank": bank,
                "geometry_role": "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY",
                "source_institution": "Autoridad Nacional del Agua",
                "source_resolution": "RESOLUCIÓN DIRECTORAL N° 0525-2023-ANA-AAA.CF",
                "source_epsg": 32718,
                "source_pdf_sha256": source_sha,
                "coordinate_ledger_sha256": ledger_sha,
                "activation_evidence": False,
                "event_footprint": False,
                "catchment_polygon": False,
                "channel_centerline": False,
                "outlet_or_confluence": False,
                "historical_hydraulic_capacity": False,
                "routing_parameter": False,
                "risk_or_alert_layer": False,
                "alerting_enabled": False,
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        }

    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "component_id": "rio_seco",
            "geometry_role": "ANA_REGULATORY_FAJA_MARGIN_CONTEXT_ONLY",
            "source_segments_union_performed": False,
            "event_footprint": False,
            "catchment_polygon": False,
            "channel_centerline": False,
            "outlet_or_confluence": False,
            "routing_enabled": False,
            "risk_or_alert_layer": False,
        },
        "features": [feature("RIGHT", right), feature("LEFT", left)],
    }


def blocked_manifest(error: str) -> dict:
    return {
        "schema_version": "0.1",
        "status": "BLOCKED_PUBLIC_ANA_SOURCE_OR_TABLE_NOT_REPRODUCIBLE",
        **SAFE,
        "component_id": "rio_seco",
        "source_bytes_archived": False,
        "coordinate_ledger_frozen": False,
        "regulatory_context_geometry_frozen": False,
        "partial_archive_retained": False,
        "map_eligible": False,
        "error": error,
        "rule": "Source or extraction failure remains UNKNOWN/BLOCKED and cannot become missing-event evidence, approximate geometry, an outlet, routing, capacity, risk or alert semantics.",
    }


def verify_existing(contract: dict, identity: dict, pdf_path: Path, ledger_path: Path, geometry_path: Path, manifest_path: Path) -> dict:
    manifest = load(manifest_path)
    guard(manifest, "MANIFEST")
    if manifest.get("status") == "BLOCKED_PUBLIC_ANA_SOURCE_OR_TABLE_NOT_REPRODUCIBLE":
        if manifest.get("partial_archive_retained") is not False:
            raise ArchiveError("UNSAFE_PARTIAL_BLOCKED_ARCHIVE")
        if any(path.exists() for path in (pdf_path, ledger_path, geometry_path)):
            raise ArchiveError("BLOCKED_STATE_RETAINS_DERIVED_OR_SOURCE_ARTIFACT")
        if identity["source"].get("remote_bytes_sha256") is not None:
            raise ArchiveError("BLOCKED_IDENTITY_HAS_SOURCE_SHA")
        return manifest
    if manifest.get("status") != "PASS_REPRODUCIBLE_ANA_RIO_SECO_MAIN_FAJA_ARCHIVE":
        raise ArchiveError(f"UNKNOWN_MANIFEST_STATUS {manifest.get('status')}")
    for path in (pdf_path, ledger_path, geometry_path):
        if not path.is_file():
            raise ArchiveError(f"MISSING_FROZEN_ARTIFACT {path}")
    if sha256_file(pdf_path) != manifest["pdf_sha256"]:
        raise ArchiveError("PDF_HASH_DRIFT")
    if sha256_file(ledger_path) != manifest["coordinate_ledger_sha256"]:
        raise ArchiveError("LEDGER_HASH_DRIFT")
    if sha256_file(geometry_path) != manifest["geometry_sha256"]:
        raise ArchiveError("GEOMETRY_HASH_DRIFT")
    if identity["source"].get("remote_bytes_sha256") != manifest["pdf_sha256"]:
        raise ArchiveError("IDENTITY_SOURCE_SHA_DRIFT")
    if identity["regulatory_geometry_evidence"].get("coordinate_ledger_path") != contract["coordinate_ledger_path"]:
        raise ArchiveError("IDENTITY_LEDGER_PATH_DRIFT")
    if identity["regulatory_geometry_evidence"].get("geometry_path") != contract["geometry_path"]:
        raise ArchiveError("IDENTITY_GEOMETRY_PATH_DRIFT")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    guard(contract, "ARCHIVE_CONTRACT")
    identity_path = ROOT / contract["identity_contract"]
    identity = load(identity_path)
    guard(identity, "IDENTITY_CONTRACT")
    if identity.get("component_id") != "rio_seco":
        raise ArchiveError("IDENTITY_COMPONENT_MISMATCH")
    if identity["source"].get("resolution") != contract["source"]["resolution"]:
        raise ArchiveError("RESOLUTION_MISMATCH")
    if identity["source"].get("cut") != contract["source"]["cut"]:
        raise ArchiveError("CUT_MISMATCH")
    if identity["source"].get("authenticity_key") != contract["source"]["authenticity_key"]:
        raise ArchiveError("AUTHENTICITY_KEY_MISMATCH")

    pdf_path = ROOT / contract["pdf_archive_path"]
    ledger_path = ROOT / contract["coordinate_ledger_path"]
    geometry_path = ROOT / contract["geometry_path"]
    manifest_path = ROOT / contract["manifest_path"]

    if manifest_path.is_file() and not args.refresh:
        manifest = verify_existing(contract, identity, pdf_path, ledger_path, geometry_path, manifest_path)
        print(canonical({"status": manifest["status"], "component_id": "rio_seco"}).strip())
        return
    if not args.refresh:
        raise ArchiveError("MISSING_MANIFEST_REFRESH_REQUIRED")

    for path in (pdf_path, ledger_path, geometry_path):
        if path.exists():
            path.unlink()

    try:
        pdf_bytes = download_pdf(contract["source"]["download_url"], int(contract["max_pdf_bytes"]))
        header_text = extract_header_text(pdf_bytes)
        if contract["source"]["authenticity_key"] not in header_text:
            raise SourceBlocked("AUTHENTICITY_KEY_NOT_FOUND")
        if "0525-2023-ANA-AAA.CF" not in header_text:
            raise SourceBlocked("RESOLUTION_NUMBER_NOT_FOUND")
        first_page, last_page = contract["pdf_page_window_zero_based"]
        table_text, page_count = extract_window_text(pdf_bytes, int(first_page), int(last_page))
        expected = contract["expected_main_faja"]
        right = _parse_first_occurrences(table_text, expected["right_bank_prefix"], int(expected["right_bank_count"]))
        left = _parse_first_occurrences(table_text, expected["left_bank_prefix"], int(expected["left_bank_count"]))
        validate_coordinates(right + left)
        if len(right) + len(left) != int(expected["total_hito_count"]):
            raise SourceBlocked("TOTAL_HITO_COUNT_MISMATCH")

        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        source_sha = sha256_bytes(pdf_bytes)
        write_csv(ledger_path, right + left)
        ledger_sha = sha256_file(ledger_path)
        geometry = make_geojson(right, left, source_sha, ledger_sha)
        geometry_path.parent.mkdir(parents=True, exist_ok=True)
        geometry_path.write_text(canonical(geometry), encoding="utf-8")
        geometry_sha = sha256_file(geometry_path)

        rg = identity["regulatory_geometry_evidence"]
        identity["schema_version"] = "0.2"
        identity["status"] = "OFFICIAL_ANA_RIO_SECO_REGULATORY_FAJA_FROZEN_CONTEXT_CATCHMENT_OUTLET_UNRESOLVED"
        identity["source"]["remote_bytes_sha256"] = source_sha
        identity["source"]["archive_status"] = "ARCHIVED_REPRODUCIBLE_PUBLIC_BYTES"
        identity["source"]["archive_path"] = contract["pdf_archive_path"]
        rg["exact_hito_coordinates_archived_in_repository"] = True
        rg["coordinate_reprojection_frozen"] = True
        rg["map_eligible_now"] = True
        rg["coordinate_ledger_path"] = contract["coordinate_ledger_path"]
        rg["geometry_path"] = contract["geometry_path"]
        rg["archive_manifest_path"] = contract["manifest_path"]
        rg["coordinate_ledger_sha256"] = ledger_sha
        rg["geometry_sha256"] = geometry_sha
        rg["reason_map_withheld"] = None
        rg["map_semantics"] = "SEPARATE_ANA_REGULATORY_FAJA_CONTEXT_ONLY_NOT_ACTIVATION_GEOMETRY"
        identity["next_gate"] = [
            "publish the frozen ANA faja only as a separate gray/regulatory research-context layer with explicit non-footprint and non-catchment semantics",
            "resolve natural channel/catchment geometry and outlet/confluence from independent reproducible hydrographic or DEM evidence before collector coupling",
            "retain Q_i(t), travel time, attenuation, receiver response and hydraulic capacity as UNKNOWN/null until independently supported",
        ]
        identity_path.write_text(canonical(identity), encoding="utf-8")

        manifest = {
            "schema_version": "0.1",
            "status": "PASS_REPRODUCIBLE_ANA_RIO_SECO_MAIN_FAJA_ARCHIVE",
            **SAFE,
            "component_id": "rio_seco",
            "source_bytes_archived": True,
            "coordinate_ledger_frozen": True,
            "regulatory_context_geometry_frozen": True,
            "partial_archive_retained": False,
            "map_eligible": True,
            "source_url": contract["source"]["download_url"],
            "pdf_page_count": page_count,
            "pdf_archive_path": contract["pdf_archive_path"],
            "pdf_bytes": len(pdf_bytes),
            "pdf_sha256": source_sha,
            "coordinate_ledger_path": contract["coordinate_ledger_path"],
            "coordinate_ledger_sha256": ledger_sha,
            "geometry_path": contract["geometry_path"],
            "geometry_sha256": geometry_sha,
            "source_epsg": 32718,
            "output_epsg": 4326,
            "right_bank_hito_count": len(right),
            "left_bank_hito_count": len(left),
            "total_hito_count": len(right) + len(left),
            "faja_is_event_footprint": False,
            "faja_is_catchment_polygon": False,
            "faja_is_channel_centerline": False,
            "faja_may_define_outlet_or_confluence": False,
            "routing_enabled": False,
            "risk_or_alert_semantics": False,
        }
    except SourceBlocked as exc:
        for path in (pdf_path, ledger_path, geometry_path):
            if path.exists():
                path.unlink()
        manifest = blocked_manifest(str(exc))

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(canonical(manifest), encoding="utf-8")
    print(canonical({"status": manifest["status"], "component_id": "rio_seco"}).strip())


if __name__ == "__main__":
    main()
