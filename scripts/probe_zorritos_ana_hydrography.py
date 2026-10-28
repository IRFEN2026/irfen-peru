#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_source_plan_v0_1.json"
OUT = ROOT / "site/data/phase2/sources/tumbes_zorritos_ana_hydrography_candidate_snapshot_v0_1.json"

SERVICE = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer"
LAYER = 0

TARGETS = {
    "el_grillo": ["GRILLO"],
    "san_andres": ["ANDRES", "ANDRÉS"],
    "la_paja": ["PAJA"],
    "marinero": ["MARINERO"],
    "el_rubio": ["RUBIO"],
    "san_pedro": ["SAN PEDRO"],
    "pena_negra": ["PENA NEGRA", "PEÑA NEGRA"],
    "el_tiburon": ["TIBURON", "TIBURÓN"],
    "leoncio_prado": ["LEONCIO PRADO"],
    "nuevo_paraiso": ["NUEVO PARAISO", "NUEVO PARAÍSO"],
    "sechurita": ["SECHURITA"],
    "los_pozos": ["LOS POZOS", "POZOS"],
    "nueva_esperanza": ["NUEVA ESPERANZA"],
    "mal_paso_01": ["MAL PASO"],
    "mal_paso_02": ["MAL PASO"],
    "las_delicias": ["LAS DELICIAS", "DELICIAS"],
    "miramar": ["MIRAMAR"],
    "la_tucilla": ["LA TUCILLA", "TUCILLA"],
}

# LIKE '%TUCILLA%' also matches TUCILLAL, a separate INGEMMET entity with no
# documented equivalence. Such rows are kept in a quarantine list, never merged.
LEXICAL_NEIGHBOUR_EXCLUSIONS = {
    "la_tucilla": ["TUCILLAL"],
}

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

def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def strip_accents(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch))

def fetch(url: str):
    req = Request(url, headers={"User-Agent": "IRFEN-research-source-probe/1.0"})
    with urlopen(req, timeout=90) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")), raw

def metadata_url() -> str:
    return f"{SERVICE}/{LAYER}?f=pjson"

def candidate_text_fields(metadata: dict) -> list[str]:
    fields = []
    for field in metadata.get("fields") or []:
        if field.get("type") != "esriFieldTypeString":
            continue
        key = strip_accents(f"{field.get('name','')} {field.get('alias','')}").lower()
        if any(token in key for token in ("nom", "name", "rio", "queb", "cauce")):
            fields.append(field["name"])
    if not fields:
        raise ValueError("ANA metadata exposes no defensible name-like text field")
    return sorted(set(fields))

def query_url(field: str, token: str) -> str:
    escaped = token.replace("'", "''")
    params = {
        "where": f"{field} LIKE '%{escaped}%'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return f"{SERVICE}/{LAYER}/query?" + urlencode(params)

def valid_geojson_position(position: object) -> bool:
    """WGS84 longitude/latitude and any extra ordinates must be finite numbers."""
    return (
        isinstance(position, list)
        and len(position) >= 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v) for v in position)
        and -180 <= position[0] <= 180
        and -90 <= position[1] <= 90
    )


def nonzero_xy_ring_area(ring: list) -> bool:
    """Reject zero signed XY area without imposing a hydraulic threshold."""
    x0, y0 = ring[0][:2]
    twice_area = math.fsum(
        (ring[i][0] - x0) * (ring[i + 1][1] - y0)
        - (ring[i + 1][0] - x0) * (ring[i][1] - y0)
        for i in range(len(ring) - 1)
    )
    return twice_area != 0


def valid_geojson_ring(ring: object) -> bool:
    """A context-only polygon ring must be closed with finite WGS84 positions."""
    return (
        isinstance(ring, list)
        and len(ring) >= 4
        and all(valid_geojson_position(position) for position in ring)
        and ring[0] == ring[-1]
        # Three distinct XY vertices can still be collinear or self-crossing
        # with zero signed area; neither is defensible polygon context.
        and len({(position[0], position[1]) for position in ring[:-1]}) >= 3
        and nonzero_xy_ring_area(ring)
    )


