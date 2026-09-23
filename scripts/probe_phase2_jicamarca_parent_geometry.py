#!/usr/bin/env python3
"""Resolve and freeze official ANA Jicamarca/Canto Grande parent context geometries.

Identity is discovered with bounded, attribute-only official-name queries and checked
against preregistered documentary areas before exact OBJECTID geometry fetches. The
outputs are context only: this script never derives child catchments, outlets,
confluences, routing, discharge, thresholds, event footprints, risk or alerts.
"""
from __future__ import annotations
import argparse, json, unicodedata
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config/phase2_jicamarca_parent_geometry_v0_1.json"
DISC=ROOT/"config/phase2_jicamarca_discovery_v0_1.json"
ZONE=ROOT/"site/data/validation/phase2_zone_contracts/lima_este_santa_eulalia_rimac.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class ProbeError(RuntimeError): pass

def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def digest_bytes(v): return sha256(v).hexdigest()
def digest_path(p): return sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text(encoding="utf-8"))
def dump(p,v): p.parent.mkdir(parents=True,exist_ok=True); raw=canonical(v); p.write_bytes(raw); return digest_bytes(raw)
def guards(o,label):
    for k,e in SAFE.items():
        if o.get(k)!=e: raise ProbeError(f"UNSAFE_{label}_{k}")
def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD",str(s or "")) if not unicodedata.combining(c)).casefold().strip()
def request_json(url,params=None):
    if params: url=url+("&" if "?" in url else "?")+urlencode(params)
    with urlopen(Request(url,headers={"User-Agent":"IRFEN-RESEARCH-ONLY/0.2"}),timeout=90) as r:
        obj=json.loads(r.read().decode("utf-8"))
    if isinstance(obj,dict) and obj.get("error"): raise ProbeError(f"ANA_SERVICE_ERROR {obj['error']}")
    return obj,url

def validate_contracts(cfg,disc,zone):
    guards(cfg,"GEOMETRY_CONTRACT"); guards(disc,"DISCOVERY")
    if zone.get("deployment_status")!="RESEARCH_ONLY" or zone.get("test_mode")!="TEST_ONLY": raise ProbeError("UNSAFE_ZONE")
    for k in ("production_use","production_ready","operational_alerting_enabled"):
        if zone.get(k) is not False: raise ProbeError(f"UNSAFE_ZONE_{k}")
    if zone.get("activation_gate")!="BLOCKED" or zone.get("missing_data_rule")!="UNKNOWN_NOT_LOW_RISK": raise ProbeError("UNSAFE_ZONE_GATE")
    if zone.get("decision_thresholds") is not None or zone.get("hydraulic_factors") is not None: raise ProbeError("UNSAFE_ZONE_NUMERIC_GUARDS")
    role=cfg["scientific_role"]
    required={"parent_context_only":True,"local_activation_geometry":False,"counts_as_complete_candidate_geometry":False,"candidate_wide_sampling_ready":False,"counts_as_event_footprint":False,"counts_as_operational_geometry":False,"child_geometry_inferred":False,"confluence_inferred":False,"routing_inferred":False}
    for k,e in required.items():
        if role.get(k)!=e: raise ProbeError(f"UNSAFE_ROLE_{k}")
    if set(cfg.get("units",{}))!={"jicamarca_parent","canto_grande_parent"}: raise ProbeError("PARENT_UNIT_SET_DRIFT")
    if (disc.get("hierarchy_binding") or {}).get("candidate_inventory_registration") is not False: raise ProbeError("DISCOVERY_MUST_REMAIN_UNREGISTERED")
    if (disc.get("territorial_identity") or {}).get("jicamarca_is_single_hydrologic_unit") is not False: raise ProbeError("SYNTHETIC_JICAMARCA_FORBIDDEN")

def metadata(cfg):
    service=cfg["source_service"]; meta,_=request_json(service["layer_url"],{"f":service["metadata_format"]})
    field_defs=[f for f in meta.get("fields",[]) if f.get("name")]
    fields={f["name"] for f in field_defs}
    oid=meta.get("objectIdField") or meta.get("objectIdFieldName")
    if not oid or oid not in fields:
        oid=next((f["name"] for f in field_defs if f.get("type")=="esriFieldTypeOID"),None)
    if not oid or oid not in fields:
        oid=next((x for x in ("OBJECTID","FID","OID","OBJECTID_1") if x in fields),None)
    if not oid: raise ProbeError(f"ANA_OBJECT_ID_FIELD_UNRESOLVED fields={sorted(fields)!r}")
    names=[f for f in service["preferred_name_fields"] if f in fields]
    codes=[f for f in service["preferred_code_fields"] if f in fields]
    area=service["preferred_area_field"] if service["preferred_area_field"] in fields else None
    if not names or not area: raise ProbeError(f"ANA_REQUIRED_FIELDS_MISSING names={names} area={area} fields={sorted(fields)!r}")
    return oid,names,codes,area

