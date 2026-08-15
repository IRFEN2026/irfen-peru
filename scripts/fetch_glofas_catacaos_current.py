#!/usr/bin/env python3
"""Obtiene el proxy fluvial categórico actual de GloFAS para Catacaos.

Uso experimental secundario. SENAMHI/PHISIS tiene prioridad cuando exista un
estado/caudal oficial disponible. No convierte capas GloFAS a m3/s ni genera
alertas de producción.
"""
from __future__ import annotations
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import xml.etree.ElementTree as ET

import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
VALID=SITE/'data/hydrology/glofas_catacaos_probe.json'
OUT=SITE/'data/hydrology/glofas_catacaos_current.json'
WMS='https://ows.globalfloods.eu/glofas-ows/ows.py'
PUBLIC_FALLBACK='https://irfen2026.github.io/irfen-peru/data/hydrology/glofas_catacaos_current.json'
WEST,SOUTH,EAST,NORTH=-80.75252564,-5.31538835,-80.60180695,-5.20222687
LAYERS={
    'rp5':'sumALHEGE','rp20':'sumALEEGE',
    'days_1_3':'sumAL41EGE','days_4_10':'sumAL42EGE','days_11_15':'sumAL43EGE',
}
HEAD={'User-Agent':'IRFEN-research/0.8 (+public CEMS WMS operational test)'}


def previous_valid():
    """Recupera solo la última señal válida como contexto, nunca como dato actual."""
    candidates=[]
    if OUT.exists():
        try:candidates.append(json.loads(OUT.read_text(encoding='utf-8')))
        except Exception:pass
    try:
        r=requests.get(PUBLIC_FALLBACK,params={'fallback':int(datetime.now(timezone.utc).timestamp())},headers=HEAD,timeout=(8,30))
        r.raise_for_status();candidates.append(r.json())
    except (requests.RequestException,ValueError,OSError):
        pass
    previous=next((x for x in candidates if x.get('status')=='available'),None)
    if not previous:return None
    return {
        'generated_at':previous.get('generated_at'),
        'source':previous.get('source'),
        'river_proxy_class':previous.get('river_proxy_class'),
        'forecast_signal':previous.get('forecast_signal'),
        'signals':previous.get('signals'),
        'usable_as_current':False,
    }


def contingency(error):
    return {
        'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,'status':'SOURCE_TEMPORARILY_UNREACHABLE',
        'usable_for_experimental_decision':False,'stale':True,
        'source':'Copernicus Emergency Management Service / GloFAS WMS',
        'role':'secondary_categorical_modelled_river_proxy',
        'authority_priority':'Use SENAMHI/PHISIS observed or forecast river state when available.',
        'source_error':{'type':type(error).__name__,'message':str(error)[:500]},
        'last_valid':previous_valid(),
        'interpretation':'La indisponibilidad de GloFAS no equivale a ausencia de peligro. La señal previa se conserva solo como contexto y no se usa como estado fluvial actual.',
    }


def lname(tag): return tag.split('}')[-1]
def child_text(node,name):
    for c in list(node):
        if lname(c.tag)==name:return (c.text or '').strip()
    return None

def layer_meta(root):
    out={}
    for n in root.iter():
        if lname(n.tag)!='Layer':continue
        name=child_text(n,'Name')
        if not name:continue
        dim=None
        for c in list(n):
            if lname(c.tag) in ('Dimension','Extent') and (c.attrib.get('name') or '').lower()=='time':
                dim=(c.text or '').strip();break
        out[name]={'title':child_text(n,'Title'),'time_dimension':dim}
    return out

def latest_time(dim):
    if not dim:return None
    if ',' in dim:
        vals=[x.strip() for x in dim.split(',') if x.strip()];return vals[-1] if vals else None
    parts=dim.split('/')
    return parts[1] if len(parts)>=2 else dim

def map_signal(session,layer,time_value):
    params={
        'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap','LAYERS':layer,'STYLES':'',
        'CRS':'EPSG:4326','BBOX':f'{SOUTH},{WEST},{NORTH},{EAST}',
        'WIDTH':'600','HEIGHT':'450','FORMAT':'image/png','TRANSPARENT':'TRUE','TIME':time_value,
    }
    r=session.get(WMS,params=params,timeout=(15,60));r.raise_for_status()
    if not r.content.startswith(b'\x89PNG'):raise RuntimeError(f'{layer} no devolvió PNG')
    img=Image.open(BytesIO(r.content)).convert('RGBA')
    visible=[p for p in img.getdata() if p[3]>0]
    colours={p for p in visible}
    return {
        'layer':layer,'time':time_value,'signal':bool(visible),
        'visible_pixel_count':len(visible),
        'visible_pixel_pct':round(100*len(visible)/(img.width*img.height),5),
        'unique_visible_colours':len(colours),
    }

def main():
    validation=json.loads(VALID.read_text(encoding='utf-8')) if VALID.exists() else {}
    if validation.get('status')!='GLOFAS_PROXY_MINIMUM_VALIDATION_PASS':
        payload={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'status':'BLOCKED_BY_PROXY_VALIDATION','validation_status':validation.get('status'),'usable_for_experimental_decision':False}
    else:
        try:
            s=requests.Session();s.headers.update(HEAD)
            cap=s.get(WMS,params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetCapabilities'},timeout=(15,60));cap.raise_for_status()
            meta=layer_meta(ET.fromstring(cap.content)); signals={}
            for key,layer in LAYERS.items():
                m=meta.get(layer)
                if not m: signals[key]={'layer':layer,'available':False,'signal':False};continue
                t=latest_time(m.get('time_dimension'))
                signals[key]={**map_signal(s,layer,t),'available':True,'title':m.get('title')}
            if signals['rp20'].get('signal'): river_class='MODELLED_20Y_EXCEEDANCE'
            elif signals['rp5'].get('signal'): river_class='MODELLED_5Y_EXCEEDANCE'
            else: river_class='NO_MODELLED_RETURN_PERIOD_EXCEEDANCE'
            payload={
                'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),
                'production_use':False,'status':'available','usable_for_experimental_decision':True,'stale':False,
                'source':'Copernicus Emergency Management Service / GloFAS WMS',
                'role':'secondary_categorical_modelled_river_proxy',
                'authority_priority':'Use SENAMHI/PHISIS observed or forecast river state when available.',
                'bbox_wgs84':{'west':WEST,'south':SOUTH,'east':EAST,'north':NORTH},
                'river_proxy_class':river_class,'signals':signals,
                'forecast_signal':{
                    'days_1_3':bool(signals['days_1_3'].get('signal')),
                    'days_4_10':bool(signals['days_4_10'].get('signal')),
                    'days_11_15':bool(signals['days_11_15'].get('signal')),
                },
                'interpretation':'Categorical GloFAS signal only. It is not an observed discharge and must never be labelled m3/s.',
                'validation_reference':'data/hydrology/glofas_catacaos_probe.json',
            }
        except (requests.RequestException,ET.ParseError,OSError,RuntimeError,ValueError) as exc:
            payload=contingency(exc)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