def valid_geojson_polygon(polygon: object) -> bool:
    return (
        isinstance(polygon, list)
        and bool(polygon)
        and all(valid_geojson_ring(ring) for ring in polygon)
    )


def validated_geojson_features(payload: dict, context: str) -> list[dict]:
    """Reject malformed ANA responses instead of treating them as empty matches."""
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"non-GeoJSON FeatureCollection for {context}")
    if "features" not in payload or not isinstance(payload["features"], list):
        raise ValueError(f"invalid or missing GeoJSON features array for {context}")
    # ANA may return a truncated FeatureCollection. Never treat it as a
    # complete candidate search (or as evidence that a child is absent).
    for location in (payload, payload.get("properties")):
        if location is None:
            continue
        if not isinstance(location, dict):
            raise ValueError(f"invalid GeoJSON transfer metadata for {context}")
        if ("exceededTransferLimit" in location
                and location["exceededTransferLimit"] is not False):
            raise ValueError(f"incomplete ANA result exceededTransferLimit for {context}")
    for index, feature in enumerate(payload["features"]):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"invalid GeoJSON feature at {context}[{index}]")
        if feature.get("properties") is not None and not isinstance(feature["properties"], dict):
            raise ValueError(f"invalid GeoJSON properties at {context}[{index}]")
        if feature.get("geometry") is not None and not isinstance(feature["geometry"], dict):
            raise ValueError(f"invalid GeoJSON geometry at {context}[{index}]")
        # Validate line coordinate structure before preserving any ANA candidate.
        # Other geometry types remain context-only, never promoted to line geometry.
        geometry = feature.get("geometry")
        if geometry is not None:
            # Preserve valid non-line geometry as context only, but never
            # classify malformed GeoJSON geometry objects as ANA candidates.
            geometry_type = geometry.get("type")
            if not isinstance(geometry_type, str) or geometry_type not in {
                "Point", "MultiPoint", "LineString", "MultiLineString",
                "Polygon", "MultiPolygon", "GeometryCollection",
            }:
                raise ValueError(f"invalid ANA geometry type at {context}[{index}]")
            if geometry_type == "GeometryCollection":
                geometries = geometry.get("geometries")
                if not isinstance(geometries, list):
                    raise ValueError(f"invalid ANA geometry collection at {context}[{index}]")
                # Nested collection members must pass the same fail-closed
                # validation as top-level features, including their coordinates.
                for child_index, child in enumerate(geometries):
                    if not isinstance(child, dict):
                        raise ValueError(f"invalid ANA collection member at {context}[{index}]")
                    validated_geojson_features(
                        {"type": "FeatureCollection",
                         "features": [{"type": "Feature", "geometry": child}]},
                        f"{context}[{index}].geometries[{child_index}]",
                    )
            elif not isinstance(geometry.get("coordinates"), list):
                raise ValueError(f"invalid ANA geometry coordinates at {context}[{index}]")
            if geometry_type == "Point" and not valid_geojson_position(geometry["coordinates"]):
                raise ValueError(f"invalid ANA point position at {context}[{index}]")
            if geometry_type == "MultiPoint":
                points = geometry["coordinates"]
                if not points or any(not valid_geojson_position(p) for p in points):
                    raise ValueError(f"invalid ANA multipoint positions at {context}[{index}]")
            if geometry_type == "Polygon" and not valid_geojson_polygon(geometry["coordinates"]):
                raise ValueError(f"invalid ANA polygon rings at {context}[{index}]")
            if geometry_type == "MultiPolygon":
                polygons = geometry["coordinates"]
                if not polygons or any(not valid_geojson_polygon(p) for p in polygons):
                    raise ValueError(f"invalid ANA multipolygon rings at {context}[{index}]")
        if geometry is not None and geometry.get("type") in {"LineString", "MultiLineString"}:
            kind = geometry["type"]
            coordinates = geometry.get("coordinates")
            if not isinstance(coordinates, list) or not coordinates:
                raise ValueError(f"invalid ANA line coordinates at {context}[{index}]")
            lines = [coordinates] if kind == "LineString" else coordinates
            if any(not isinstance(line, list) or len(line) < 2 for line in lines):
                raise ValueError(f"invalid ANA line structure at {context}[{index}]")
            for line in lines:
                for position in line:
                    if not valid_geojson_position(position):
                        raise ValueError(f"invalid ANA line position at {context}[{index}]")
                # A zero-length XY line is not a defensible watercourse
                # candidate, even if its Z ordinates differ.
                if len({(position[0], position[1]) for position in line}) < 2:
                    raise ValueError(f"degenerate ANA line at {context}[{index}]")
    return payload["features"]


