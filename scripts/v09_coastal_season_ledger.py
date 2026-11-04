"""IRFEN coastal season 2026–27: offline append-only evidence envelopes.

No network, prediction, calibration, alerts or overwrites. Caller supplies legitimately
obtained source bytes and a sidecar JSON; this utility NEVER invents availability time.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

COAST=("Tumbes","Piura","Lambayeque","La Libertad","Áncash","Lima",
       "Callao","Ica","Arequipa","Moquegua","Tacna")
HORIZONS=(1,3,6,12,24)
PRODUCTS={"IMERG_EARLY","GOES19","INDECI_COEN","SENAMHI","INAMHI"}
def utc(s):
    v=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if v.tzinfo is None: raise ValueError("timezone required")
    return v.astimezone(dt.timezone.utc)
def validate(meta, data, ingest_time):
    required=("source","product","department","basin","subbasin","observation_time",
              "unit","qc","coverage","expires_at")
    missing=[x for x in required if x not in meta]
    if missing:raise ValueError("missing metadata: "+",".join(missing))
    if meta["department"] not in COAST:raise ValueError("out of coastal scope")
    if meta["product"] not in PRODUCTS:raise ValueError("unapproved product")
    if not meta["source"] or not meta["basin"] or not meta["subbasin"]:
        raise ValueError("missing provenance or hydrologic association")
    if not meta["unit"] or meta["qc"] not in ("VERIFIED","UNVERIFIED","MISSING"):
        raise ValueError("invalid units or QC")
    coverage=meta["coverage"]
    if coverage is not None and (not isinstance(coverage,(float,int)) or
                                 isinstance(coverage,bool) or not math.isfinite(coverage)
                                 or not 0<=coverage<=1):
        raise ValueError("invalid coverage")
    obs=utc(meta["observation_time"]);expiry=utc(meta["expires_at"])
    ing=utc(ingest_time)
    if obs>ing:raise ValueError("observation from future")
    if expiry<obs:raise ValueError("expiry before observation")
    published=meta.get("published_at");available=meta.get("available_at")
    if published is not None and utc(published)<obs:
        raise ValueError("publication before observation")
    if available is not None and utc(available)<obs:
        raise ValueError("availability before observation")
    if available is not None and utc(available)>ing:
        raise ValueError("unavailable at ingestion")
    if published is not None and available is not None and utc(available)<utc(published):
        raise ValueError("available before publication")
    if meta["product"]=="IMERG_EARLY" and meta.get("forecast",False):
        raise ValueError("observed IMERG Early must not be labeled forecast")
    if meta.get("value") is not None:
        v=meta["value"]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
            raise ValueError("invalid numeric value; missing is null")
    if meta["qc"]=="MISSING" and meta.get("value") is not None:
        raise ValueError("missing observation cannot contain numeric value")
    # Unknown availability is not estimated from the nominal 4h IMERG latency.
    usable=available is not None and meta["qc"]=="VERIFIED" and coverage is not None and coverage>=0.9
    return dict(schema="irfen_coastal_season_evidence_v0_1",mode="RESEARCH_ONLY",
                test_only=True,activation_gate="BLOCKED",operational_use=False,
                observation=meta,ingest_time=ingest_time,
                source_sha256=hashlib.sha256(data).hexdigest(),source_bytes=len(data),
                observed_not_forecast=not meta.get("forecast",False),
                available_at_verified=available is not None,
                eligible_for_prospective_replay=bool(usable and obs<=utc(available)),
                hydrologic_forecast_validated=False,horizons_hours=list(HORIZONS))
def store(root, meta, data, ingest_time):
    envelope=validate(meta,data,ingest_time)
    # One observation is immutable: content address includes metadata, bytes hash and ingestion.
    encoded=(json.dumps(envelope,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    digest=hashlib.sha256(encoded).hexdigest()
    folder=Path(root)/"2026-2027"/meta["department"]/digest[:2]
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(digest+".json")
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
    except FileExistsError:
        if path.read_bytes()!=encoded:raise ValueError("hash collision or modified evidence")
        return path,False
    with os.fdopen(fd,"wb") as f:
        f.write(encoded);f.flush();os.fsync(f.fileno())
    return path,True
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True,type=Path)
    p.add_argument("--source-file",required=True,type=Path)
    p.add_argument("--archive",required=True,type=Path)
    p.add_argument("--ingest-time",required=True)
    a=p.parse_args()
    path,created=store(a.archive,json.loads(a.metadata.read_text(encoding="utf-8")),
                       a.source_file.read_bytes(),a.ingest_time)
    print(json.dumps({"path":str(path),"created":created,"activation_gate":"BLOCKED"}))
if __name__=="__main__":main()
