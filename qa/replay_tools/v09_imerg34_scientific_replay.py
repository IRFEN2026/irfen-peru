#!/usr/bin/env python3
"""Independent sample replay from NASA IMERG Early v07 HDF5 (research only).
Bounded 4 fresh downloads; verifies original SHA-256 and all 22 zone statistics.
Writes a JSON audit outside the repo. NO changes to live data/engine/map.
"""
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
ARCHIVE=ROOT/"data/v09/rain/recovered_research/imerg_early_20261015_20261016_34_recovered_v0_1.json"
BRANCH="research/imerg34-scientific-replay-20261020"
GUARDS={"deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY",
        "production_use":False,"production_ready":False,
        "operational_alerting_enabled":False,"activation_gate":"BLOCKED",
        "missing_data_rule":"UNKNOWN_NOT_LOW_RISK"}

def selected_rows(rows):
    """Include endpoints and two granules with strongest nonzero signals."""
    if len(rows)!=34 or len({r["time_utc"] for r in rows})!=34:
        raise ValueError("ARCHIVE_SCOPE_INVALID")
    ordered=sorted(rows,key=lambda r:r["time_utc"])
    peak=lambda r:max((x["rate_mm_hr"] or 0) for x in r["targets"].values())
    ranked=sorted(ordered,key=lambda r:(-peak(r),r["time_utc"]))
    selected={ordered[0]["time_utc"]:ordered[0],ordered[-1]["time_utc"]:ordered[-1]}
    for r in ranked:
        if len(selected)==4:break
        selected[r["time_utc"]]=r
    if len(selected)!=4:raise ValueError("SAMPLE_SCOPE_INVALID")
    return sorted(selected.values(),key=lambda r:r["time_utc"])

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def weighted_mean_independent(geom,lat,lon,values):
    """Independent implementation of area-weighted grid mean; not calling polygon_mean."""
    import numpy as np
    from shapely.geometry import box
    dx=float(np.median(np.abs(np.diff(lon))))
    dy=float(np.median(np.abs(np.diff(lat))))
    xmin,ymin,xmax,ymax=geom.bounds
    weighted=0.0
    area=0.0
    valid=0
    intersected=0
    for ri in range(len(lat)):
        yy=float(lat[ri])
        if yy < ymin-dy/2 or yy > ymax+dy/2:continue
        for ci in range(len(lon)):
            xx=float(lon[ci])
            if xx < xmin-dx/2 or xx > xmax+dx/2:continue
            cell=box(xx-dx/2,yy-dy/2,xx+dx/2,yy+dy/2)
            part=geom.intersection(cell)
            if part.is_empty or part.area<=0:continue
            intersected+=1
            value=float(values[ri,ci])
            if np.isfinite(value):
                valid+=1
                weighted+=part.area*value
                area+=part.area
    return None if area==0 else weighted/area,valid,intersected,round(min(100.,100.*area/max(geom.area,1e-15)),2)

