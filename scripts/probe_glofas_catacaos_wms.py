#!/usr/bin/env python3
"""Prueba final acotada de GloFAS WMS como proxy secundario para Catacaos.

Valida el camino raster oficial con dos controles: Niño Costero 2017 y estiaje
14/08/2026. SENAMHI/PHISIS sigue siendo la autoridad principal. GloFAS nunca se
convierte en caudal observado ni modifica producción en esta prueba.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
import json, re
import xml.etree.ElementTree as ET

import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/glofas_catacaos_probe.json'
WMS='https://ows.globalfloods.eu/glofas-ows/ows.py'
HEAD={'User-Agent':'IRFEN-research/0.8 (+public CEMS WMS validation)'}
# Extensión oficial documental Catacaos/INDECI 2011 ya almacenada en IRFEN.
WEST,SOUTH,EAST,NORTH=-80.75252564,-5.31538835,-80.60180695,-5.20222687
LAYERS=['sumALHEGE','sumALEEGE','sumAL41EGE','sumAL42EGE','sumAL43EGE','UpstreamArea']
CONTROL_DATES=[
    {'id':'piura_2017_pre_event','time':'2017-03-26T00:00Z','role':'known_flood_event_forecast_control'},
    {'id':'piura_2017_event_day','time':'2017-03-27T00:00Z','role':'known_flood_event_forecast_control'},
    {'id':'piura_2026_dry','time':'2026-08-14T00:00Z','role':'dry_season_control'},
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
    if len(parts)>=2:
        # ISO strings sort chronologically for the fixed UTC format used here.
        return parts[0] <= value <= parts[1]
    return value==dim

def map_profile(session,layer,time_value=None):
    # WMS 1.3 + EPSG:4326 axis order = latitude,longitude.
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
            row['image_ok']=False; row['preview']=r.text[:1000] if 'text' in (r.headers.get('content-type') or '') else None; return row
        img=Image.open(BytesIO(r.content)).convert('RGBA')
        px=list(img.getdata()); visible=[p for p in px if p[3]>0]
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
    }
    s=requests.Session();s.headers.update(HEAD)
    try:
        r=s.get(WMS,params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetCapabilities'},timeout=(15,60));r.raise_for_status()
        root=ET.fromstring(r.content); by=layers(root)
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
                    if time_supported(dim,c['time']):item['maps'].append({**c,**map_profile(s,layer,c['time'])})
                    else:item['maps'].append({**c,'time_supported':False,'has_rendered_signal':False})
            result['layer_tests'][layer]=item
        network_signal=any(x.get('has_rendered_signal') for x in result['layer_tests'].get('UpstreamArea',{}).get('maps',[]))
        historic_signal=False; dry_signal=False
        evidence=[]
        for layer in ('sumALHEGE','sumALEEGE','sumAL41EGE','sumAL42EGE','sumAL43EGE'):
            for m in result['layer_tests'].get(layer,{}).get('maps',[]):
                if m.get('id') in ('piura_2017_pre_event','piura_2017_event_day') and m.get('has_rendered_signal'):
                    historic_signal=True;evidence.append({'layer':layer,'control':m['id'],'visible_pixel_count':m.get('visible_pixel_count')})
                if m.get('id')=='piura_2026_dry' and m.get('has_rendered_signal'):
                    dry_signal=True
        result['validation_summary']={'lisflood_network_rendered_in_catacaos_bbox':network_signal,'known_2017_event_has_forecast_signal':historic_signal,'dry_2026_has_forecast_signal':dry_signal,'historic_signal_evidence':evidence}
        if network_signal and historic_signal and not dry_signal:
            result['status']='GLOFAS_PROXY_VALIDATION_PROMISING'
            result['decision']='Proceed only to calibration against official Piura flow/event references; use GloFAS return-period signal as secondary proxy, not m3/s and not a SENAMHI replacement.'
        elif network_signal and historic_signal:
            result['status']='GLOFAS_PROXY_NEEDS_FALSE_ALARM_REVIEW'
            result['decision']='Historical event is detected but dry/current map also renders signal; inspect legend/pixel semantics before any use.'
        else:
            result['status']='GLOFAS_PROXY_NOT_VALIDATED_FOR_CATACAOS'
            result['decision']='Close GloFAS as automatic Catacaos river-state proxy. Keep river state as external SENAMHI/PHISIS input requirement.'
    except Exception as exc:
        result['status']='GLOFAS_WMS_ACCESS_OR_PARSE_ERROR';result['error_type']=type(exc).__name__;result['error']=str(exc);result['decision']='Close proxy route unless documented CEMS WMS changes.'
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'validation_summary':result.get('validation_summary'),'decision':result['decision']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
