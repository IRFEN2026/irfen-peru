#!/usr/bin/env python3
"""Freeze/replay exact ANA Casma N7 child polygons as research context only.

The discovery parent is never materialized as an activation polygon. The probe uses
the detailed ANA/IDEP hydrographic-unit layer (MapServer/7), selects each child by
its exact final-unit CODIGO and independently verifies parent hierarchy plus official
name. No event outcome, outlet, flow, capacity, routing parameter, threshold or
negative control participates in geometry selection.
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DID = "ancash_casma_sechin_yautan"
PACKAGE = ROOT / f"site/data/validation/phase2_discovery_packages/{DID}.json"
CONTRACT = ROOT / f"site/data/validation/phase2_discovery_contracts/{DID}.json"
SOURCE_DIR = ROOT / "site/data/phase2/sources/north_coast_discovery_geometry"
DETAILED_ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/7/query"
LEGACY_GENERALIZED_ENDPOINT = "https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8/query"
PARENT_N6_CODE = "137596"
PARENT_N6_NAME = "Cuenca Casma"

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

EXPECTED = {
    "bajo_casma": ("1375961", "Bajo Casma"),
    "rio_sechin": ("1375962", "Rio Sechin"),
    "medio_bajo_casma": ("1375963", "Medio Bajo Casma"),
    "rio_yautan": ("1375964", "Rio Yautan"),
    "medio_casma_grande_context": ("1375965", "Medio Casma"),
    "rio_vado": ("1375966", "Rio Vado"),
    "medio_alto_casma_chacchan_context": ("1375967", "Medio Alto Casma"),
    "rio_pira": ("1375968", "Rio Pira"),
    "alto_casma_chacchan_context": ("1375969", "Alto Casma"),
}


class CasmaGeometryError(RuntimeError):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))
    return digest(path)


def folded(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip().casefold()


def guards(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise CasmaGeometryError(f"UNSAFE_{label}_{key}")


def source_path(code: str) -> Path:
    return SOURCE_DIR / f"ana_ancash_casma_{code}.geojson"


def validation_path(geometry_path: Path) -> Path:
    return geometry_path.with_name(geometry_path.stem + "_validation.json")


def exact_n7_query(code: str) -> dict:
    return {
        "endpoint": DETAILED_ENDPOINT,
        "where": f"CODIGO='{code}'",
        "out_fields": "*",
        "out_sr": 4326,
        "geometry_precision": 7,
        "format": "geojson",
    }


def request_url(query: dict) -> str:
    params = {
        "where": query["where"],
        "outFields": query["out_fields"],
        "returnGeometry": "true",
        "outSR": str(query["out_sr"]),
        "geometryPrecision": str(query["geometry_precision"]),
        "f": query["format"],
    }
    return query["endpoint"] + "?" + urlencode(params)


def fetch_json(query: dict) -> tuple[dict, str]:
    url = request_url(query)
    req = Request(url, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1", "Accept": "application/geo+json,application/json"})
    with urlopen(req, timeout=90) as response:
        payload = response.read()
    if not payload:
        raise CasmaGeometryError("ANA_EMPTY_RESPONSE")
    try:
        return json.loads(payload.decode("utf-8")), url
    except Exception as exc:
        raise CasmaGeometryError("ANA_RESPONSE_NOT_JSON") from exc


def validate_package(package: dict) -> list[dict]:
    guards(package, "PACKAGE")
    if package.get("discovery_id") != DID:
        raise CasmaGeometryError("DISCOVERY_ID_DRIFT")
    identity = package.get("hydrologic_identity") or {}
    if str(identity.get("ana_parent_unit_code")) != PARENT_N6_CODE or folded(identity.get("ana_parent_unit_name")) != folded(PARENT_N6_NAME):
        raise CasmaGeometryError("CASMA_PARENT_IDENTITY_DRIFT")
    policy = package.get("component_policy") or {}
    if policy.get("parent_is_map_polygon") is not False:
        raise CasmaGeometryError("PARENT_MAP_POLYGON_NOT_FORBIDDEN")
    if policy.get("components_must_remain_separate") is not True or policy.get("composite_union_forbidden") is not True:
        raise CasmaGeometryError("CHILD_SEPARATION_GUARD_DRIFT")
    if policy.get("whole_casma_n6_may_replace_child_layers") is not False:
        raise CasmaGeometryError("PARENT_REPLACEMENT_GUARD_DRIFT")

    components = (package.get("assets") or {}).get("geometry_components") or []
    if len(components) != len(EXPECTED):
        raise CasmaGeometryError(f"CHILD_COUNT_DRIFT_{len(components)}")
    by_id = {row.get("component_id"): row for row in components}
    if set(by_id) != set(EXPECTED):
        raise CasmaGeometryError("CHILD_ID_SET_DRIFT")

    for cid, (code, name) in EXPECTED.items():
        row = by_id[cid]
        ident = row.get("hydrologic_identity") or {}
        if str(ident.get("ana_unit_code")) != code or folded(ident.get("ana_unit_name")) != folded(name):
            raise CasmaGeometryError(f"CHILD_IDENTITY_DRIFT_{cid}")
        if str(ident.get("parent_code")) != PARENT_N6_CODE or ident.get("level") != "N7":
            raise CasmaGeometryError(f"CHILD_HIERARCHY_DRIFT_{cid}")
        query = row.get("source_query") or {}
        if query.get("endpoint") not in {DETAILED_ENDPOINT, LEGACY_GENERALIZED_ENDPOINT}:
            raise CasmaGeometryError(f"ENDPOINT_DRIFT_{cid}")
        if query.get("where") not in {f"CODIGO='{code}'", f"NIVEL7='{code}'"}:
            raise CasmaGeometryError(f"WHERE_DRIFT_{cid}")
        if query.get("out_fields") != "*" or query.get("out_sr") != 4326 or query.get("geometry_precision") != 7 or query.get("format") != "geojson":
            raise CasmaGeometryError(f"QUERY_CONTRACT_DRIFT_{cid}")
        row["source_query"] = exact_n7_query(code)
        geometry = row.get("geometry") or {}
        raw_path = geometry.get("path")
        if not isinstance(raw_path, str) or not raw_path.startswith("site/data/phase2/geometries/"):
            raise CasmaGeometryError(f"GEOMETRY_PATH_DRIFT_{cid}")
        if geometry.get("counts_as_operational_geometry") is not False or geometry.get("counts_as_event_footprint") is not False:
            raise CasmaGeometryError(f"UNSAFE_GEOMETRY_ROLE_{cid}")
    return [by_id[cid] for cid in EXPECTED]


def exact_feature(snapshot: dict, code: str, expected_name: str) -> tuple[dict, str]:
    if snapshot.get("type") != "FeatureCollection":
        raise CasmaGeometryError(f"ANA_NOT_FEATURE_COLLECTION_{code}")
    features = snapshot.get("features") or []
    if len(features) != 1:
        raise CasmaGeometryError(f"ANA_EXACT_QUERY_NOT_UNIQUE_{code}_{len(features)}")
    feature = features[0]
    props = feature.get("properties") or {}

    actual_code = str(props.get("CODIGO") or props.get("codigo") or "")
    actual_name = props.get("NOMBRE") or props.get("nombre") or props.get("NOMB_UH_N7") or props.get("nomb_uh_n7")
    parent_code = str(props.get("NIVEL6") or props.get("nivel6") or "")
    parent_name = props.get("NOMB_UH_N6") or props.get("nomb_uh_n6")
    hierarchy_n7 = str(props.get("NIVEL7") or props.get("nivel7") or "")
    order = props.get("ORDEN") if "ORDEN" in props else props.get("orden")

    if actual_code != code:
        raise CasmaGeometryError(f"ANA_CODIGO_IDENTITY_MISMATCH_{code}_{actual_code}")
    if folded(actual_name) != folded(expected_name):
        raise CasmaGeometryError(f"ANA_NAME_IDENTITY_MISMATCH_{code}_{actual_name}")
    if parent_code != PARENT_N6_CODE or folded(parent_name) != folded(PARENT_N6_NAME):
        raise CasmaGeometryError(f"ANA_N6_PARENT_MISMATCH_{code}_{parent_code}_{parent_name}")
    if hierarchy_n7 and hierarchy_n7 != code:
        raise CasmaGeometryError(f"ANA_N7_HIERARCHY_MISMATCH_{code}_{hierarchy_n7}")
    if order is not None and int(float(order)) != 7:
        raise CasmaGeometryError(f"ANA_ORDER_MISMATCH_{code}_{order}")

    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in {"Polygon", "MultiPolygon"} or not geometry.get("coordinates"):
        raise CasmaGeometryError(f"ANA_POLYGON_MISSING_{code}")
    return feature, str(actual_name)


def normalized_geometry(cid: str, code: str, expected_name: str, official_name: str, feature: dict, source_sha: str) -> dict:
    props = {
        "unit_id": f"{DID}__{cid}",
        "parent_discovery_id": DID,
        "component_id": cid,
        "name": expected_name,
        "official_name": official_name,
        "official_unit_code": code,
        "official_identity_field": "CODIGO",
        "official_name_field": "NOMBRE",
        "official_hierarchy_level": "N7",
        "official_parent_identity_field": "NIVEL6",
        "official_parent_unit_code": PARENT_N6_CODE,
        "official_parent_unit_name": PARENT_N6_NAME,
        "source_layer": 7,
        "source_id": f"ANA-UH-{code}-{cid.upper()}",
        "source_snapshot_sha256": source_sha,
        "representation": "OFFICIAL_ANA_N7_HYDROGRAPHIC_CHILD_CONTEXT",
        "context_only": True,
        "parent_composite": False,
        "counts_as_event_footprint": False,
        "counts_as_operational_geometry": False,
        "alerting_enabled": False,
        **SAFE,
    }
    return {
        "type": "FeatureCollection",
        "properties": {
            **SAFE,
            "context_only": True,
            "parent_composite": False,
            "source_layer": 7,
            "source_id": props["source_id"],
            "source_snapshot_sha256": source_sha,
        },
        "features": [{"type": "Feature", "properties": props, "geometry": feature["geometry"]}],
    }


def build_contract(package: dict, components: list[dict]) -> dict:
    return {
        "schema_version": "0.2",
        "discovery_id": DID,
        "system_name": package.get("system_name"),
        "contract_status": "DISCOVERY_CHILD_GEOMETRIES_REPRODUCIBLE_CONTEXT_ONLY",
        **SAFE,
        "source_layer_policy": {
            "service": "ANA_WMS",
            "detailed_layer_id": 7,
            "generalized_layer_id_not_valid_for_n7_bootstrap": 8,
            "selection_field": "CODIGO",
            "selection_is_outcome_independent": True,
        },
        "official_source_ids": [row["source_id"] for row in components],
        "component_policy": {
            "parent_is_hydrologic_basin": False,
            "parent_is_map_polygon": False,
            "components_must_remain_separate": True,
            "composite_union_forbidden": True,
            "territorial_reference_is_basin": False,
            "whole_casma_n6_may_be_used_as_context_only": True,
            "whole_casma_n6_may_replace_child_layers": False,
        },
        "assets": {
            "geometry": {
                "status": "MISSING_PARENT_GROUPER_NO_SYNTHETIC_GEOMETRY",
                "path": None,
                "representation": None,
                "source_ids": [],
                "counts_as_operational_geometry": False,
                "counts_as_event_footprint": False,
            },
            "geometry_components": components,
        },
        "map_policy": {
            "parent_composite_polygon_forbidden": True,
            "publish_parent_composite": False,
            "publish_children_independently": True,
            "approximate_geometry_forbidden": True,
            "risk_or_alert_coloring_forbidden": True,
            "event_footprint_from_basin_geometry_forbidden": True,
        },
        "forbidden": [
            "union the nine N7 children into a synthetic activation geometry",
            "promote Cuenca Casma or the territorial discovery parent as activated because one child has evidence",
            "use these basin polygons as event footprints",
            "infer outlets, confluences, Q_i(t), travel time, attenuation or receiver response from basin polygons",
            "propagate Rio Sechin or Rio Grande event evidence to sibling children",
            "materialize Quebrada Cruz Punta or Quebrada Muna without independent reproducible geometry",
            "derive negative controls from documentary silence",
            "derive risk, operational threshold or alert state",
        ],
    }


def run(refresh_source: bool) -> dict:
    package = load(PACKAGE)
    rows = validate_package(package)
    existing = [source_path(EXPECTED[row["component_id"]][0]).is_file() for row in rows]
    if any(existing) and not all(existing):
        raise CasmaGeometryError("PARTIAL_FROZEN_SOURCE_SET_FAIL_CLOSED")

    staged: dict[str, tuple[dict, str, str]] = {}
    if refresh_source:
        for row in rows:
            cid = row["component_id"]
            code, expected_name = EXPECTED[cid]
            snapshot, url = fetch_json(row["source_query"])
            _, official_name = exact_feature(snapshot, code, expected_name)
            staged[cid] = (snapshot, url, official_name)
        for cid, (snapshot, _, _) in staged.items():
            code, _ = EXPECTED[cid]
            dump(source_path(code), snapshot)
    elif not all(existing):
        raise CasmaGeometryError("FROZEN_SOURCE_SET_MISSING_USE_REFRESH_SOURCE")

    materialized: list[dict] = []
    package_by_id = {row["component_id"]: row for row in rows}
    for cid, (code, expected_name) in EXPECTED.items():
        source = source_path(code)
        snapshot = load(source)
        feature, official_name = exact_feature(snapshot, code, expected_name)
        source_sha = digest(source)
        package_row = package_by_id[cid]
        geom_path = ROOT / package_row["geometry"]["path"]
        geom_sha = dump(geom_path, normalized_geometry(cid, code, expected_name, official_name, feature, source_sha))
        val_path = validation_path(geom_path)
        validation = {
            "schema_version": "0.2",
            "discovery_id": DID,
            "component_id": cid,
            "status": "PASS_EXACT_OFFICIAL_ANA_N7_CHILD_GEOMETRY",
            **SAFE,
            "ana_unit_code": code,
            "ana_expected_name": expected_name,
            "ana_official_name": official_name,
            "ana_identity_field": "CODIGO",
            "ana_name_field": "NOMBRE",
            "ana_parent_identity_field": "NIVEL6",
            "ana_parent_unit_code": PARENT_N6_CODE,
            "ana_parent_unit_name": PARENT_N6_NAME,
            "source_layer": 7,
            "source_id": package_row["source_id"],
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_sha256": source_sha,
            "geometry_path": geom_path.relative_to(ROOT).as_posix(),
            "geometry_sha256": geom_sha,
            "request_url": request_url(package_row["source_query"]),
            "exact_query_unique_feature": True,
            "selection_depends_on_outcomes": False,
            "approximate_geometry_used": False,
            "parent_composite_created": False,
            "event_footprint_created": False,
            "outlet_inferred": False,
            "discharge_inferred": False,
            "travel_time_inferred": False,
            "attenuation_inferred": False,
            "capacity_inferred": False,
            "thresholds_used": False,
            "negative_controls_read": False,
        }
        val_sha = dump(val_path, validation)
        geometry = {
            "status": "PARTIAL_OFFICIAL_ANA_N7_HYDROGRAPHIC_CHILD_CONTEXT",
            "path": geom_path.relative_to(ROOT).as_posix(),
            "representation": "OFFICIAL_ANA_N7_HYDROGRAPHIC_CHILD_CONTEXT",
            "sha256": geom_sha,
            "validation_path": val_path.relative_to(ROOT).as_posix(),
            "validation_sha256": val_sha,
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_sha256": source_sha,
            "counts_as_operational_geometry": False,
            "counts_as_event_footprint": False,
        }
        package_row["geometry"] = geometry
        materialized.append({
            "component_id": cid,
            "name": expected_name,
            "hydrologic_identity": package_row["hydrologic_identity"],
            "source_id": package_row["source_id"],
            "source_query": package_row["source_query"],
            "geometry": geometry,
        })

    package["contract_status"] = "DISCOVERY_CHILD_GEOMETRIES_REPRODUCIBLE_CONTEXT_ONLY"
    package["geometry_contract_path"] = CONTRACT.relative_to(ROOT).as_posix()
    package["geometry_source_layer"] = 7
    package["geometry_selection_field"] = "CODIGO"
    dump(PACKAGE, package)
    contract_sha = dump(CONTRACT, build_contract(package, materialized))
    return {
        "status": "PASS_EXACT_ANA_CASMA_N7_CHILD_GEOMETRIES",
        "discovery_id": DID,
        "child_count": len(materialized),
        "source_layer": 7,
        "selection_field": "CODIGO",
        "contract_sha256": contract_sha,
        "source_sha256": {cid: digest(source_path(code)) for cid, (code, _) in EXPECTED.items()},
        "geometry_sha256": {row["component_id"]: row["geometry"]["sha256"] for row in materialized},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-source", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.refresh_source), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