def check_geojson_payload_guard() -> None:
    """Offline regression smoke test, exercised by --check-plan-only in CI."""
    invalid = (
        {"type": "FeatureCollection"},
        {"type": "FeatureCollection", "features": None},
        {"type": "FeatureCollection", "features": False},
        {"type": "FeatureCollection", "features": {}},
        {"type": "FeatureCollection", "features": ""},
        {"type": "FeatureCollection", "features": "[]"},
        {"type": "FeatureCollection", "features": [None]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": None}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": "not-an-array"}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-80.1, -3.1]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-80.1, -3.1], [-80.1, -3.1]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[-80.1, -3.1, 1.0], [-80.1, -3.1, 2.0]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[True, -3.1], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-80.1, -3.1, float("nan")], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-80.1, -3.1, float("inf")], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-80.1, -3.1, "invalid"], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[-80.1, -3.1, True], [-80.2, -3.2]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[0, 0]]]}}]},
        # ANA query requests outSR=4326: finite but out-of-range
        # longitude/latitude are invalid GeoJSON positions, not candidates.
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[181, -3.1], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-181, -3.1], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-80.1, 91], [-80.2, -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [[[-80.1, -91], [-80.2, -3.2]]]}}]},

        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Unknown", "coordinates": []}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": None}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [True, -3.1]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-80.1, 91]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [-80.1, -3.1, float("nan")]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiPoint", "coordinates": []}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiPoint", "coordinates": [[-80.1, -3.1], ["bad", -3.2]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": None}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": [None]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": [{"type": "Unknown", "coordinates": []}]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [181, -3.1]}]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": [{"type": "LineString", "coordinates": [[-80.1, -3.1]]}]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "GeometryCollection", "geometries": [{"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [True, -3.1]}]}]}}]},
        # Distinct XY vertices do not imply nonzero area (collinear or bowtie).
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-80, -3], [-81, -3], [-82, -3], [-80, -3]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[[[-80, -3], [-81, -4], [-82, -5], [-80, -3]]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-80, -3], [-81, -4], [-80, -4], [-81, -3], [-80, -3]]]}}]},
        # Closed but degenerate rings are not defensible context geometry.
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-80.1, -3.1], [-80.1, -3.1], [-80.1, -3.1], [-80.1, -3.1]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[[[-80.1, -3.1], [-80.2, -3.1], [-80.1, -3.1], [-80.1, -3.1]]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-80.1, -3.1], [-80.2, -3.1], [-80.1, -3.1]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-80.1, -3.1], [-80.2, -3.1], [-80.2, -3.2], [-80.1, -3.3]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-80.1, -3.1], [-80.2, -3.1], [-80.2, -3.2], [float("nan"), -3.1]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": []}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[[[-80.1, -3.1], [-80.2, -3.1], [-80.2, -3.2], [-80.1, 91]]]]}}]},
        {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": []}]},
        {"type": "FeatureCollection", "features": [], "exceededTransferLimit": True},
        {"type": "FeatureCollection", "features": [], "exceededTransferLimit": None},
        {"type": "FeatureCollection", "features": [], "exceededTransferLimit": "false"},
        {"type": "FeatureCollection", "features": [], "properties": {"exceededTransferLimit": True}},
        {"type": "FeatureCollection", "features": [], "properties": {"exceededTransferLimit": None}},
        {"type": "FeatureCollection", "features": [], "properties": []},
    )
    for payload in invalid:
        try:
            validated_geojson_features(payload, "offline-regression")
        except ValueError:
            continue
        raise AssertionError(f"malformed GeoJSON accepted: {payload!r}")
    for valid in (
        {"type": "FeatureCollection", "features": []},
        {"type": "FeatureCollection", "features": [], "exceededTransferLimit": False},
        {"type": "FeatureCollection", "features": [], "properties": {"exceededTransferLimit": False}},
    ):
        assert validated_geojson_features(valid, "offline-regression") == []
    for geometry in (
        {"type": "LineString", "coordinates": [[-80.1, -3.1], [-80.2, -3.2]]},
        {"type": "LineString", "coordinates": [[-80.1, -3.1], [-80.2, -3.2], [-80.1, -3.1]]},
        {"type": "MultiLineString", "coordinates": [[[-80.1, -3.1], [-80.2, -3.2]]]},
        {"type": "LineString", "coordinates": [[-80.1, -3.1, 1.5], [-80.2, -3.2, 2.5]]},
        {"type": "LineString", "coordinates": [[-180, -90], [180, 90]]},
        {"type": "MultiLineString", "coordinates": [[[-80.1, -3.1, 1.5], [-80.2, -3.2, 2.5]]]},
        {"type": "Point", "coordinates": [-80.1, -3.1]},
        {"type": "MultiPoint", "coordinates": [[-80.1, -3.1], [-80.2, -3.2, 4.0]]},
        {"type": "GeometryCollection", "geometries": []},
        {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [-80.1, -3.1]}, {"type": "LineString", "coordinates": [[-80.1, -3.1], [-80.2, -3.2]]}]},
        {"type": "GeometryCollection", "geometries": [{"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [-80.1, -3.1]}]}]},
        {"type": "Polygon", "coordinates": [[[-80.1, -3.1], [-80.2, -3.1], [-80.2, -3.2], [-80.1, -3.1]]]},
        {"type": "Polygon", "coordinates": [[[-80, -3, 0], [-81, -3, 0], [-81, -4, 0], [-80, -3, 0]]]},
        {"type": "MultiPolygon", "coordinates": [[[[-80.1, -3.1], [-80.2, -3.1], [-80.2, -3.2], [-80.1, -3.1]]]]},
    ):
        payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geometry}]}
        assert len(validated_geojson_features(payload, "offline-regression")) == 1


