#!/usr/bin/env python3
"""Archive exact public IGP CENDEHUA event-report bytes without interpreting them."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT=ROOT/"config/phase2_jicamarca_cendehua_archive_contract_v0_1.json"
SAFE={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None}
class ArchiveError(RuntimeError): pass

def load(p:Path): return json.loads(p.read_text(encoding="utf-8"))
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
def digest_bytes(b:bytes): return hashlib.sha256(b).hexdigest()
def guards(o,label):
    for k,e in SAFE.items():
        if o.get(k)!=e: raise ArchiveError(f"UNSAFE_{label}_{k}")

def download(url:str, max_bytes:int)->bytes:
    req=Request(url,headers={"User-Agent":"IRFEN-RESEARCH-ONLY/0.1","Accept":"application/pdf,*/*;q=0.5"})
    with urlopen(req,timeout=90) as r:
        length=r.headers.get("Content-Length")
        if length and int(length)>max_bytes: raise ArchiveError(f"REPORT_TOO_LARGE declared={length}")
        data=r.read(max_bytes+1)
    if len(data)>max_bytes: raise ArchiveError(f"REPORT_TOO_LARGE actual>{max_bytes}")
    if not data.startswith(b"%PDF-"): raise ArchiveError(f"NOT_PDF_MAGIC {url}")
    if not data: raise ArchiveError(f"EMPTY_REPORT {url}")
    return data

def verify_existing(contract, metadata, archive_root):
    meta_by={x["record_id"]:x for x in metadata.get("events",[])}
    rows=[]
    for r in contract["reports"]:
        p=archive_root/r["archive_filename"]
        if not p.is_file(): raise ArchiveError(f"MISSING_ARCHIVE {p}")
        data=p.read_bytes()
        if not data.startswith(b"%PDF-"): raise ArchiveError(f"NOT_PDF_MAGIC {p}")
        sha=digest_bytes(data); ev=meta_by.get(r["record_id"])
        if ev is None: raise ArchiveError(f"MISSING_METADATA_RECORD {r['record_id']}")
        if ev.get("event_report_sha256")!=sha: raise ArchiveError(f"METADATA_HASH_DRIFT {r['record_id']}")
        if ev.get("byte_archive_status")!="ARCHIVED_REPRODUCIBLE_BYTES": raise ArchiveError(f"METADATA_ARCHIVE_STATUS {r['record_id']}")
        if ev.get("archive_path")!=p.relative_to(ROOT).as_posix(): raise ArchiveError(f"METADATA_ARCHIVE_PATH {r['record_id']}")
        rows.append({"record_id":r["record_id"],"component_id":r["component_id"],"station_label":r["station_label"],"timestamp_local":r["timestamp_local"],"source_url":r["url"],"archive_path":p.relative_to(ROOT).as_posix(),"bytes":len(data),"sha256":sha})
    return rows

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--contract",type=Path,default=DEFAULT_CONTRACT); ap.add_argument("--refresh",action="store_true"); a=ap.parse_args()
    cp=a.contract if a.contract.is_absolute() else ROOT/a.contract
    contract=load(cp); guards(contract,"ARCHIVE_CONTRACT")
    metadata_path=ROOT/contract["metadata_contract"]; metadata=load(metadata_path); guards(metadata,"METADATA_CONTRACT")
    archive_root=ROOT/contract["archive_root"]; archive_root.mkdir(parents=True,exist_ok=True)
    meta_by={x["record_id"]:x for x in metadata.get("events",[])}
    expected={r["record_id"] for r in contract["reports"]}
    if len(expected)!=len(contract["reports"]): raise ArchiveError("DUPLICATE_RECORD_ID")
    for r in contract["reports"]:
        ev=meta_by.get(r["record_id"])
        if ev is None: raise ArchiveError(f"MISSING_METADATA_RECORD {r['record_id']}")
        if ev.get("component_id")!=r["component_id"] or ev.get("station_label")!=r["station_label"] or ev.get("timestamp_local")!=r["timestamp_local"] or ev.get("source_url")!=r["url"]:
            raise ArchiveError(f"CONTRACT_METADATA_IDENTITY_MISMATCH {r['record_id']}")
    if a.refresh:
        max_bytes=int(contract["max_bytes_per_report"])
        for r in contract["reports"]:
            data=download(r["url"],max_bytes); p=archive_root/r["archive_filename"]; p.write_bytes(data); sha=digest_bytes(data)
            ev=meta_by[r["record_id"]]; ev["event_report_sha256"]=sha; ev["event_report_bytes"]=len(data); ev["archive_path"]=p.relative_to(ROOT).as_posix(); ev["byte_archive_status"]="ARCHIVED_REPRODUCIBLE_BYTES"
        metadata_path.write_text(canonical(metadata),encoding="utf-8")
    rows=verify_existing(contract,metadata,archive_root)
    manifest={"schema_version":"0.1","status":"PASS_REPRODUCIBLE_CENDEHUA_BYTE_ARCHIVE","deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY","production_use":False,"production_ready":False,"operational_alerting_enabled":False,"activation_gate":"BLOCKED","missing_data_rule":"UNKNOWN_NOT_LOW_RISK","decision_thresholds":None,"hydraulic_factors":None,"content_interpreted":False,"thresholds_imported":False,"outlets_inferred":False,"discharge_inferred":False,"routing_enabled":False,"report_count":len(rows),"reports":rows}
    mp=ROOT/contract["manifest_path"]; mp.parent.mkdir(parents=True,exist_ok=True); mp.write_text(canonical(manifest),encoding="utf-8")
    print(json.dumps({"status":manifest["status"],"report_count":len(rows),"sha256":{r['record_id']:r['sha256'] for r in rows}},ensure_ascii=False,sort_keys=True))

if __name__=="__main__": main()
