#!/usr/bin/env python3
"""Replay and verify frozen ANA Rio Tumbes geometry snapshots.

RESEARCH_ONLY / TEST_ONLY. This script never downloads data and never updates
the map catalog. It requires exact provider bytes to have been frozen first.
"""
from __future__ import annotations
import argparse, json
from hashlib import sha256
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/"site/data/phase2/sources/tumbes_rio_tumbes_geometry_freeze_plan_v0_3.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}

class ReplayError(RuntimeError): pass

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def cb(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def dig_bytes(b): return sha256(b).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    return dig_bytes(data)

def validate_plan(p):
    for k,v in SAFE.items():
        if p.get(k)!=v: raise ReplayError(f"UNSAFE_PLAN_{k}")
    if p.get("status")!="RESEARCH_ONLY_FREEZE_PLAN": raise ReplayError("PLAN_STATUS_DRIFT")
    rows={r["layer_id"]:r for r in p.get("layers",[])}
    if set(rows)!={2,66,67}: raise ReplayError("LAYER_SET_DRIFT")
    if rows[2]["role"]!="OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT": raise ReplayError("BASIN_ROLE_DRIFT")
    for lid in (66,67):
        if rows[lid]["role"]!="OBSERVED_EVENT_FOOTPRINT_ONLY": raise ReplayError(f"EVENT_ROLE_DRIFT_{lid}")
        if rows[lid].get("counts_as_basin_geometry") is not False: raise ReplayError(f"EVENT_BASIN_GUARD_DRIFT_{lid}")
    for k,v in (p.get("guards") or {}).items():
        if v is not False: raise ReplayError(f"GUARD_DRIFT_{k}")

def validate_metadata(meta,row):
    if meta.get("name")!=row.get("expected_name"): raise ReplayError(f"LAYER_NAME_MISMATCH_{row['layer_id']}")
    if meta.get("type") not in {"Feature Layer","FeatureLayer",None}: raise ReplayError(f"LAYER_TYPE_MISMATCH_{row['layer_id']}")

def validate_fc(fc,row):
    if fc.get("type")!="FeatureCollection": raise ReplayError(f"NOT_FEATURE_COLLECTION_{row['layer_id']}")
    fs=fc.get("features")
    if not isinstance(fs,list) or not fs: raise ReplayError(f"EMPTY_FEATURE_COLLECTION_{row['layer_id']}")
    types=set()
    for f in fs:
        g=(f or {}).get("geometry") or {}
        if not g.get("coordinates"): raise ReplayError(f"MISSING_GEOMETRY_{row['layer_id']}")
        types.add(g.get("type"))
    if not types.issubset({"Polygon","MultiPolygon"}): raise ReplayError(f"UNEXPECTED_GEOMETRY_{row['layer_id']}_{sorted(types)}")
    return fs,types

def replay():
    p=load(PLAN); validate_plan(p)
    rawdir=ROOT/p["freeze_contract"]["raw_directory"]; results=[]
    for row in p["layers"]:
        lid=row["layer_id"]
        mp=rawdir/f"layer_{lid}_metadata_raw.json"
        gp=rawdir/f"layer_{lid}_query_raw.geojson"
        if not mp.is_file() or not gp.is_file(): raise ReplayError(f"FROZEN_RAW_BYTES_MISSING_{lid}")
        mb=mp.read_bytes(); gb=gp.read_bytes()
        try:
            meta=json.loads(mb.decode("utf-8")); fc=json.loads(gb.decode("utf-8"))
        except Exception as e:
            raise ReplayError(f"INVALID_PROVIDER_JSON_{lid}") from e
        validate_metadata(meta,row); fs,types=validate_fc(fc,row)
        cp=ROOT/row["canonical_path"]; csha=write(cp,cb(fc))
        results.append({"layer_id":lid,"role":row["role"],"source_id":row["source_id"],"event_date":row.get("event_date"),"raw_metadata_path":mp.relative_to(ROOT).as_posix(),"raw_metadata_sha256":dig_bytes(mb),"raw_geojson_path":gp.relative_to(ROOT).as_posix(),"raw_geojson_sha256":dig_bytes(gb),"canonical_path":cp.relative_to(ROOT).as_posix(),"canonical_sha256":csha,"feature_count":len(fs),"geometry_types":sorted(types),"counts_as_event_footprint":row["role"]=="OBSERVED_EVENT_FOOTPRINT_ONLY","counts_as_basin_geometry":row["role"]=="OFFICIAL_HYDROLOGIC_BASIN_RESEARCH_CONTEXT","counts_as_operational_geometry":False,"counts_as_irfen_threshold":False,"counts_as_hydraulic_capacity":False})
    manifest={"schema_version":"0.1","discovery_id":p["discovery_id"],"status":"PASS_FROZEN_PROVIDER_BYTES_AND_CANONICAL_GEOJSON",**SAFE,"official_service":p["official_service"],"service_item_id":p.get("service_item_id"),"layers":results,"guards":p["guards"],"map_catalog_updated":False,"thresholds_promoted":False,"hydraulic_capacity_inferred":False,"cross_system_transfer_performed":False}
    write(ROOT/p["freeze_contract"]["manifest_path"],cb(manifest))
    return manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--validate-plan-only",action="store_true")
    a=ap.parse_args()
    p=load(PLAN); validate_plan(p)
    if a.validate_plan_only:
        print(json.dumps({"status":"PASS_PLAN_ONLY","discovery_id":p["discovery_id"]},sort_keys=True)); return
    m=replay()
    print(json.dumps({"status":m["status"],"layers":[x["layer_id"] for x in m["layers"]]},sort_keys=True))

if __name__=="__main__": main()
