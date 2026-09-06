#!/usr/bin/env python3
"""Validate an existing research geometry without fabricating DEM-derived morphometrics."""
import argparse, json, hashlib
from pathlib import Path
def main():
    p=argparse.ArgumentParser(); p.add_argument("--geometry",required=True); p.add_argument("--feature-id",required=True); p.add_argument("--output",required=True); a=p.parse_args()
    raw=Path(a.geometry).read_bytes(); gj=json.loads(raw)
    feat=next((f for f in gj["features"] if f.get("properties",{}).get("unit_id")==a.feature_id),None)
    if feat is None: raise SystemExit("feature_id not found")
    props=feat["properties"]
    if props.get("deployment_status")!="RESEARCH_ONLY": raise SystemExit("geometry must remain RESEARCH_ONLY")
    out={"unit_id":a.feature_id,"status":"RESEARCH_ONLY","geometry_source":a.geometry,"geometry_file_sha256":hashlib.sha256(raw).hexdigest(),"existing_area_km2":props.get("coverage",{}).get("delineated_area_km2"),"computed_morphometrics":None,"blocked_reason":"DEM raster acquisition/processing is intentionally not fabricated; acquire/version Copernicus GLO-30 before computing slope, drainage, relief and Basin Susceptibility Index."}
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
