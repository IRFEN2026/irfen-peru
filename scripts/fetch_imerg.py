#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse, json, os, re, tempfile
import numpy as np
import h5py
import earthaccess

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config' / 'zones.json'
OUT = ROOT / 'site' / 'data' / 'latest.json'
HISTORY_OUT = ROOT / 'site' / 'data' / 'history.json'

def load_config():
    return json.loads(CONFIG.read_text(encoding='utf-8'))

def date_from_name(path: Path):
    m = re.search(r'(20\d{2})(\d{2})(\d{2})', path.name)
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date() if m else None

def find_dataset(group, preferred):
    for name in preferred:
        if name in group: return group[name]
        p=f'Grid/{name}'
        if p in group: return group[p]
    found=[]
    wanted={x.lower() for x in preferred}
    def visitor(name,obj):
        if isinstance(obj,h5py.Dataset) and name.split('/')[-1].lower() in wanted:
            found.append(obj)
    group.visititems(visitor)
    return found[0] if found else None

def read_daily_grid(path: Path):
    with h5py.File(path,'r') as f:
        lat_ds=find_dataset(f,['lat','latitude']); lon_ds=find_dataset(f,['lon','longitude'])
        p_ds=find_dataset(f,['precipitation','precipitationCal','precipitationUncal'])
        if lat_ds is None or lon_ds is None or p_ds is None:
            raise RuntimeError(f'No se encontraron lat/lon/precipitation en {path.name}')
        lat=np.asarray(lat_ds[:]).squeeze(); lon=np.asarray(lon_ds[:]).squeeze(); p=np.asarray(p_ds[:],dtype=float).squeeze()
        while p.ndim>2: p=p[0]
        if p.shape==(lon.size,lat.size): p=p.T
        elif p.shape!=(lat.size,lon.size): raise RuntimeError(f'Dimensiones inesperadas {p.shape}')
        p[p<0]=np.nan
        units=p_ds.attrs.get('units','')
        if isinstance(units,bytes): units=units.decode(errors='ignore')
        units=str(units).lower()
        if 'mm/hr' in units or 'mm h-1' in units or 'mm/hour' in units: p*=24.0
        return lat,lon,p,units

def area_mean(lat,lon,grid,bbox):
    west,south,east,north=bbox
    yi=np.where((lat>=south)&(lat<=north))[0]; xi=np.where((lon>=west)&(lon<=east))[0]
    if not len(yi) or not len(xi): return None,0
    block=grid[np.ix_(yi,xi)]
    return (float(np.nanmean(block)),int(np.isfinite(block).sum())) if np.isfinite(block).any() else (None,0)

def weighted_zone_mean(zone,lat,lon,grid):
    total=0.0; tw=0.0; details=[]
    for area in zone['sampling_areas']:
        value,cells=area_mean(lat,lon,grid,area['bbox']); w=float(area.get('weight',1))
        details.append({'area':area['name'],'mean_mm':None if value is None else round(value,2),'cells':cells,'weight':w})
        if value is not None: total+=value*w; tw+=w
    return (total/tw if tw else None),details

def search_granules(start,end):
    errors=[]
    for version in ('08','07'):
        try:
            g=earthaccess.search_data(short_name='GPM_3IMERGDL',version=version,temporal=(start.isoformat(),end.isoformat()),count=30)
            if g: return g,version
        except Exception as e: errors.append(f'V{version}: {e}')
    g=earthaccess.search_data(short_name='GPM_3IMERGDL',temporal=(start.isoformat(),end.isoformat()),count=30)
    if g: return g,'auto'
    raise RuntimeError('No se encontraron granulos. '+' | '.join(errors))

def build_payload(config,series,version,warning=None):
    output=[]
    for z in config['zones']:
        items=sorted(series.get(z['id'],[]),key=lambda x:x['date'])
        vals=[x['rain_mm'] for x in items if x['rain_mm'] is not None]
        r24=vals[-1] if len(vals)>=1 else None; r72=sum(vals[-3:]) if len(vals)>=3 else None; r7=sum(vals[-7:]) if len(vals)>=7 else None
        output.append({'id':z['id'],'name':z['name'],'region':z['region'],'hazard':z['hazard'],'impact_score':z['impact_score'],'thresholds_provisional':z['thresholds_provisional'],'rain24':None if r24 is None else round(r24,2),'rain72':None if r72 is None else round(r72,2),'rain7d':None if r7 is None else round(r7,2),'days_available':len(vals),'series':items[-14:]})
    return {'schema_version':'0.5','generated_at':datetime.now(timezone.utc).isoformat(),'source':'NASA GPM IMERG Late Daily','product':'GPM_3IMERGDL','product_version':version,'warning':warning or 'IMERG es fuente satelital complementaria. Umbrales y áreas de muestreo son preliminares; validar con SENAMHI y delimitaciones hidrológicas.','zones':output}

def demo_payload(config):
    today=datetime.now(timezone.utc).date(); samples={'san_ildefonso':[3,4.5,8,10,15,17,20],'chosica':[1,2,5,7,9,11,13],'catacaos':[10,14,18,22,25,30,34]}; series={}
    for z in config['zones']:
        series[z['id']]=[{'date':(today-timedelta(days=6-i)).isoformat(),'rain_mm':v} for i,v in enumerate(samples[z['id']])]
    return build_payload(config,series,'DEMO','Datos demostrativos; NASA no consultada.')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--demo',action='store_true'); ap.add_argument('--days',type=int,default=10); args=ap.parse_args(); config=load_config()
    if args.demo:
        payload=demo_payload(config); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); print('DEMO:',OUT); return
    if not os.getenv('EARTHDATA_TOKEN'): raise SystemExit('Falta EARTHDATA_TOKEN')
    earthaccess.login(strategy='environment')
    end=datetime.now(timezone.utc).date(); start=end-timedelta(days=args.days+2); granules,version=search_granules(start,end); print('Granulos:',len(granules),'version',version)
    series={z['id']:[] for z in config['zones']}
    with tempfile.TemporaryDirectory(prefix='irfen_imerg_') as td:
        paths=earthaccess.download(granules,local_path=td,threads=4,show_progress=True)
        for p in sorted(map(Path,paths)):
            dt=date_from_name(p)
            if dt is None: continue
            try: lat,lon,grid,units=read_daily_grid(p)
            except Exception as e: print('Error',p.name,e); continue
            for z in config['zones']:
                mean,details=weighted_zone_mean(z,lat,lon,grid)
                if mean is not None: series[z['id']].append({'date':dt.isoformat(),'rain_mm':round(mean,2),'sampling':details,'units_source':units})
    for zid,items in series.items():
        by={x['date']:x for x in items}; series[zid]=[by[k] for k in sorted(by)]
    payload=build_payload(config,series,version); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    HISTORY_OUT.write_text(json.dumps({'generated_at':payload['generated_at'],'zones':series},ensure_ascii=False,indent=2),encoding='utf-8'); print('Actualizado:',OUT)

if __name__=='__main__': main()
