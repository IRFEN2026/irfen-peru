#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json, os, re, tempfile
import numpy as np
import h5py
import earthaccess

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"config"/"historical_events.json"
ZONES=ROOT/"config"/"historical_zones.json"
OUT=ROOT/"site"/"data"/"history.json"

def find_dataset(group, names):
    for n in names:
        if n in group: return group[n]
        if f"Grid/{n}" in group: return group[f"Grid/{n}"]
    found=[]
    lows={x.lower() for x in names}
    def visit(name,obj):
        if isinstance(obj,h5py.Dataset) and name.split("/")[-1].lower() in lows:
            found.append(obj)
    group.visititems(visit)
    return found[0] if found else None

def read_grid(path):
    with h5py.File(path,"r") as f:
        latd=find_dataset(f,["lat","latitude"]); lond=find_dataset(f,["lon","longitude"])
        pd=find_dataset(f,["precipitation","precipitationCal","precipitationUncal"])
        if latd is None or lond is None or pd is None: raise RuntimeError("datasets no encontrados")
        lat=np.asarray(latd[:]).squeeze(); lon=np.asarray(lond[:]).squeeze()
        p=np.asarray(pd[:],dtype=float).squeeze()
        while p.ndim>2: p=p[0]
        if p.shape==(lon.size,lat.size): p=p.T
        p[p<0]=np.nan
        units=pd.attrs.get("units","")
        if isinstance(units,bytes): units=units.decode(errors="ignore")
        u=str(units).lower()
        if "mm/hr" in u or "mm h-1" in u or "mm/hour" in u: p=p*24.0
        return lat,lon,p,u

def area_mean(lat,lon,p,bbox):
    west,south,east,north=bbox
    yi=np.where((lat>=south)&(lat<=north))[0]; xi=np.where((lon>=west)&(lon<=east))[0]
    if len(yi)==0 or len(xi)==0: return None
    b=p[np.ix_(yi,xi)]
    return float(np.nanmean(b)) if np.isfinite(b).any() else None

def zone_mean(zone,lat,lon,p):
    vals=[]; ws=[]
    for a in zone["sampling_areas"]:
        v=area_mean(lat,lon,p,a["bbox"])
        if v is not None: vals.append(v*float(a.get("weight",1))); ws.append(float(a.get("weight",1)))
    return sum(vals)/sum(ws) if ws else None

def date_from_name(name):
    m=re.search(r"(20\d{2})(\d{2})(\d{2})",name)
    return datetime(int(m[1]),int(m[2]),int(m[3])).date() if m else None

def main():
    if not os.getenv("EARTHDATA_TOKEN"): raise SystemExit("Falta EARTHDATA_TOKEN")
    earthaccess.login(strategy="environment")
    ev=json.loads(EVENTS.read_text(encoding="utf-8"))["events"]
    zones={z["id"]:z for z in json.loads(ZONES.read_text(encoding="utf-8"))["zones"]}
    results=[]
    for e in ev:
        rec=dict(e)
        if not e.get("imerg") or not e.get("date"):
            rec["status"]="pre-IMERG o fecha pendiente"
            results.append(rec); continue
        d=datetime.fromisoformat(e["date"]).date()
        start=d-timedelta(days=7); end=d+timedelta(days=1)
        granules=earthaccess.search_data(short_name="GPM_3IMERGDF",version="07",
             temporal=(start.isoformat(),end.isoformat()),count=20)
        if not granules:
            rec["status"]="sin granulos"; results.append(rec); continue
        series=[]
        with tempfile.TemporaryDirectory(prefix="irfen_hist_") as td:
            paths=earthaccess.download(granules,local_path=td,threads=4,show_progress=False)
            for pp in map(Path,paths):
                dt=date_from_name(pp.name)
                if dt is None: continue
                try: lat,lon,p,u=read_grid(pp)
                except Exception: continue
                value=zone_mean(zones[e["zone_id"]],lat,lon,p)
                if value is not None: series.append({"date":dt.isoformat(),"rain_mm":round(value,2)})
        series=sorted({x["date"]:x for x in series}.values(),key=lambda x:x["date"])
        by={x["date"]:x["rain_mm"] for x in series}
        def total(n):
            vals=[by.get((d-timedelta(days=i)).isoformat()) for i in range(n)]
            return round(sum(vals),2) if all(v is not None for v in vals) else None
        rec.update({"status":"IMERG Final procesado","rain24":total(1),"rain72":total(3),"rain7d":total(7),"series":series})
        results.append(rec)
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"product":"GPM_3IMERGDF v07 Final","events":results}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Generado",OUT)

if __name__=="__main__": main()
