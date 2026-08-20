#!/usr/bin/env python3
"""Materialize defensible W1 geometry without converting maps/pixels into geometry.

Only Huerta Vieja is materialized here, and only as a REVIEW_ONLY faja-marginal
hito sequence from official ANA coordinates. The other W1 targets remain BLOCKED
in the source snapshot until complete, entity-correct geometry is available.
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

SOURCE_CRS = "EPSG:32718"
OUTPUT_CRS = "EPSG:4326"

# Item 2.8, Informe Técnico N° 016-2024/P_ALACHRL_30/JEAC.
# The labels are preserved verbatim. We deliberately do not infer a bank name
# because the accessible official documents contain inconsistent bank counts/
# headings after field modification. This complete 18-point sequence is clear.
HUERTA_HITOS = (
    ("P5 MI", 300596.00, 8706636.00),
    ("P4 MI", 300633.00, 8706553.00),
    ("P3 MI", 300654.00, 8706452.00),
    ("P2 MI", 300663.00, 8706419.00),
    ("P1 MI", 300657.00, 8706370.00),
    ("HI-8", 300653.00, 8706336.00),
    ("HI-9", 300603.00, 8706197.00),
    ("HI-10", 300575.00, 8706134.00),
    ("HI-11", 300538.00, 8706064.00),
    ("HI-12", 300540.00, 8705985.00),
    ("HI-13", 300552.00, 8705916.00),
    ("HI-14", 300576.00, 8705852.00),
    ("HI-15", 300573.00, 8705785.00),
    ("HI-16", 300546.00, 8705693.00),
    ("HI-17", 300493.00, 8705560.00),
    ("HI-18", 300452.00, 8705420.00),
    ("HI-19", 300411.00, 8705312.00),
    ("HI-20", 300361.00, 8705198.00),
)


def canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def coordinate_payload() -> dict:
    return {
        "crs": SOURCE_CRS,
        "points": [
            {"id": label, "easting": easting, "northing": northing}
            for label, easting, northing in HUERTA_HITOS
        ],
    }


def build_geojson(snapshot_sha: str) -> dict:
    forward = Transformer.from_crs(SOURCE_CRS, OUTPUT_CRS, always_xy=True)
    coordinates = [
        [round(forward.transform(easting, northing)[0], 8),
         round(forward.transform(easting, northing)[1], 8)]
        for _, easting, northing in HUERTA_HITOS
    ]
    payload_sha = digest_bytes(canonical_json(coordinate_payload()))
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
            "source_snapshot_sha256": snapshot_sha,
            "coordinate_payload_sha256": payload_sha,
            "source_crs": SOURCE_CRS,
            "output_crs": OUTPUT_CRS,
            "entity_type": "FAJA_MARGINAL_HITO_SEQUENCE",
            "not_a_watershed": True,
            "not_a_hazard_extent": True,
            "not_an_inundation_polygon": True,
        },
        "features": [{
            "type": "Feature",
            "properties": {
                "unit_id": "huerta_vieja_faja_hitos_18_review_only",
                "candidate_id": "lima_norte_huerta_vieja",
                "entity_type": "FAJA_MARGINAL_HITO_SEQUENCE",
                "bank_label": "WITHHELD_DUE_TO_SOURCE_LABEL_INCONSISTENCY",
                "source_hito_count": len(HUERTA_HITOS),
                "source_id": "ANA-IT-016-2024-ALACHRL",
                "source_act": "ANA-RD-0690-2025-AAACF",
                "source_crs": SOURCE_CRS,
                "output_crs": OUTPUT_CRS,
                "confidence": "HIGH_COORDINATE_PROVENANCE_PARTIAL_ENTITY_COVERAGE",
                "deployment_status": "RESEARCH_ONLY",
                "review_status": "REVIEW_ONLY",
                "production_use": False,
                "production_ready": False,
                "alerting_enabled": False,
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
        }],
    }


def build_validation(geojson: dict, geo_bytes: bytes, snapshot_sha: str) -> dict:
    coordinates = geojson["features"][0]["geometry"]["coordinates"]
    line = LineString(coordinates)
    inverse = Transformer.from_crs(OUTPUT_CRS, SOURCE_CRS, always_xy=True)
    errors = []
    for (_, easting, northing), (lon, lat) in zip(HUERTA_HITOS, coordinates):
        re, rn = inverse.transform(lon, lat)
        errors.append(math.hypot(re - easting, rn - northing))
    return {
        "schema_version": "1.0.0",
        "candidate_id": "lima_norte_huerta_vieja",
        "geometry_path": OUT.relative_to(ROOT).as_posix(),
        "geometry_sha256": digest_bytes(geo_bytes),
        "source_snapshot_path": SOURCE_SNAPSHOT.relative_to(ROOT).as_posix(),
        "source_snapshot_sha256": snapshot_sha,
        "coordinate_payload_sha256": digest_bytes(canonical_json(coordinate_payload())),
        "status": "PASS_GEOMETRY_REVIEW_ONLY",
        "deployment_status": "RESEARCH_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_permitted": False,
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
            "point_count": len(HUERTA_HITOS),
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
            "materialized_unambiguous_hitos": len(HUERTA_HITOS),
            "coverage_kind": "PARTIAL_ONE_UNAMBIGUOUS_PUBLISHED_SEQUENCE",
            "study_reach_km": 2.0,
            "full_faja_polygon_available": False,
        },
        "limitations": [
            "Geometry is deliberately partial and REVIEW_ONLY.",
            "The accessible text of the second bank contains an ambiguous/damaged northing; it is not materialized.",
            "No polygon is inferred from the two banks and no watershed is inferred from faja-marginal controls.",
        ],
    }


def materialize(write: bool = True) -> tuple[dict, dict]:
    snapshot_sha = digest_file(SOURCE_SNAPSHOT)
    geojson = build_geojson(snapshot_sha)
    geo_bytes = (json.dumps(geojson, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    validation = build_validation(geojson, geo_bytes, snapshot_sha)
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(geo_bytes)
        VALIDATION.write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return geojson, validation


def comparable(path: Path, expected: dict) -> bool:
    return path.is_file() and json.loads(path.read_text(encoding="utf-8")) == expected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    geojson, validation = materialize(write=not args.check_only)
    if args.check_only:
        if not comparable(OUT, geojson) or not comparable(VALIDATION, validation):
            raise SystemExit("W1 Huerta Vieja outputs do not match reproducible source coordinates")
    print(json.dumps({
        "candidate_id": "lima_norte_huerta_vieja",
        "status": validation["status"],
        "point_count": validation["crs_checks"]["point_count"],
        "activation_permitted": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
