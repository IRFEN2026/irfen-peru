#!/usr/bin/env python3
"""Frozen-season A3 extractor for the IBVF blind multipista pool.

RESEARCH_ONLY / TEST_ONLY. A partition is selected only by its frozen ID in
ibvf_parallel_a3_bulk_execution_plan.json. Rainfall, sensor availability,
known event dates, territorial outcomes and Cashahuacra magnitudes are never
read for date/geometry selection. Pedregal remains canonically UNKNOWN while
its three REVIEW_ONLY geometries are retained as sidecars only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ibvf_parallel_a3_first_day_pilot as pilot  # noqa: E402
import ibvf_parallel_a3_opendap_preflight as base  # noqa: E402
import ibvf_parallel_a3_opendap_earthdata_adapter  # noqa: F401,E402

TRACKS=("shingolay","pedregal","huaycoloro","san_ildefonso")
NUMERIC_TRACKS=("shingolay","huaycoloro","san_ildefonso")
UA="IRFEN-IBVF-A3-SEASON/0.1 RESEARCH_ONLY TEST_ONLY"
LOCK=threading.Lock()


def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def sha(raw): return hashlib.sha256(raw).hexdigest()
def shatxt(s): return sha(s.encode("utf-8"))
def csha(x): return shatxt(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False))
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def guard(d):
    assert d["deployment_status"]=="RESEARCH_ONLY"
    assert d["test_only"] is True
    assert d["production_use"] is False and d["production_ready"] is False
    assert d["operational_alerting_enabled"] is False
    assert d["uses_operational_event_none_labels"] is False
    assert d["territorial_activation_evidence_blinded"] is True
    assert d["serious_modeling_gate"]=="CLOSED_MINIMUM_DATASET_NOT_REACHED"


def slots_for(part,tz):
    s=datetime.combine(date.fromisoformat(part["input_start_local"]),datetime.min.time(),tzinfo=tz).astimezone(timezone.utc)
    e=datetime.combine(date.fromisoformat(part["input_end_exclusive_local"]),datetime.min.time(),tzinfo=tz).astimezone(timezone.utc)
    out=[]; t=s
    while t<e:
        out.append(t); t+=timedelta(minutes=30)
    assert len(out)==int(part["expected_half_hour_slots"])
    return out


def cmr_partition(a3,slots,page_size=2000):
    endpoint=a3["product_identity"]["cmr_endpoint"]
    start=slots[0]; end=slots[-1]+timedelta(minutes=29,seconds=59)
    base_params={"collection_concept_id":a3["product_identity"]["collection_concept_id"],"temporal":f"{start.isoformat().replace('+00:00','Z')},{end.isoformat().replace('+00:00','Z')}","page_size":str(page_size),"sort_key[]":"start_date"}
    pages=[]; entries=[]; page=1
    while True:
        params=dict(base_params); params["page_num"]=str(page)
        try: r=requests.get(endpoint,params=params,headers={"User-Agent":UA},timeout=120)
        except Exception as exc: return {"status":"UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING","error":repr(exc),"pages":pages}
        rec={"page_num":page,"http_status":r.status_code,"resolved_query_url":r.url,"raw_bytes":len(r.content),"raw_sha256":sha(r.content)}; pages.append(rec)
        if r.status_code!=200: return {"status":"UNKNOWN_TRANSPORT_BLOCKED_NOT_MISSING","pages":pages}
        try: batch=(r.json().get("feed") or {}).get("entry") or []
        except Exception as exc: return {"status":"UNKNOWN_SCHEMA_BLOCKED_NOT_ZERO","error":repr(exc),"pages":pages}
        entries.extend(batch); rec["returned_entry_count"]=len(batch)
        if len(batch)<page_size: break
        page+=1
        if page>50: return {"status":"UNKNOWN_CMR_PAGINATION_GUARD","pages":pages,"returned_entry_count":len(entries)}
    by={}
    for e in entries:
        ts=e.get("time_start")
        if not ts: continue
        try: key=pilot.parse_dt(str(ts)).astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except Exception: continue
        by.setdefault(key,[]).append(e)
    keys=[x.replace(microsecond=0).isoformat() for x in slots]; keyset=set(keys)
    missing=[]; dup=[]; selected=[]
    for k in keys:
        es=by.get(k,[])
        if not es: missing.append(k)
        elif len(es)>1: dup.append({"slot":k,"count":len(es)})
        else: selected.append(es[0])
    out={"status":"PASS_CMR_EXACT_PARTITION_SLOT_IDENTITIES" if len(selected)==len(slots) and not missing and not dup else "UNKNOWN_GRANULE_IDENTITY_NO_IMPUTATION","page_count":len(pages),"pages":pages,"returned_entry_count":len(entries),"exact_selected_count":len(selected),"expected_slot_count":len(slots),"missing_slots":missing,"duplicate_slots":dup,"extra_slot_count":sum(len(v) for k,v in by.items() if k not in keyset)}
    if out["status"].startswith("PASS_"):
        rr=[]
        for e in selected:
            rr.append({"producer_granule_id":e.get("producer_granule_id") or e.get("title"),"time_start":e.get("time_start"),"time_end":e.get("time_end"),"links":[{"href":x.get("href"),"title":x.get("title"),"rel":x.get("rel")} for x in (e.get("links") or []) if x.get("href")]})
        out["entries"]=rr; out["ordered_granule_id_manifest_sha256"]=shatxt("\n".join(str(x["producer_granule_id"]) for x in rr)+"\n")
    return out


def checkpoint_read(p):
    d={}
    if not p.exists(): return d
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: r=json.loads(line)
        except Exception: continue
        if r.get("producer_granule_id"): d[str(r["producer_granule_id"])]=r
    return d


def checkpoint_append(p,r):
    p.parent.mkdir(parents=True,exist_ok=True)
    line=json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n"
    with LOCK:
        with p.open("a",encoding="utf-8") as f:
            f.write(line); f.flush(); os.fsync(f.fileno())


def targets(repo,manifest):
    by={c.get("unit_id"):c for c in manifest.get("cases",[])}; out=[]
    for u in NUMERIC_TRACKS:
        fs=pilot.selected_feature_dicts(repo,by[u]); assert len(fs)==1; out.append((u,shape(fs[0]["geometry"])))
    pf=pilot.selected_feature_dicts(repo,by["pedregal"]); assert len(pf)==3
    fmap={pilot.fid(f):f for f in pf}; ids=sorted(fmap)
    for cid in ids: out.append((cid,shape(fmap[cid]["geometry"])))
    return out,ids


def worker(entry,pdecl,lb,ab,token,weights,min_valid):
    r=pilot.fetch_subset(entry,pdecl,lb,ab,token)
    out={k:v for k,v in r.items() if k!="matrix"}; out["producer_granule_id"]=entry["producer_granule_id"]; out["time_start"]=entry["time_start"]
    if r.get("status")!="PASS_NATIVE_SUBSET":
        out["depths_mm"]={k:None for k in weights}; out["valid_area_fraction"]={k:0.0 for k in weights}; return out
    depths={}; fracs={}
    for k,wr in weights.items():
        d,f=pilot.basin_depth(r["matrix"],wr,min_valid); depths[k]=d; fracs[k]=f
    out["depths_mm"]=depths; out["valid_area_fraction"]=fracs; out["depths_canonical_sha256"]=csha(depths)
    return out


def features(series,i):
    if i<336 or i+48>len(series): return {"P3H_MAX":None,"P24H_LOCAL":None,"ANTECEDENT_7D":None,"status":"UNKNOWN_INDEX_WINDOW"}
    ant=series[i-336:i]; day=series[i:i+48]
    if any(x is None for x in ant+day): return {"P3H_MAX":None,"P24H_LOCAL":None,"ANTECEDENT_7D":None,"status":"UNKNOWN_REQUIRED_SLOT"}
    a=[float(x) for x in ant]; d=[float(x) for x in day]
    return {"P3H_MAX":max(sum(d[j:j+6]) for j in range(43)),"P24H_LOCAL":sum(d),"ANTECEDENT_7D":sum(a),"status":"PASS_COMPLETE_REQUIRED_SLOTS"}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--repo-root",type=Path,default=Path(".")); ap.add_argument("--execution-plan",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_bulk_execution_plan.json")); ap.add_argument("--a3-contract",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_opendap_contract.json")); ap.add_argument("--preflight",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_opendap_preflight.json")); ap.add_argument("--geometry-audit",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_geometry_audit.json")); ap.add_argument("--manifest",type=Path,default=Path("site/data/validation/independent_basin_validation_map.json")); ap.add_argument("--first-day-result",type=Path,default=Path("site/data/validation/ibvf_parallel_a3_first_day_pilot.json")); ap.add_argument("--partition-id",required=True); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--checkpoint",type=Path,required=True); ap.add_argument("--workers",type=int,default=4); args=ap.parse_args(); repo=args.repo_root.resolve()
    plan=load(repo/args.execution_plan); a3=load(repo/args.a3_contract); pre=load(repo/args.preflight); audit=load(repo/args.geometry_audit); manifest=load(repo/args.manifest); first=load(repo/args.first_day_result)
    for d in (plan,a3,pre,audit,manifest,first): guard(d)
    assert plan["partition_selection_uses_rainfall"] is False and plan["partition_selection_uses_outcome"] is False and plan["partition_selection_uses_known_event_dates"] is False and plan["partition_selection_uses_sensor_availability"] is False and plan["partition_selection_uses_cashahuacra_magnitudes"] is False
    assert plan["completion_gate"]["meteorological_ranking_before_completion_forbidden"] is True
    assert pre["bulk_a3_allowed"] is True and pre["preflight_status"].startswith("PASS_")
    assert audit["summary"]["pedregal_track_level_status"]=="UNKNOWN_GEOMETRY_UNRESOLVED" and audit["union_of_alternative_candidates_used_for_canonical_weighting"] is False
    parts={p["partition_id"]:p for p in plan["partitions"]}; assert args.partition_id in parts; part=parts[args.partition_id]; tz=ZoneInfo(plan["timezone"]); slots=slots_for(part,tz)
    report={"schema_version":"irfen-ibvf-parallel-a3-season-partition-result-v0.1","generated_at":now(),"framework":"IRFEN Independent Basin Validation Framework","deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED","partition_id":args.partition_id,"partition_contract":part,"partition_selection_uses_rainfall":False,"partition_selection_uses_outcome":False,"known_event_dates_read":False,"territorial_outcome_fields_read":False,"cashahuacra_magnitudes_read":False,"sensor_availability_deletes_calendar_days":False,"window_selection_performed":False,"meteorological_ranking_performed":False,"case_control_assignment_performed":False,"modeling_allowed":False,"provenance":{"execution_plan_sha256":sha((repo/args.execution_plan).read_bytes()),"a3_contract_sha256":sha((repo/args.a3_contract).read_bytes()),"preflight_sha256":sha((repo/args.preflight).read_bytes()),"geometry_audit_sha256":sha((repo/args.geometry_audit).read_bytes()),"manifest_sha256":sha((repo/args.manifest).read_bytes()),"first_day_result_sha256":sha((repo/args.first_day_result).read_bytes())}}
    cmr=cmr_partition(a3,slots); report["cmr"]={k:v for k,v in cmr.items() if k!="entries"}
    if cmr.get("status")!="PASS_CMR_EXACT_PARTITION_SLOT_IDENTITIES": report["partition_status"]=cmr.get("status"); dump(args.output,report); return 0
    entries=cmr["entries"]; token=os.environ.get("EARTHDATA_TOKEN"); coord,lon,lat,dds=pilot.fetch_coordinate_vectors(pre,entries[0],token); report["coordinate_gate"]=coord
    if coord.get("status")!="PASS_COORDINATES_MATCH_FROZEN_PREFLIGHT": report["partition_status"]=coord.get("status"); dump(args.output,report); return 0
    lb=tuple(plan["transport_plan"]["native_subset_lon_index_bounds"]); ab=tuple(plan["transport_plan"]["native_subset_lat_index_bounds"]); assert (lb[1]-lb[0]+1,ab[1]-ab[0]+1)==tuple(plan["transport_plan"]["native_subset_shape"]); lon_sub=lon[lb[0]:lb[1]+1]; lat_sub=lat[ab[0]:ab[1]+1]; pdecl=dds["precipitation_declaration"]
    tg,pids=targets(repo,manifest); weights={n:pilot.geometry_weights(g,lon_sub,lat_sub) for n,g in tg}; report["weighting"]={k:{kk:vv for kk,vv in v.items() if kk!="weights"} for k,v in weights.items()}
    if any(v.get("status")!="PASS_WEIGHT_SUM" for v in weights.values()): report["partition_status"]="BLOCKED_GEOMETRY_WEIGHT_SUM"; dump(args.output,report); return 0
    old=checkpoint_read(args.checkpoint); reusable={k:v for k,v in old.items() if v.get("status")=="PASS_NATIVE_SUBSET" and v.get("producer_granule_id")==k}; pending=[e for e in entries if str(e["producer_granule_id"]) not in reusable]; min_valid=float(a3["basin_weighting_contract"]["minimum_valid_area_fraction_per_slot"]); maxw=max(1,min(int(args.workers),int(plan["transport_plan"]["bounded_parallelism_max_workers"]))); byid=dict(reusable)
    with ThreadPoolExecutor(max_workers=maxw) as ex:
        futs={ex.submit(worker,e,pdecl,lb,ab,token,weights,min_valid):e for e in pending}
        for fut in as_completed(futs):
            e=futs[fut]
            try: rec=fut.result()
            except Exception as exc: rec={"status":"UNKNOWN_TRANSPORT_OR_SCHEMA_NOT_MISSING","producer_granule_id":e["producer_granule_id"],"time_start":e["time_start"],"error":repr(exc),"depths_mm":{k:None for k in weights},"valid_area_fraction":{k:0.0 for k in weights}}
            byid[str(e["producer_granule_id"])]=rec; checkpoint_append(args.checkpoint,rec)
    ordered=[byid.get(str(e["producer_granule_id"])) for e in entries]
    if any(x is None for x in ordered): report["partition_status"]="UNKNOWN_CHECKPOINT_INCOMPLETE"; dump(args.output,report); return 0
    pc=sum(1 for r in ordered if r.get("status")=="PASS_NATIVE_SUBSET"); compact=[{"producer_granule_id":r.get("producer_granule_id"),"time_start":r.get("time_start"),"status":r.get("status"),"raw_sha256":r.get("raw_sha256"),"matrix_canonical_sha256":r.get("matrix_canonical_sha256"),"depths_canonical_sha256":r.get("depths_canonical_sha256")} for r in ordered]; report["subset_summary"]={"requested_slots":len(entries),"checkpoint_reused_slots":len(reusable),"newly_requested_slots":len(pending),"pass_slots":pc,"failed_or_unknown_slots":len(entries)-pc,"bounded_parallelism_max_workers":maxw,"no_failed_slot_replacement":True}; report["slot_hash_manifest"]=compact; report["ordered_subset_identity_manifest_sha256"]=csha(compact)
    series={k:[] for k in weights}; fracs={k:[] for k in weights}
    for r in ordered:
        ds=r.get("depths_mm") or {}; fs=r.get("valid_area_fraction") or {}
        for k in weights: series[k].append(ds.get(k)); fracs[k].append(float(fs.get(k,0.0) or 0.0))
    istart=date.fromisoformat(part["input_start_local"]); ostart=date.fromisoformat(part["output_start_local"]); oend=date.fromisoformat(part["output_end_local"]); days=(oend-ostart).days+1; assert days==int(part["output_days"]); rows=[]; statuses=[]; side=[]; numeric=0; cur=ostart
    while cur<=oend:
        idx=(cur-istart).days*48; ff={k:features(series[k],idx) for k in weights}
        for u in TRACKS:
            if u=="pedregal": vals={"P3H_MAX":None,"P24H_LOCAL":None,"ANTECEDENT_7D":None}; st="UNKNOWN_GEOMETRY_UNRESOLVED"
            else: vals={k:ff[u][k] for k in ("P3H_MAX","P24H_LOCAL","ANTECEDENT_7D")}; st=ff[u]["status"]; numeric+=int(st=="PASS_COMPLETE_REQUIRED_SLOTS")
            rows.append({"unit_id":u,"season_id":args.partition_id,"date_local":cur.isoformat(),**vals}); statuses.append({"unit_id":u,"season_id":args.partition_id,"date_local":cur.isoformat(),"feature_status":st})
        for cid in pids:
            side.append({"candidate_id":cid,"unit_id":"pedregal","season_id":args.partition_id,"date_local":cur.isoformat(),"P3H_MAX":ff[cid]["P3H_MAX"],"P24H_LOCAL":ff[cid]["P24H_LOCAL"],"ANTECEDENT_7D":ff[cid]["ANTECEDENT_7D"],"feature_status":ff[cid]["status"],"sidecar_only":True})
        cur+=timedelta(days=1)
    assert len(rows)==int(part["expected_canonical_rows"]); ped=[r for r in rows if r["unit_id"]=="pedregal"]; assert len(ped)==days and all(r["P3H_MAX"] is None and r["P24H_LOCAL"] is None and r["ANTECEDENT_7D"] is None for r in ped); assert len(side)==days*3
    report["canonical_rows"]=rows; report["canonical_row_status"]=statuses; report["pedregal_candidate_sidecars"]=side; report["canonical_rows_sha256"]=csha(rows); report["pedregal_sidecars_sha256"]=csha(side); report["canonical_row_summary"]={"expected_rows":int(part["expected_canonical_rows"]),"actual_rows":len(rows),"numeric_single_geometry_rows_expected":days*3,"numeric_single_geometry_rows_complete":numeric,"pedregal_unknown_rows":len(ped),"pedregal_unknown_rows_retained":True,"pedregal_sidecar_rows":len(side),"ranking_performed":False}; report["spatial_support_quality"]={k:{"intersecting_cell_count":weights[k]["intersecting_cell_count"],"minimum_valid_area_fraction_observed":min(fracs[k]) if fracs[k] else 0.0,"semantics":"REGIONAL_PRECIPITATION_CONTEXT_AT_NATIVE_0_1_DEG_GRID"} for k in weights}
    if args.partition_id=="2014-2015" and first.get("pilot_status","").startswith("PASS_"):
        first_rows=[r for r in rows if r["date_local"]=="2014-09-01"]; first_side=[r for r in side if r["date_local"]=="2014-09-01"]; report["first_day_crosscheck"]={"canonical_rows_match_frozen_pilot":csha(first_rows)==first["canonical_rows_sha256"],"pedregal_sidecars_match_frozen_pilot":csha([{k:v for k,v in r.items() if k!="feature_status" and k!="sidecar_only"} for r in first_side])==first["pedregal_sidecars_sha256"]}
    full=(pc==len(entries) and numeric==days*3 and len(rows)==int(part["expected_canonical_rows"])); report["partition_status"]="PASS_SEASON_PARTITION_COMPLETE_NO_RANKING_NO_UNBLINDING" if full else "UNKNOWN_PARTITION_RETAINS_ALL_ROWS_NO_IMPUTATION"; report["bulk_a3_complete"]=False; report["next_gate"]="CONTINUE_NEXT_FROZEN_CHRONOLOGICAL_PARTITION; METEOROLOGICAL_RANKING_FORBIDDEN_UNTIL_ALL_11628_CANONICAL_ROWS EXIST"; dump(args.output,report); print(json.dumps({"partition_id":args.partition_id,"partition_status":report["partition_status"],"subset_pass":pc,"subset_total":len(entries),"canonical_rows":len(rows),"numeric_rows_complete":numeric,"pedregal_unknown_rows":len(ped),"sidecars":len(side)},indent=2)); return 0


if __name__=="__main__": raise SystemExit(main())
