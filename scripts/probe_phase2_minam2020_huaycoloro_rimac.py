#!/usr/bin/env python3
"""Live MINAM Huaycoloro/Rímac vector probe for Phase-2 QA.

RESEARCH_ONLY / TEST_ONLY. This probe can freeze reproducible source payload
hashes and expose geometric candidates. It MUST NOT promote a name match,
OBJECTID match, /find match or literal source-line intersection to hydrologic
identity, an official confluence, routing, travel time, discharge, capacity,
overflow or map publication.

Source access failure remains UNKNOWN. A completed zero-result query is not
hydrologic absence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = (
    "https://geoservidorperu.minam.gob.pe/arcgis/rest/services/"
    "CS/Desarrollo_Urbano/MapServer"
)
LAYER_ID = 10
LAYER_ENDPOINT = f"{SERVICE_ROOT}/{LAYER_ID}"
QUERY_ENDPOINT = LAYER_ENDPOINT + "/query"
FIND_ENDPOINT = SERVICE_ROOT + "/find"

# Independent official MINAM fallback. This nationwide 1:100,000 hydrography
# layer is kept separate from the 2020 Desarrollo_Urbano source so that a
# degraded source cannot be mistaken for hydrologic absence.
SECONDARY_SERVICE_ROOT = (
    "https://geoservidorperu.minam.gob.pe/arcgis/rest/services/"
    "ServicioActivacionQuebrada/MapServer"
)
SECONDARY_LAYER_ID = 36
SECONDARY_LAYER_ENDPOINT = f"{SECONDARY_SERVICE_ROOT}/{SECONDARY_LAYER_ID}"
SECONDARY_FIND_ENDPOINT = SECONDARY_SERVICE_ROOT + "/find"
SECONDARY_QUERY_ENDPOINT = SECONDARY_LAYER_ENDPOINT + "/query"

OUT = ROOT / "artifacts/phase2_minam2020_huaycoloro_rimac_probe.json"
TARGETS = {
    "huaycoloro": ("HUAYCOLORO",),
    "rimac": ("RIMAC", "RÍMAC"),
}
OUT_FIELDS = (
    "OBJECTID,COD_RIO,TIPO,SUBTIPO,NOM_RIO,NOM_UH,LONG_KM,LONG_M,"
    "LABEL_RIO,NOMBDIST,NOMBPROV,NOMBDEP"
)


class SourceAccessError(Exception):
    def __init__(self, message: str, trace=None):
        super().__init__(message)
        self.trace = trace


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(s.split())


def query_url() -> str:
    """Legacy exact-name GeoJSON URL retained for compatibility/tests."""
    names = tuple(name for values in TARGETS.values() for name in values)
    where = " OR ".join(f"NOM_RIO='{name}'" for name in names)
    params = {
        "where": where,
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return QUERY_ENDPOINT + "?" + urlencode(params)


def id_query_url(name: str) -> str:
    params = {
        "where": f"NOM_RIO='{name}'",
        "returnIdsOnly": "true",
        "f": "json",
    }
    return QUERY_ENDPOINT + "?" + urlencode(params)


def find_url(name: str) -> str:
    params = {
        "searchText": name,
        "contains": "false",
        "searchFields": "NOM_RIO",
        "layers": str(LAYER_ID),
        "returnGeometry": "false",
        "f": "json",
    }
    return FIND_ENDPOINT + "?" + urlencode(params)


def geometry_query_url(objectids) -> str:
    params = {
        "objectIds": ",".join(str(int(v)) for v in sorted(set(objectids))),
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return QUERY_ENDPOINT + "?" + urlencode(params)


def secondary_find_url(name: str) -> str:
    params = {
        "searchText": name,
        "contains": "true",
        "searchFields": "r_q_text,nombre,nomb_min",
        "layers": str(SECONDARY_LAYER_ID),
        "returnGeometry": "false",
        "f": "json",
    }
    return SECONDARY_FIND_ENDPOINT + "?" + urlencode(params)


def secondary_geometry_query_url(objectids) -> str:
    params = {
        "objectIds": ",".join(str(int(v)) for v in sorted(set(objectids))),
        "outFields": (
            "OBJECTID_1,nombre,tipo,estado,codigo,zona,text_tramo,aaa,"
            "nivel5,nivel6,nivel7,id,escala,code_rio,tipo_g,r_q_text,"
            "nomb_min,fuente"
        ),
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return SECONDARY_QUERY_ENDPOINT + "?" + urlencode(params)


def _fetch_json(url: str, timeout: int, user_agent: str):
    req = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except (TimeoutError, URLError, OSError) as exc:
        raise SourceAccessError(f"{type(exc).__name__}: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceAccessError(f"{type(exc).__name__}: {exc}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise SourceAccessError(json.dumps(data["error"], ensure_ascii=False, sort_keys=True))
    if not isinstance(data, dict):
        raise SourceAccessError("MINAM response is not a JSON object")
    return raw, data


def _trace_success(trace, method: str, group: str, target: str, url: str, raw: bytes, data: dict):
    trace.append({
        "method": method,
        "group": group,
        "target": target,
        "url": url,
        "status": "SUCCESS",
        "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_payload_sha256": hashlib.sha256(canonical(data)).hexdigest(),
    })


def _trace_error(trace, method: str, group: str, target: str, url: str, exc: Exception):
    trace.append({
        "method": method,
        "group": group,
        "target": target,
        "url": url,
        "status": "SOURCE_ACCESS_UNAVAILABLE",
        "error_class": type(exc).__name__,
        "error_message": str(exc),
    })


def _ids_from_id_query(data: dict):
    ids = data.get("objectIds")
    if ids is None:
        return []
    if not isinstance(ids, list):
        raise SourceAccessError("returnIdsOnly response objectIds is not a list")
    return [int(v) for v in ids]


def _ids_from_find(data: dict, target: str):
    results = data.get("results")
    if results is None:
        return []
    if not isinstance(results, list):
        raise SourceAccessError("/find response results is not a list")
    wanted = norm(target)
    ids = []
    for row in results:
        if not isinstance(row, dict) or int(row.get("layerId", -1)) != LAYER_ID:
            continue
        attrs = row.get("attributes") or {}
        name = norm(attrs.get("NOM_RIO") or row.get("value"))
        if name != wanted:
            continue
        oid = attrs.get("OBJECTID")
        if oid is None:
            oid = row.get("foundFieldName") == "OBJECTID" and row.get("value")
        if oid is not None:
            try:
                ids.append(int(oid))
            except (TypeError, ValueError):
                pass
    return ids


def _secondary_ids_from_find(data: dict, target: str):
    results = data.get("results")
    if results is None:
        return []
    if not isinstance(results, list):
        raise SourceAccessError("secondary /find response results is not a list")
    wanted = norm(target)
    ids = []
    for row in results:
        if not isinstance(row, dict) or int(row.get("layerId", -1)) != SECONDARY_LAYER_ID:
            continue
        attrs = row.get("attributes") or {}
        name = norm(
            attrs.get("r_q_text")
            or attrs.get("nombre")
            or attrs.get("nomb_min")
            or row.get("value")
        )
        # Contains is discovery-only. The candidate remains unadjudicated even
        # when the literal target token is present in the official label.
        if wanted not in name:
            continue
        oid = attrs.get("OBJECTID_1")
        if oid is not None:
            try:
                ids.append(int(oid))
            except (TypeError, ValueError):
                pass
    return ids


def _discover_group_ids(group: str, targets, timeout: int, trace, raw_parts):
    ids = set()
    completed_paths = 0

    for target in targets:
        url = id_query_url(target)
        try:
            raw, data = _fetch_json(url, timeout, "IRFEN-research-minam-huaycoloro-probe/0.2")
            _trace_success(trace, "RETURN_IDS_ONLY", group, target, url, raw, data)
            raw_parts.append(raw)
            ids.update(_ids_from_id_query(data))
            completed_paths += 1
        except SourceAccessError as exc:
            _trace_error(trace, "RETURN_IDS_ONLY", group, target, url, exc)

        url = find_url(target)
        try:
            raw, data = _fetch_json(url, timeout, "IRFEN-research-minam-huaycoloro-probe/0.2")
            _trace_success(trace, "SERVICE_ROOT_FIND", group, target, url, raw, data)
            raw_parts.append(raw)
            ids.update(_ids_from_find(data, target))
            completed_paths += 1
        except SourceAccessError as exc:
            _trace_error(trace, "SERVICE_ROOT_FIND", group, target, url, exc)

    if completed_paths == 0:
        raise SourceAccessError(
            f"Both exact-ID and service-root /find paths unavailable for group {group}",
            trace=trace,
        )
    return sorted(ids)


def _fetch_primary(timeout: int = 30):
    trace = []
    raw_parts = []
    ids_by_group = {}
    for group, targets in TARGETS.items():
        try:
            ids_by_group[group] = _discover_group_ids(group, targets, timeout, trace, raw_parts)
        except SourceAccessError as exc:
            if exc.trace is None:
                exc.trace = trace
            raise

    features = []
    for group, objectids in ids_by_group.items():
        if not objectids:
            continue
        url = geometry_query_url(objectids)
        try:
            raw, data = _fetch_json(url, timeout, "IRFEN-research-minam-huaycoloro-probe/0.2")
        except SourceAccessError as exc:
            _trace_error(trace, "OBJECTID_GEOMETRY", group, "*", url, exc)
            raise SourceAccessError(
                f"Geometry query unavailable for group {group}: {exc}",
                trace=trace,
            ) from exc
        if data.get("type") != "FeatureCollection":
            exc = SourceAccessError("MINAM geometry response is not a GeoJSON FeatureCollection")
            _trace_error(trace, "OBJECTID_GEOMETRY", group, "*", url, exc)
            raise SourceAccessError(str(exc), trace=trace)
        _trace_success(trace, "OBJECTID_GEOMETRY", group, "*", url, raw, data)
        raw_parts.append(raw)
        features.extend(data.get("features") or [])

    synthetic = {"type": "FeatureCollection", "features": features}
    material = b"\n--IRFEN-PAYLOAD--\n".join(raw_parts)
    return material, synthetic, {
        "strategy": "PER_TARGET_RETURN_IDS_ONLY_WITH_INDEPENDENT_SERVICE_ROOT_FIND_FALLBACK_THEN_OBJECTID_GEOMETRY",
        "ids_by_group": ids_by_group,
        "source_payloads": trace,
        "zero_candidates_inferred_as_hydrologic_absence": False,
    }


def _fetch_secondary(timeout: int = 30):
    """Probe independent MINAM 1:100k hydrography without promoting identity."""
    trace = []
    raw_parts = []
    ids_by_group = {}

    for group, targets in TARGETS.items():
        ids = set()
        completed = 0
        for target in targets:
            url = secondary_find_url(target)
            try:
                raw, data = _fetch_json(
                    url,
                    timeout,
                    "IRFEN-research-minam-huaycoloro-probe/0.3-secondary",
                )
                _trace_success(
                    trace,
                    "SECONDARY_SERVICE_FIND",
                    group,
                    target,
                    url,
                    raw,
                    data,
                )
                raw_parts.append(raw)
                ids.update(_secondary_ids_from_find(data, target))
                completed += 1
            except SourceAccessError as exc:
                _trace_error(
                    trace,
                    "SECONDARY_SERVICE_FIND",
                    group,
                    target,
                    url,
                    exc,
                )
        if completed == 0:
            raise SourceAccessError(
                f"Secondary MINAM service unavailable for group {group}",
                trace=trace,
            )
        ids_by_group[group] = sorted(ids)

    features = []
    for group, objectids in ids_by_group.items():
        if not objectids:
            continue
        url = secondary_geometry_query_url(objectids)
        try:
            raw, data = _fetch_json(
                url,
                timeout,
                "IRFEN-research-minam-huaycoloro-probe/0.3-secondary",
            )
        except SourceAccessError as exc:
            _trace_error(
                trace,
                "SECONDARY_OBJECTID_GEOMETRY",
                group,
                "*",
                url,
                exc,
            )
            raise SourceAccessError(
                f"Secondary geometry query unavailable for group {group}: {exc}",
                trace=trace,
            ) from exc
        if data.get("type") != "FeatureCollection":
            exc = SourceAccessError(
                "Secondary MINAM geometry response is not a GeoJSON FeatureCollection"
            )
            _trace_error(
                trace,
                "SECONDARY_OBJECTID_GEOMETRY",
                group,
                "*",
                url,
                exc,
            )
            raise SourceAccessError(str(exc), trace=trace)
        _trace_success(
            trace,
            "SECONDARY_OBJECTID_GEOMETRY",
            group,
            "*",
            url,
            raw,
            data,
        )
        raw_parts.append(raw)

        for feature in data.get("features") or []:
            if not isinstance(feature, dict):
                continue
            props = dict(feature.get("properties") or {})
            source_name = (
                props.get("r_q_text")
                or props.get("nombre")
                or props.get("nomb_min")
                or ""
            )
            normalized = dict(props)
            normalized["NOM_RIO"] = source_name
            normalized["OBJECTID"] = props.get("OBJECTID_1")
            features.append({
                "type": "Feature",
                "properties": normalized,
                "geometry": feature.get("geometry"),
            })

    synthetic = {"type": "FeatureCollection", "features": features}
    material = b"\n--IRFEN-PAYLOAD--\n".join(raw_parts)
    return material, synthetic, {
        "strategy": "INDEPENDENT_MINAM_100K_FIND_THEN_OBJECTID_GEOMETRY",
        "layer": "ServicioActivacionQuebrada/MapServer/36",
        "source_role": "INDEPENDENT_OFFICIAL_HYDROGRAPHY_QA_FALLBACK",
        "ids_by_group": ids_by_group,
        "source_payloads": trace,
        "zero_candidates_inferred_as_hydrologic_absence": False,
    }


def fetch(timeout: int = 30):
    """Use the 2020 source first, then independent MINAM hydrography if needed."""
    try:
        primary = _fetch_primary(timeout)
    except SourceAccessError as primary_exc:
        try:
            return _fetch_secondary(timeout)
        except SourceAccessError as secondary_exc:
            combined = list(getattr(primary_exc, "trace", None) or [])
            combined.extend(list(getattr(secondary_exc, "trace", None) or []))
            raise SourceAccessError(
                "Primary and independent secondary MINAM vector sources unavailable",
                trace=combined,
            ) from secondary_exc

    raw, data, source_trace = primary
    ids_by_group = source_trace.get("ids_by_group") or {}
    if all(ids_by_group.get(group) for group in TARGETS):
        return primary

    # A completed zero/partial result is not absence. Probe a second official
    # source for corroboration, but preserve the primary result if that source
    # is also unavailable.
    try:
        return _fetch_secondary(timeout)
    except SourceAccessError as secondary_exc:
        source_trace["secondary_fallback"] = {
            "status": "SOURCE_ACCESS_UNAVAILABLE",
            "source_payloads": getattr(secondary_exc, "trace", None),
            "zero_candidates_inferred_as_hydrologic_absence": False,
        }
        return raw, data, source_trace


def iter_lines(geometry: dict):
    if not geometry:
        return
    typ = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if typ == "LineString":
        yield coords
    elif typ == "MultiLineString":
        yield from coords


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def segment_intersection(a, b, c, d, eps=1e-12):
    ax, ay = map(float, a); bx, by = map(float, b)
    cx, cy = map(float, c); dx, dy = map(float, d)
    rx, ry = bx-ax, by-ay
    sx, sy = dx-cx, dy-cy
    den = _cross(rx, ry, sx, sy)
    qpx, qpy = cx-ax, cy-ay
    if abs(den) <= eps:
        return None
    t = _cross(qpx, qpy, sx, sy) / den
    u = _cross(qpx, qpy, rx, ry) / den
    if -eps <= t <= 1+eps and -eps <= u <= 1+eps:
        return [ax+t*rx, ay+t*ry]
    return None


def exact_intersections(g1: dict, g2: dict):
    pts = []
    for l1 in iter_lines(g1) or []:
        for l2 in iter_lines(g2) or []:
            for a, b in zip(l1, l1[1:]):
                for c, d in zip(l2, l2[1:]):
                    p = segment_intersection(a, b, c, d)
                    if p is not None and all(math.isfinite(x) for x in p):
                        if not any(abs(p[0]-q[0]) < 1e-10 and abs(p[1]-q[1]) < 1e-10 for q in pts):
                            pts.append(p)
    return pts


def fail_closed_guards():
    return {
        "name_match_confirms_local_identity": False,
        "objectid_match_confirms_local_identity": False,
        "find_match_confirms_local_identity": False,
        "literal_line_intersection_confirms_official_confluence": False,
        "exact_huaycoloro_rimac_confluence_resolved": False,
        "routing_enabled": False,
        "travel_time_enabled": False,
        "flow_or_capacity_inference_enabled": False,
        "overflow_inference_enabled": False,
        "map_publish_enabled": False,
        "zero_query_result_may_be_inferred_as_hydrologic_absence": False,
    }


def build(raw: bytes, data: dict, source_trace=None):
    groups = {"huaycoloro": [], "rimac": []}
    for feature in data.get("features") or []:
        props = dict(feature.get("properties") or {})
        name = norm(props.get("NOM_RIO"))
        key = "huaycoloro" if name == "HUAYCOLORO" else ("rimac" if name == "RIMAC" else None)
        if key is None:
            continue
        geom = feature.get("geometry")
        groups[key].append({
            "objectid": props.get("OBJECTID"),
            "properties": props,
            "geometry": geom,
            "geometry_sha256": hashlib.sha256(canonical(geom)).hexdigest(),
        })

    intersections = []
    for hi, hf in enumerate(groups["huaycoloro"]):
        for ri, rf in enumerate(groups["rimac"]):
            pts = exact_intersections(hf["geometry"], rf["geometry"])
            if pts:
                intersections.append({
                    "huaycoloro_candidate_index": hi,
                    "rimac_candidate_index": ri,
                    "intersection_count": len(pts),
                    "literal_source_line_intersections": pts,
                    "scientific_status": "GEOMETRIC_INTERSECTION_CANDIDATE_NOT_ADJUDICATED_CONFLUENCE",
                })

    objectids = sorted({
        int(row["objectid"])
        for rows in groups.values()
        for row in rows
        if row["objectid"] is not None
    })

    source = {
        "institution": "Ministerio del Ambiente",
        "platform": "Geoservidor",
        "layer": "CS/Desarrollo_Urbano/MapServer/10",
        "attribution": "IMP/ANA",
        "source_year": 2020,
        "query_format": "json IDs + geoJSON geometry",
        "requested_out_sr": 4326,
        "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_payload_sha256": hashlib.sha256(canonical(data)).hexdigest(),
    }
    if source_trace:
        source.update(source_trace)

    return {
        "schema_version": "0.2",
        "status": "RESEARCH_ONLY_LIVE_VECTOR_PROBE",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "query_completed": True,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "candidate_counts": {k: len(v) for k, v in groups.items()},
        "matching_objectids": objectids,
        "matching_feature_count": sum(len(v) for v in groups.values()),
        "candidates": groups,
        "literal_intersection_candidates": intersections,
        "guards": fail_closed_guards(),
    }


def build_unavailable(exc: Exception):
    trace = getattr(exc, "trace", None)
    return {
        "schema_version": "0.2",
        "status": "SOURCE_ACCESS_UNAVAILABLE",
        "deployment_status": "RESEARCH_ONLY",
        "test_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "activation_gate": "BLOCKED",
        "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds": None,
        "hydraulic_factors": None,
        "query_completed": False,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "institution": "Ministerio del Ambiente",
            "platform": "Geoservidor",
            "layer": "CS/Desarrollo_Urbano/MapServer/10 + ServicioActivacionQuebrada/MapServer/36 fallback",
            "strategy": "PRIMARY_2020_SOURCE_THEN_INDEPENDENT_MINAM_100K_FALLBACK",
            "source_payloads": trace,
        },
        "candidate_counts": {"huaycoloro": None, "rimac": None},
        "matching_objectids": None,
        "matching_feature_count": None,
        "candidates": None,
        "literal_intersection_candidates": None,
        "access": {
            "error_class": type(exc).__name__,
            "error_message": str(exc),
            "zero_candidates_inferred": False,
            "hydrologic_absence_inferred": False,
        },
        "guards": fail_closed_guards(),
    }


def self_test():
    url = query_url()
    assert "returnGeometry=true" in url
    assert "outSR=4326" in url
    assert "NOM_RIO%3D%27HUAYCOLORO%27" in url
    assert "returnIdsOnly=true" in id_query_url("HUAYCOLORO")
    assert "searchFields=NOM_RIO" in find_url("HUAYCOLORO")
    assert "layers=10" in find_url("HUAYCOLORO")
    assert "returnGeometry=false" in find_url("HUAYCOLORO")
    assert "objectIds=1%2C2" in geometry_query_url([2, 1])
    assert "layers=36" in secondary_find_url("HUAYCOLORO")
    assert "searchFields=r_q_text%2Cnombre%2Cnomb_min" in secondary_find_url("HUAYCOLORO")
    assert "returnGeometry=false" in secondary_find_url("HUAYCOLORO")
    assert "objectIds=1%2C2" in secondary_geometry_query_url([2, 1])
    a = {"type":"LineString","coordinates":[[0,0],[2,2]]}
    b = {"type":"LineString","coordinates":[[0,2],[2,0]]}
    assert exact_intersections(a,b) == [[1.0,1.0]]
    d = build_unavailable(SourceAccessError("timeout"))
    assert d["query_completed"] is False
    assert d["candidate_counts"] == {"huaycoloro": None, "rimac": None}
    assert d["guards"]["zero_query_result_may_be_inferred_as_hydrologic_absence"] is False
    assert d["access"]["hydrologic_absence_inferred"] is False
    print("self-test ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw, data, source_trace = fetch()
        doc = build(raw, data, source_trace)
        code = 0
    except SourceAccessError as exc:
        doc = build_unavailable(exc)
        code = 2
    path.write_bytes(canonical(doc))
    print(json.dumps({
        "status": doc["status"],
        "query_completed": doc["query_completed"],
        "candidate_counts": doc["candidate_counts"],
        "matching_feature_count": doc["matching_feature_count"],
        "intersection_candidate_count": None if doc["literal_intersection_candidates"] is None else len(doc["literal_intersection_candidates"]),
        "output": str(path),
    }, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