def normalize_feature(feature: dict) -> dict:
    geometry = feature.get("geometry")
    if geometry is not None and geometry.get("type") not in {"LineString", "MultiLineString"}:
        geometry_type = geometry.get("type")
    else:
        geometry_type = None if geometry is None else geometry.get("type")
    return {
        "type": "Feature",
        "properties": feature.get("properties") or {},
        "geometry": geometry,
        "_irfen_probe": {"geometry_type": geometry_type},
    }

def lexical_neighbour_hit(feature: dict, field: str, component_id: str):
    value = strip_accents(str((feature.get("properties") or {}).get(field) or "")).upper()
    for token in LEXICAL_NEIGHBOUR_EXCLUSIONS.get(component_id, []):
        if token in value:
            return token
    return None

def run() -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        if plan.get(key) != expected:
            raise ValueError(f"unsafe source-plan guard: {key}")

    metadata, metadata_raw = fetch(metadata_url())
    if metadata.get("id") != LAYER:
        raise ValueError(f"unexpected ANA layer id: {metadata.get('id')}")
    if "query" not in str(metadata.get("capabilities") or "").lower():
        raise ValueError("ANA layer 0 is not queryable")

    name_fields = candidate_text_fields(metadata)
    target_results = {}
    for component_id, tokens in TARGETS.items():
        requests = []
        candidates = []
        lexical_quarantine = []
        seen = set()
        for field in name_fields:
            for token in tokens:
                url = query_url(field, token)
                payload, raw = fetch(url)
                rows = validated_geojson_features(
                    payload, f"{component_id}/{field}/{token}"
                )
                requests.append({
                    "field": field,
                    "token": token,
                    "url": url,
                    "raw_response_sha256": sha256(raw),
                    "feature_count": len(rows),
                })
                for feature in rows:
                    normalized = normalize_feature(feature)
                    feature_key = sha256(canonical(normalized))
                    if feature_key in seen:
                        continue
                    seen.add(feature_key)
                    hit = lexical_neighbour_hit(normalized, field, component_id)
                    if hit:
                        normalized["_irfen_probe"]["lexical_neighbour_token"] = hit
                        lexical_quarantine.append(normalized)
                        continue
                    candidates.append(normalized)
        target_results[component_id] = {
            "status": "CANDIDATES_ONLY_NOT_ADJUDICATED" if candidates else "NO_CANDIDATE_RETURNED_NOT_NEGATIVE",
            "candidate_count": len(candidates),
            "requests": requests,
            "candidates": candidates,
            "lexical_neighbour_quarantine": lexical_quarantine,
            "target_context": (plan.get("target_context") or {}).get(component_id),
            "name_match_is_identity_adjudication": False,
            "geometry_map_publishable": False,
            "outlet_verified": False,
            "independent_identity_crosscheck_complete": False,
        }

    snapshot = {
        "schema_version": "0.3",
        **SAFE,
        "discovery_id": "tumbes_zorritos_bocapan_coastal_ravines",
        "source_id": "ANA-ONRH-RIOS-QUEBRADAS-AAVI-2018-PROBE",
        "institution": "Autoridad Nacional del Agua",
        "service": SERVICE,
        "layer_id": LAYER,
        "layer_name": metadata.get("name"),
        "source_year": 2018,
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "metadata_url": metadata_url(),
        "metadata_raw_sha256": sha256(metadata_raw),
        "name_fields_queried": name_fields,
        "target_results": target_results,
        "scientific_guards": {
            "candidate_name_match_is_geometry_adjudication": False,
            "candidate_geometry_is_map_publishable": False,
            "spatial_context_check_required": True,
            "independent_identity_source_required": True,
            "exact_snapshot_hash_required_before_map_publication": True,
            "outlet_or_downstream_connectivity_required": True,
            "homonym_quarantine": ["san_pedro", "pena_negra"],
            "sector_vs_ravine_quarantine": ["nueva_esperanza", "mal_paso_01", "mal_paso_02"],
            "shared_name_candidate_quarantine": ["mal_paso_01", "mal_paso_02"],
            "marine_hazard_separation_required": ["nueva_esperanza", "la_tucilla"],
            "paired_event_context_quarantine": ["leoncio_prado"],
            "spatial_crosswalk_quarantine": ["miramar"],
            "official_map_anchor_not_line_geometry_quarantine": ["la_tucilla"],
            "scope_adjudication_quarantine": list(plan["query_policy"]["scope_adjudication_quarantine"]),
            "distinct_entity_guard": [["la_tucilla", "tucillal"]],
            "lexical_neighbour_exclusions": LEXICAL_NEIGHBOUR_EXCLUSIONS,
            "absence_of_candidate_is_negative": False,
            "synthetic_connectors_allowed": False,
            "composite_parent_geometry_allowed": False,
        },
    }
    OUT.write_bytes(canonical(snapshot))
    return snapshot

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-plan-only", action="store_true")
    args = parser.parse_args()
    if args.check_plan_only:
        check_geojson_payload_guard()
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        for key, expected in SAFE.items():
            assert plan.get(key) == expected
        assert set(plan["target_children"]) == set(TARGETS)
        assert len(TARGETS) == 18
        assert "la_tucilla" in TARGETS
        assert "la_tucilla" in plan["query_policy"]["official_map_anchor_not_line_geometry_quarantine"]
        assert "la_tucilla" not in plan["query_policy"]["scope_adjudication_quarantine"]
        assert plan["query_policy"]["scope_adjudication_quarantine"] == []
        assert plan["target_context"]["la_tucilla"]["official_coordinates"]["easting_m"] == 538042
        assert plan["target_context"]["la_tucilla"]["official_coordinates"]["northing_m"] == 9594412
        assert plan["query_policy"]["lexical_neighbour_exclusions"] == LEXICAL_NEIGHBOUR_EXCLUSIONS
        assert "tucillal" not in TARGETS
        for component_id, excluded in LEXICAL_NEIGHBOUR_EXCLUSIONS.items():
            assert not set(excluded) & set(TARGETS[component_id])
        print("PASS_ZORRITOS_ANA_HYDROGRAPHY_PLAN")
        return 0
    result = run()
    print(json.dumps({
        "status": "PASS_CANDIDATE_PROBE_NOT_ADJUDICATED",
        "targets": len(result["target_results"]),
        "activation_gate": result["activation_gate"],
        "production_use": result["production_use"],
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