def run():
    if os.getenv("GITHUB_REF_NAME")!=BRANCH:
        raise SystemExit("BRANCH_GATE_BLOCKED")
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("EARTHDATA_TOKEN_MISSING")
    import earthaccess
    import probe_imerg_early_live as probe
    import v09_imerg_north_archive as north
    source=json.loads(ARCHIVE.read_text(encoding="utf-8"))
    for k,v in GUARDS.items():
        if source.get(k)!=v:raise SystemExit("ARCHIVE_GUARD_MISMATCH")
    chosen=selected_rows(source["granules"])
    targets=north.load_targets()
    target_map={t["id"]:t for t in targets}
    if set(target_map)!=set(chosen[0]["targets"]):
        raise SystemExit("ZONE_SET_CHANGED_CANNOT_COMPARE")
    probe.earthdata_preflight()
    earthaccess.login(strategy="environment")
    found=earthaccess.search_data(short_name="GPM_3IMERGHHE",version="07",
             temporal=("2026-10-15T00:00:00Z","2026-10-17T00:00:00Z"),count=140)
    indexed=probe.index_granules(found)
    records=[]
    with tempfile.TemporaryDirectory(prefix="irfen_replay_") as td:
        for r in chosen:
            ts=datetime.fromisoformat(r["time_utc"].replace("Z","+00:00"))
            matches=[g for g in indexed if g[0]==ts and g[1]==r["granule"]]
            if len(matches)!=1:raise SystemExit("CATALOG_ID_MISMATCH")
            paths=earthaccess.download([matches[0][2]],local_path=td,threads=1,show_progress=False)
            p=next((Path(x) for x in paths if Path(x).name==r["granule"]),None)
            if p is None or not p.is_file():raise SystemExit("DOWNLOAD_FAILED")
            if p.stat().st_size>12_000_000:raise SystemExit("FILE_LIMIT")
            actual_sha=digest(p)
            if actual_sha!=r["sha256"]:raise SystemExit("HDF5_SHA256_DIFF")
            if p.stat().st_size!=r["size_bytes"]:raise SystemExit("HDF5_SIZE_DIFF")
            lat,lon,grid,units=probe.read_grid(p)
            if units!=r["units"]:raise SystemExit("UNITS_DIFF")
            comparisons=[]
            for zid,target in sorted(target_map.items()):
                original=r["targets"][zid]
                mean,valid,cells,cover=weighted_mean_independent(target["geometry"],lat,lon,grid)
                rate=None if mean is None else round(mean,4)
                accum=None if mean is None else round(mean*0.5,4)
                computed={"rate_mm_hr":rate,"accum_30min_mm":accum,
                          "valid_cells":valid,"cells_intersected":cells,
                          "covered_pct":cover}
                diffs={key:{"original":original[key],"replayed":value}
                       for key,value in computed.items()
                       if (abs(original[key]-value)>0.00011 if isinstance(value,float) and original[key] is not None
                           else original[key]!=value)}
                comparisons.append({"zone":zid,"match":not diffs,"differences":diffs})
            records.append({"time_utc":r["time_utc"],"granule":r["granule"],
                "sha256":actual_sha,"size_bytes":p.stat().st_size,
                "compared_zones":len(comparisons),"matching_zones":sum(x["match"] for x in comparisons),
                "differences":[x for x in comparisons if not x["match"]]})
            p.unlink()
    report={"schema_version":"0.1","deployment_status":"RESEARCH_ONLY","test_mode":"TEST_ONLY",
            "production_use":False,"production_ready":False,"activation_gate":"BLOCKED",
            "map_publishable":False,"engine_consumable":False,
            "method":"independent_polygon_area_weighted_recalculation_from_fresh_NASA_HDF5",
            "sample_policy":"first, last, two largest per-granule zone rates",
            "sampling_scope":"4 of 34 October 15/16 2026 IMERG Early v07",
            "source_archive_path":str(ARCHIVE.relative_to(ROOT)),
            "records":records,
            "granules_compared":len(records),
            "zone_interval_comparisons":sum(r["compared_zones"] for r in records),
            "zones_matching":sum(r["matching_zones"] for r in records),
            "validation_status":"SAMPLE_MATCH" if all(not r["differences"] for r in records) else "SAMPLE_DIFFERENCES",
            "limitation":"Only four of 34 intervals independently replayed; not full 34/34 scientific revalidation. No risk assessment."}
    output=Path("/tmp/irfen-scientific-replay/report.json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"validation_status":report["validation_status"],"granules":len(records),
                      "zone_matches":report["zones_matching"],"zone_total":report["zone_interval_comparisons"]}))
    if report["validation_status"]!="SAMPLE_MATCH":
        raise SystemExit("REPLAY_DIFFERENCES_REQUIRE_REVIEW")

if __name__=="__main__":
    run()
