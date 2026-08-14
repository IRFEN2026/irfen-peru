#!/usr/bin/env python3
"""Prueba decisiva de señal subdiaria para Pedregal, evento 23/03/2015.

Consulta NASA Earthdata GIS IMERG Final Half-Hourly V07 sobre las celdas 0.1°
que intersectan el candidato Pedregal controlado por ANA. No modifica umbrales
ni producción. Si la señal subdiaria no discrimina el evento, la siguiente
puerta es observación terrestre/local, no retocar la fórmula diaria.
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
END = datetime(2015,3,25,0,0,tzinfo=timezone.utc)  # exclusive: 72 h


def load_candidate():
    val = json.loads(VALIDATION.read_text(encoding="utf-8"))
    if val.get("status") != "ANA_CONTROLLED_CANDIDATE":
        raise RuntimeError("Pedregal no ha superado control ANA")
    fc = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    feat = next(f for f in fc["features"] if f.get("properties",{}).get("id") == "pedregal_3_8")
    return shape(feat["geometry"]).buffer(0), feat["properties"]


def imerg_cells(geom):
    # IMERG 0.1° usa centros ... .05; generamos celdas que intersectan el polígono.
    minx,miny,maxx,maxy = geom.bounds
    ix0 = math.floor((minx + 180.0)/0.1)-1
    ix1 = math.floor((maxx + 180.0)/0.1)+1
    iy0 = math.floor((miny + 90.0)/0.1)-1
    iy1 = math.floor((maxy + 90.0)/0.1)+1
    cells=[]
    for ix in range(ix0, ix1+1):
        cx=-179.95 + ix*0.1
        for iy in range(iy0, iy1+1):
            cy=-89.95 + iy*0.1
            cell=box(cx-0.05,cy-0.05,cx+0.05,cy+0.05)
            inter=geom.intersection(cell)
            if not inter.is_empty and inter.area>0:
                cells.append({"lon":round(cx,5),"lat":round(cy,5),"weight":float(inter.area)})
    s=sum(c["weight"] for c in cells)
    for c in cells: c["weight"] /= s
    return cells


def get_value(lon,lat,dt,session):
    geom=json.dumps({"x":lon,"y":lat,"spatialReference":{"wkid":4326}})
    params={
        "geometry":geom,
        "geometryType":"esriGeometryPoint",
        "time":str(int(dt.timestamp()*1000)),
        "returnFirstValueOnly":"true",
        "outFields":"StdTime",
        "f":"json",
    }
    last=None
    for attempt in range(3):
        try:
            r=session.get(SERVICE,params=params,timeout=30)
            data=r.json()
            if r.status_code!=200 or data.get("error"):
                raise RuntimeError(f"HTTP {r.status_code}: {data}")
            samples=data.get("samples") or []
            if not samples: return None
            raw=samples[0].get("value")
            if raw in (None,"NoData"): return None
            v=float(raw)
            return None if v<0 else v
        except Exception as exc:
            last=exc
            if attempt<2: time.sleep(1.5*(attempt+1))
    raise RuntimeError(f"NASA GIS getSamples falló {dt.isoformat()} {lon},{lat}: {last}")


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
    geom, props=load_candidate(); cells=imerg_cells(geom)
    session=requests.Session(); session.headers.update({"User-Agent":"IRFEN-research/0.8"})
    rows=[]; dt=START
    while dt<END:
        vals=[]
        for c in cells:
            v=get_value(c["lon"],c["lat"],dt,session)
            if v is not None: vals.append((v,c["weight"]))
        if vals:
            sw=sum(w for _,w in vals); rate=sum(v*w for v,w in vals)/sw
            accum=rate*0.5  # mm/hr representative of 30-minute interval
        else:
            rate=accum=None
        rows.append({"time_utc":dt.isoformat(),"rate_mm_hr":None if rate is None else round(rate,3),"accum_mm":None if accum is None else round(accum,3)})
        dt += timedelta(minutes=30)

    valid=[x for x in rows if x["accum_mm"] is not None]
    coverage=100.0*len(valid)/len(rows)
    peak=max(valid,key=lambda x:x["rate_mm_hr"]) if valid else None
    days={}
    for r in rows:
        day=r["time_utc"][:10]
        if r["accum_mm"] is not None: days.setdefault(day,0.0); days[day]+=r["accum_mm"]
    result={
        "version":"0.8-experimental",
        "production_use":False,
        "candidate_id":"pedregal_3_8",
        "event":"Chosica local debris flows 23/03/2015",
        "source":{
            "institution":"NASA GES DISC / GPM IMERG",
            "product":"GPM_3IMERGHH Final V07",
            "service":SERVICE.rsplit("/",1)[0],
            "spatial_resolution_deg":0.1,
            "temporal_resolution_minutes":30,
            "units_input":"mm/hr",
        },
        "window_utc":{"start":START.isoformat(),"end_exclusive":END.isoformat()},
        "sampling":{"intersecting_grid_cells":cells,"expected_intervals":len(rows),"valid_intervals":len(valid),"coverage_pct":round(coverage,2)},
        "metrics":{
            "peak_rate_mm_hr":None if not peak else peak["rate_mm_hr"],
            "peak_rate_time_utc":None if not peak else peak["time_utc"],
            "max_30min":rolling_max(rows,1),
            "max_1h":rolling_max(rows,2),
            "max_3h":rolling_max(rows,6),
            "max_6h":rolling_max(rows,12),
            "max_24h":rolling_max(rows,48),
            "utc_calendar_day_totals_mm":{k:round(v,3) for k,v in days.items()},
        },
        "decision_gate":{
            "status":"REVIEW_AFTER_RESULT",
            "rule":"No threshold is derived from this single event. This test only determines whether sub-daily satellite intensity adds discriminating signal relative to daily IMERG.",
            "next_if_weak":"Require local ground/station or higher-fidelity rainfall evidence; do not tune daily thresholds to force detection.",
        },
        "series":rows,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"coverage_pct":result["sampling"]["coverage_pct"],"metrics":result["metrics"]},ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
