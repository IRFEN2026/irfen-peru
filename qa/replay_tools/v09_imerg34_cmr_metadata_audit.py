#!/usr/bin/env python3
"""NASA CMR metadata-only audit for two IMERG Early V07C historic granules.
RESEARCH_ONLY/TEST_ONLY. No Earthdata token, no HDF5 download, no live writes.
"""
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

RECORDS = [
 {"time_utc":"2026-10-16T13:00:00Z",
  "concept_id":"G4374452323-GES_DISC",
  "title":"3B-HHR-E.MS.MRG.3IMERG.20261016-S130000-E132959.0780.V07C.HDF5",
  "sha256_hdf5_from_recovery":"7925067c32055c30a23f2c6c8d01d687218d9cb217f443dcf4a8b6eb17f9f047"},
 {"time_utc":"2026-10-16T23:30:00Z",
  "concept_id":"G4374376915-GES_DISC",
  "title":"3B-HHR-E.MS.MRG.3IMERG.20261016-S233000-E235959.1410.V07C.HDF5",
  "sha256_hdf5_from_recovery":"3274414c48a5c1c4e27b493c81647caa861e8e95bbbb789b2ce7bdf7bf67bc6c"}
]
BASE = "https://cmr.earthdata.nasa.gov/search/granules.json"
OUTPUT = Path("qa/evidence/imerg34_cmr_identity_20261020_v2.json")
MAX_BODY = 2_000_000

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("REDIRECT_FORBIDDEN")

OPENER = urllib.request.build_opener(NoRedirect())

def fetch(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme, parsed.hostname, parsed.path) != (
            "https","cmr.earthdata.nasa.gov","/search/granules.json"):
        raise ValueError("URL_FORBIDDEN")
    request = urllib.request.Request(url,headers={
        "Accept":"application/json",
        "User-Agent":"IRFEN-CMR-identity-research-TEST-ONLY/0.1"
    })
    record={"url":url, "queried_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "http_status":None,"response_sha256":None,"body_bytes":None,
            "cmr_hits":None,"entries":[],"error":None,"complete":False}
    try:
        with OPENER.open(request,timeout=30) as response:
            raw=response.read(MAX_BODY+1)
            record["http_status"]=response.status
            hits=response.headers.get("CMR-Hits")
            record["cmr_hits"]=int(hits) if hits and hits.isdecimal() else None
        if not raw or len(raw)>MAX_BODY:raise ValueError("EMPTY_OR_OVERSIZED_RESPONSE")
        record["response_sha256"]=hashlib.sha256(raw).hexdigest()
        record["body_bytes"]=len(raw)
        entries=json.loads(raw).get("feed",{}).get("entry")
        if not isinstance(entries,list):raise ValueError("INVALID_CMR_FEED")
        record["entries"]=[{
            "id":e.get("id"),"title":e.get("title"),
            "producer_granule_id":e.get("producer_granule_id"),
            "time_start":e.get("time_start"),"time_end":e.get("time_end"),
            "updated":e.get("updated"),"revision_date":e.get("revision_date"),
            "collection_concept_id":e.get("collection_concept_id"),
            "data_center":e.get("data_center")
            } for e in entries]
        record["complete"]=(record["cmr_hits"] is not None
                            and record["cmr_hits"]==len(entries)
                            and len(entries)<=2000)
        if not record["complete"]:record["error"]="UNVERIFIED_PAGINATION_OR_HITS"
    except Exception as error:
        record["error"]=type(error).__name__+": "+str(error)[:200]
    return record

def audit():
    outcomes=[]
    for historic in RECORDS:
        start=dt.datetime.fromisoformat(historic["time_utc"].replace("Z","+00:00"))
        beg=(start-dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end=(start+dt.timedelta(minutes=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        queries={
            "by_original_concept":fetch({"concept_id":historic["concept_id"],"page_size":100}),
            "by_original_title":fetch({"short_name":"GPM_3IMERGHHE","version":"07","producer_granule_id[]":historic["title"],"page_size":100}),
            "by_time_and_product":fetch({"short_name":"GPM_3IMERGHHE","version":"07",
                                         "temporal[]":beg+","+end,"page_size":2000,
                                         "sort_key":"start_date"})
        }
        by_concept=queries["by_original_concept"]
        concepts=[e for e in by_concept["entries"] if e["id"]==historic["concept_id"]]
        exact=[e for q in queries.values() for e in q["entries"]
               if e.get("title")==historic["title"] or e.get("producer_granule_id")==historic["title"]]
        neighboring=[e for e in queries["by_time_and_product"]["entries"]
                     if str(e.get("time_start","")).startswith(historic["time_utc"][:16])]
        # If catalog is incomplete, never declare an item unavailable.
        valid=all(q["complete"] for q in queries.values())
        verdict=("ORIGINAL_CONCEPT_AND_TITLE_MATCH" if valid and concepts
                 and any(c in exact for c in concepts) else
                 "ORIGINAL_CONCEPT_PRESENT_TITLE_DIFFERS" if valid and concepts else
                 "ORIGINAL_TITLE_PRESENT_CONCEPT_CHANGED" if valid and exact else
                 "NOT_LISTED_IN_COMPLETE_QUERIES_AT_CHECK_TIME" if valid else
                 "UNKNOWN_INCOMPLETE_CATALOG")
        outcomes.append({"historical":historic,"queries":queries,
                         "original_concept_matches":concepts,
                         "exact_title_matches":exact,
                         "nearby_start_candidates":neighboring,
                         "catalog_verdict":verdict,
                         "note":"CMR granule identifiers/versions, NOT HDF5 identity proof. No replacement approved."})
    return {
        "schema_version":"0.1","deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY",
        "production_use":False,"production_ready":False,
        "operational_alerting_enabled":False,"activation_gate":"BLOCKED",
        "missing_data_rule":"UNKNOWN_NOT_LOW_RISK",
        "decision_thresholds":None,"hydraulic_factors":None,
        "source":"NASA CMR metadata-only",
        "hdf5_downloads":0,"archive_modifications":0,"outcomes":outcomes
    }

if __name__=="__main__":
    report=audit()
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    if OUTPUT.exists():raise SystemExit("REFUSE_OVERWRITE")
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    for item in report["outcomes"]:
        print(item["historical"]["time_utc"],item["catalog_verdict"],
              [(k,v["cmr_hits"],v["error"]) for k,v in item["queries"].items()])
