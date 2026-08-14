#!/usr/bin/env python3
"""Cierra la puerta de acceso automático a ISAAC SENAMHI de forma conservadora.

Solo inspecciona el HTML público al que redirigen los enlaces oficiales y busca
recursos de datos explícitos (CSV/JSON/API documentada/enlace de descarga). No
ejecuta JS, no consulta endpoints internos de Power BI y no intenta reproducir
la lógica privada del reporte. Si no existe una salida pública estable, ISAAC se
trata como canal oficial externo/manual y se detiene la exploración técnica.
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
    low=(url+' '+ctype+' '+text[:30000]).lower()
    if 'app.powerbi.com' in low: return 'power_bi_public_report'
    if 'lookerstudio.google.com' in low or 'datastudio.google.com' in low: return 'looker_studio'
    if 'docs.google.com/spreadsheets' in low: return 'google_sheets'
    if 'arcgis' in low: return 'arcgis'
    if 'senamhi' in low: return 'senamhi_web'
    return 'web_unknown'


def explicit_data_links(text):
    links=sorted(set(re.findall(r'https?://[^\"\'<>\\\s]+',text or '')))
    out=[]
    for x in links:
        low=x.lower()
        if any(token in low for token in ('.csv','.json','download?format=csv','export?format=csv','/api/public/','FeatureServer','MapServer')):
            out.append(x[:1000])
    return out[:50]


def public_metadata(text):
    # Identificadores visibles en el HTML se guardan solo para trazabilidad;
    # no se usan para construir llamadas a endpoints internos de Power BI.
    keys=['datasetId','reportId','modelId','resolvedClusterUrl','activityId','requestId']
    found={}
    for key in keys:
        vals=[]
        for pat in (
            rf'"{re.escape(key)}"\s*:\s*"([^"]+)"',
            rf'{re.escape(key)}\s*[:=]\s*["\']([^"\']+)["\']',
        ):
            vals.extend(re.findall(pat,text or '',re.I))
        if vals:
            found[key]=sorted(set(vals))[:10]
    return found


def main():
    result={
        'version':'0.8-experimental',
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,
        'purpose':'Decide once whether official ISAAC exposes a stable public machine-readable feed suitable for IRFEN.',
        'policy':'No reverse engineering of Power BI internal query endpoints; only explicit public data links are eligible.',
        'tests':[]
    }
    sess=requests.Session(); sess.headers.update(HEAD)
    for u in URLS:
        row={'short_url':u}
        try:
            r=sess.get(u,allow_redirects=True,timeout=(15,60))
            ctype=r.headers.get('content-type') or ''
            text=r.text if ('text' in ctype.lower() or 'html' in ctype.lower()) else ''
            data_links=explicit_data_links(text)
            row.update({
                'status':r.status_code,
                'final_url':r.url,
                'content_type':ctype,
                'bytes':len(r.content),
                'redirect_history':[{'status':h.status_code,'url':h.url,'location':h.headers.get('location')} for h in r.history],
                'target_type':classify(r.url,ctype,text),
                'explicit_public_data_links':data_links,
                'public_metadata_visible':public_metadata(text),
                'stable_machine_feed_found':bool(data_links),
            })
        except Exception as e:
            row.update({'error_type':type(e).__name__,'error':str(e),'stable_machine_feed_found':False})
        result['tests'].append(row)

    reachable=[x for x in result['tests'] if x.get('status')==200]
    machine=[x for x in reachable if x.get('stable_machine_feed_found')]
    if machine:
        result['status']='PUBLIC_MACHINE_FEED_CANDIDATE_FOUND'
        result['decision']='Review only the explicit public data links for stability, provenance and freshness before integration.'
    elif reachable:
        result['status']='AUTHORITATIVE_EXTERNAL_CHANNEL_NO_STABLE_PUBLIC_MACHINE_FEED'
        result['decision']='Stop ISAAC scraping/probing. Use ISAAC as authoritative external/manual ground-state channel and seek an official published station/API feed for automation.'
    else:
        result['status']='OFFICIAL_LINK_NOT_MACHINE_REACHABLE_FROM_GITHUB'
        result['decision']='Stop probing and retain ISAAC as authoritative external/manual channel.'
    result['next_gate']='Automated Pedregal operation requires a stable official ground-observation feed; thresholds/alerts may align with official local plans but must not be inferred from Power BI internals.'
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'decision':result['decision'],'feeds_found':sum(1 for x in result['tests'] if x.get('stable_machine_feed_found'))},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
