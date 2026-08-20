#!/usr/bin/env python3
"""Build the only defensible remaining-W1 geometry evidence.

Huerta Vieja is a partial sequence of official faja-marginal control points.
The official sources conflict on the bank assignment. The sequence therefore
remains REVIEW_ONLY, is not map eligible, and cannot become a territorial or
operational IRFEN geometry.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SNAPSHOT = ROOT / "site/data/phase2/sources/w1_remaining_geometry_source_snapshot.json"
OUT = ROOT / "site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only_validation.json"
CATALOG = ROOT / "site/data/phase2/w1_remaining_geometry_catalog.json"

SOURCE_CRS = "EPSG:32718"
OUTPUT_CRS = "EPSG:4326"
BANK_ASSIGNMENT = "UNRESOLVED_OFFICIAL_SOURCE_CONFLICT"
SOURCE_PDF_SNAPSHOT_ID = "SIGRID-19291-HUERTA-VIEJA"
SOURCE_PDF_SHA256 = "ded278b730c4daa0eb28086582a5fe3d7af817b9c5964890f700a48503cc5ec0"

# Literal 18-point sequence from the official Huerta Vieja technical table.
# Codes and coordinates are intentionally preserved exactly. The table title,
# code suffixes and final official conclusions conflict on the bank assignment.
HUERTA_HITOS = (
    ("P5 MI", 300596.0, 8706636.0),
    ("P4 MI", 300633.0, 8706553.0),
    ("P3 MI", 300654.0, 8706452.0),
    ("P2 MI", 300663.0, 8706419.0),
    ("P1 MI", 300657.0, 8706370.0),
    ("HI-8", 300653.0, 8706336.0),
    ("HI-9", 300603.0, 8706197.0),
    ("HI-10", 300575.0, 8706134.0),
    ("HI-11", 300538.0, 8706064.0),
    ("HI-12", 300540.0, 8705985.0),
    ("HI-13", 300552.0, 8705916.0),
    ("HI-14", 300576.0, 8705852.0),
    ("HI-15", 300573.0, 8705785.0),
    ("HI-16", 300546.0, 8705693.0),
    ("HI-17", 300493.0, 8705560.0),
    ("HI-18", 300452.0, 8705420.0),
    ("HI-19", 300411.0, 8705312.0),
    ("HI-20", 300361.0, 8705198.0),
)


def pretty_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def canonical_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def coordinate_payload() -> dict:
    return {
        "crs": SOURCE_CRS,
        "points": [
            {"id": label, "easting": easting, "northing": northing}
            for label, easting, northing in HUERTA_HITOS
        ],
    }


def build_geojson(source_snapshot_sha256: str) -> dict:
    transformer = Transformer.from_crs(SOURCE_CRS, OUTPUT_CRS, always_xy=True)
    coordinates = [
        [
            round(transformer.transform(easting, northing)[0], 8),
            round(transformer.transform(easting, northing)[1], 8),
        ]
        for _, easting, northing in HUERTA_HITOS
    ]
    coordinate_sha = digest_bytes(canonical_bytes(coordinate_payload()))
    return {
        "type": "FeatureCollection",
        "name": "w1_huerta_vieja_faja_margin_review_only",
        "properties": {
            "candidate_id": "lima_norte_huerta_vieja",
            "deployment_status": "RESEARCH_ONLY",
            "review_status": "REVIEW_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "source_snapshot": SOURCE_SNAPSHOT.relative_to(ROOT).as_posix(),
            "source_snapshot_sha256": source_snapshot_sha256,
            "coordinate_payload_sha256": coordinate_sha,
            "source_crs": SOURCE_CRS,
            "output_crs": OUTPUT_CRS,
            "entity_type": "FAJA_MARGINAL_HITO_SEQUENCE",
            "bank_assignment": BANK_ASSIGNMENT,
            "map_eligible_research_only": False,
            "not_a_watershed": True,
            "not_a_faja_polygon": True,
            "not_a_hazard_extent": True,
            "not_an_inundation_polygon": True,
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "unit_id": "huerta_vieja_faja_hitos_18_review_only",
                    "candidate_id": "lima_norte_huerta_vieja",
                    "entity_type": "FAJA_MARGINAL_HITO_SEQUENCE",
                    "bank_assignment": BANK_ASSIGNMENT,
                    "source_hito_count": 18,
                    "source_id": "ANA-IT-016-2024-ALACHRL",
                    "source_act": "ANA-RD-0690-2025-AAACF",
                    "source_snapshot_id": SOURCE_PDF_SNAPSHOT_ID,
                    "source_pdf_sha256": SOURCE_PDF_SHA256,
                    "source_crs": SOURCE_CRS,
                    "output_crs": OUTPUT_CRS,
                    "confidence": "HIGH_COORDINATE_PROVENANCE_UNRESOLVED_BANK_ASSIGNMENT_PARTIAL_ENTITY_COVERAGE",
                    "deployment_status": "RESEARCH_ONLY",
                    "review_status": "REVIEW_ONLY",
                    "production_use": False,
                    "production_ready": False,
                    "alerting_enabled": False,
                    "map_eligible_research_only": False,
                    "artificial_links": False,
                    "closed_ring": False,
                    "not_a_watershed": True,
                    "not_a_faja_polygon": True,
                    "not_a_hazard_extent": True,
                    "not_an_inundation_polygon": True,
                    "source_hitos": [label for label, _, _ in HUERTA_HITOS],
                    "source_utm": [[easting, northing] for _, easting, northing in HUERTA_HITOS],
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        ],
    }


def build_validation(geojson: dict, geojson_bytes: bytes, source_snapshot_sha256: str) -> dict:
    coordinates = geojson["features"][0]["geometry"]["coordinates"]
    line = LineString(coordinates)
    inverse = Transformer.from_crs(OUTPUT_CRS, SOURCE_CRS, always_xy=True)
    errors = []
    for (_, easting, northing), (lon, lat) in zip(HUERTA_HITOS, coordinates):
        reasting, rnorthing = inverse.transform(lon, lat)
        errors.append(math.hypot(reasting - easting, rnorthing - northing))
    return {
        "schema_version": "1.1.0",
        "candidate_id": "lima_norte_huerta_vieja",
        "geometry_path": OUT.relative_to(ROOT).as_posix(),
        "geometry_sha256": digest_bytes(geojson_bytes),
        "source_snapshot_path": SOURCE_SNAPSHOT.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": source_snapshot_sha256,
        "coordinate_payload_sha256": digest_bytes(canonical_bytes(coordinate_payload())),
        "source_pdf_snapshot_id": SOURCE_PDF_SNAPSHOT_ID,
        "source_pdf_sha256": SOURCE_PDF_SHA256,
        "status": "PASS_GEOMETRY_REVIEW_ONLY",
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_permitted": False,
        "map_eligible_research_only": False,
        "bank_assignment_check": {
            "bank_assignment": BANK_ASSIGNMENT,
            "definitive_bank_assignment_permitted": False,
            "technical_report_conclusion": "21 hitos margen derecha; 18 hitos margen izquierda",
            "resolution_conflict": "RD 0690-2025 contains passages that invert that assignment.",
            "table_conflict": "The 18-point table is titled margen derecha while its codes include P…MI/HI.",
        },
        "entity_checks": {
            "entity_type": "FAJA_MARGINAL_HITO_SEQUENCE",
            "not_a_watershed": True,
            "not_a_faja_polygon": True,
            "not_a_hazard_extent": True,
            "not_an_inundation_polygon": True,
            "artificial_links": False,
        },
        "crs_checks": {
            "source_crs": SOURCE_CRS,
            "output_crs": OUTPUT_CRS,
            "point_count": 18,
            "max_roundtrip_error_m": round(max(errors), 6),
            "within_expected_peru_bounds": all(
                -82 < lon < -68 and -19 < lat < 1 for lon, lat in coordinates
            ),
        },
        "topology_checks": {
            "geometry_type": "LineString",
            "is_simple": line.is_simple,
            "is_empty": line.is_empty,
            "closed_ring": line.is_ring,
            "duplicate_consecutive_points": any(
                left == right for left, right in zip(coordinates, coordinates[1:])
            ),
        },
        "coverage_checks": {
            "published_final_hitos_total": 39,
            "materialized_unambiguous_hitos": 18,
            "coverage_kind": "PARTIAL_ONE_UNAMBIGUOUS_PUBLISHED_SEQUENCE",
            "study_reach_km": 2.0,
            "full_faja_polygon_available": False,
        },
        "limitations": [
            "Geometry is deliberately partial and REVIEW_ONLY.",
            "Official sources conflict on bank assignment; the 18-point sequence is not assigned to right or left bank.",
            "No polygon is inferred from faja-marginal controls and no watershed/hazard/inundation geometry is inferred.",
        ],
    }


def build_catalog(
    geojson_bytes: bytes,
    validation_bytes: bytes,
    source_snapshot_sha256: str,
) -> dict:
    return {
        "version": "phase2-w1-remaining-geometry-catalog-v1.1",
        "generated_at": "2026-08-20T18:48:52Z",
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "default_visibility": False,
        "summary": {
            "targets": 4,
            "materialized_review_only": 1,
            "blocked": 3,
            "map_eligible_research_only": 0,
            "new_operational_zones": 0,
        },
        "layers": [
            {
                "candidate_id": "lima_norte_huerta_vieja",
                "geometry_status": "PARTIAL_REVIEW_ONLY",
                "path": "data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only.geojson",
                "validation_path": "data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only_validation.json",
                "entity_type": "FAJA_MARGINAL_HITO_SEQUENCE",
                "bank_assignment": BANK_ASSIGNMENT,
                "default_visibility": False,
                "map_eligible_research_only": False,
                "map_integration": "WITHHELD_FROM_GENERAL_MAP_UNTIL_TERRITORIAL_GEOMETRY_IS_DEFENSIBLE",
                "loaded_into_operational_calculation": False,
                "carries_alert_values": False,
                "carries_risk_classification": False,
                "source_snapshot_sha256": source_snapshot_sha256,
                "coordinate_payload_sha256": digest_bytes(canonical_bytes(coordinate_payload())),
                "geometry_sha256": digest_bytes(geojson_bytes),
                "validation_sha256": digest_bytes(validation_bytes),
                "source_pdf_sha256": SOURCE_PDF_SHA256,
                "disclaimer": "REVIEW_ONLY: secuencia parcial de hitos de faja marginal con asignación de margen no resuelta; no cuenca, no polígono de faja, peligro o inundación, no alerta.",
            }
        ],
        "blocked": [
            {
                "candidate_id": "lima_sur_malanche",
                "reason": "No se recuperó la serie completa de hitos/vector oficial; la modificación 2024 es sólo parcial.",
            },
            {
                "candidate_id": "lambayeque_chongoyape_oyotun_zana",
                "reason": "El corredor cruza al menos Chancay-Lambayeque y Zaña; prohibido crear enlace o polígono compuesto artificial.",
            },
            {
                "candidate_id": "arequipa_acari_san_agustin",
                "reason": "No se recuperó geometría separada reproducible de quebrada San Agustín; referencias de río Acarí no pueden sustituirla.",
            },
        ],
    }


def expected_outputs() -> tuple[bytes, bytes, bytes]:
    source_snapshot_sha256 = digest_bytes(SOURCE_SNAPSHOT.read_bytes())
    geojson = build_geojson(source_snapshot_sha256)
    geojson_bytes = pretty_bytes(geojson)
    validation = build_validation(geojson, geojson_bytes, source_snapshot_sha256)
    validation_bytes = pretty_bytes(validation)
    catalog = build_catalog(geojson_bytes, validation_bytes, source_snapshot_sha256)
    return geojson_bytes, validation_bytes, pretty_bytes(catalog)


def materialize() -> None:
    geojson_bytes, validation_bytes, catalog_bytes = expected_outputs()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(geojson_bytes)
    VALIDATION.write_bytes(validation_bytes)
    CATALOG.write_bytes(catalog_bytes)


def check_only() -> None:
    expected = zip(
        (OUT, VALIDATION, CATALOG),
        expected_outputs(),
    )
    mismatches = [path.as_posix() for path, content in expected if path.read_bytes() != content]
    if mismatches:
        raise SystemExit("W1 reproducibility mismatch: " + ", ".join(mismatches))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        check_only()
    else:
        materialize()
    print(
        json.dumps(
            {
                "candidate_id": "lima_norte_huerta_vieja",
                "bank_assignment": BANK_ASSIGNMENT,
                "map_eligible_research_only": False,
                "activation_permitted": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
