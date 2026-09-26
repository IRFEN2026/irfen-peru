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


def query_url():
    params = {
        "where":"1=1",
        "geometry":",".join(str(x) for x in BBOX),
        "geometryType":"esriGeometryEnvelope",
        "inSR":"4326",
        "spatialRel":"esriSpatialRelIntersects",
        "outFields":"OBJECTID_1,CODIGO_CA,NOMBRE_CA,CATEGORIA,LONG_KM,TIPO_CA,CODIGO_UH,NOMBRE_UH,CODIGO_AAA,NOMBRE_AAA,CODIGO_RH,NOMBRE_RH",
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
        "query_url":query_url(),
        "bbox_wgs84":list(BBOX),
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


def fetch():
    req = Request(query_url(), headers={"User-Agent":"IRFEN-research-ana-hydrography-probe/0.1"})
    with urlopen(req, timeout=60) as r:
        raw = r.read()
    data = json.loads(raw.decode("utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError("ANA response is not a GeoJSON FeatureCollection")
    return data


def candidate_key(feature):
    p = feature.get("properties") or {}
    name = norm(p.get("NOMBRE_CA"))
    for key, needle in TARGETS.items():
        if needle in name:
            return key
    return None


def build(data):
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
    return {
        "schema_version":"0.1",
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
    return {
        "schema_version":"0.1",
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
            "error_class":type(exc).__name__,
            "error_message":str(exc),
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
    unavailable=build_unavailable(TimeoutError("timed out"))
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
        doc=build(fetch())
        exit_code=0
    except (TimeoutError, URLError, OSError) as exc:
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
            "error_class":doc["access"]["error_class"],
            "zero_candidates_inferred":False,
            "output":str(path),
        }
    print(json.dumps(summary,ensure_ascii=False,sort_keys=True))
    return exit_code


if __name__=="__main__":
    raise SystemExit(main())
