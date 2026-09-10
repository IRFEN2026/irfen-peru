#!/usr/bin/env python3
"""Query fixed candidate-only Sentinel-1 metadata windows without reading pixel data or outcomes."""
from __future__ import annotations
import argparse, hashlib, json, re, urllib.parse
from pathlib import Path
import requests
from shapely.geometry import shape

FORBIDDEN = ("a6680","official_outcome_evidence","pedregal","quirio","carossio","carosio","rayos de sol","cashahuacra","la libertad")
CODE_RE = re.compile(r"^C_[0-9a-f]{12}$")

def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def sha_file(p: Path) -> str: return sha_bytes(p.read_bytes())
def pick(props, *keys):
    for k in keys:
        if k in props and props[k] not in (None, ""): return props[k]
    return None

def norm_scene(feature: dict, response_sha: str) -> dict:
    p=feature.get("properties") or {}
    geom=feature.get("geometry")
    center=None
    if geom:
        c=shape(geom).centroid; center=[round(float(c.x),6),round(float(c.y),6)]
    return {
        "granule_name": pick(p,"sceneName","granuleName","fileID","productName","name"),
        "start_time": pick(p,"startTime","start","start_time"),
        "stop_time": pick(p,"stopTime","stop","endTime","stop_time"),
        "relative_orbit": pick(p,"relativeOrbit","pathNumber","relativeOrbitNumber"),
        "path_number": pick(p,"pathNumber","path"),
        "frame_number": pick(p,"frameNumber","frame"),
        "flight_direction": pick(p,"flightDirection","flight_direction"),
        "polarization": pick(p,"polarization","polarizationMode"),
        "beam_mode": pick(p,"beamMode","beam_mode"),
        "processing_level": pick(p,"processingLevel","processing_level"),
        "scene_center_lon": center[0] if center else None,
        "scene_center_lat": center[1] if center else None,
        "metadata_response_sha256": response_sha
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--contract",type=Path,required=True); ap.add_argument("--geometry",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); co=json.loads(a.contract.read_text()); raw=a.geometry.read_bytes()
    if sha_bytes(raw)!=co["candidate_geometry"]["sha256"]: raise SystemExit("FAIL_CLOSED_GEOMETRY_HASH")
    low=raw.lower()
    if any(x.encode() in low for x in FORBIDDEN): raise SystemExit("FAIL_CLOSED_REVEALING_GEOMETRY_CONTENT")
    gj=json.loads(raw); feats=gj.get("features",[])
    if len(feats)!=co["candidate_geometry"]["candidate_count"]: raise SystemExit("FAIL_CLOSED_CANDIDATE_COUNT")
    endpoint=co["source"]["search_endpoint"]
    u=urllib.parse.urlparse(endpoint)
    if u.scheme!="https" or u.hostname!=co["source"]["endpoint_host"]: raise SystemExit("FAIL_CLOSED_ENDPOINT")
    session=requests.Session(); session.headers.update({"User-Agent":"IRFEN-research-cleanroom/0.1"})
    windows=co["fixed_windows"]; rows=[]
    for f in sorted(feats,key=lambda z:str((z.get("properties") or {}).get("candidate_code",""))):
        props=f.get("properties") or {}; code=props.get("candidate_code")
        if not isinstance(code,str) or CODE_RE.fullmatch(code) is None: raise SystemExit("FAIL_CLOSED_CANDIDATE_CODE")
        wkt=shape(f["geometry"]).wkt
        cand={"candidate_code":code,"windows":{}}
        for wn in ("pre","post"):
            w=windows[wn]
            params={"platform":co["query"]["platform"],"beamMode":co["query"]["beam_mode"],"processingLevel":co["query"]["processing_level"],"intersectsWith":wkt,"start":w["start"],"end":w["end"],"output":co["query"]["output"],"maxResults":str(co["query"]["max_results_per_candidate_window"])}
            r=session.get(endpoint,params=params,timeout=(20,120),allow_redirects=False)
            if r.is_redirect or r.is_permanent_redirect: raise SystemExit("FAIL_CLOSED_REDIRECT")
            if r.status_code!=200: raise SystemExit(f"FAIL_CLOSED_HTTP_{r.status_code}")
            rb=r.content; digest=sha_bytes(rb)
            try: doc=r.json()
            except Exception: raise SystemExit("FAIL_CLOSED_NON_JSON")
            if doc.get("type")!="FeatureCollection" or not isinstance(doc.get("features"),list): raise SystemExit("FAIL_CLOSED_NON_GEOJSON")
            scenes=[norm_scene(x,digest) for x in doc["features"]]
            scenes.sort(key=lambda x:(str(x.get("start_time") or ""),str(x.get("granule_name") or "")))
            cand["windows"][wn]={"query_response_sha256":digest,"result_count":len(scenes),"scenes":scenes}
        pre=cand["windows"]["pre"]["scenes"]; post=cand["windows"]["post"]["scenes"]
        def sig(s): return (str(s.get("relative_orbit")),str(s.get("flight_direction")),str(s.get("polarization")))
        compatible=sorted({sig(x) for x in pre if x.get("relative_orbit") is not None} & {sig(x) for x in post if x.get("relative_orbit") is not None})
        cand["compatible_metadata_signatures"]=[{"relative_orbit":x[0],"flight_direction":x[1],"polarization":x[2]} for x in compatible]
        cand["same_orbit_bracketing_available"]=bool(compatible); rows.append(cand)
    out={"schema_version":"0.1","batch_id":co["batch_id"],"status":"PASS_CANDIDATE_ONLY_SENTINEL1_AVAILABILITY_FROZEN_INPUTS","guards":co["guards"],"contract_sha256":sha_file(a.contract),"candidate_geometry_sha256":sha_file(a.geometry),"event_anchor_utc":co["event_anchor_utc"],"fixed_windows":windows,"candidate_count":len(rows),"candidates":rows,"pixel_data_downloaded":False,"outcome_evidence_read":False,"target_names_or_ids_read":False,"a6680_read":False,"contaminated_adjudication_used":False,"candidate_selection_modified":False,"candidate_ranking_modified":False,"free_web_search_used":False,"sealed_target_unblind_allowed":False}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n")
    print(json.dumps({"status":out["status"],"candidate_count":len(rows),"with_same_orbit_pairing":sum(x["same_orbit_bracketing_available"] for x in rows)},sort_keys=True))
if __name__=="__main__": main()
