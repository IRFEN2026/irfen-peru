#!/usr/bin/env python3
"""Prueba única de acceso automático a ISAAC SENAMHI.

Resuelve los enlaces oficiales publicados por SENAMHI y clasifica el destino y
posibles recursos de datos. No extrae credenciales, no evade controles y no se
usa en producción.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, re
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/stations/isaac_access_probe.json'
URLS=['https://bit.ly/ISAAC_SENAMHI','https://bit.ly/3uhJtjj']
HEAD={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'}

def classify(url,ctype,text):
    low=(url+' '+ctype+' '+text[:20000]).lower()
    if 'lookerstudio.google.com' in low or 'datastudio.google.com' in low: return 'looker_studio'
    if 'app.powerbi.com' in low: return 'power_bi'
    if 'docs.google.com/spreadsheets' in low: return 'google_sheets'
    if 'arcgis' in low: return 'arcgis'
    if 'senamhi' in low: return 'senamhi_web'
    return 'web_unknown'

def main():
    result={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'purpose':'Determine whether official ISAAC can be consumed automatically by IRFEN without bypassing access controls.','tests':[]}
    sess=requests.Session(); sess.headers.update(HEAD)
    for u in URLS:
        row={'short_url':u}
        try:
            r=sess.get(u,allow_redirects=True,timeout=(15,60))
            text=r.text if 'text' in (r.headers.get('content-type') or '') or 'html' in (r.headers.get('content-type') or '') else ''
            row.update({'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type'),'bytes':len(r.content),'redirect_history':[{'status':h.status_code,'url':h.url,'location':h.headers.get('location')} for h in r.history],'target_type':classify(r.url,r.headers.get('content-type') or '',text)})
            # Solo referencias públicas presentes en HTML; no ejecuta JS ni intenta autenticación.
            links=sorted(set(re.findall(r'https?://[^\"\'<>\\\s]+',text)))
            row['public_link_hints']=[x[:500] for x in links if any(k in x.lower() for k in ('csv','json','sheet','api','arcgis','looker','powerbi','senamhi'))][:100]
            row['html_markers']={k:(k in text.lower()) for k in ['csv','json','api','google.visualization','looker','powerbi','arcgis','iframe']}
        except Exception as e:
            row.update({'error_type':type(e).__name__,'error':str(e)})
        result['tests'].append(row)
    reachable=[x for x in result['tests'] if x.get('status')==200]
    result['status']='TARGET_RESOLVED' if reachable else 'OFFICIAL_LINK_NOT_MACHINE_REACHABLE_FROM_GITHUB'
    result['next_gate']='Inspect only openly exposed target resources if TARGET_RESOLVED; otherwise treat ISAAC as authoritative external/manual channel and stop probing.'
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
