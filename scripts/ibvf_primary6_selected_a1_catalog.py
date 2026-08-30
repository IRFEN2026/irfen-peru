#!/usr/bin/env python3
"""Freeze A1 catalog evidence for already-selected PRIMARY6 blind windows.

No outcome/event evidence is read. Selected windows are never replaced because a
sensor is missing. Sentinel-1 pair choice follows the sensor rules frozen before
ranking. Landsat pair choice remains pending until AOI QA_PIXEL is measured.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json
from pathlib import Path
from typing import Any, Iterable
import requests

UTC=dt.timezone.utc
PERU=dt.timezone(dt.timedelta(hours=-5))

def bsha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def csha(x:Any)->str:return bsha(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())
def load(p:Path)->dict[str,Any]:return json.loads(p.read_text(encoding="utf-8"))
def guards(d:dict[str,Any])->None:
    assert d["deployment_status"]=="RESEARCH_ONLY" and d.get("test_only") is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False and d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"
def iter_xy(n:Any)->Iterable[tuple[float,float]]:
    if isinstance(n,(list,tuple)):
        if len(n)>=2 and isinstance(n[0],(int,float)) and isinstance(n[1],(int,float)):yield float(n[0]),float(n[1])
        else:
            for x in n:yield from iter_xy(x)
def resolve_geometry(site_root:Path,case:dict[str,Any])->dict[str,Any]:
    rel=case.get("geometry_path");sel=case.get("geometry_selector") or {}
    if not rel:return {"status":"GEOMETRY_PATH_UNKNOWN","bbox":None}
    p=site_root/rel
    if not p.exists():return {"status":"GEOMETRY_FILE_BLOCKED_NOT_MISSING","bbox":None,"path":rel}
    d=load(p); feats=d.get("features",[]) if d.get("type")=="FeatureCollection" else [d]
    prop,val=sel.get("property"),sel.get("value")
    m=[f for f in feats if prop is None or (f.get("properties") or {}).get(prop)==val]
    xy=[z for f in m for z in iter_xy((f.get("geometry") or {}).get("coordinates"))]
    if len(m)!=1 or not xy:return {"status":"GEOMETRY_NOT_UNIQUE_OR_EMPTY","bbox":None,"matched_feature_count":len(m),"path":rel,"selector":sel}
    xs=[x for x,_ in xy];ys=[y for _,y in xy]
    return {"status":"PASS_UNIQUE_FROZEN_OR_EXPLICIT_CANDIDATE_GEOMETRY","path":rel,"selector":sel,"feature_sha256":csha(m[0]),"bbox":[min(xs),min(ys),max(xs),max(ys)]}
def parse_z(s:str)->dt.datetime:return dt.datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(UTC)
def interval(anchor:str,before:int,after:int)->str:
    d=dt.date.fromisoformat(anchor);a=d+dt.timedelta(days=before);b=d+dt.timedelta(days=after+1)
    # local 00:00 Peru -> UTC 05:00; end is next local midnight minus one second
    start=dt.datetime.combine(a,dt.time(0),PERU).astimezone(UTC)
    end=dt.datetime.combine(b,dt.time(0),PERU).astimezone(UTC)-dt.timedelta(seconds=1)
    return f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
def query(sess:requests.Session,root:str,collection:str,bbox:list[float],window:str|None)->dict[str,Any]:
    payload={"collections":[collection],"bbox":bbox,"limit":1000}
    if window:payload["datetime"]=window
    base={"request_payload":payload,"request_payload_sha256":csha(payload)}
    try:r=sess.post(root.rstrip('/')+"/search",json=payload,timeout=90)
    except requests.RequestException as e:return {**base,"transport_status":"TRANSPORT_BLOCKED","error_class":type(e).__name__,"items":[]}
    raw=r.content;out={**base,"http_status":r.status_code,"raw_response_sha256":bsha(raw),"raw_response_bytes":len(raw)}
    if r.status_code!=200:return {**out,"transport_status":"TRANSPORT_BLOCKED_HTTP","items":[]}
    try:d=r.json()
    except ValueError:return {**out,"transport_status":"TRANSPORT_BLOCKED_INVALID_JSON","items":[]}
    feats=d.get("features") or [];trunc=any(isinstance(x,dict) and x.get("rel")=="next" for x in d.get("links") or [])
    return {**out,"transport_status":"SUCCESS","catalog_truncated":trunc,"returned_item_count":len(feats),"items":feats}
def min_item(f:dict[str,Any],collection:str)->dict[str,Any]:
    p=f.get("properties") or {};a=f.get("assets") or {}
    out={"id":f.get("id"),"datetime":p.get("datetime"),"asset_keys":sorted(a)}
    if collection=="sentinel-1-grd":
        out.update({"platform":p.get("platform"),"instrument_mode":p.get("sar:instrument_mode"),"orbit_state":p.get("sat:orbit_state"),"relative_orbit":p.get("sat:relative_orbit"),"polarizations":p.get("sar:polarizations") or [],"vv_href":(a.get("vv") or {}).get("href")})
    else:
        out.update({"platform":p.get("platform"),"wrs_path":p.get("landsat:wrs_path"),"wrs_row":p.get("landsat:wrs_row"),"qa_pixel_href":(a.get("qa_pixel") or {}).get("href"),"red_href":(a.get("red") or {}).get("href"),"nir08_href":(a.get("nir08") or {}).get("href")})
    return out
def s1_compat(a:dict[str,Any],b:dict[str,Any])->bool:
    return all(a.get(k)==b.get(k) and a.get(k) is not None for k in ("platform","instrument_mode","orbit_state","relative_orbit")) and "VV" in a.get("polarizations",[]) and "VV" in b.get("polarizations",[])
def choose_s1(pre:list[dict[str,Any]],post:list[dict[str,Any]],anchor:str)->dict[str,Any]|None:
    ad=dt.datetime.combine(dt.date.fromisoformat(anchor),dt.time(0),PERU).astimezone(UTC);pairs=[]
    for a in pre:
      for b in post:
        if not s1_compat(a,b) or not a.get("datetime") or not b.get("datetime"):continue
        ap,bp=parse_z(a["datetime"]),parse_z(b["datetime"]);da=abs((ad-ap).total_seconds());db=abs((bp-ad).total_seconds())
        pairs.append(((da+db,max(da,db),a["datetime"],b["datetime"],str(a["id"])+str(b["id"])),a,b))
    if not pairs:return None
    _,a,b=min(pairs,key=lambda x:x[0]);return {"pre_item_id":a["id"],"post_item_id":b["id"],"pre_datetime":a["datetime"],"post_datetime":b["datetime"],"platform":a["platform"],"instrument_mode":a["instrument_mode"],"orbit_state":a["orbit_state"],"relative_orbit":a["relative_orbit"]}
def ls_compatible_pairs(pre:list[dict[str,Any]],post:list[dict[str,Any]])->list[dict[str,Any]]:
    out=[]
    for a in pre:
      for b in post:
        if all(a.get(k)==b.get(k) and a.get(k) is not None for k in ("platform","wrs_path","wrs_row")):
          out.append({"pre_item_id":a["id"],"post_item_id":b["id"],"platform":a["platform"],"wrs_path":a["wrs_path"],"wrs_row":a["wrs_row"]})
    return sorted(out,key=lambda x:(str(x["pre_item_id"]),str(x["post_item_id"])))

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",type=Path,default=Path('.'));ap.add_argument("--ranking",default="site/data/validation/ibvf_primary6_meteorological_ranking.json");ap.add_argument("--contract",default="site/data/validation/ibvf_primary6_selected_a1_contract.json");ap.add_argument("--rules",default="site/data/validation/ibvf_parallel_a1_sensor_rules.json");ap.add_argument("--map",default="site/data/validation/independent_basin_validation_map.json");ap.add_argument("--stac-root",default="https://earth-search.aws.element84.com/v1");ap.add_argument("--output",required=True);args=ap.parse_args();root=args.repo_root.resolve()
    ranking=load(root/args.ranking);contract=load(root/args.contract);rules=load(root/args.rules);m=load(root/args.map)
    for d in (ranking,contract,rules,m):guards(d)
    assert ranking["cohort_id"]=="PRIMARY6_CHRONOLOGICAL" and ranking["case_control_assignment_performed"] is False and ranking["modeling_allowed"] is False
    assert ranking["status"]=="PRIMARY6_BLIND_METEOROLOGICAL_RANKING_EXECUTED_NO_OUTCOME_NO_CASE_CONTROL_NO_MODELING"
    assert rules["execution_status"]=="PREREGISTERED_BEFORE_PARALLEL_METEOROLOGICAL_RANKING_EXECUTION"
    selected=[r for r in ranking["rows"] if r.get("selected") is True]
    if any(r.get("case_control_role")!="UNASSIGNED" for r in selected):raise SystemExit("FAIL_CLOSED_SELECTED_ROLE_NOT_UNASSIGNED")
    keys=[(r["unit_id"],r["season_id"],r["date_local"],r["selected_target_order"]) for r in selected]
    if len(keys)!=len(set(keys)):raise SystemExit("FAIL_CLOSED_DUPLICATE_SELECTED_IDENTITY")
    if any(r["unit_id"]=="pedregal" for r in selected):raise SystemExit("FAIL_CLOSED_PEDREGAL_SELECTED_WHILE_GEOMETRY_UNRESOLVED")
    cases={c.get("unit_id"):c for c in m.get("cases",[])};site_root=(root/args.map).parents[2]
    geoms={u:resolve_geometry(site_root,cases[u]) for u in sorted({r["unit_id"] for r in selected})}
    if any(g.get("bbox") is None for g in geoms.values()):raise SystemExit("FAIL_CLOSED_SELECTED_TRACK_GEOMETRY_UNRESOLVED")
    sess=requests.Session();sess.headers.update({"User-Agent":"IRFEN-IBVF-RESEARCH-ONLY/PRIMARY6-A1"})
    records=[];request_count=0;blocked=0;truncated=0;s1_yes=0;s1_missing=0;s1_unknown=0;ls_pending=0;ls_missing=0;ls_unknown=0
    for r in sorted(selected,key=lambda x:(x["unit_id"],x["season_id"],x["date_local"],x["selected_target_order"])):
      bbox=geoms[r["unit_id"]]["bbox"];D=r["date_local"]
      s1pre=query(sess,args.stac_root,"sentinel-1-grd",bbox,interval(D,-36,-1));s1post=query(sess,args.stac_root,"sentinel-1-grd",bbox,interval(D,1,36));lspre=query(sess,args.stac_root,"landsat-c2-l2",bbox,interval(D,-48,-1));lspost=query(sess,args.stac_root,"landsat-c2-l2",bbox,interval(D,1,48));request_count+=4
      qs=[s1pre,s1post,lspre,lspost];blocked+=sum(q.get("transport_status")!="SUCCESS" for q in qs);truncated+=sum(q.get("catalog_truncated") is True for q in qs)
      s1_complete=all(q.get("transport_status")=="SUCCESS" and not q.get("catalog_truncated") for q in (s1pre,s1post));sp=[min_item(x,"sentinel-1-grd") for x in s1pre.pop("items")];so=[min_item(x,"sentinel-1-grd") for x in s1post.pop("items")];pair=choose_s1(sp,so,D) if s1_complete else None
      if not s1_complete:s1status="UNKNOWN_CATALOG_INCOMPLETE_OR_TRANSPORT_BLOCKED";s1_unknown+=1
      elif pair:s1status="COMPATIBLE_BRACKETING_PAIR_SELECTED_BY_FROZEN_RULE";s1_yes+=1
      else:s1status="MISSING_COMPATIBLE_BRACKETING_PAIR_COMPLETE_FIXED_QUERY";s1_missing+=1
      ls_complete=all(q.get("transport_status")=="SUCCESS" and not q.get("catalog_truncated") for q in (lspre,lspost));lp=[min_item(x,"landsat-c2-l2") for x in lspre.pop("items")];lo=[min_item(x,"landsat-c2-l2") for x in lspost.pop("items")];lspairs=ls_compatible_pairs(lp,lo) if ls_complete else []
      if not ls_complete:lsstatus="UNKNOWN_CATALOG_INCOMPLETE_OR_TRANSPORT_BLOCKED";ls_unknown+=1
      elif lspairs:lsstatus="COMPATIBLE_CANDIDATES_FROZEN_PAIR_CHOICE_PENDING_AOI_QA";ls_pending+=1
      else:lsstatus="MISSING_COMPATIBLE_BRACKETING_PAIR_COMPLETE_FIXED_QUERY";ls_missing+=1
      records.append({"unit_id":r["unit_id"],"season_id":r["season_id"],"date_local":D,"selected_target_order":r["selected_target_order"],"selected_target_percentile":r["selected_target_percentile"],"case_control_role":"UNASSIGNED",
        "sentinel1":{"status":s1status,"pre_query":s1pre,"post_query":s1post,"pre_candidates":sp,"post_candidates":so,"selected_pair":pair},
        "landsat":{"status":lsstatus,"pre_query":lspre,"post_query":lspost,"pre_candidates":lp,"post_candidates":lo,"compatible_pair_identities":lspairs,"pair_choice_performed":False,"next_gate":"AOI_QA_PIXEL_STRICT_CLEAR_FOR_EVERY_COMPATIBLE_CANDIDATE"}})
    dem=[]
    for u,g in geoms.items():
      q=query(sess,args.stac_root,"cop-dem-glo-30",g["bbox"],None);request_count+=1;blocked+=q.get("transport_status")!="SUCCESS";truncated+=q.get("catalog_truncated") is True;items=[{"id":x.get("id"),"asset_keys":sorted((x.get("assets") or {}).keys()),"data_href":((x.get("assets") or {}).get("data") or {}).get("href")} for x in q.pop("items")]
      dem.append({"unit_id":u,"geometry_sha256":g["feature_sha256"],"query":q,"items":items,"status":"CATALOG_FROZEN_A2_BYTE_HASH_PENDING" if q.get("transport_status")=="SUCCESS" and not q.get("catalog_truncated") and items else "UNKNOWN_OR_MISSING_CATALOG_NO_A2_INFERENCE"})
    summary={"selected_window_count":len(selected),"selected_track_count":len(geoms),"fixed_stac_request_count":request_count,"transport_blocked_request_count":blocked,"truncated_request_count":truncated,"sentinel1_pair_selected_count":s1_yes,"sentinel1_missing_compatible_pair_count":s1_missing,"sentinel1_unknown_count":s1_unknown,"landsat_compatible_candidates_pending_aoi_qa_count":ls_pending,"landsat_missing_compatible_pair_count":ls_missing,"landsat_unknown_count":ls_unknown,"pedregal_selected_count":0}
    report={"schema_version":"irfen-ibvf-primary6-selected-a1-catalog-v0.1","generated_at":dt.datetime.now(UTC).isoformat(),"framework":"IRFEN Independent Basin Validation Framework","deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED","cohort_id":"PRIMARY6_CHRONOLOGICAL","source_ranking_sha256":bsha((root/args.ranking).read_bytes()),"source_contract_sha256":bsha((root/args.contract).read_bytes()),"source_sensor_rules_sha256":bsha((root/args.rules).read_bytes()),"selected_window_identity_sha256":csha(keys),"case_control_assignment_performed":False,"territorial_outcome_fields_read":False,"known_event_dates_read":False,"selected_windows_replaced_for_sensor_availability":False,"activation_inference_allowed":False,"modeling_allowed":False,"geometries":geoms,"windows":records,"cop_dem_catalog":dem,"summary":summary,"status":"PASS_SELECTED_PRIMARY6_A1_CATALOG_FREEZE_NO_OUTCOME_NO_REPLACEMENT" if blocked==0 and truncated==0 else "PARTIAL_SELECTED_PRIMARY6_A1_CATALOG_UNKNOWN_TRANSPORT_OR_TRUNCATION_RETAINED","next_gate":"LANDSAT_AOI_QA_AND_RAW_ASSET_BYTE_FREEZE_FOR_SELECTED_WINDOWS; RETAIN EVERY SELECTED WINDOW"}
    guards(report);out=root/args.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");print(json.dumps(summary,indent=2));print(report["status"]);return 0
if __name__=="__main__":raise SystemExit(main())
