#!/usr/bin/env python3
"""Prueba final y acotada del hidrograma oficial SENAMHI Puente Ñácara.

Consulta únicamente la página pública exacta del hidrograma para una fecha
histórica indexada y una fecha actual. Busca series numéricas embebidas o un
recurso público explícito. No recorre endpoints, no evade controles y no hace
scraping iterativo. Si no hay salida reutilizable, esta ruta se cierra.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json, re
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/nacara_hydrograph_probe.json'
BASE='https://www.senamhi.gob.pe/mapas/mapa-monitoreohidro/include/mnt-grafica-new.php'
STATION='47E0415A'
DATES=['2024-09-06 19:00:00','2026-08-14 12:00:00']
HEAD={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'}


def extract_public_refs(text):
    refs=[]
    for pat in (r'https?://[^\"\'<>\\\s]+',r'[\"\']([^\"\']+\.(?:php|json|csv)(?:\?[^\"\']*)?)[\"\']'):
        for m in re.finditer(pat,text or '',re.I):
            value=m.group(0) if pat.startswith('http') else m.group(1)
            low=value.lower()
            if any(k in low for k in ('ajax','data','graf','hidro','caudal','json','csv','php')): refs.append(value[:1000])
    return sorted(set(refs))[:100]


def numeric_signatures(text):
    # Conserva solo evidencia estructural; no interpreta cualquier número como caudal.
    sig={
        'highcharts': 'highcharts' in text.lower(),
        'series_keyword': bool(re.search(r'\bseries\s*:',text,re.I)),
        'data_keyword': bool(re.search(r'\bdata\s*:',text,re.I)),
        'ajax_keyword': any(x in text.lower() for x in ('$.ajax','fetch(','xmlhttprequest')),
        'caudal_unit': bool(re.search(r'm3\s*/?\s*s|m³\s*/?\s*s',text,re.I)),
    }
    # pares timestamp/valor típicos de Highcharts: [epoch,value]
    pairs=re.findall(r'\[(1[3-9]\d{11}|2\d{12})\s*,\s*(-?\d+(?:\.\d+)?)\]',text)
    sig['timestamp_value_pair_count']=len(pairs)
    sig['timestamp_value_pairs_sample']=[{'epoch_ms':int(a),'value_text':b} for a,b in pairs[:30]]
    return sig


def main():
    result={'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),'production_use':False,'station':{'name':'Puente Ñácara','id':STATION,'river':'Piura'},'purpose':'Final bounded test for a stable public numeric river-state path.','tests':[]}
    sess=requests.Session(); sess.headers.update(HEAD)
    for date in DATES:
        params={'fecha_hora':date,'id':STATION,'variable':'CAUDAL','variable_opcion':'C'}
        row={'fecha_hora_request':date}
        try:
            r=sess.get(BASE,params=params,timeout=(10,25))
            text=r.text if 'html' in (r.headers.get('content-type') or '').lower() or 'text' in (r.headers.get('content-type') or '').lower() else ''
            sig=numeric_signatures(text)
            refs=extract_public_refs(text)
            row.update({'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type'),'bytes':len(r.content),'signatures':sig,'public_resource_hints':refs,'machine_numeric_series_found':sig['timestamp_value_pair_count']>=3})
        except Exception as exc:
            row.update({'error_type':type(exc).__name__,'error':str(exc),'machine_numeric_series_found':False})
        result['tests'].append(row)
    good=[x for x in result['tests'] if x.get('machine_numeric_series_found')]
    if good:
        result['status']='PUBLIC_HYDROGRAPH_SERIES_CANDIDATE_FOUND'
        result['decision']='Use only the embedded public SENAMHI series after validating timestamps, units and freshness against the rendered hydrograph.'
    else:
        result['status']='NO_STABLE_PUBLIC_NUMERIC_SERIES_FROM_GITHUB'
        result['decision']='Close direct machine scraping route. Keep PHISIS/SENAMHI as authoritative external river-state channel; do not fabricate dry-season flow.'
    result['season_rule']='Puente Ñácara short-term forecast is published only during avenida; absence outside avenida is not interpreted as zero flow.'
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'tests':[{k:x.get(k) for k in ('fecha_hora_request','status','bytes','machine_numeric_series_found','error_type')} for x in result['tests']]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
