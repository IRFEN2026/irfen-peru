#!/usr/bin/env python3
"""Prueba acotada de GloFAS WMS como proxy fluvial secundario para Catacaos.

GloFAS/Copernicus NO sustituye a SENAMHI. La prueba verifica únicamente si las
capas oficiales abiertas de probabilidad de excedencia de periodo de retorno
son consultables sobre el ámbito Catacaos/Bajo Piura desde GitHub Actions.
No modifica alertas ni transforma clases GloFAS en caudales m3/s.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, re
import xml.etree.ElementTree as ET

import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/glofas_catacaos_probe.json'
WMS='https://ows.globalfloods.eu/glofas-ows/ows.py'
# Puntos sobre/adyacentes al corredor documentado Catacaos-Piura; la prueba usa
# varios puntos para no depender de que un único píxel coincida con la red.
POINTS=[
    {'id':'catacaos_north','lon':-80.665,'lat':-5.235},
    {'id':'catacaos_centre','lon':-80.665,'lat':-5.260},
    {'id':'catacaos_south','lon':-80.665,'lat':-5.285},
    {'id':'la_legua_context','lon':-80.650,'lat':-5.300},
]
TARGET_LAYERS=['sumAL41EGE','sumAL42EGE','sumAL43EGE','sumALHEGE','sumALEEGE','reportingPoints','UpstreamArea']
HEAD={'User-Agent':'IRFEN-research/0.8 (+public CEMS WMS test)'}


def lname(tag): return tag.split('}')[-1]


def child_text(node,name):
    for c in list(node):
        if lname(c.tag)==name: return (c.text or '').strip()
    return None


def layer_records(root):
    out=[]
    for node in root.iter():
        if lname(node.tag)!='Layer': continue
        name=child_text(node,'Name')
        if not name: continue
        title=child_text(node,'Title')
        queryable=node.attrib.get('queryable')=='1'
        dims={}
        for c in list(node):
            if lname(c.tag) in ('Dimension','Extent'):
                key=c.attrib.get('name') or c.attrib.get('Name')
                if key: dims[key]=(c.text or '').strip()
        out.append({'name':name,'title':title,'queryable':queryable,'dimensions':dims})
    return out


def latest_time(text):
    if not text: return None
    s=text.strip()
    # comma list or ISO interval start/end/period
    if ',' in s:
        vals=[x.strip() for x in s.split(',') if x.strip()]
        return vals[-1] if vals else None
    parts=s.split('/')
    if len(parts)>=2: return parts[1]
    return s if re.match(r'^\d{4}-\d{2}-\d{2}',s) else None


def get_info(session,layer,point,time_value):
    lon,lat=point['lon'],point['lat']; d=.035
    # WMS 1.3 EPSG:4326 axis order is lat,lon.
    bbox=f'{lat-d},{lon-d},{lat+d},{lon+d}'
    base={
        'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetFeatureInfo',
        'LAYERS':layer,'QUERY_LAYERS':layer,'STYLES':'','CRS':'EPSG:4326',
        'BBOX':bbox,'WIDTH':'101','HEIGHT':'101','I':'50','J':'50',
        'FORMAT':'image/png','INFO_FORMAT':'text/plain','FEATURE_COUNT':'10',
    }
    if time_value: base['TIME']=time_value
    try:
        r=session.get(WMS,params=base,timeout=(15,45))
        text=r.text[:10000]
        lower=text.lower()
        nonempty=bool(text.strip()) and not any(x in lower for x in ('search returned no results','no results','serviceexception'))
        return {'point':point,'status':r.status_code,'url':r.url,'content_type':r.headers.get('content-type'),'bytes':len(r.content),'text_preview':text[:1800],'has_feature_info':r.status_code==200 and nonempty}
    except Exception as exc:
        return {'point':point,'error_type':type(exc).__name__,'error':str(exc),'has_feature_info':False}


def main():
    result={
        'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,
        'role':'secondary_modelled_river_proxy_only',
        'authority_priority':['SENAMHI/PHISIS observed or forecast river state','GloFAS/Copernicus modelled flood signal'],
        'wms':WMS,'tests':[]
    }
    sess=requests.Session(); sess.headers.update(HEAD)
    try:
        r=sess.get(WMS,params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetCapabilities'},timeout=(15,60))
        r.raise_for_status(); root=ET.fromstring(r.content)
        records=layer_records(root); by={x['name']:x for x in records}
        result['capabilities']={'status':r.status_code,'bytes':len(r.content),'layer_count':len(records)}
        result['target_layers']={}
        for layer in TARGET_LAYERS:
            rec=by.get(layer)
            if not rec:
                result['target_layers'][layer]={'available':False}; continue
            t=latest_time(rec['dimensions'].get('time') or rec['dimensions'].get('TIME'))
            item={'available':True,'title':rec['title'],'queryable':rec['queryable'],'latest_time_candidate':t,'dimensions':rec['dimensions'],'feature_info':[]}
            if rec['queryable']:
                for point in POINTS: item['feature_info'].append(get_info(sess,layer,point,t))
            item['any_catacaos_feature_info']=any(x.get('has_feature_info') for x in item['feature_info'])
            result['target_layers'][layer]=item
        usable=[k for k,v in result['target_layers'].items() if v.get('any_catacaos_feature_info') and k in ('sumAL41EGE','sumAL42EGE','sumAL43EGE','sumALHEGE','sumALEEGE')]
        network=result['target_layers'].get('UpstreamArea',{}).get('any_catacaos_feature_info',False)
        if usable:
            result['status']='GLOFAS_FLOOD_SIGNAL_QUERYABLE_AT_CATACAOS'
            result['usable_forecast_layers']=usable
            result['decision']='Candidate secondary automated proxy. Next gate is historical validation against 2017 and official Piura discharge references; never convert WMS classes directly to m3/s.'
        elif network:
            result['status']='GLOFAS_NETWORK_PRESENT_BUT_FORECAST_SIGNAL_NOT_QUERYABLE_NOW'
            result['decision']='Network coverage exists; current absence of a flood signal can be a valid no-signal state only after historical validation of the same query path.'
        else:
            result['status']='GLOFAS_WMS_NOT_USABLE_FOR_CATACAOS_PROXY'
            result['decision']='Close GloFAS proxy route; river state remains an external official-input requirement.'
    except Exception as exc:
        result['status']='GLOFAS_WMS_ACCESS_OR_PARSE_ERROR'; result['error_type']=type(exc).__name__; result['error']=str(exc); result['decision']='Do not retry variants; close this automated proxy route unless the documented WMS endpoint itself changes.'
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'usable_forecast_layers':result.get('usable_forecast_layers'),'decision':result['decision']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
