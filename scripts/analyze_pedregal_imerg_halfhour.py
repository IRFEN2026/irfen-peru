#!/usr/bin/env python3
"""Prueba decisiva de señal subdiaria para Pedregal, evento 23/03/2015.

Usa NASA Earthdata GIS IMERG Final Half-Hourly V07 sobre las celdas 0.1° que
intersectan el candidato Pedregal controlado por ANA. Agrupa puntos y bloques
temporales para evitar cientos de peticiones. No modifica umbrales ni producción.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json, math, time

import requests
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "site/data/watersheds/chosica_local_candidate_sets.geojson"
VALIDATION = ROOT / "site/data/calibration/pedregal_ana_validation.json"
OUT = ROOT / "site/data/calibration/pedregal_2015_imerg_halfhour.json"
SERVICE = "https://gis.earthdata.nasa.gov/image/rest/services/GESDISC/GPM_3IMERGHH/ImageServer/getSamples"
START = datetime(2015,3,22,0,0,tzinfo=timezone.utc)
END = datetime(2015,3,25,0,0,tzinfo=timezone.utc)
BLOCK_HOURS = 8  # <=17 half-hour slices, below service max mosaic image count 20


def load_candidate():
    val=json.loads(VALIDATION.read_text(encoding="utf-8"))
    if val.get("status") != "ANA_CONTROLLED_CANDIDATE":
        raise RuntimeError("Pedregal no ha superado control ANA")
    fc=json.loads(CANDIDATES.read_text(encoding="utf-8"))
    feat=next(f for f in fc["features"] if f.get("properties",{}).get("id")=="pedregal_3_8")
    return shape(feat["geometry"]).buffer(0)


def imerg_cells(geom):
    minx,miny,maxx,maxy=geom.bounds
    ix0=math.floor((minx+180.0)/0.1)-1; ix1=math.floor((maxx+180.0)/0.1)+1
    iy0=math.floor((miny+90.0)/0.1)-1; iy1=math.floor((maxy+90.0)/0.1)+1
    cells=[]
    for ix in range(ix0,ix1+1):
        cx=-179.95+ix*0.1
        for iy in range(iy0,iy1+1):
            cy=-89.95+iy*0.1
            inter=geom.intersection(box(cx-0.05,cy-0.05,cx+0.05,cy+0.05))
            if not inter.is_empty and inter.area>0:
                cells.append({"lon":round(cx,5),"lat":round(cy,5),"weight":float(inter.area)})
    total=sum(c["weight"] for c in cells)
    if not total: raise RuntimeError("Pedregal no intersecta ninguna celda IMERG")
    for c in cells: c["weight"]/=total
    return cells


def as_millis(value):
    if value is None: return None
    if isinstance(value,(int,float)): return int(value)
    s=str(value).strip()
    if s.isdigit(): return int(s)
    try:
        return int(datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()*1000)
    except Exception:
        return None


def sample_block(cells,start,end_inclusive,session):
    geom=json.dumps({"points":[[c["lon"],c["lat"]] for c in cells],"spatialReference":{"wkid":4326}})
    params={
        "geometry":geom,
        "geometryType":"esriGeometryMultipoint",
        "time":f"{int(start.timestamp()*1000)},{int(end_inclusive.timestamp()*1000)}",
        "returnFirstValueOnly":"false",
        "outFields":"StdTime",
        "f":"json",
    }
    last=None
    for attempt in range(3):
        try:
            r=session.get(SERVICE,params=params,timeout=60)
            data=r.json()
            if r.status_code!=200 or data.get("error"):
                raise RuntimeError(f"HTTP {r.status_code}: {data}")
            return data.get("samples") or []
        except Exception as exc:
            last=exc
            if attempt<2: time.sleep(2*(attempt+1))
    raise RuntimeError(f"NASA GIS batch falló {start.isoformat()}–{end_inclusive.isoformat()}: {last}")


def rolling_max(rows,n):
    best=None
    for i in range(n-1,len(rows)):
        chunk=rows[i-n+1:i+1]
        if any(x["accum_mm"] is None for x in chunk): continue
        total=sum(x["accum_mm"] for x in chunk)
        if best is None or total>best["mm"]:
            best={"mm":round(total,3),"start_utc":chunk[0]["time_utc"],"end_utc":chunk[-1]["time_utc"]}
    return best


def main():
    geom=load_candidate(); cells=imerg_cells(geom)
    session=requests.Session(); session.headers.update({"User-Agent":"IRFEN-research/0.8"})
    # keyed by exact half-hour epoch -> weighted values from intersecting cells
    observations={}
    cursor=START
    request_count=0
    while cursor<END:
        block_end=min(END-timedelta(minutes=30), cursor+timedelta(hours=BLOCK_HOURS)-timedelta(minutes=30))
        samples=sample_block(cells,cursor,block_end,session); request_count+=1
        for s in samples:
            attrs=s.get("attributes") or {}
            tm=as_millis(attrs.get("StdTime",attrs.get("stdtime")))
            if tm is None: continue
            loc=s.get("location") or {}
            x=float(loc.get("x",0)); y=float(loc.get("y",0))
            idx=min(range(len(cells)),key=lambda i:(cells[i]["lon"]-x)**2+(cells[i]["lat"]-y)**2)
            raw=s.get("value")
            try: value=float(raw)
            except Exception: continue
            if value<0: continue
            observations.setdefault(tm,{})[idx]=value
        cursor += timedelta(hours=BLOCK_HOURS)

    rows=[]; dt=START
    while dt<END:
        tm=int(dt.timestamp()*1000); vals=observations.get(tm,{})
        weighted=[(v,cells[i]["weight"]) for i,v in vals.items()]
        if weighted:
            sw=sum(w for _,w in weighted); rate=sum(v*w for v,w in weighted)/sw; accum=rate*0.5
        else: rate=accum=None
        rows.append({"time_utc":dt.isoformat(),"rate_mm_hr":None if rate is None else round(rate,3),"accum_mm":None if accum is None else round(accum,3),"sampled_cells":len(weighted)})
        dt+=timedelta(minutes=30)

    valid=[x for x in rows if x["accum_mm"] is not None]
    coverage=100.0*len(valid)/len(rows)
    peak=max(valid,key=lambda x:x["rate_mm_hr"]) if valid else None
    days={}
    for r in rows:
        if r["accum_mm"] is not None: days[r["time_utc"][:10]]=days.get(r["time_utc"][:10],0.0)+r["accum_mm"]
    result={
        "version":"0.8-experimental","production_use":False,"candidate_id":"pedregal_3_8",
        "event":"Chosica local debris flows 23/03/2015",
        "source":{"institution":"NASA GES DISC / GPM IMERG","product":"GPM_3IMERGHH Final V07","service":SERVICE.rsplit("/",1)[0],"spatial_resolution_deg":0.1,"temporal_resolution_minutes":30,"units_input":"mm/hr"},
        "window_utc":{"start":START.isoformat(),"end_exclusive":END.isoformat()},
        "sampling":{"intersecting_grid_cells":cells,"batch_requests":request_count,"expected_intervals":len(rows),"valid_intervals":len(valid),"coverage_pct":round(coverage,2)},
        "metrics":{"peak_rate_mm_hr":None if not peak else peak["rate_mm_hr"],"peak_rate_time_utc":None if not peak else peak["time_utc"],"max_30min":rolling_max(rows,1),"max_1h":rolling_max(rows,2),"max_3h":rolling_max(rows,6),"max_6h":rolling_max(rows,12),"max_24h":rolling_max(rows,48),"utc_calendar_day_totals_mm":{k:round(v,3) for k,v in days.items()}},
        "decision_gate":{"status":"REVIEW_AFTER_RESULT","rule":"No threshold is derived from this single event. Test only whether sub-daily satellite intensity adds signal relative to daily IMERG.","next_if_weak":"Require local ground/station or higher-fidelity rainfall evidence; do not tune daily thresholds to force detection."},
        "series":rows,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"coverage_pct":round(coverage,2),"batch_requests":request_count,"metrics":result["metrics"]},ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
