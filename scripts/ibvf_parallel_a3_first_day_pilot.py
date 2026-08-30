#!/usr/bin/env python3
"""First-day end-to-end A3 pilot for the frozen parallel blind pool.

RESEARCH_ONLY / TEST_ONLY. The target is fixed by contract as the chronologically
first A0 day (2014-09-01 America/Lima), never by rainfall, sensor availability,
known event date, or territorial outcome. Pedregal alternatives are weighted
separately; no candidate union or candidate choice is permitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time as time_mod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ibvf_parallel_a3_opendap_preflight as base  # noqa: E402
import ibvf_parallel_a3_opendap_earthdata_adapter  # noqa: F401,E402  patches resolver

TRACKS = ("shingolay", "pedregal", "huaycoloro", "san_ildefonso")
UA = "IRFEN-IBVF-A3-FIRST-DAY/0.1 RESEARCH_ONLY TEST_ONLY"
INDEX_RE = re.compile(r"\[\s*(-?\d+)\s*\]")
FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_sha(obj: Any) -> str:
    return sha256_text(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def guard(d: dict[str, Any]) -> None:
    assert d["deployment_status"] == "RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False
    assert d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"] == "CLOSED_MINIMUM_DATASET_NOT_REACHED"


def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def expected_slots(contract: dict[str, Any]) -> list[datetime]:
    start = parse_dt(contract["required_input_start_local"]).astimezone(timezone.utc)
    end = parse_dt(contract["required_input_end_exclusive_local"]).astimezone(timezone.utc)
    slots=[]; t=start
    while t < end:
        slots.append(t); t += timedelta(minutes=30)
    assert len(slots) == contract["expected_half_hour_slots"] == 384
    return slots


def cmr_interval(a3: dict[str, Any], slots: list[datetime]) -> dict[str, Any]:
    start=slots[0]; end=slots[-1] + timedelta(minutes=29, seconds=59)
    params={
        "collection_concept_id": a3["product_identity"]["collection_concept_id"],
        "temporal": f"{start.isoformat().replace('+00:00','Z')},{end.isoformat().replace('+00:00','Z')}",
        "page_size": "500",
        "sort_key[]": "start_date",
    }
    try:
        r=requests.get(a3["product_identity"]["cmr_endpoint"],params=params,headers={"User-Agent":UA},timeout=120)
    except Exception as exc:
        return {"status":"UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING","error":repr(exc)}
    raw=r.content
    out={"http_status":r.status_code,"resolved_query_url":r.url,"raw_bytes":len(raw),"raw_sha256":sha256_bytes(raw)}
    if r.status_code != 200:
        out["status"]="UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING"; return out
    try: payload=r.json()
    except Exception as exc:
        out.update(status="UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO",error=repr(exc)); return out
    entries=(payload.get("feed") or {}).get("entry") or []
    by_slot: dict[str,list[dict[str,Any]]]={}
    for e in entries:
        ts=e.get("time_start")
        if not ts: continue
        try: dt=parse_dt(str(ts)).astimezone(timezone.utc)
        except Exception: continue
        key=dt.replace(microsecond=0).isoformat()
        by_slot.setdefault(key,[]).append(e)
    expected_keys=[x.replace(microsecond=0).isoformat() for x in slots]
    missing=[]; duplicate=[]; selected=[]
    for key in expected_keys:
        es=by_slot.get(key,[])
        if len(es)==0: missing.append(key)
        elif len(es)>1: duplicate.append({"slot":key,"count":len(es)})
        else: selected.append(es[0])
    extras=[]
    expected_set=set(expected_keys)
    for key,es in by_slot.items():
        if key not in expected_set: extras.extend([key]*len(es))
    out.update(
        status="PASS_CMR_384_EXACT_SLOT_IDENTITIES" if len(selected)==384 and not missing and not duplicate else "UNKNOWN_GRANULE_IDENTITY_NO_IMPUTATION",
        returned_entry_count=len(entries), exact_selected_count=len(selected), missing_slots=missing, duplicate_slots=duplicate, extra_slot_count=len(extras),
    )
    if out["status"].startswith("PASS_"):
        records=[]
        for e in selected:
            rec={
                "producer_granule_id":e.get("producer_granule_id") or e.get("title"),
                "time_start":e.get("time_start"),
                "time_end":e.get("time_end"),
                "links":[{"href":x.get("href"),"title":x.get("title"),"rel":x.get("rel")} for x in (e.get("links") or []) if x.get("href")],
            }
            records.append(rec)
        out["entries"]=records
        out["ordered_granule_id_manifest_sha256"]=sha256_text("\n".join(str(x["producer_granule_id"]) for x in records)+"\n")
    return out


def fetch_coordinate_vectors(preflight: dict[str,Any], cmr_entry: dict[str,Any], token: str|None) -> tuple[dict[str,Any],list[float],list[float],dict[str,Any]]:
    base_url=base.resolve_opendap_url({"links":cmr_entry["links"]})
    if not base_url:
        return {"status":"UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO","blocker":"OPENDAP_URL_NOT_RESOLVED"},[],[],{}
    dds=base.fetch_dds(base_url,token)
    if dds.get("status")!="PASS_DDS_SCHEMA_RESOLVED": return dds,[],[],{}
    lon_d=dds["lon_declaration"]; lat_d=dds["lat_declaration"]
    lon_fetch=base.fetch_ascii(base_url,base.ce_name_candidates(lon_d["name"]),token)
    lat_fetch=base.fetch_ascii(base_url,base.ce_name_candidates(lat_d["name"]),token)
    if lon_fetch["status"]!="SUCCESS" or lat_fetch["status"]!="SUCCESS":
        return {"status":"UNKNOWN_TRANSPORT_OR_AUTH_NOT_MISSING","lon":lon_fetch["status"],"lat":lat_fetch["status"]},[],[],dds
    lon=base.parse_coordinate(lon_fetch["chosen"]["text"],lo=-180,hi=180,expected_size=base.declaration_size(lon_d))
    lat=base.parse_coordinate(lat_fetch["chosen"]["text"],lo=-90,hi=90,expected_size=base.declaration_size(lat_d))
    lon_hash=sha256_text("\n".join(f"{x:.10f}" for x in lon)+"\n") if lon else None
    lat_hash=sha256_text("\n".join(f"{x:.10f}" for x in lat)+"\n") if lat else None
    frozen=preflight["native_grid"]
    status="PASS_COORDINATES_MATCH_FROZEN_PREFLIGHT" if lon_hash==frozen["lon_canonical_sha256"] and lat_hash==frozen["lat_canonical_sha256"] else "UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO"
    return {
        "status":status,"opendap_base_url":base_url,"dds_sha256":dds.get("raw_sha256"),
        "lon_canonical_sha256":lon_hash,"lat_canonical_sha256":lat_hash,
        "lon_count":len(lon),"lat_count":len(lat),
    },lon,lat,dds


def full_precip_ce(decl: dict[str,Any], lb: tuple[int,int], ab: tuple[int,int], varname: str) -> str:
    slices=[]
    for d in decl.get("dimensions") or []:
        n=str(d["name"]).lower(); size=int(d["size"])
        if "lon" in n:
            slices.append(f"[{lb[0]}:1:{lb[1]}]")
        elif "lat" in n:
            slices.append(f"[{ab[0]}:1:{ab[1]}]")
        elif "time" in n or size==1:
            slices.append("[0:1:0]")
        else:
            slices.append("[0:1:0]")
    return varname+"".join(slices)


def matrix_from_ascii(text: str, decl: dict[str,Any], lb: tuple[int,int], ab: tuple[int,int]) -> tuple[str,list[list[float]]]:
    nx=lb[1]-lb[0]+1; ny=ab[1]-ab[0]+1
    dims=decl.get("dimensions") or []
    names=[str(d["name"]).lower() for d in dims]
    lon_pos=next((i for i,n in enumerate(names) if "lon" in n),None)
    lat_pos=next((i for i,n in enumerate(names) if "lat" in n),None)
    if lon_pos is None or lat_pos is None:
        return "UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO",[]
    m=[[math.nan for _ in range(ny)] for _ in range(nx)]
    filled=0
    body=text.split("---------------------------------------------",1)[-1]
    for line in body.splitlines():
        if "," not in line: continue
        lhs,rhs=line.split(",",1)
        idx=[int(x) for x in INDEX_RE.findall(lhs)]
        vals=[]
        for tok in FLOAT_RE.findall(rhs):
            try:
                v=float(tok)
                vals.append(v)
            except ValueError: pass
        if not vals: continue
        # Common Hyrax ASCII form: all dimensions except the last are indexed,
        # and the final requested dimension is emitted as a comma-separated row.
        if len(idx)==len(dims)-1:
            last=len(dims)-1
            indexed={i:idx[i] for i in range(len(idx))}
            if last==lat_pos and len(vals)==ny:
                li=indexed.get(lon_pos)
                if li is None: continue
                ii=li-lb[0] if lb[0]<=li<=lb[1] else li if 0<=li<nx else -1
                if 0<=ii<nx:
                    for j,v in enumerate(vals):
                        if math.isnan(m[ii][j]): filled+=1
                        m[ii][j]=v
            elif last==lon_pos and len(vals)==nx:
                aj=indexed.get(lat_pos)
                if aj is None: continue
                jj=aj-ab[0] if ab[0]<=aj<=ab[1] else aj if 0<=aj<ny else -1
                if 0<=jj<ny:
                    for i,v in enumerate(vals):
                        if math.isnan(m[i][jj]): filled+=1
                        m[i][jj]=v
        elif len(idx)==len(dims) and len(vals)>=1:
            li=idx[lon_pos]; aj=idx[lat_pos]
            ii=li-lb[0] if lb[0]<=li<=lb[1] else li if 0<=li<nx else -1
            jj=aj-ab[0] if ab[0]<=aj<=ab[1] else aj if 0<=aj<ny else -1
            if 0<=ii<nx and 0<=jj<ny:
                if math.isnan(m[ii][jj]): filled+=1
                m[ii][jj]=vals[-1]
    if filled != nx*ny:
        # Fail closed rather than guessing flattened orientation.
        return f"UNKNOWN_SCHEMA_MATRIX_FILL_{filled}_OF_{nx*ny}",[]
    return "PASS_NATIVE_MATRIX_SHAPE_EXPLICIT",m


def selected_feature_dicts(repo: Path, case: dict[str,Any]) -> list[dict[str,Any]]:
    rel=str(case["geometry_path"]); p=repo/(rel if rel.startswith("site/") else f"site/{rel}")
    raw=load_json(p); feats=raw.get("features",[]) if raw.get("type")=="FeatureCollection" else [raw]
    sel=case.get("geometry_selector") or {}; prop=sel.get("property"); val=sel.get("value")
    if prop: feats=[f for f in feats if (f.get("properties") or {}).get(prop)==val]
    return [f for f in feats if f.get("geometry")]


def fid(f: dict[str,Any]) -> str:
    p=f.get("properties") or {}
    return str(p.get("id") or p.get("unit_id") or p.get("name") or canonical_sha(f)[:16])


def utm_epsg(lon: float) -> int:
    zone=int(math.floor((lon+180.0)/6.0)+1)
    return 32700+zone


def geometry_weights(g, lon_sub: list[float], lat_sub: list[float]) -> dict[str,Any]:
    epsg=utm_epsg(g.centroid.x)
    tr=Transformer.from_crs("EPSG:4326",f"EPSG:{epsg}",always_xy=True)
    gp=transform(tr.transform,g); basin_area=gp.area
    if not math.isfinite(basin_area) or basin_area<=0:
        return {"status":"BLOCKED_NONPOSITIVE_GEOMETRY_AREA","weights":[]}
    sx=base.spacing(lon_sub); sy=base.spacing(lat_sub)
    if sx is None or sy is None: return {"status":"BLOCKED_GRID_SPACING","weights":[]}
    weights=[]
    for i,x in enumerate(lon_sub):
        for j,y in enumerate(lat_sub):
            cell=box(x-sx/2,y-sy/2,x+sx/2,y+sy/2)
            if not cell.intersects(g): continue
            cp=transform(tr.transform,cell)
            a=gp.intersection(cp).area
            if a>0: weights.append({"i":i,"j":j,"weight":a/basin_area})
    wsum=sum(x["weight"] for x in weights)
    return {
        "status":"PASS_WEIGHT_SUM" if abs(wsum-1.0)<=1e-5 else "BLOCKED_WEIGHT_SUM",
        "epsg":epsg,"basin_area_m2":basin_area,"intersecting_cell_count":len(weights),"weight_sum":wsum,
        "weights":weights,
        "weights_canonical_sha256":canonical_sha([{k:v for k,v in x.items()} for x in weights]),
    }


def fetch_subset(entry: dict[str,Any], pdecl: dict[str,Any], lb: tuple[int,int], ab: tuple[int,int], token: str|None) -> dict[str,Any]:
    op=base.resolve_opendap_url({"links":entry["links"]})
    if not op: return {"status":"UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO","granule":entry["producer_granule_id"]}
    last=None
    for attempt in range(3):
        for vn in base.ce_name_candidates(pdecl["name"]):
            ce=full_precip_ce(pdecl,lb,ab,vn)
            x=base.fetch_ascii(op,[ce],token)
            if x.get("status")=="SUCCESS":
                chosen=x["chosen"]
                status,m=matrix_from_ascii(chosen["text"],pdecl,lb,ab)
                if status.startswith("PASS_"):
                    flat=[v for row in m for v in row]
                    return {
                        "status":"PASS_NATIVE_SUBSET","granule":entry["producer_granule_id"],"time_start":entry["time_start"],
                        "ce":ce,"raw_sha256":chosen["raw_sha256"],"raw_bytes":chosen["raw_bytes"],
                        "matrix_status":status,"matrix_canonical_sha256":sha256_text("\n".join(f"{v:.12g}" for v in flat)+"\n"),"matrix":m,
                    }
                last={"status":status,"granule":entry["producer_granule_id"],"ce":ce}
            else:
                last={"status":x.get("status"),"granule":entry["producer_granule_id"],"ce":ce}
        if attempt<2: time_mod.sleep(1.5*(attempt+1))
    return last or {"status":"UNKNOWN_TRANSPORT_OR_AUTH_NOT_MISSING","granule":entry["producer_granule_id"]}


def basin_depth(matrix: list[list[float]], wr: dict[str,Any], min_valid: float) -> tuple[float|None,float]:
    valid_w=0.0; rate=0.0
    for x in wr["weights"]:
        v=matrix[x["i"]][x["j"]]; w=x["weight"]
        if math.isfinite(v) and v>=0:
            valid_w+=w; rate+=v*w
    frac=valid_w/wr["weight_sum"] if wr["weight_sum"]>0 else 0.0
    if frac < min_valid: return None,frac
    # Normalize by the tiny numerical weight-sum deviation from exactly 1.
    basin_rate=rate/valid_w if valid_w>0 else None
    return (basin_rate*0.5 if basin_rate is not None else None),frac


def daily_features(depths: list[float|None]) -> dict[str,Any]:
    assert len(depths)==384
    ant=depths[:336]; day=depths[336:384]
    if any(x is None for x in ant+day):
        return {"P3H_MAX":None,"P24H_LOCAL":None,"ANTECEDENT_7D":None,"status":"UNKNOWN_REQUIRED_SLOT"}
    aa=[float(x) for x in ant]; dd=[float(x) for x in day]
    p3=max(sum(dd[i:i+6]) for i in range(0,43))
    return {"P3H_MAX":p3,"P24H_LOCAL":sum(dd),"ANTECEDENT_7D":sum(aa),"status":"PASS_COMPLETE_384_SLOTS"}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    ap.add_argument("--pilot-contract",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_first_day_pilot_contract.json"))
    ap.add_argument("--a3-contract",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_opendap_contract.json"))
    ap.add_argument("--preflight",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_opendap_preflight.json"))
    ap.add_argument("--geometry-audit",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_geometry_audit.json"))
    ap.add_argument("--manifest",type=Path,default=Path("site/data/validation/independent_basin_validation_map.json"))
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--workers",type=int,default=4)
    args=ap.parse_args(); repo=args.repo_root.resolve()
    pilot=load_json(repo/args.pilot_contract); a3=load_json(repo/args.a3_contract); pre=load_json(repo/args.preflight); audit=load_json(repo/args.geometry_audit); manifest=load_json(repo/args.manifest)
    for d in (pilot,a3,pre,audit,manifest): guard(d)
    assert pilot["selection_rule"]=="CHRONOLOGICALLY_FIRST_A0_LOCAL_CALENDAR_DAY_ONLY"
    assert pilot["target_date_local"]=="2014-09-01"
    assert pre["bulk_a3_allowed"] is True and pre["preflight_status"].startswith("PASS_")
    assert audit["summary"]["pedregal_track_level_status"]=="UNKNOWN_GEOMETRY_UNRESOLVED"
    assert audit["union_of_alternative_candidates_used_for_canonical_weighting"] is False
    slots=expected_slots(pilot)
    report={
        "schema_version":"irfen-ibvf-parallel-a3-first-day-pilot-result-v0.1","generated_at":utc_now(),"framework":"IRFEN Independent Basin Validation Framework",
        "deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,
        "uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
        "target_date_local":"2014-09-01","selection_rule":pilot["selection_rule"],"expected_half_hour_slots":384,
        "precipitation_values_used_for_date_selection":False,"territorial_outcome_fields_read":False,"known_event_dates_read":False,"cashahuacra_magnitudes_read":False,
        "window_selection_performed":False,"meteorological_ranking_performed":False,"case_control_assignment_performed":False,"bulk_a3_complete":False,"modeling_allowed":False,
        "provenance":{
            "pilot_contract_sha256":sha256_bytes((repo/args.pilot_contract).read_bytes()),"a3_contract_sha256":sha256_bytes((repo/args.a3_contract).read_bytes()),
            "preflight_sha256":sha256_bytes((repo/args.preflight).read_bytes()),"geometry_audit_sha256":sha256_bytes((repo/args.geometry_audit).read_bytes()),
            "manifest_sha256":sha256_bytes((repo/args.manifest).read_bytes()),
        },
    }
    cmr=cmr_interval(a3,slots); report["cmr"]= {k:v for k,v in cmr.items() if k!="entries"}
    if cmr.get("status")!="PASS_CMR_384_EXACT_SLOT_IDENTITIES":
        report["pilot_status"]=cmr.get("status"); write_json(args.output,report); return 0
    entries=cmr["entries"]
    token=os.environ.get("EARTHDATA_TOKEN")
    coord,lon,lat,dds=fetch_coordinate_vectors(pre,entries[0],token); report["coordinate_gate"]=coord
    if coord.get("status")!="PASS_COORDINATES_MATCH_FROZEN_PREFLIGHT":
        report["pilot_status"]=coord.get("status"); write_json(args.output,report); return 0
    lb=tuple(pilot["native_subset"]["lon_index_bounds"]); ab=tuple(pilot["native_subset"]["lat_index_bounds"])
    lon_sub=lon[lb[0]:lb[1]+1]; lat_sub=lat[ab[0]:ab[1]+1]
    assert len(lon_sub)==pilot["native_subset"]["expected_lon_count"] and len(lat_sub)==pilot["native_subset"]["expected_lat_count"]
    pdecl=dds["precipitation_declaration"]

    by_unit={c.get("unit_id"):c for c in manifest.get("cases",[])}
    geometry_targets=[]
    for unit in ("shingolay","huaycoloro","san_ildefonso"):
        feats=selected_feature_dicts(repo,by_unit[unit]); assert len(feats)==1
        geometry_targets.append((unit,shape(feats[0]["geometry"])))
    pfeats=selected_feature_dicts(repo,by_unit["pedregal"]); assert len(pfeats)==3
    for f in sorted(pfeats,key=fid): geometry_targets.append((fid(f),shape(f["geometry"])))
    weights={name:geometry_weights(g,lon_sub,lat_sub) for name,g in geometry_targets}
    report["weighting"]={k:{kk:vv for kk,vv in v.items() if kk!="weights"} for k,v in weights.items()}
    if any(v.get("status")!="PASS_WEIGHT_SUM" for v in weights.values()):
        report["pilot_status"]="BLOCKED_GEOMETRY_WEIGHT_SUM"; write_json(args.output,report); return 0

    results=[None]*len(entries)
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,6))) as ex:
        futs={ex.submit(fetch_subset,e,pdecl,lb,ab,token):i for i,e in enumerate(entries)}
        for fut in as_completed(futs):
            i=futs[fut]
            try: results[i]=fut.result()
            except Exception as exc: results[i]={"status":"UNKNOWN_TRANSPORT_OR_SCHEMA_NOT_MISSING","error":repr(exc),"granule":entries[i]["producer_granule_id"]}
    pass_count=sum(1 for x in results if x and x.get("status")=="PASS_NATIVE_SUBSET")
    report["subset_summary"]={"requested_slots":384,"pass_slots":pass_count,"failed_or_unknown_slots":384-pass_count}
    report["slot_identity_and_transport"]=[{k:v for k,v in x.items() if k!="matrix"} for x in results if x]
    if pass_count!=384:
        report["pilot_status"]="UNKNOWN_INCOMPLETE_NATIVE_SUBSET_TRANSPORT_NOT_REPLACED"; write_json(args.output,report); return 0

    min_valid=float(pilot["native_subset"]["minimum_valid_area_fraction_per_slot"])
    series={name:[] for name,_ in geometry_targets}; valid_fracs={name:[] for name,_ in geometry_targets}
    for r in results:
        m=r["matrix"]
        for name in series:
            d,frac=basin_depth(m,weights[name],min_valid); series[name].append(d); valid_fracs[name].append(frac)
    numeric={unit:daily_features(series[unit]) for unit in ("shingolay","huaycoloro","san_ildefonso")}
    candidate={cid:daily_features(series[cid]) for cid in pilot["pedregal_candidate_sidecars"]}
    canonical_rows=[]
    for unit in TRACKS:
        f=numeric.get(unit)
        if unit=="pedregal":
            canonical_rows.append({"unit_id":unit,"season_id":"2014-2015","date_local":"2014-09-01","P3H_MAX":None,"P24H_LOCAL":None,"ANTECEDENT_7D":None})
        else:
            canonical_rows.append({"unit_id":unit,"season_id":"2014-2015","date_local":"2014-09-01","P3H_MAX":f["P3H_MAX"],"P24H_LOCAL":f["P24H_LOCAL"],"ANTECEDENT_7D":f["ANTECEDENT_7D"]})
    sidecars=[{"candidate_id":cid,"unit_id":"pedregal","season_id":"2014-2015","date_local":"2014-09-01",**{k:candidate[cid][k] for k in ("P3H_MAX","P24H_LOCAL","ANTECEDENT_7D")}} for cid in pilot["pedregal_candidate_sidecars"]]
    report["canonical_rows"]=canonical_rows; report["pedregal_candidate_sidecars"]=sidecars
    report["valid_area_fraction_min"]={name:min(valid_fracs[name]) for name in valid_fracs}
    report["canonical_rows_sha256"]=canonical_sha(canonical_rows); report["pedregal_sidecars_sha256"]=canonical_sha(sidecars)
    pass_numeric=all(numeric[u]["status"]=="PASS_COMPLETE_384_SLOTS" for u in numeric)
    pass_side=all(candidate[c]["status"]=="PASS_COMPLETE_384_SLOTS" for c in candidate)
    report["pilot_status"]="PASS_FIRST_BLIND_A3_DAY_END_TO_END_BULK_STILL_INCOMPLETE_NO_RANKING" if pass_numeric and pass_side else "UNKNOWN_DAILY_FEATURE_REQUIRED_SLOT"
    report["next_gate"]="SCALE_IDENTICAL_IMPLEMENTATION_TO_FROZEN_SEASON_PARTITIONS_THEN_REQUIRE_ALL_11628_CANONICAL_ROWS_BEFORE_PREREGISTERED_RANKING"
    write_json(args.output,report)
    print(json.dumps({"pilot_status":report["pilot_status"],"cmr_slots":cmr["exact_selected_count"],"subset_pass":pass_count,"rows":canonical_rows,"pedregal_sidecars":sidecars},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
