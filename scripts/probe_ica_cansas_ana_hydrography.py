#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

EP="https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0/query"
FIELDS="CODIGO_CA,NOMBRE_CA,TIPO_CA,LONG_KM,NOMBRE_UH,CODIGO_UH,NOMBRE_AAA"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}

def canon(x):
    return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()

def url():
    return EP+"?"+urlencode({"where":"NOMBRE_CA='Cansas'","outFields":FIELDS,"returnGeometry":"true","outSR":"4326","geometryPrecision":"7","f":"geojson"})

def validate(d):
    fs=d.get("features") or []
    if d.get("type")!="FeatureCollection" or len(fs)!=1: raise ValueError("expected one Cansas feature")
    f=fs[0]; p=f.get("properties") or {}; g=f.get("geometry") or {}
    if p.get("NOMBRE_CA")!="Cansas": raise ValueError("name mismatch")
    if str(p.get("CODIGO_UH") or "")!="1374": raise ValueError("parent UH mismatch")
    if g.get("type") not in {"LineString","MultiLineString"}: raise ValueError("channel geometry required")
    if not p.get("CODIGO_CA"): raise ValueError("channel code missing")
    return f

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--output-dir",default="/tmp/irfen-cansas-probe"); a=ap.parse_args()
    with urlopen(Request(url(),headers={"User-Agent":"IRFEN-research-probe/1.0"}),timeout=45) as r: raw=r.read()
    d=json.loads(raw.decode()); f=validate(d); p=f["properties"]; out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    c=canon(d); (out/"ana_cansas_channel.geojson").write_bytes(c)
    rec={**SAFE,"status":"PASS_EXACT_NAME_PLUS_PARENT_UH","source_id":"ANA-SNIRH-RIOS-QUEBRADAS-AAVI-2018","query_url":url(),"raw_response_sha256":hashlib.sha256(raw).hexdigest(),"canonical_geojson_sha256":hashlib.sha256(c).hexdigest(),"child_id":"ica_cansas","official_channel_code":str(p["CODIGO_CA"]),"official_parent_uh_code":str(p["CODIGO_UH"]),"official_parent_uh_name":p.get("NOMBRE_UH"),"geometry_status":"OFFICIAL_CHANNEL_LINE_PROBE_NOT_MAP_PUBLISHED","map_publishable":False,"outlet":None,"catchment_geometry":None,"event_state_transferred":False,"new_operational_zones":0}
    (out/"probe_receipt.json").write_bytes(canon(rec)); print(json.dumps(rec,ensure_ascii=False,sort_keys=True))
if __name__=="__main__": main()
