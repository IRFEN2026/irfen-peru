#!/usr/bin/env python3
"""Bounded official MINAM hydrography probe for the Jicamarca Rio Seco child.

This is a source-discovery gate only. It queries the official MINAM Geoservidor
hydrography layer inside the already-preregistered coarse documentary Jicamarca
window and returns candidate polylines for a later independent identity/topology
review. It never accepts a Rio Seco channel, catchment, outlet, confluence,
routing parameter, event footprint, negative control, threshold, risk state or
alert.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config/phase2_jicamarca_rio_seco_minam_hydrography_probe_v0_1.json"
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


class ProbeError(RuntimeError):
    pass


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def guard(doc: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if doc.get(key) != expected:
            raise ProbeError(f"UNSAFE_{label}_{key}")


def get_json(url: str, params: dict, max_bytes: int) -> tuple[dict, bytes, str]:
    full = url + "?" + urlencode(params)
    req = Request(
        full,
        headers={
            "User-Agent": "IRFEN-RESEARCH-ONLY/0.1",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=90) as response:
        data = response.read(max_bytes + 1)
        final_url = response.geturl()
    if len(data) > max_bytes:
        raise ProbeError("SOURCE_RESPONSE_TOO_LARGE")
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ProbeError("SOURCE_NOT_JSON") from exc
    if isinstance(obj, dict) and obj.get("error"):
        raise ProbeError(f"ARCGIS_ERROR {obj['error']}")
    return obj, data, final_url


def spatial_wkid(meta: dict) -> int | None:
    sr = (meta.get("extent") or {}).get("spatialReference") or {}
    value = sr.get("latestWkid") or sr.get("wkid")
    return int(value) if value is not None else None


def field_names(meta: dict) -> set[str]:
    return {str(f.get("name")) for f in meta.get("fields") or [] if f.get("name")}


def geometry_bbox(paths: list) -> list[float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for path in paths or []:
        for coordinate in path or []:
            if isinstance(coordinate, list) and len(coordinate) >= 2:
                xs.append(float(coordinate[0]))
                ys.append(float(coordinate[1]))
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def candidate_row(feature: dict, output_wkid: int) -> dict:
    attrs = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}
    paths = geometry.get("paths") or []
    return {
        "source_objectid": attrs.get("OBJECTID_1"),
        "source_objectid_secondary": attrs.get("objectid"),
        "name": normalize_text(attrs.get("nombre")),
        "type_code": normalize_text(attrs.get("tipo")),
        "state_code": attrs.get("estado"),
        "code": normalize_text(attrs.get("codigo")),
        "zone": attrs.get("zona"),
        "segment_text": normalize_text(attrs.get("text_tramo")),
        "aaa": normalize_text(attrs.get("aaa")),
        "level5": normalize_text(attrs.get("nivel5")),
        "level6": normalize_text(attrs.get("nivel6")),
        "level7": normalize_text(attrs.get("nivel7")),
        "source_id": attrs.get("id"),
        "scale": attrs.get("escala"),
        "river_code": attrs.get("code_rio"),
        "geometry_type_text": normalize_text(attrs.get("tipo_g")),
        "river_or_ravine_text": normalize_text(attrs.get("r_q_text")),
        "minam_name": normalize_text(attrs.get("nomb_min")),
        "source_text": normalize_text(attrs.get("fuente")),
        "source_geometry": {
            "type": "MultiLineStringCandidate",
            "paths": paths,
            "spatial_reference_wkid": output_wkid,
        },
        "source_geometry_bbox_wgs84": geometry_bbox(paths),
        "geometry_accepted_as_rio_seco_channel": False,
        "catchment_accepted": False,
        "outlet_or_confluence_accepted": False,
        "routing_enabled": False,
        "event_footprint": False,
        "requires_separate_identity_and_topology_review": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    guard(contract, "CONTRACT")
    if contract.get("component_id") != "rio_seco":
        raise ProbeError("COMPONENT_MISMATCH")
    if contract.get("system_id") != "lima_este_jicamarca_huaycoloro_rioseco_canto_grande":
        raise ProbeError("SYSTEM_MISMATCH")

    policy = contract.get("candidate_policy") or {}
    forbidden_true = [
        "candidate_is_accepted_rio_seco_channel",
        "name_match_is_sufficient_identity",
        "documentary_window_is_catchment_geometry",
        "line_endpoint_is_outlet",
        "line_intersection_is_confluence_without_independent_topology_review",
        "line_length_may_define_travel_time",
        "candidate_may_define_Q_i_t",
        "candidate_may_define_attenuation",
        "candidate_may_define_hydraulic_capacity",
        "candidate_may_define_event_footprint",
        "candidate_may_enable_routing",
        "candidate_may_promote_parent_activation",
        "candidate_may_promote_rimac_overflow",
    ]
    for key in forbidden_true:
        if policy.get(key) is not False:
            raise ProbeError(f"CANDIDATE_POLICY_DRIFT_{key}")
    required_true = [
        "selection_requires_separate_frozen_identity_and_topology_review",
        "selection_must_not_use_event_outcomes",
        "selection_must_not_use_A6680",
        "selection_must_not_use_quarantined_qda_colca_as_rio_seco_geometry",
        "same_name_feature_outside_jicamarca_window_must_not_be_rebound",
    ]
    for key in required_true:
        if policy.get(key) is not True:
            raise ProbeError(f"CANDIDATE_POLICY_DRIFT_{key}")

    window = contract["query_window"]
    if window.get("buffer_applied") is not False:
        raise ProbeError("QUERY_WINDOW_BUFFER_NOT_ALLOWED")
    west = float(window["west_lon"])
    south = float(window["south_lat"])
    east = float(window["east_lon"])
    north = float(window["north_lat"])
    if not (-77.1 <= west < east <= -76.5 and -12.2 <= south < north <= -11.6):
        raise ProbeError("QUERY_WINDOW_OUTSIDE_JICAMARCA_REGION")

    source = contract["source"]
    layer_url = f"{source['service_url']}/{int(source['layer_id'])}"
    query = contract["query"]
    max_bytes = int(query["max_response_bytes"])

    meta, meta_bytes, meta_url = get_json(layer_url, {"f": "json"}, max_bytes)
    if meta.get("name") != source["expected_layer_name"]:
        raise ProbeError(f"LAYER_NAME_DRIFT {meta.get('name')}")
    if meta.get("geometryType") != source["expected_geometry_type"]:
        raise ProbeError(f"GEOMETRY_TYPE_DRIFT {meta.get('geometryType')}")
    wkid = spatial_wkid(meta)
    if wkid != int(source["service_spatial_reference_wkid"]):
        raise ProbeError(f"SOURCE_SPATIAL_REFERENCE_DRIFT {wkid}")
    available = field_names(meta)
    missing = [field for field in source["required_fields"] if field not in available]
    if missing:
        raise ProbeError(f"SOURCE_SCHEMA_DRIFT missing={missing}")

    envelope = {
        "xmin": west,
        "ymin": south,
        "xmax": east,
        "ymax": north,
        "spatialReference": {"wkid": int(window["input_spatial_reference_wkid"])},
    }
    out_fields = ",".join(source["required_fields"])
    result, result_bytes, result_url = get_json(
        layer_url + "/query",
        {
            "where": query["where"],
            "geometry": json.dumps(envelope, separators=(",", ":")),
            "geometryType": query["geometry_type"],
            "inSR": str(int(window["input_spatial_reference_wkid"])),
            "spatialRel": query["spatial_relation"],
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": str(int(query["output_spatial_reference_wkid"])),
            "resultRecordCount": str(int(query["max_candidate_features"]) + 1),
            "f": "json",
        },
        max_bytes,
    )
    features = result.get("features") or []
    if result.get("exceededTransferLimit"):
        raise ProbeError("ARCGIS_TRANSFER_LIMIT_EXCEEDED")
    if len(features) > int(query["max_candidate_features"]):
        raise ProbeError(f"TOO_MANY_CANDIDATES {len(features)}")

    output_wkid = int(query["output_spatial_reference_wkid"])
    candidates = [candidate_row(feature, output_wkid) for feature in features]
    candidates.sort(
        key=lambda row: (
            str(row.get("name") or "").casefold(),
            str(row.get("minam_name") or "").casefold(),
            str(row.get("river_or_ravine_text") or "").casefold(),
            int(row.get("source_objectid") or 0),
        )
    )

    report = {
        "schema_version": "0.1",
        "status": "PASS_BOUNDED_MINAM_RIO_SECO_HYDROGRAPHY_CANDIDATE_PROBE",
        **SAFE,
        "system_id": contract["system_id"],
        "component_id": "rio_seco",
        "query_window": {
            "basis": window["basis"],
            "west_lon": west,
            "south_lat": south,
            "east_lon": east,
            "north_lat": north,
            "buffer_applied": False,
            "catchment_geometry": False,
        },
        "source": {
            "institution": source["institution"],
            "publication_host": source["publication_host"],
            "layer_url": layer_url,
            "layer_name": meta.get("name"),
            "geometry_type": meta.get("geometryType"),
            "source_spatial_reference_wkid": wkid,
            "metadata_request_url": meta_url,
            "metadata_response_sha256": sha256(meta_bytes),
            "query_request_url": result_url,
            "query_response_sha256": sha256(result_bytes),
        },
        "candidate_count": len(candidates),
        "candidate_geometry_requested": True,
        "candidate_geometry_accepted": False,
        "catchment_geometry_accepted": False,
        "outlet_inferred": False,
        "confluence_inferred": False,
        "routing_enabled": False,
        "Q_i_t": None,
        "travel_time": None,
        "attenuation": None,
        "hydraulic_capacity": None,
        "parent_activation_promoted": False,
        "rimac_overflow_inferred": False,
        "candidates": candidates,
        "interpretation_rule": "Every returned MINAM line is candidate-only. Name and intersection with the coarse documentary Jicamarca window are insufficient identity. Promotion requires a separate frozen, outcome-independent identity/topology review compatible with independent official evidence and must keep Rio Seco distinct from Colca, Huaycoloro and unrelated same-name Rio Seco features.",
    }
    guard(report, "REPORT")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "candidate_count": len(candidates)}, sort_keys=True))


if __name__ == "__main__":
    main()