def bounded_candidates(cfg,unit,oid,name_fields,code_fields,area_field):
    service=cfg["source_service"]; endpoint=service["layer_url"]+"/query"; token=unit["search_token"].replace("'","''")
    by_oid={}
    for field in name_fields:
        obj,_=request_json(endpoint,{"where":f"{field} LIKE '%{token}%'","outFields":"*","returnGeometry":"false","f":"json"})
        for feat in obj.get("features",[]):
            p=feat.get("attributes") or feat.get("properties") or {}
            if p.get(oid) is not None: by_oid[str(p[oid])]=p
    expected_name=norm(unit["search_token"]); expected_area=float(unit["expected_area_km2"]); tol=float(unit["area_tolerance_km2"])
    matches=[]
    for p in by_oid.values():
        names=[str(p.get(f) or "") for f in name_fields]
        if not any(expected_name in norm(n) for n in names): continue
        try: area=float(p.get(area_field))
        except (TypeError,ValueError): continue
        if abs(area-expected_area)>tol: continue
        live_codes={f:str(p.get(f)) for f in code_fields if p.get(f) not in (None,"")}
        matches.append({"object_id":p[oid],"names":{f:p.get(f) for f in name_fields},"area_km2":area,"live_codes":live_codes})
    if len(matches)!=1:
        summary=[{"object_id":p.get(oid),"names":{f:p.get(f) for f in name_fields},"area":p.get(area_field),"codes":{f:p.get(f) for f in code_fields}} for p in by_oid.values()]
        raise ProbeError(f"ANA_BOUNDED_IDENTITY_NOT_UNIQUE token={unit['search_token']!r} matches={matches!r} candidates={summary!r}")
    return matches[0]

def exact_geometry(cfg,match,oid):
    s=cfg["source_service"]; endpoint=s["layer_url"]+"/query"
    obj,url=request_json(endpoint,{"where":f"{oid}={match['object_id']}","outFields":"*","returnGeometry":"true","outSR":str(s["geometry_fetch_out_sr"]),"geometryPrecision":str(s["geometry_precision"]),"f":s["geometry_format"]})
    if obj.get("type")!="FeatureCollection" or len(obj.get("features") or [])!=1: raise ProbeError("ANA_EXACT_OBJECT_GEOMETRY_NOT_UNIQUE")
    g=(obj["features"][0].get("geometry") or {})
    if g.get("type") not in {"Polygon","MultiPolygon"} or not g.get("coordinates"): raise ProbeError("ANA_EXACT_OBJECT_GEOMETRY_INVALID")
    return obj,url

def normalize_geometry(unit_key,unit,source,source_sha,match):
    f=source["features"][0]; source_id=f"ANA-LIVE-{unit_key.upper()}-{match['object_id']}"
    base={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,"context_only":True,"local_activation_geometry":False,"counts_as_event_footprint":False,"counts_as_operational_geometry":False,"source_id":source_id,"source_snapshot_sha256":source_sha}
    props={**base,"unit_id":unit_key,"name":unit["search_token"],"live_object_id":match["object_id"],"live_codes":match["live_codes"],"provider_area_km2":match["area_km2"],"documentary_current_code":unit["documentary_current_code"],"representation":"OFFICIAL_ANA_PARENT_CONTEXT_UNIT"}
    return {"type":"FeatureCollection","properties":base,"features":[{"type":"Feature","properties":props,"geometry":f["geometry"]}]},source_id

def source_paths(cfg): return {k:ROOT/u["source_snapshot"] for k,u in cfg["units"].items()}
def geometry_paths(cfg): return {k:ROOT/u["normalized_geometry"] for k,u in cfg["units"].items()}

