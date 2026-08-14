#!/usr/bin/env python3
"""Monitorea frescura/disponibilidad de fuentes hidrológicas oficiales de Piura.

No inventa caudales. Registra frescura del informe regional y disponibilidad de
productos oficiales SENAMHI, manteniendo separado cualquier valor histórico o
umbral de referencia del estado numérico actual del río.
"""
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
import html as html_lib
import json
import re
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'site/data/hydrology/piura_source_status.json'
BASE = 'https://servicios.regionpiura.gob.pe'
SEN_FORECAST = 'https://www.senamhi.gob.pe/?p=pronostico-caudales'
SEN_REFERENCE = 'https://www.senamhi.gob.pe/servicios/?ca=28012&ce=47E0415A&p=avisos-detalle-hidrologicos'

MONTHS = {
    'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
    'julio':7,'agosto':8,'septiembre':9,'setiembre':9,'octubre':10,
    'noviembre':11,'diciembre':12,
}


def clean_html(text):
    text = re.sub(r'<script[\s\S]*?</script>', ' ', text, flags=re.I)
    text = re.sub(r'<style[\s\S]*?</style>', ' ', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html_lib.unescape(text)).strip()


def parse_spanish_dates(text):
    found=[]
    pattern=r'\b(\d{1,2})\s+(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Setiembre|Octubre|Noviembre|Diciembre)\s*-\s*(20\d{2})\b'
    for day, month, year in re.findall(pattern, text, flags=re.I):
        try:
            d=date(int(year), MONTHS[month.lower()], int(day))
            found.append(d)
        except Exception:
            pass
    return sorted(set(found), reverse=True)


def main():
    peru = timezone(timedelta(hours=-5))
    now = datetime.now(peru)
    url = f'{BASE}/datosh/data/{now.year}/{now.month:02d}'
    headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8','Accept':'text/html,application/json,*/*'}

    status={
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'zone_id':'catacaos',
        'production_use':False,
        'purpose':'Frescura y referencias oficiales; no representa por sí solo caudal ni nivel actual del río.',
        'gore_piura':{'catalog_url':url},
        'senamhi':{
            'station':'Puente Ñacara',
            'station_id':'47E0415A',
            'river':'Río Piura',
            'role':'Fuente hidrológica oficial primaria prevista para el modelo fluvial.',
            'numeric_river_state_available':False,
            'automatic_numeric_access_status':'unresolved_from_github_actions',
            'forecast_page_url':SEN_FORECAST,
            'forecast_only_during_flood_season':True,
            'reference_advisory_url':SEN_REFERENCE,
            'reference_red_threshold_m3s':1100,
            'reference_threshold_date':'2023-04-17',
            'reference_threshold_note':'Umbral rojo publicado por SENAMHI en aviso histórico de Puente Ñácara; no es caudal actual ni umbral de Catacaos.'
        }
    }

    try:
        r=requests.get(url,timeout=35,headers={**headers,'Accept':'application/json,*/*'})
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

    try:
        r=requests.get(SEN_FORECAST,timeout=25,headers=headers)
        text=clean_html(r.text)
        idx=text.lower().find('río piura')
        if idx < 0: idx=text.lower().find('rio piura')
        window=text[idx:idx+2500] if idx >= 0 else text
        dates=parse_spanish_dates(window)
        latest_date=dates[0] if dates else None
        status['senamhi'].update({
            'forecast_page_http_status':r.status_code,
            'forecast_page_access_status':'available' if r.status_code==200 else 'http_error',
            'latest_forecast_bulletin_date':latest_date.isoformat() if latest_date else None,
            'latest_forecast_bulletin_age_days':(now.date()-latest_date).days if latest_date else None,
            'forecast_bulletin_status':'seasonal_or_event_driven_product' if latest_date else 'page_available_date_not_parsed',
        })
    except Exception as exc:
        status['senamhi'].update({
            'forecast_page_access_status':'access_error',
            'forecast_page_error_type':type(exc).__name__,
            'forecast_page_error':str(exc),
        })

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
