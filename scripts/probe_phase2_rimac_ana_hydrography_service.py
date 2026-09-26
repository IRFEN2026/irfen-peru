#!/usr/bin/env python3
"""Bounded live probe of ANA national hydrography for Rímac Phase-2 QA.

RESEARCH_ONLY / TEST_ONLY. The probe may discover candidate official polyline
features and literal line intersections. It MUST NOT adjudicate local-unit
identity, promote an intersection to an official confluence, replace frozen D8
nodes, infer routing/travel time/discharge/capacity, or publish map geometry.

Source access failure is an explicit UNKNOWN state. It is never converted to a
zero-candidate result, a negative hydrologic finding, or permission to relax
any downstream gate.
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
ENDPOINT = "https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0/query"
BBOX = (-76.74, -11.97, -76.67, -11.89)
OUT = ROOT / "artifacts/phase2_rimac_ana_hydrography_probe.json"
TARGETS = {"quirio": "quirio", "pedregal": "pedregal", "rimac": "rimac"}
OUT_FIELDS = "OBJECTID_1,CODIGO_CA,NOMBRE_CA,CATEGORIA,LONG_KM,TIPO_CA,CODIGO_UH,NOMBRE_UH,CODIGO_AAA,NOMBRE_AAA,CODIGO_RH,NOMBRE_RH"
NAME_WHERE = "NOMBRE_CA LIKE '%Quirio%' OR NOMBRE_CA LIKE '%Pedregal%' OR NOMBRE_CA LIKE '%Rimac%' OR NOMBRE_CA LIKE '%Rímac%'"
BATCH_SIZE = 50

class SourceAccessError(Exception):
    def __init__(self, stage, cause):
        super().__init__(f"{stage}: {type(cause).__name__}: {cause}")
        self.stage = stage
        self.cause = cause


def canonical(v: object) -> bytes:
    return (json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def norm(v: object) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def iter_lines(geom: dict):
    if not geom:
        return
    typ = geom.get("type")
    coords = geom.get("coordinates") or []
    if typ == "LineString":
        yield coords
    elif typ == "MultiLineString":
        yield from coords


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def segment_intersection(a, b, c, d, eps=1e-12):
    """Return one exact planar segment intersection point, else None.

    Coordinates are lon/lat and this is used only for source-line topology QA
    over a small local bbox; it is NOT a distance/routing/hydraulic model.
    """
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
            for a,b in zip(l1, l1[1:]):
                for c,d in zip(l2, l2[1:]):
                    p = segment_intersection(a,b,c,d)
                    if p is not None and all(math.isfinite(x) for x in p):
                        if not any(abs(p[0]-q[0])<1e-10 and abs(p[1]-q[1])<1e-10 for q in pts):
                            pts.append(p)
    return pts


def id_query_url():
    params = {
        "where": NAME_WHERE,
        "geometry": ",".join(str(x) for x in BBOX),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnIdsOnly": "true",
        "f": "json",
    }
    return ENDPOINT + "?" + urlencode(params)


def geometry_query_url(object_ids):
    params = {
        "objectIds": ",".join(str(int(x)) for x in sorted(set(object_ids))),
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "geometryPrecision": "7",
        "f": "geojson",
    }
    return ENDPOINT + "?" + urlencode(params)


def query_url():
    """Legacy full-geometry URL retained only for regression compatibility.

    The live fetch path never calls this function; it uses id_query_url()
    followed by geometry_query_url(object_ids).
    """
    params = {
        "where":"1=1",
        "geometry":",".join(str(x) for x in BBOX),
        "geometryType":"esriGeometryEnvelope",
        "inSR":"4326",
        "spatialRel":"esriSpatialRelIntersects",
        "outFields":OUT_FIELDS,
        "returnGeometry":"true",
        "outSR":"4326",
        "geometryPrecision":"7",
        "f":"geojson",
    }
    return ENDPOINT + "?" + urlencode(params)


def source_stub():
    return {
        "institution":"Autoridad Nacional del Agua",
        "service":"ONRH/Rios_Quebradas_AAVI/MapServer/0",
        "service_item_id":"99cc803fb9044523b6ee55f24dcab270",
        "query_strategy":"BOUNDED_TARGET_NAME_ID_ONLY_THEN_OBJECTID_GEOMETRY",
        "id_query_url":id_query_url(),
        "bbox_wgs84":list(BBOX),
        "target_names":["Quirio","Pedregal","Rimac","Rímac"],
    }


def fail_closed_adjudication():
    return {
        "name_match_confirms_local_unit_identity":False,
        "literal_line_intersection_confirms_official_confluence":False,
        "exact_surface_confluence_resolved":False,
        "replace_existing_d8_nodes":False,
        "routing_enabled":False,
        "travel_time_enabled":False,
        "map_publish_enabled":False,
    }


def fetch_json(url, stage, timeout=25):
    req = Request(url, headers={"User-Agent":"IRFEN-research-ana-hydrography-probe/0.2"})
    try:
        with urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except (TimeoutError, URLError, OSError) as exc:
        raise SourceAccessError(stage, exc) from exc
    return json.loads(raw.decode("utf-8"))


def fetch():
    ids_doc = fetch_json(id_query_url(), "id_query")
    object_ids = ids_doc.get("objectIds")
    if object_ids is None:
        raise ValueError("ANA ID-only response has no objectIds field")
    object_ids = sorted({int(x) for x in object_ids})
    features = []
    geometry_urls = []
    geometry_hashes = []
    for i in range(0, len(object_ids), BATCH_SIZE):
        batch = object_ids[i:i+BATCH_SIZE]
        url = geometry_query_url(batch)
        geometry_urls.append(url)
        doc = fetch_json(url, "geometry_query")
        if doc.get("type") != "FeatureCollection":
            raise ValueError("ANA geometry response is not a GeoJSON FeatureCollection")
        features.extend(doc.get("features") or [])
        geometry_hashes.append(hashlib.sha256(canonical(doc)).hexdigest())
    data = {"type":"FeatureCollection","features":features}
    meta = {
        "object_ids": object_ids,
        "object_id_count": len(object_ids),
        "id_payload_sha256": hashlib.sha256(canonical(ids_doc)).hexdigest(),
        "geometry_query_urls": geometry_urls,
        "geometry_payload_sha256": geometry_hashes,
    }
    return data, meta


def candidate_key(feature):
    p = feature.get("properties") or {}
    name = norm(p.get("NOMBRE_CA"))
    for key, needle in TARGETS.items():
        if needle in name:
            return key
    return None


def build(data, access_meta=None):
    features = data.get("features") or []
    groups = {k: [] for k in TARGETS}
    for f in features:
        k = candidate_key(f)
        if k:
            p = dict(f.get("properties") or {})
            groups[k].append({
                "properties":p,
                "geometry":f.get("geometry"),
                "geometry_sha256":hashlib.sha256(canonical(f.get("geometry"))).hexdigest(),
            })
    pairs = []
    for local in ("quirio","pedregal"):
        for li, lf in enumerate(groups[local]):
            for ri, rf in enumerate(groups["rimac"]):
                pts = exact_intersections(lf["geometry"], rf["geometry"])
                if pts:
                    pairs.append({
                        "local_target":local,
                        "local_candidate_index":li,
                        "receiver_candidate_index":ri,
                        "literal_source_line_intersections":pts,
                        "intersection_count":len(pts),
                        "scientific_status":"GEOMETRIC_INTERSECTION_CANDIDATE_NOT_ADJUDICATED_CONFLUENCE",
                    })
    source = source_stub()
    source["source_payload_sha256"] = hashlib.sha256(canonical(data)).hexdigest()
    if access_meta:
        source["two_stage_access"] = access_meta
    return {
        "schema_version":"0.2",
        "status":"RESEARCH_ONLY_LIVE_VECTOR_PROBE",
        "deployment_status":"RESEARCH_ONLY",
        "test_mode":"TEST_ONLY",
        "production_use":False,
        "production_ready":False,
        "operational_alerting_enabled":False,
        "activation_gate":"BLOCKED",
        "query_completed":True,
        "source":source,
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "candidate_counts":{k:len(v) for k,v in groups.items()},
        "candidates":groups,
        "literal_intersection_candidates":pairs,
        "adjudication":fail_closed_adjudication(),
        "forbidden":[
            "promote a name match to local-unit identity without independent QA",
            "promote a literal source-line intersection to official confluence without identity/topology adjudication",
            "replace frozen D8 nodes automatically",
            "infer routing, discharge, travel time, attenuation, capacity, risk or receiver overflow",
            "publish probe geometry to the IRFEN map automatically",
            "treat source access failure as zero candidates or hydrologic absence",
        ],
    }


def build_unavailable(exc):
    source = source_stub()
    cause = getattr(exc, "cause", exc)
    stage = getattr(exc, "stage", "unknown")
    return {
        "schema_version":"0.2",
        "status":"SOURCE_ACCESS_UNAVAILABLE",
        "deployment_status":"RESEARCH_ONLY",
        "test_mode":"TEST_ONLY",
        "production_use":False,
        "production_ready":False,
        "operational_alerting_enabled":False,
        "activation_gate":"BLOCKED",
        "query_completed":False,
        "source":source,
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "candidate_counts":{k:None for k in TARGETS},
        "candidates":None,
        "literal_intersection_candidates":None,
        "access":{
            "stage":stage,
            "error_class":type(cause).__name__,
            "error_message":str(cause),
            "zero_candidates_inferred":False,
            "hydrologic_absence_inferred":False,
        },
        "adjudication":fail_closed_adjudication(),
        "forbidden":[
            "treat source access failure as zero candidates",
            "treat source access failure as evidence a named channel does not exist",
            "replace frozen D8 nodes automatically",
            "infer routing, discharge, travel time, attenuation, capacity, risk or receiver overflow",
            "publish geometry to the IRFEN map from an unavailable-source state",
        ],
    }


def self_test():
    a={"type":"LineString","coordinates":[[0,0],[2,2]]}
    b={"type":"LineString","coordinates":[[0,2],[2,0]]}
    c={"type":"LineString","coordinates":[[3,3],[4,4]]}
    assert exact_intersections(a,b)==[[1.0,1.0]]
    assert exact_intersections(a,c)==[]
    unavailable=build_unavailable(SourceAccessError("id_query", TimeoutError("timed out")))
    assert unavailable["query_completed"] is False
    assert all(v is None for v in unavailable["candidate_counts"].values())
    print("self-test ok")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--output",default=str(OUT))
    args=ap.parse_args()
    if args.self_test:
        self_test(); return 0

    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        data, meta = fetch()
        doc=build(data, meta)
        exit_code=0
    except SourceAccessError as exc:
        doc=build_unavailable(exc)
        exit_code=2

    path.write_bytes(canonical(doc))
    if doc["query_completed"]:
        summary={
            "status":doc["status"],
            "candidate_counts":doc["candidate_counts"],
            "literal_intersection_candidate_count":len(doc["literal_intersection_candidates"]),
            "exact_surface_confluence_resolved":False,
            "output":str(path),
        }
    else:
        summary={
            "status":doc["status"],
            "query_completed":False,
            "access_stage":doc["access"]["stage"],
            "error_class":doc["access"]["error_class"],
            "zero_candidates_inferred":False,
            "output":str(path),
        }
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    return exit_code


if __name__=="__main__":
    raise SystemExit(main())
