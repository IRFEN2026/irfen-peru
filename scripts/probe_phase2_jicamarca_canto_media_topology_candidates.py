#!/usr/bin/env python3
"""Freeze bounded official IGP topology candidates for Canto Grande / Media Luna.

The probe uses only frozen official child channel lines plus a preregistered spatial
query against the official IGP Quebrada_Lima layer. Results are candidate source
geometries only. No outlet, confluence, receiver, catchment, routing parameter,
event attribution, threshold, risk state or alert is accepted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/phase2_jicamarca_canto_media_topology_candidate_probe_v0_1.json"
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


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def canonical_bytes(value) -> bytes:
    return canonical(value).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def guard(obj: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if obj.get(key) != expected:
            raise ProbeError(f"UNSAFE_{label}_{key}")


def get_json(url: str, params: dict, max_bytes: int) -> dict:
    full = url + "?" + urlencode(params)
    req = Request(full, headers={"User-Agent": "IRFEN-RESEARCH-ONLY/0.1", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=90) as response:
            payload = response.read(max_bytes + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise ProbeError(f"SOURCE_FETCH_FAILED {type(exc).__name__}") from exc
    if len(payload) > max_bytes:
        raise ProbeError("SOURCE_RESPONSE_TOO_LARGE")
    if not payload:
        raise ProbeError("SOURCE_EMPTY_RESPONSE")
    try:
        obj = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise ProbeError("SOURCE_NOT_JSON") from exc
    if isinstance(obj, dict) and obj.get("error"):
        raise ProbeError(f"ARCGIS_ERROR {obj['error']}")
    return obj


def field_map(meta: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in meta.get("fields", []):
        name = str(field.get("name") or "")
        suffix = name.rsplit(".", 1)[-1].casefold()
        if suffix and suffix not in out:
            out[suffix] = name
    oid = str(meta.get("objectIdField") or "")
    if oid:
        out["objectid"] = oid
    return out


def iter_lines(fc: dict):
    if fc.get("type") != "FeatureCollection":
        raise ProbeError("FROZEN_CHANNEL_NOT_FEATURE_COLLECTION")
    features = fc.get("features") or []
    if not features:
        raise ProbeError("FROZEN_CHANNEL_EMPTY")
    for feature in features:
        geometry = feature.get("geometry") or {}
        gtype = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if gtype == "LineString":
            yield coordinates
        elif gtype == "MultiLineString":
            for line in coordinates or []:
                yield line
        else:
            raise ProbeError(f"FROZEN_CHANNEL_UNEXPECTED_GEOMETRY {gtype}")


def channel_points(fc: dict) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for line in iter_lines(fc):
        if not line or len(line) < 2:
            raise ProbeError("FROZEN_CHANNEL_SHORT_LINE")
        for xy in line:
            if not isinstance(xy, list) or len(xy) < 2:
                raise ProbeError("FROZEN_CHANNEL_BAD_COORDINATE")
            x, y = float(xy[0]), float(xy[1])
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ProbeError("FROZEN_CHANNEL_NONFINITE_COORDINATE")
            points.append((x, y))
    return points


def envelope(points: list[tuple[float, float]], buffer_degrees: float) -> dict:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return {
        "xmin": round(min(xs) - buffer_degrees, 7),
        "ymin": round(min(ys) - buffer_degrees, 7),
        "xmax": round(max(xs) + buffer_degrees, 7),
        "ymax": round(max(ys) + buffer_degrees, 7),
        "spatialReference": {"wkid": 4326},
    }


def validate_contract(contract: dict) -> None:
    guard(contract, "CONTRACT")
    if contract.get("scientific_parent_context") != "jicamarca":
        raise ProbeError("PARENT_CONTEXT_DRIFT")
    children = contract.get("children") or []
    if [row.get("child_id") for row in children] != ["canto_grande_upper_branch", "media_luna"]:
        raise ProbeError("CHILD_SET_OR_ORDER_DRIFT")
    if float(contract["search"]["envelope_buffer_degrees"]) <= 0:
        raise ProbeError("INVALID_SEARCH_BUFFER")
    if contract["search"].get("buffer_role") != "BOUNDED_SOURCE_DISCOVERY_ONLY_NOT_HYDROLOGIC_DISTANCE_OR_ROUTING_PARAMETER":
        raise ProbeError("UNSAFE_BUFFER_ROLE")
    if contract["search"].get("line_endpoint_is_outlet") is not False:
        raise ProbeError("ENDPOINT_OUTLET_PROMOTION_FORBIDDEN")
    guards = contract.get("promotion_guards") or {}
    unsafe = [key for key, value in guards.items() if value is not False]
    if unsafe:
        raise ProbeError(f"UNSAFE_PROMOTION_GUARDS {unsafe}")
    forbidden = " ".join(contract.get("forbidden_inputs") or []).casefold()
    for needle in ("event outcomes", "a6680", "contaminated", "synthetic quebrada jicamarca"):
        if needle not in forbidden:
            raise ProbeError(f"MISSING_FORBIDDEN_INPUT_{needle}")


def validate_frozen_child(row: dict) -> tuple[Path, dict, list[tuple[float, float]]]:
    path = ROOT / row["frozen_channel_path"]
    if not path.is_file():
        raise ProbeError(f"MISSING_FROZEN_CHILD {row['child_id']}")
    if git_blob_sha(path) != row["frozen_channel_git_blob_sha"]:
        raise ProbeError(f"FROZEN_CHILD_BLOB_DRIFT {row['child_id']}")
    fc = load(path)
    guard(fc.get("properties") or {}, f"FROZEN_CHILD_{row['child_id']}")
    if (fc.get("properties") or {}).get("hydrologic_child_id") != row["child_id"]:
        raise ProbeError(f"FROZEN_CHILD_ID_DRIFT {row['child_id']}")
    if (fc.get("properties") or {}).get("outlet_or_confluence") is not False:
        raise ProbeError(f"FROZEN_CHILD_ALREADY_PROMOTES_OUTLET {row['child_id']}")
    if (fc.get("properties") or {}).get("routing_enabled") is not False:
        raise ProbeError(f"FROZEN_CHILD_ALREADY_PROMOTES_ROUTING {row['child_id']}")
    points = channel_points(fc)
    own = sorted({int(x) for x in row["own_source_objectids"]})
    observed = sorted({int((f.get("properties") or {}).get("source_objectid")) for f in fc.get("features", [])})
    if observed != own:
        raise ProbeError(f"FROZEN_CHILD_OBJECTID_DRIFT {row['child_id']}")
    return path, fc, points


def arcgis_geometry_lines(geometry: dict) -> list[list[tuple[float, float]]]:
    paths = geometry.get("paths")
    if not isinstance(paths, list) or not paths:
        raise ProbeError("CANDIDATE_MISSING_POLYLINE_PATHS")
    out = []
    for path in paths:
        if not isinstance(path, list) or len(path) < 2:
            raise ProbeError("CANDIDATE_SHORT_POLYLINE_PATH")
        line = []
        for xy in path:
            if not isinstance(xy, list) or len(xy) < 2:
                raise ProbeError("CANDIDATE_BAD_COORDINATE")
            x, y = float(xy[0]), float(xy[1])
            if not (math.isfinite(x) and math.isfinite(y)):
                raise ProbeError("CANDIDATE_NONFINITE_COORDINATE")
            line.append((x, y))
        out.append(line)
    return out


def child_segments(fc: dict):
    for line in iter_lines(fc):
        pts = [(float(xy[0]), float(xy[1])) for xy in line]
        for a, b in zip(pts, pts[1:]):
            yield a, b


def orientation(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a, b, p, eps=1e-10) -> bool:
    if abs(orientation(a, b, p)) > eps:
        return False
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def segments_intersect(a, b, c, d, eps=1e-10) -> bool:
    o1, o2, o3, o4 = orientation(a, b, c), orientation(a, b, d), orientation(c, d, a), orientation(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)):
        return True
    return any(
        (
            abs(o) <= eps and on_segment(x, y, p, eps)
            for o, x, y, p in (
                (o1, a, b, c),
                (o2, a, b, d),
                (o3, c, d, a),
                (o4, c, d, b),
            )
        )
    )


def candidate_signals(child_fc: dict, candidate_geometry: dict) -> dict:
    exact_vertices = {
        (round(float(xy[0]), 7), round(float(xy[1]), 7))
        for line in iter_lines(child_fc)
        for xy in line
    }
    candidate_lines = arcgis_geometry_lines(candidate_geometry)
    shared = sorted(
        {
            (round(p[0], 7), round(p[1], 7))
            for line in candidate_lines
            for p in line
            if (round(p[0], 7), round(p[1], 7)) in exact_vertices
        }
    )
    intersects = False
    for a, b in child_segments(child_fc):
        for line in candidate_lines:
            for c, d in zip(line, line[1:]):
                if segments_intersect(a, b, c, d):
                    intersects = True
                    break
            if intersects:
                break
        if intersects:
            break
    return {
        "shares_exact_vertex_with_frozen_child": bool(shared),
        "shared_exact_vertex_count": len(shared),
        "literal_2d_segment_intersection_detected": intersects,
        "signal_role": "CANDIDATE_TOPOLOGY_SIGNAL_ONLY_NOT_ACCEPTED_JUNCTION_OUTLET_OR_RECEIVER",
    }


def fetch_snapshot(contract: dict, child_row: dict, child_points: list[tuple[float, float]]) -> dict:
    src = contract["source"]
    search = contract["search"]
    max_bytes = int(search["max_response_bytes"])
    layer_url = f"{src['service_url']}/{int(src['layer_id'])}"
    meta = get_json(layer_url, {"f": "json"}, max_bytes)
    if meta.get("name") != src["expected_layer_name"]:
        raise ProbeError(f"LAYER_NAME_DRIFT {meta.get('name')}")
    if meta.get("geometryType") != src["expected_geometry_type"]:
        raise ProbeError(f"LAYER_GEOMETRY_TYPE_DRIFT {meta.get('geometryType')}")
    spatial_ref = (meta.get("extent") or {}).get("spatialReference") or {}
    wkid = spatial_ref.get("latestWkid") or spatial_ref.get("wkid")
    if int(wkid) != int(src["expected_spatial_reference_wkid"]):
        raise ProbeError(f"LAYER_WKID_DRIFT {wkid}")
    if meta.get("serviceItemId") not in (None, src["service_item_id"]):
        raise ProbeError(f"SERVICE_ITEM_DRIFT {meta.get('serviceItemId')}")

    fmap = field_map(meta)
    required = {str(x).casefold() for x in src["required_fields"]}
    missing = sorted(required - set(fmap))
    if missing:
        raise ProbeError(f"SOURCE_SCHEMA_DRIFT missing={missing}")
    env = envelope(child_points, float(search["envelope_buffer_degrees"]))
    envelope_json = json.dumps(env, sort_keys=True, separators=(",", ":"))
    query_url = layer_url + "/query"
    id_obj = get_json(
        query_url,
        {
            "where": search["where"],
            "geometry": envelope_json,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "returnIdsOnly": "true",
            "f": "json",
        },
        max_bytes,
    )
    object_ids = sorted({int(x) for x in (id_obj.get("objectIds") or [])})
    if len(object_ids) > int(search["max_candidate_object_ids_per_child"]):
        raise ProbeError(f"CANDIDATE_ID_LIMIT_EXCEEDED {child_row['child_id']} {len(object_ids)}")
    if not object_ids:
        raise ProbeError(f"NO_SOURCE_FEATURES_IN_BOUNDED_ENVELOPE {child_row['child_id']}")

    semantic = {
        "objectid": "objectid",
        "nombre": "name",
        "nomdep": "department",
        "nomprov": "province",
        "nomdist": "district",
        "clasificac": "classification",
        "tipo": "source_type",
        "ubigeo": "ubigeo",
    }
    actual_fields = [fmap[key] for key in sorted(required)]
    chunk = int(search["query_chunk_size"])
    features = []
    for start in range(0, len(object_ids), chunk):
        subset = object_ids[start : start + chunk]
        obj = get_json(
            query_url,
            {
                "objectIds": ",".join(map(str, subset)),
                "outFields": ",".join(actual_fields),
                "returnGeometry": "true",
                "outSR": str(search["out_sr"]),
                "geometryPrecision": str(search["geometry_precision"]),
                "f": "json",
            },
            max_bytes,
        )
        for feature in obj.get("features", []):
            attrs = feature.get("attributes") or {}
            normalized_attrs = {semantic[key]: attrs.get(fmap[key]) for key in semantic}
            oid = int(normalized_attrs["objectid"])
            geometry = feature.get("geometry") or {}
            arcgis_geometry_lines(geometry)
            features.append({"attributes": normalized_attrs, "geometry": geometry})
    features.sort(key=lambda row: int(row["attributes"]["objectid"]))
    observed_ids = [int(row["attributes"]["objectid"]) for row in features]
    if observed_ids != object_ids:
        raise ProbeError(f"FEATURE_ID_SET_MISMATCH {child_row['child_id']}")

    return {
        "schema_version": "0.1",
        "status": "FROZEN_BOUNDED_OFFICIAL_IGP_SPATIAL_CANDIDATE_SNAPSHOT",
        **SAFE,
        "child_id": child_row["child_id"],
        "source": {
            "institution": src["institution"],
            "layer_url": layer_url,
            "layer_name": meta.get("name"),
            "geometry_type": meta.get("geometryType"),
            "spatial_reference_wkid": int(wkid),
            "service_item_id": meta.get("serviceItemId") or src["service_item_id"],
            "resolved_fields": {key: fmap[key] for key in sorted(required)},
        },
        "query": {
            "where": search["where"],
            "spatial_relationship": "esriSpatialRelIntersects",
            "geometry_type": "esriGeometryEnvelope",
            "envelope": env,
            "envelope_buffer_degrees": float(search["envelope_buffer_degrees"]),
            "buffer_role": search["buffer_role"],
            "out_sr": int(search["out_sr"]),
            "geometry_precision": int(search["geometry_precision"]),
        },
        "object_ids": object_ids,
        "feature_count": len(features),
        "features": features,
        "candidate_only": True,
        "geometry_accepted_as_receiver": False,
        "junction_or_outlet_accepted": False,
        "routing_enabled": False,
    }


def validate_snapshot(contract: dict, child_row: dict, snapshot: dict) -> None:
    guard(snapshot, f"SNAPSHOT_{child_row['child_id']}")
    if snapshot.get("status") != "FROZEN_BOUNDED_OFFICIAL_IGP_SPATIAL_CANDIDATE_SNAPSHOT":
        raise ProbeError(f"SNAPSHOT_STATUS_DRIFT {child_row['child_id']}")
    if snapshot.get("child_id") != child_row["child_id"]:
        raise ProbeError(f"SNAPSHOT_CHILD_DRIFT {child_row['child_id']}")
    if snapshot.get("candidate_only") is not True:
        raise ProbeError(f"SNAPSHOT_NOT_CANDIDATE_ONLY {child_row['child_id']}")
    if snapshot.get("geometry_accepted_as_receiver") is not False or snapshot.get("junction_or_outlet_accepted") is not False or snapshot.get("routing_enabled") is not False:
        raise ProbeError(f"SNAPSHOT_UNSAFE_PROMOTION {child_row['child_id']}")
    expected_buffer = float(contract["search"]["envelope_buffer_degrees"])
    query = snapshot.get("query") or {}
    if float(query.get("envelope_buffer_degrees")) != expected_buffer or query.get("buffer_role") != contract["search"]["buffer_role"]:
        raise ProbeError(f"SNAPSHOT_QUERY_DRIFT {child_row['child_id']}")
    ids = [int(x) for x in snapshot.get("object_ids") or []]
    features = snapshot.get("features") or []
    if len(ids) != len(set(ids)) or len(ids) != len(features) or snapshot.get("feature_count") != len(features):
        raise ProbeError(f"SNAPSHOT_CARDINALITY_DRIFT {child_row['child_id']}")
    if len(ids) > int(contract["search"]["max_candidate_object_ids_per_child"]):
        raise ProbeError(f"SNAPSHOT_ID_LIMIT_DRIFT {child_row['child_id']}")
    observed = []
    for feature in features:
        oid = int((feature.get("attributes") or {})["objectid"])
        observed.append(oid)
        arcgis_geometry_lines(feature.get("geometry") or {})
    if observed != sorted(ids):
        raise ProbeError(f"SNAPSHOT_FEATURE_ORDER_OR_SET_DRIFT {child_row['child_id']}")


def build_report(contract: dict, child_context: dict[str, tuple[dict, dict]]) -> dict:
    child_reports = []
    for child_row in contract["children"]:
        child_id = child_row["child_id"]
        child_fc, snapshot = child_context[child_id]
        own = {int(x) for x in child_row["own_source_objectids"]}
        candidates = []
        for feature in snapshot["features"]:
            attrs = feature["attributes"]
            oid = int(attrs["objectid"])
            if oid in own:
                continue
            signals = candidate_signals(child_fc, feature["geometry"])
            candidates.append(
                {
                    "source_objectid": oid,
                    "source_name": attrs.get("name"),
                    "department": attrs.get("department"),
                    "province": attrs.get("province"),
                    "district": attrs.get("district"),
                    "classification": attrs.get("classification"),
                    "source_type": attrs.get("source_type"),
                    "ubigeo": attrs.get("ubigeo"),
                    **signals,
                    "accepted_as_child_geometry": False,
                    "accepted_as_receiver": False,
                    "accepted_as_junction": False,
                    "accepted_as_outlet": False,
                    "accepted_for_routing": False,
                }
            )
        candidates.sort(key=lambda row: row["source_objectid"])
        child_reports.append(
            {
                "child_id": child_id,
                "frozen_channel_path": child_row["frozen_channel_path"],
                "frozen_channel_git_blob_sha": child_row["frozen_channel_git_blob_sha"],
                "source_snapshot_path": child_row["snapshot_path"],
                "source_snapshot_sha256": sha256_file(ROOT / child_row["snapshot_path"]),
                "source_feature_count_in_bounded_envelope": snapshot["feature_count"],
                "own_source_objectids_excluded": sorted(own),
                "candidate_count_after_own_source_exclusion": len(candidates),
                "literal_2d_intersection_candidate_count": sum(1 for row in candidates if row["literal_2d_segment_intersection_detected"]),
                "shared_exact_vertex_candidate_count": sum(1 for row in candidates if row["shares_exact_vertex_with_frozen_child"]),
                "candidates": candidates,
                "junction_or_outlet_resolved": False,
                "receiver_resolved": False,
                "routing_enabled": False,
            }
        )
    return {
        "schema_version": "0.1",
        "status": "PASS_FROZEN_BOUNDED_LOCAL_TOPOLOGY_CANDIDATE_DISCOVERY",
        **SAFE,
        "contract_path": DEFAULT_CONTRACT.relative_to(ROOT).as_posix(),
        "contract_sha256": sha256_file(DEFAULT_CONTRACT),
        "assessment_contract": contract["assessment_contract"],
        "effective_evidence_index": contract["effective_evidence_index"],
        "selection_used_event_outcomes": False,
        "selection_used_A6680": False,
        "selection_used_CENDEHUA_activation_labels": False,
        "selection_used_SOPHy_rainfall": False,
        "selection_used_free_web_search": False,
        "children": child_reports,
        "geometry_promoted": False,
        "junction_or_outlet_promoted": False,
        "receiver_promoted": False,
        "catchment_created": False,
        "Q_i_t_promoted": False,
        "travel_time_promoted": False,
        "attenuation_promoted": False,
        "hydraulic_capacity_promoted": False,
        "thresholds_promoted": False,
        "routing_enabled": False,
        "parent_activation_promoted": False,
        "rimac_overflow_promoted": False,
        "next_gate": contract["next_gate_if_candidates_are_frozen"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--refresh-source", action="store_true")
    args = parser.parse_args()
    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    contract = load(contract_path)
    validate_contract(contract)
    if contract_path.resolve() != DEFAULT_CONTRACT.resolve():
        raise ProbeError("NONDEFAULT_CONTRACT_NOT_SUPPORTED_FOR_FROZEN_REPORT_PATH")

    assessment = load(ROOT / contract["assessment_contract"])
    evidence_index = load(ROOT / contract["effective_evidence_index"])
    guard(assessment, "ASSESSMENT")
    guard(evidence_index, "EVIDENCE_INDEX")
    if assessment.get("outlet_resolution_gate", {}).get("status") != "BLOCKED_PENDING_DETERMINISTIC_TERRAIN_TOPOLOGY_RESOLUTION_AND_QA":
        raise ProbeError("OUTLET_GATE_NOT_BLOCKED")
    if evidence_index.get("collector_effect", {}).get("routing_enabled") is not False:
        raise ProbeError("EVIDENCE_INDEX_ROUTING_ALREADY_ENABLED")

    loaded_children: dict[str, tuple[dict, list[tuple[float, float]]]] = {}
    for row in contract["children"]:
        _, fc, points = validate_frozen_child(row)
        loaded_children[row["child_id"]] = (fc, points)

    snapshot_paths = [ROOT / row["snapshot_path"] for row in contract["children"]]
    report_path = ROOT / contract["candidate_report_path"]
    existence = [path.is_file() for path in snapshot_paths]
    if any(existence) and not all(existence):
        raise ProbeError("PARTIAL_FROZEN_SNAPSHOT_SET")
    if args.refresh_source and all(existence):
        raise ProbeError("FROZEN_SNAPSHOT_SET_ALREADY_EXISTS_NO_REFRESH_ALLOWED")
    if not args.refresh_source and not all(existence):
        raise ProbeError("FROZEN_SNAPSHOT_SET_MISSING_USE_REFRESH_SOURCE")

    if args.refresh_source:
        staged: list[tuple[Path, dict]] = []
        for row in contract["children"]:
            _, points = loaded_children[row["child_id"]]
            snapshot = fetch_snapshot(contract, row, points)
            validate_snapshot(contract, row, snapshot)
            staged.append((ROOT / row["snapshot_path"], snapshot))
        for path, snapshot in staged:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(canonical(snapshot), encoding="utf-8")

    context: dict[str, tuple[dict, dict]] = {}
    for row in contract["children"]:
        path = ROOT / row["snapshot_path"]
        snapshot = load(path)
        validate_snapshot(contract, row, snapshot)
        child_fc, _ = loaded_children[row["child_id"]]
        context[row["child_id"]] = (child_fc, snapshot)

    report = build_report(contract, context)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    new_bytes = canonical_bytes(report)
    if report_path.is_file() and report_path.read_bytes() != new_bytes:
        raise ProbeError("FROZEN_CANDIDATE_REPORT_REPLAY_DRIFT")
    report_path.write_bytes(new_bytes)
    print(
        json.dumps(
            {
                "status": report["status"],
                "children": {
                    row["child_id"]: {
                        "candidate_count": row["candidate_count_after_own_source_exclusion"],
                        "literal_2d_intersection_candidate_count": row["literal_2d_intersection_candidate_count"],
                    }
                    for row in report["children"]
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
