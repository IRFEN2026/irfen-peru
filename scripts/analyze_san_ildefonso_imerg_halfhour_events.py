#!/usr/bin/env python3
"""Compara intensidad IMERG 30 min en eventos San Ildefonso 2017/2023/2025.

Pregunta científica única: ¿la intensidad subdiaria distingue mejor el huaico
2023 de la activación controlada 2025 que los acumulados diarios? No deriva ni
promueve umbrales.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json, math, time
import requests
from shapely.geometry import box, shape

ROOT=Path(__file__).resolve().parents[1]
GEO=ROOT/'site/data/watersheds/san_ildefonso_watershed.geojson'
VAL=ROOT/'site/data/watersheds/san_ildefonso_validation.json'
OUT=ROOT/'site/data/calibration/san_ildefonso_imerg_halfhour_events.json'
SERVICE='https://gis.earthdata.nasa.gov/image/rest/services/GESDISC/GPM_3IMERGHH/ImageServer/getSamples'
EVENTS=[
    {'id':'SI-2017-03-15','date':'2017-03-15','outcome':'urban_debris_flow_impact','infrastructure_phase':'pre_integral_solution'},
    {'id':'SI-2023-03-10','date':'2023-03-10','outcome':'urban_debris_flow_impact','infrastructure_phase':'before_completion_of_35_dikes'},
    {'id':'SI-2025-03-29','date':'2025-03-29','outcome':'activation_controlled_no_san_ildefonso_urban_huaico','infrastructure_phase':'post_dike_system_pre_full_integral_completion'},
]
BLOCK_HOURS=8


def load_geom():
    v=json.loads(VAL.read_text(encoding='utf-8'))
    if str(v.get('status','')).upper()!='PASS': raise RuntimeError('San Ildefonso geometry not PASS')
    f=json.loads(GEO.read_text(encoding='utf-8'))
    return shape(f['geometry']).buffer(0),v


def cells_for(geom):
    minx,miny,maxx,maxy=geom.bounds
    ix0=math.floor((minx+180)/0.1)-1; ix1=math.floor((maxx+180)/0.1)+1
    iy0=math.floor((miny+90)/0.1)-1; iy1=math.floor((maxy+90)/0.1)+1
    cells=[]
    for ix in range(ix0,ix1+1):
        cx=-179.95+ix*0.1
        for iy in range(iy0,iy1+1):
            cy=-89.95+iy*0.1
            inter=geom.intersection(box(cx-.05,cy-.05,cx+.05,cy+.05))
            if not inter.is_empty and inter.area>0: cells.append({'lon':round(cx,5),'lat':round(cy,5),'weight':float(inter.area)})
    s=sum(c['weight'] for c in cells)
    for c in cells: c['weight']/=s
    return cells


def millis(v):
    if isinstance(v,(int,float)): return int(v)
    s=str(v or '').strip()
    if s.isdigit(): return int(s)
    try:return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
    except:return None


def sample(cells,start,end,session):
    geom=json.dumps({'points':[[c['lon'],c['lat']] for c in cells],'spatialReference':{'wkid':4326}})
    params={'geometry':geom,'geometryType':'esriGeometryMultipoint','time':f'{int(start.timestamp()*1000)},{int(end.timestamp()*1000)}','returnFirstValueOnly':'false','outFields':'StdTime','f':'json'}
    last=None
    for a in range(3):
        try:
            r=session.get(SERVICE,params=params,timeout=60); data=r.json()
            if r.status_code!=200 or data.get('error'): raise RuntimeError(f'HTTP {r.status_code}: {data}')
            return data.get('samples') or []
        except Exception as exc:
            last=exc
            if a<2: time.sleep(2*(a+1))
    raise RuntimeError(str(last))


def rolling(rows,n):
    best=None
    for i in range(n-1,len(rows)):
        ch=rows[i-n+1:i+1]
        if any(x['accum_mm'] is None for x in ch): continue
        total=sum(x['accum_mm'] for x in ch)
        if best is None or total>best['mm']: best={'mm':round(total,3),'start_utc':ch[0]['time_utc'],'end_utc':ch[-1]['time_utc']}
    return best


def analyze_event(meta,cells,session):
    d=datetime.fromisoformat(meta['date']).replace(tzinfo=timezone.utc)
    start=d-timedelta(hours=24); end=d+timedelta(hours=48)
    obs={}; cursor=start; requests_count=0; raw_samples=0; samples_with_time=0
    while cursor<end:
        block_end=min(end-timedelta(minutes=30),cursor+timedelta(hours=BLOCK_HOURS)-timedelta(minutes=30))
        batch=sample(cells,cursor,block_end,session); raw_samples+=len(batch)
        for s in batch:
            attrs=s.get('attributes') or {}
            tm=millis(attrs.get('StdTime',attrs.get('stdtime')))
            if tm is None: continue
            samples_with_time+=1
            loc=s.get('location') or {}; x=float(loc.get('x',0)); y=float(loc.get('y',0))
            idx=min(range(len(cells)),key=lambda i:(cells[i]['lon']-x)**2+(cells[i]['lat']-y)**2)
            try:v=float(s.get('value'))
            except:continue
            if v>=0: obs.setdefault(tm,{})[idx]=v
        requests_count+=1; cursor+=timedelta(hours=BLOCK_HOURS)
    rows=[]; dt=start
    while dt<end:
        vals=obs.get(int(dt.timestamp()*1000),{})
        weighted=[(v,cells[i]['weight']) for i,v in vals.items()]
        if weighted:
            sw=sum(w for _,w in weighted); rate=sum(v*w for v,w in weighted)/sw; accum=rate*.5
        else: rate=accum=None
        rows.append({'time_utc':dt.isoformat(),'rate_mm_hr':None if rate is None else round(rate,3),'accum_mm':None if accum is None else round(accum,3)})
        dt+=timedelta(minutes=30)
    valid=[x for x in rows if x['accum_mm'] is not None]
    peak=max(valid,key=lambda x:x['rate_mm_hr']) if valid else None
    return {**meta,'window_utc':{'start':start.isoformat(),'end_exclusive':end.isoformat()},'coverage_pct':round(100*len(valid)/len(rows),2),'batch_requests':requests_count,'raw_sample_count':raw_samples,'samples_with_time':samples_with_time,'peak_rate_mm_hr':None if not peak else peak['rate_mm_hr'],'peak_time_utc':None if not peak else peak['time_utc'],'max_30min':rolling(rows,1),'max_1h':rolling(rows,2),'max_3h':rolling(rows,6),'max_6h':rolling(rows,12),'max_24h':rolling(rows,48)}


def main():
    geom,val=load_geom(); cells=cells_for(geom)
    sess=requests.Session(); sess.headers.update({'User-Agent':'IRFEN-research/0.8'})
    cases=[analyze_event(e,cells,sess) for e in EVENTS]
    result={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'question':'Does sub-daily IMERG intensity discriminate damaging 2023 from controlled 2025 better than daily accumulation?','geometry':{'file':'data/watersheds/san_ildefonso_watershed.geojson','validation_status':val.get('status'),'area_km2':val.get('delineated_area_km2')},'source':{'institution':'NASA GES DISC / GPM IMERG','product':'GPM_3IMERGHH Final V07','spatial_resolution_deg':0.1,'temporal_resolution_minutes':30},'sampling_cells':cells,'cases':cases,'decision_gate':{'status':'REVIEW_AFTER_COMPARISON','rule':'No threshold from three cases. If 2023 does not show a materially stronger short-duration signal than 2025, require ground/local monitoring rather than lowering daily thresholds.'},'parser_note':'ArcGIS returned temporal field as lowercase stdtime; parser accepts both StdTime and stdtime.'}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':[{k:c.get(k) for k in ('id','coverage_pct','peak_rate_mm_hr','max_1h','max_3h','max_6h','max_24h')} for c in cases]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