def bind(cfg,disc,zone,records,validation_sha):
    refs={}
    layers=((zone.setdefault("assets",{})).setdefault("geometry",{})).setdefault("component_layers",[])
    retired={"jicamarca_parent_subbasin_context_v0_1"}; layers[:]=[x for x in layers if x.get("layer_id") not in retired]
    for key,rec in records.items():
        u=cfg["units"][key]
        refs[key]={"status":"REPRODUCIBLE_OFFICIAL_PARENT_CONTEXT","path":u["normalized_geometry"],"sha256":rec["geometry_sha256"],"validation_path":cfg["validation_output"],"validation_sha256":validation_sha,"source_path":u["source_snapshot"],"source_sha256":rec["source_sha256"],"source_ids":[rec["source_id"]],"live_object_id":rec["match"]["object_id"],"live_codes":rec["match"]["live_codes"],"provider_area_km2":rec["match"]["area_km2"],"representation":"OFFICIAL_ANA_PARENT_CONTEXT_UNIT","context_only":True,"local_activation_geometry":False,"counts_as_event_footprint":False,"counts_as_operational_geometry":False}
        layer={"layer_id":u["map_layer_id"],"title":u["map_title"],"deployment_status":"RESEARCH_ONLY","path":u["normalized_geometry"],"source_ids":[rec["source_id"]],"validation_path":cfg["validation_output"],"representation":"OFFICIAL_ANA_PARENT_CONTEXT_UNIT","confidence":"OFFICIAL_NAME_AREA_OBJECTID_RECONCILED_PARENT_CONTEXT_ONLY","default_visibility":False,"counts_as_complete_candidate_geometry":False,"candidate_wide_sampling_ready":False,"map_disclaimer":"Unidad ANA reproducible mostrada en gris/contexto RESEARCH_ONLY. No es activación local, riesgo, alerta, footprint de evento, geometría de hijos ni capacidad hidráulica."}
        hits=[i for i,x in enumerate(layers) if x.get("layer_id")==u["map_layer_id"]]
        if len(hits)>1: raise ProbeError(f"DUPLICATE_MAP_LAYER {u['map_layer_id']}")
        if hits: layers[hits[0]]=layer
        else: layers.append(layer)
    disc["official_parent_context_units"]=refs
    ti=disc.setdefault("territorial_identity",{})
    ti["official_partition_reconciliation"]={"status":"RECONCILED_BY_LIVE_ANA_NAME_AREA_OBJECTID","legacy_2010_code_not_used_as_live_query_key":True,"jicamarca_and_canto_grande_kept_separate":True,"source_contract":"config/phase2_jicamarca_parent_geometry_v0_1.json"}
    mp=disc.setdefault("map_policy",{}); mp["publish_parent_polygon"]=False; mp["publish_official_parent_context_units_separately"]=True; mp["official_parent_context_style"]="GRAY_CONTEXT_NON_ACTIVATABLE"

def run(refresh):
    cfg=load(CFG); disc=load(DISC); zone=load(ZONE); validate_contracts(cfg,disc,zone)
    oid,name_fields,code_fields,area_field=metadata(cfg); sources=source_paths(cfg); geoms=geometry_paths(cfg); records={}; request_urls={}
    for key,u in cfg["units"].items():
        sp=sources[key]
        if refresh:
            match=bounded_candidates(cfg,u,oid,name_fields,code_fields,area_field); src,url=exact_geometry(cfg,match,oid); source_sha=dump(sp,src); request_urls[key]=url
        else:
            if not sp.is_file(): raise ProbeError(f"FROZEN_SOURCE_MISSING {key}")
            src=load(sp); source_sha=digest_path(sp); p=src["features"][0].get("properties") or {}
            names=[str(p.get(f) or "") for f in name_fields]; expected_name=norm(u["search_token"])
            if not any(expected_name in norm(n) for n in names): raise ProbeError(f"FROZEN_SOURCE_NAME_DRIFT {key}")
            try: area=float(p.get(area_field))
            except (TypeError,ValueError): raise ProbeError(f"FROZEN_SOURCE_AREA_MISSING {key}")
            if abs(area-float(u["expected_area_km2"]))>float(u["area_tolerance_km2"]): raise ProbeError(f"FROZEN_SOURCE_AREA_DRIFT {key}")
            if p.get(oid) is None: raise ProbeError(f"FROZEN_SOURCE_OBJECT_ID_MISSING {key}")
            match={"object_id":p[oid],"names":{f:p.get(f) for f in name_fields},"area_km2":area,"live_codes":{f:str(p.get(f)) for f in code_fields if p.get(f) not in (None,"")}}
        geo,source_id=normalize_geometry(key,u,src,source_sha,match); geometry_sha=dump(geoms[key],geo)
        records[key]={"match":match,"source_id":source_id,"source_sha256":source_sha,"geometry_sha256":geometry_sha,"documentary_code_matches_live_any_field":u["documentary_current_code"] in set(match["live_codes"].values())}
    val={"schema_version":"0.2","status":"PASS_ANA_JICAMARCA_CANTO_GRANDE_PARENT_CONTEXT_RECONCILIATION","deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,"layer_url":cfg["source_service"]["layer_url"],"object_id_field":oid,"name_fields":name_fields,"code_fields":code_fields,"area_field":area_field,"units":records,"request_urls":request_urls if refresh else None,"parent_context_only":True,"local_activation_geometry":False,"child_geometry_inferred":False,"confluence_inferred":False,"routing_inferred":False,"outcomes_read":False,"rainfall_read":False,"hydraulic_capacity_read":False,"thresholds_used":False,"negative_controls_read":False,"approximate_geometry_used":False,"event_footprint_created":False}
    vp=ROOT/cfg["validation_output"]; val_sha=dump(vp,val); bind(cfg,disc,zone,records,val_sha); dump(DISC,disc); dump(ZONE,zone)
    print(json.dumps({"status":val["status"],"object_id_field":oid,"units":{k:{"object_id":v["match"]["object_id"],"area_km2":v["match"]["area_km2"],"live_codes":v["match"]["live_codes"]} for k,v in records.items()}},ensure_ascii=False,sort_keys=True))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--refresh-source",action="store_true"); a=ap.parse_args(); run(a.refresh_source)
if __name__=="__main__": main()
