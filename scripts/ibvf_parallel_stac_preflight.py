#!/usr/bin/env python3
"""Blind A1 catalog preflight for IBVF parallel tracks.

The same fixed query contract is applied to every track. Sentinel-1 GRD and
Landsat C2 L2 are queried season-by-season using the 12 already-frozen A0
September-April seasons. Copernicus GLO-30 is queried once per geometry because
it is a static DEM collection. No territorial outcome evidence is read, no
window is selected, no case/control role is assigned, and transport failures
remain UNKNOWN/TRANSPORT_BLOCKED rather than being converted to missing data.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import requests

COLLECTIONS = ("sentinel-1-grd", "landsat-c2-l2", "cop-dem-glo-30")
TEMPORAL_COLLECTIONS = ("sentinel-1-grd", "landsat-c2-l2")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(obj: Any) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def iter_xy(node: Any) -> Iterable[tuple[float, float]]:
    if isinstance(node, (list, tuple)):
        if len(node) >= 2 and isinstance(node[0], (int, float)) and isinstance(node[1], (int, float)):
            yield float(node[0]), float(node[1])
        else:
            for child in node:
                yield from iter_xy(child)


def resolve_geometry(site_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    rel = case.get("geometry_path")
    selector = case.get("geometry_selector") or {}
    if not rel:
        return {"status": "GEOMETRY_PATH_UNKNOWN", "bbox": None, "matched_feature_count": 0}
    path = site_root / rel
    if not path.exists():
        return {"status": "GEOMETRY_FILE_BLOCKED_NOT_MISSING", "path": str(path), "bbox": None, "matched_feature_count": 0}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "GEOMETRY_PARSE_BLOCKED_NOT_MISSING", "path": str(path), "error": type(exc).__name__, "bbox": None, "matched_feature_count": 0}
    features = doc.get("features", []) if doc.get("type") == "FeatureCollection" else [doc]
    prop = selector.get("property")
    value = selector.get("value")
    matched = []
    for feature in features:
        props = feature.get("properties") or {}
        if prop is None or props.get(prop) == value:
            matched.append(feature)
    if not matched:
        return {
            "status": "GEOMETRY_SELECTOR_NO_MATCH_NOT_MISSING",
            "path": rel,
            "selector": selector,
            "bbox": None,
            "matched_feature_count": 0,
        }
    xy = []
    for feature in matched:
        xy.extend(iter_xy((feature.get("geometry") or {}).get("coordinates")))
    if not xy:
        return {"status": "GEOMETRY_COORDINATES_BLOCKED_NOT_MISSING", "path": rel, "selector": selector, "bbox": None, "matched_feature_count": len(matched)}
    xs = [p[0] for p in xy]
    ys = [p[1] for p in xy]
    return {
        "status": "CANDIDATE_GEOMETRY_RESOLVED_FOR_CATALOG_PREFLIGHT_ONLY",
        "path": rel,
        "selector": selector,
        "matched_feature_count": len(matched),
        "matched_features_canonical_sha256": canonical_sha256(matched),
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
    }


def season_utc_interval(season: dict[str, Any]) -> str:
    """Exact UTC envelope for local America/Lima calendar days (UTC-5)."""
    start = dt.date.fromisoformat(season["start_local"])
    end = dt.date.fromisoformat(season["end_local_inclusive"])
    next_day = end + dt.timedelta(days=1)
    return f"{start.isoformat()}T05:00:00Z/{next_day.isoformat()}T04:59:59Z"


def summarize_items(collection: str, features: list[dict[str, Any]]) -> dict[str, Any]:
    datetimes = sorted(x for x in ((f.get("properties") or {}).get("datetime") for f in features) if isinstance(x, str))
    props = [f.get("properties") or {} for f in features]
    out: dict[str, Any] = {
        "first_returned_datetime": datetimes[0] if datetimes else None,
        "last_returned_datetime": datetimes[-1] if datetimes else None,
        "returned_item_ids_sample": [f.get("id") for f in features[:5]],
        "asset_keys_union": sorted({k for f in features for k in (f.get("assets") or {}).keys()}),
    }
    if collection == "sentinel-1-grd":
        out.update(
            {
                "platforms": sorted({str(p.get("platform")) for p in props if p.get("platform") is not None}),
                "orbit_states": sorted({str(p.get("sat:orbit_state")) for p in props if p.get("sat:orbit_state") is not None}),
                "relative_orbits": sorted({int(p.get("sat:relative_orbit")) for p in props if isinstance(p.get("sat:relative_orbit"), (int, float))}),
                "polarizations": sorted({str(pol) for p in props for pol in (p.get("sar:polarizations") or [])}),
                "instrument_modes": sorted({str(p.get("sar:instrument_mode")) for p in props if p.get("sar:instrument_mode") is not None}),
            }
        )
    elif collection == "landsat-c2-l2":
        out.update(
            {
                "wrs_paths": sorted({str(p.get("landsat:wrs_path")) for p in props if p.get("landsat:wrs_path") is not None}),
                "wrs_rows": sorted({str(p.get("landsat:wrs_row")) for p in props if p.get("landsat:wrs_row") is not None}),
                "platforms": sorted({str(p.get("platform")) for p in props if p.get("platform") is not None}),
            }
        )
    return out


def query_once(session: requests.Session, root: str, payload: dict[str, Any], collection: str, season_id: str | None) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "season_id": season_id,
        "datetime": payload.get("datetime"),
        "request_payload_sha256": canonical_sha256(payload),
    }
    try:
        response = session.post(root.rstrip("/") + "/search", json=payload, timeout=90)
    except requests.RequestException as exc:
        return {**meta, "transport_status": "TRANSPORT_BLOCKED", "error_class": type(exc).__name__, "_features": []}
    raw = response.content
    meta.update({"http_status": response.status_code, "response_sha256": sha256_bytes(raw), "response_bytes": len(raw)})
    if response.status_code != 200:
        return {**meta, "transport_status": "TRANSPORT_BLOCKED_HTTP", "_features": []}
    try:
        doc = response.json()
    except ValueError:
        return {**meta, "transport_status": "TRANSPORT_BLOCKED_INVALID_JSON", "_features": []}
    features = doc.get("features") or []
    has_next = any((link.get("rel") == "next") for link in (doc.get("links") or []) if isinstance(link, dict))
    return {
        **meta,
        "transport_status": "SUCCESS",
        "returned_item_count": len(features),
        "catalog_result_truncated": bool(has_next),
        "_features": features,
    }


def query_collection(session: requests.Session, root: str, bbox: list[float], collection: str, seasons: list[dict[str, Any]]) -> dict[str, Any]:
    request_records: list[dict[str, Any]] = []
    unique: dict[str, dict[str, Any]] = {}
    query_windows = seasons if collection in TEMPORAL_COLLECTIONS else [None]
    for season in query_windows:
        payload: dict[str, Any] = {"collections": [collection], "bbox": bbox, "limit": 1000}
        season_id = None
        if season is not None:
            season_id = str(season["season_id"])
            payload["datetime"] = season_utc_interval(season)
        q = query_once(session, root, payload, collection, season_id)
        for feature in q.pop("_features"):
            item_id = str(feature.get("id"))
            unique[item_id] = feature
        request_records.append(q)

    blocked = [r for r in request_records if r.get("transport_status") != "SUCCESS"]
    truncated = [r for r in request_records if r.get("catalog_result_truncated") is True]
    features = list(unique.values())
    if blocked:
        scientific_status = "UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING"
        transport_status = "PARTIAL_TRANSPORT_BLOCKED" if len(blocked) < len(request_records) else "TRANSPORT_BLOCKED"
    else:
        scientific_status = "PRESENT_CATALOG" if features else "NO_CATALOG_ITEM_IN_QUERY_WINDOW_NOT_IMPUTED"
        transport_status = "SUCCESS"
    result: dict[str, Any] = {
        "collection": collection,
        "query_partition_rule": "EACH_FROZEN_A0_SEASON_IDENTICALLY" if collection in TEMPORAL_COLLECTIONS else "STATIC_SINGLE_QUERY",
        "query_count": len(request_records),
        "successful_query_count": len(request_records) - len(blocked),
        "transport_blocked_query_count": len(blocked),
        "transport_status": transport_status,
        "scientific_data_status": scientific_status,
        "unique_returned_item_count": len(features),
        "any_catalog_page_truncated": bool(truncated),
        "count_semantics": "LOWER_BOUND_IF_ANY_PAGE_TRUNCATED" if truncated else "COMPLETE_RETURN_FOR_FIXED_QUERY_PARTITIONS",
        "query_records": request_records,
    }
    result.update(summarize_items(collection, features))
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="site/data/validation/independent_basin_validation_map.json")
    ap.add_argument("--pool", default="site/data/validation/ibvf_parallel_a0_pool_inventory.json")
    ap.add_argument("--stac-root", default="https://earth-search.aws.element84.com/v1")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    map_path = Path(args.map)
    pool_path = Path(args.pool)
    source = json.loads(map_path.read_text(encoding="utf-8"))
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    for doc in (source, pool):
        assert doc["deployment_status"] == "RESEARCH_ONLY"
        assert doc["test_only"] is True
        assert doc["production_use"] is False
        assert doc["production_ready"] is False
        assert doc["operational_alerting_enabled"] is False
        assert doc["uses_operational_event_none_labels"] is False
        assert doc["territorial_activation_evidence_blinded"] is True
    assert pool["case_control_assignment_allowed"] is False
    assert pool["summary"]["days_removed_for_sensor_missing"] == 0
    assert pool["summary"]["days_removed_for_outcome"] == 0
    seasons = list(pool["seasons"])
    assert len(seasons) == 12

    tracks = list((source.get("parallel_a0_pool_summary") or {}).get("tracks") or [])
    cases_by_unit = {c.get("unit_id"): c for c in source.get("cases", [])}
    site_root = map_path.parents[2]
    session = requests.Session()
    session.headers.update({"User-Agent": "IRFEN-IBVF-RESEARCH-ONLY/0.2"})

    results = []
    for unit_id in tracks:
        case = cases_by_unit.get(unit_id)
        if not case:
            results.append({"unit_id": unit_id, "geometry": {"status": "MAP_CASE_NOT_RESOLVED_NOT_MISSING"}, "collections": []})
            continue
        geom = resolve_geometry(site_root, case)
        collections = []
        if geom.get("bbox"):
            for collection in COLLECTIONS:
                collections.append(query_collection(session, args.stac_root, geom["bbox"], collection, seasons))
        results.append(
            {
                "unit_id": unit_id,
                "case_id": case.get("case_id"),
                "blind_window": case.get("blind_window"),
                "a0_case_control_role": case.get("a0_case_control_role"),
                "geometry": geom,
                "collections": collections,
            }
        )

    all_collections = [x for t in results for x in t.get("collections", [])]
    transport_blocked = sum(1 for x in all_collections if x.get("transport_status") != "SUCCESS")
    present = sum(1 for x in all_collections if x.get("scientific_data_status") == "PRESENT_CATALOG")
    request_count = sum(int(x.get("query_count", 0)) for x in all_collections)
    blocked_request_count = sum(int(x.get("transport_blocked_query_count", 0)) for x in all_collections)
    report = {
        "schema_version": "irfen-ibvf-parallel-a1-stac-preflight-v0.2",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "source_map": str(map_path),
        "source_map_sha256": sha256_bytes(map_path.read_bytes()),
        "source_a0_pool": str(pool_path),
        "source_a0_pool_sha256": sha256_bytes(pool_path.read_bytes()),
        "stac_root": args.stac_root,
        "query_partition_contract": "ALL_TRACKS_USE_IDENTICAL_12_FROZEN_SEASON_QUERIES_FOR_TEMPORAL_COLLECTIONS; COP_DEM_STATIC_SINGLE_QUERY",
        "season_count": len(seasons),
        "season_intervals_utc": [{"season_id": s["season_id"], "datetime": season_utc_interval(s)} for s in seasons],
        "collections": list(COLLECTIONS),
        "blind_window_selection_performed": False,
        "case_control_assignment_performed": False,
        "sensor_availability_deletes_calendar_days": False,
        "territorial_outcome_fields_read": False,
        "transport_failure_is_missing_data": False,
        "tracks": results,
        "summary": {
            "track_count": len(tracks),
            "aggregate_collection_results": len(all_collections),
            "fixed_stac_requests_executed": request_count,
            "catalog_present_aggregate_results": present,
            "transport_blocked_aggregate_results": transport_blocked,
            "transport_blocked_fixed_requests": blocked_request_count,
        },
        "status": "A1_SENSOR_CATALOG_PREFLIGHT_COMPLETE_NO_WINDOW_SELECTED" if transport_blocked == 0 else "A1_SENSOR_CATALOG_PREFLIGHT_PARTIAL_TRANSPORT_BLOCKED_NOT_MISSING",
        "next_gate": "FREEZE_PER_TRACK_A1_SENSOR_RULES_THEN_GENERATE_A3_FEATURES_FOR_THE_FROZEN_CALENDAR_WITHOUT_OUTCOME_FIELDS",
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
