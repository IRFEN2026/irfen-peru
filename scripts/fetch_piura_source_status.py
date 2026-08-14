#!/usr/bin/env python3
"""Monitorea frescura/disponibilidad de fuentes hidrológicas oficiales de Piura.

No extrae ni inventa caudales. Informa únicamente si existe un informe diario
regional y la disponibilidad técnica de los canales que IRFEN está evaluando.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/hydrology/piura_source_status.json'
BASE='https://servicios.regionpiura.gob.pe'


def main():
    peru=timezone(timedelta(hours=-5)); now=datetime.now(peru)
    url=f'{BASE}/datosh/data/{now.year}/{now.month:02d}'
    status={
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'zone_id':'catacaos',
        'production_use':False,
        'purpose':'Frescura de fuentes oficiales; no representa caudal ni nivel del río.',
        'gore_piura':{'catalog_url':url},
        'senamhi':{
            'station':'Puente Ñacara',
            'station_id':'47E0415A',
            'role':'Fuente hidrológica oficial primaria prevista para el modelo fluvial.',
            'automatic_access_status':'unresolved_from_github_actions'
        }
    }
    try:
        r=requests.get(url,timeout=35,headers={'User-Agent':'IRFEN-research/0.8','Accept':'application/json,*/*'})
        r.raise_for_status(); obj=r.json(); items=obj if isinstance(obj,list) else obj.get('data',[]) if isinstance(obj,dict) else []
        valid=[x for x in items if isinstance(x,dict) and x.get('fkey')]
        valid.sort(key=lambda x:str(x.get('fkey')),reverse=True)
        latest=valid[0] if valid else None
        status['gore_piura'].update({
            'catalog_http_status':r.status_code,
            'reports_in_current_month':len(valid),
            'latest_report':latest,
            'latest_report_date':latest.get('fkey') if latest else None,
            'catalog_status':'available' if latest else 'available_without_records',
            'download_values_status':'not_integrated_download_routes_return_html',
            'map_status':'jpeg_accessible_but_not_used_as_numeric_source'
        })
        if latest:
            try:
                d=datetime.fromisoformat(str(latest['fkey'])).date()
                status['gore_piura']['report_age_days']=(now.date()-d).days
            except Exception: pass
    except Exception as exc:
        status['gore_piura'].update({'catalog_status':'access_error','error_type':type(exc).__name__,'error':str(exc)})
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
