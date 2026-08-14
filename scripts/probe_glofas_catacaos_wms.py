#!/usr/bin/env python3
"""Validación mínima final de GloFAS como proxy secundario para Catacaos.

Controles positivos: Niño Costero 2017 y crecida/desborde Piura marzo 2023.
Control negativo: estiaje 14/08/2026. SENAMHI/PHISIS sigue siendo la autoridad
principal. GloFAS no se convierte en caudal observado ni modifica producción.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
import json
import xml.etree.ElementTree as ET

import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/glofas_catacaos_probe.json'
WMS='https://ows.globalfloods.eu/glofas-ows/ows.py'
HEAD={'User-Agent':'IRFEN-research/0.8 (+public CEMS WMS validation)'}
WEST,SOUTH,EAST,NORTH=-80.75252564,-5.31538835,-80.60180695,-5.20222687
LAYERS=['sumALHEGE','sumALEEGE','sumAL41EGE','sumAL42EGE','sumAL43EGE','UpstreamArea']
CONTROL_DATES=[
    {
        'id':'piura_2017_pre_event','time':'2017-03-26T00:00Z','role':'known_extreme_flood_control',
        'official_context':'Río Piura overflow 27/03/2017; official historical reference 3468 m3/s in IRFEN ANA/SIGRID catalogue.'
    },
    {
        'id':'piura_2017_event_day','time':'2017-03-27T00:00Z','role':'known_extreme_flood_control',
        'official_context':'Río Piura overflow 27/03/2017; official historical reference 3468 m3/s in IRFEN ANA/SIGRID catalogue.'
    },
    {
        'id':'piura_2023_nacara_orange','time':'2023-03-11T00:00Z','role':'known_high_flow_control',
        'official_context':'INDECI/SENAMHI: Puente Ñácara 925.41 m3/s, hydrological orange threshold on 11/03/2023.'
    },
    {
        'id':'piura_2023_tambogrande_overflow','time':'2023-03-14T00:00Z','role':'known_overflow_control',
        'official_context':'Official public reporting: Río Piura overflow at Tambogrande on 14/03/2023, approximately 1415 m3/s at that location.'
    },
    {
        'id':'piura_2026_dry','time':'2026-08-14T00:00Z','role':'dry_season_control',
        'official_context':'Dry-season control; SENAMHI short-term Puente Ñácara forecast is only published during avenida.'
    },
]


def lname(tag): return tag.split('}')[-1]
def child_text(node,name):
    for c in list(node):
        if lname(c.tag)==name:return (c.text or '').strip()
    return None

def layers(root):
    out={}
    for n in root.iter():
        if lname(n.tag)!='Layer':continue
        name=child_text(n,'Name')
        if not name:continue
        dims={}
        for c in list(n):
            if lname(c.tag) in ('Dimension','Extent'):
                key=c.attrib.get('name') or c.attrib.get('Name')
                if key:dims[key]=(c.text or '').strip()
        out[name]={'title':child_text(n,'Title'),'queryable':n.attrib.get('queryable')=='1','dimensions':dims}
    return out

def time_supported(dim,value):
    if not dim:return True
    if ',' in dim:return value in [x.strip() for x in dim.split(',')]
    parts=dim.split('/')
    if len(parts)>=2:return parts[0] <= value <= parts[1]
    return value==dim

def map_profile(session,layer,time_value=None):
    params={
        'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap','LAYERS':layer,
        'STYLES':'','CRS':'EPSG:4326','BBOX':f'{SOUTH},{WEST},{NORTH},{EAST}',
        'WIDTH':'600','HEIGHT':'450','FORMAT':'image/png','TRANSPARENT':'TRUE',
    }
    if time_value:params['TIME']=time_value
    try:
        r=session.get(WMS,params=params,timeout=(15,60))
        row={'status':r.status_code,'bytes':len(r.content),'content_type':r.headers.get('content-type'),'url':r.url}
        if r.status_code!=200 or not r.content.startswith(b'\x89PNG'):
            row['image_ok']=False
            row['preview']=r.text[:1000] if 'text' in (r.headers.get('content-type') or '') else None
            row['has_rendered_signal']=False
            return row
        img=Image.open(BytesIO(r.content)).convert('RGBA')
        visible=[p for p in img.getdata() if p[3]>0]
        colours={p for p in visible}
        row.update({
            'image_ok':True,'width':img.width,'height':img.height,
            'visible_pixel_count':len(visible),
            'visible_pixel_pct':round(100*len(visible)/(img.width*img.height),5),
            'unique_visible_colours':len(colours),
            'visible_colour_sample':[list(x) for x in sorted(colours)[:30]],
            'has_rendered_signal':len(visible)>0,
        })
        return row
    except Exception as exc:
        return {'error_type':type(exc).__name__,'error':str(exc),'image_ok':False,'has_rendered_signal':False}

def main():
    result={
        'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,'role':'secondary_modelled_river_proxy_only',
        'authority_priority':['SENAMHI/PHISIS observed or forecast river state','GloFAS/Copernicus modelled flood signal'],
        'wms':WMS,'bbox_wgs84':{'west':WEST,'south':SOUTH,'east':EAST,'north':NORTH},
        'control_dates':CONTROL_DATES,
        'validation_rule':'Minimum prototype gate requires signal in 2017 extreme event, signal in at least one independent 2023 high-flow/overflow control, and no signal in 2026 dry control. This validates only categorical proxy usefulness, not discharge magnitude.'
    }
    s=requests.Session();s.headers.update(HEAD)
    try:
        r=s.get(WMS,params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetCapabilities'},timeout=(15,60));r.raise_for_status()
        by=layers(ET.fromstring(r.content))
        result['capabilities']={'status':r.status_code,'bytes':len(r.content),'layer_count':len(by)}
        result['layer_tests']={}
        for layer in LAYERS:
            rec=by.get(layer)
            if not rec:
                result['layer_tests'][layer]={'available':False};continue
            item={'available':True,'title':rec['title'],'queryable':rec['queryable'],'dimensions':rec['dimensions'],'maps':[]}
            if layer=='UpstreamArea':
                item['maps'].append({'id':'static_network',**map_profile(s,layer,None)})
            else:
                dim=rec['dimensions'].get('time') or rec['dimensions'].get('TIME')
                for c in CONTROL_DATES:
                    item['maps'].append({**c,**map_profile(s,layer,c['time'])}) if time_supported(dim,c['time']) else item['maps'].append({**c,'time_supported':False,'has_rendered_signal':False})
            result['layer_tests'][layer]=item

        flood_layers=('sumALHEGE','sumALEEGE','sumAL41EGE','sumAL42EGE','sumAL43EGE')
        evidence_by_control={c['id']:[] for c in CONTROL_DATES}
        for layer in flood_layers:
            for m in result['layer_tests'].get(layer,{}).get('maps',[]):
                if m.get('has_rendered_signal'):
                    evidence_by_control.setdefault(m['id'],[]).append({'layer':layer,'visible_pixel_count':m.get('visible_pixel_count'),'visible_pixel_pct':m.get('visible_pixel_pct')})
        signal=lambda cid:bool(evidence_by_control.get(cid))
        event2017=signal('piura_2017_pre_event') or signal('piura_2017_event_day')
        event2023=signal('piura_2023_nacara_orange') or signal('piura_2023_tambogrande_overflow')
        dry2026=signal('piura_2026_dry')
        result['validation_summary']={
            'known_2017_extreme_event_signal':event2017,
            'independent_2023_high_flow_or_overflow_signal':event2023,
            'dry_2026_signal':dry2026,
            'evidence_by_control':evidence_by_control,
        }
        if event2017 and event2023 and not dry2026:
            result['status']='GLOFAS_PROXY_MINIMUM_VALIDATION_PASS'
            result['decision']='Accept as experimental secondary categorical river-state proxy for Catacaos. Keep SENAMHI/PHISIS primary. Do not infer m3/s; use only official GloFAS exceedance/signal classes with provenance and freshness.'
        elif event2017 and not dry2026:
            result['status']='GLOFAS_PROXY_VALIDATION_INCOMPLETE'
            result['decision']='2017 extreme is detected and dry control is clean, but independent 2023 control is not detected. Do not integrate as Catacaos decision input yet.'
        else:
            result['status']='GLOFAS_PROXY_NOT_VALIDATED_FOR_CATACAOS'
            result['decision']='Close GloFAS as automatic Catacaos river-state proxy. Keep river state as external SENAMHI/PHISIS input requirement.'
    except Exception as exc:
        result['status']='GLOFAS_WMS_ACCESS_OR_PARSE_ERROR';result['error_type']=type(exc).__name__;result['error']=str(exc);result['decision']='Close proxy route unless documented CEMS WMS changes.'
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'validation_summary':result.get('validation_summary'),'decision':result['decision']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
