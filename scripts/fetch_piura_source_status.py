#!/usr/bin/env python3
"""Monitorea frescura/disponibilidad de fuentes hidrológicas oficiales de Piura.

No inventa caudales. Registra frescura del informe regional y disponibilidad de
productos oficiales SENAMHI, manteniendo separado cualquier valor histórico o
umbral de referencia del estado numérico actual del río.
"""
from datetime import datetime, timedelta, timezone, date
from io import BytesIO
from pathlib import Path
import html as html_lib
import json
import re
import unicodedata
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


def normalize_text(text):
    """Normaliza texto para clasificar documentos sin depender de tildes."""
    normalized = unicodedata.normalize('NFKD', text or '')
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', normalized).strip().lower()


def parse_piura_forecast_entries(page_html):
    """Extrae solo enlaces de las secciones Río Piura/Puente Ñácara.

    La página mezcla decenas de cuencas y dos catálogos (diario y horario).
    Acotar por encabezado evita atribuir a Piura fechas de otra cuenca.
    """
    entries = []
    section_pattern = re.compile(
        r'<h4\b[^>]*>(?P<title>.*?)</h4>\s*<ul\b[^>]*>(?P<items>.*?)</ul>',
        flags=re.I | re.S,
    )
    link_pattern = re.compile(
        r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
        flags=re.I | re.S,
    )
    for section in section_pattern.finditer(page_html):
        title = clean_html(section.group('title'))
        normalized_title = normalize_text(title)
        if 'rio piura' not in normalized_title or 'nacara' not in normalized_title:
            continue
        cadence = (
            'hourly' if 'horario' in normalized_title
            else 'daily' if 'diario' in normalized_title
            else 'unspecified'
        )
        for link in link_pattern.finditer(section.group('items')):
            label = clean_html(link.group('label'))
            parsed_dates = parse_spanish_dates(label)
            if not parsed_dates:
                continue
            entries.append({
                'catalog_date': parsed_dates[0],
                'url': html_lib.unescape(link.group('href')),
                'cadence': cadence,
                'catalog_title': title,
            })
    entries.sort(key=lambda entry: entry['catalog_date'], reverse=True)
    return entries


def classify_bulletin_text(text):
    """Clasifica conservadoramente un PDF enlazado como boletín hidrológico."""
    normalized = normalize_text(text)
    fire_markers = (
        'indice meteorologico de incendios',
        'incendio forestal',
        'forest fire',
        'fwi',
    )
    if any(marker in normalized for marker in fire_markers):
        return 'DOCUMENT_MISMATCH_FIRE_WEATHER'

    hydrology_markers = (
        'pronostico hidrologico',
        'caudal instantaneo',
        'caudal pronosticado',
    )
    place_markers = ('rio piura', 'nacara')
    if any(marker in normalized for marker in hydrology_markers) and all(
        marker in normalized for marker in place_markers
    ):
        return 'VERIFIED_HYDROLOGICAL_BULLETIN'
    return 'DOCUMENT_MISMATCH_UNVERIFIED_CONTENT'


def inspect_bulletin(entry, headers):
    """Descarga y verifica el contenido real del documento del catálogo."""
    from pypdf import PdfReader

    result = {
        'catalog_date': entry['catalog_date'].isoformat(),
        'url': entry['url'],
        'cadence': entry['cadence'],
        'catalog_title': entry['catalog_title'],
    }
    try:
        response = requests.get(entry['url'], timeout=35, headers=headers)
        result['http_status'] = response.status_code
        response.raise_for_status()
        if not response.content.startswith(b'%PDF-'):
            result['document_status'] = 'DOCUMENT_MISMATCH_NOT_PDF'
            return result
        reader = PdfReader(BytesIO(response.content))
        text = '\n'.join((page.extract_text() or '') for page in reader.pages[:3])
        result.update({
            'document_status': classify_bulletin_text(text),
            'pdf_page_count': len(reader.pages),
            'extracted_text_characters': len(text),
        })
    except Exception as exc:
        result.update({
            'document_status': 'DOCUMENT_VERIFICATION_ERROR',
            'error_type': type(exc).__name__,
            'error': str(exc),
        })
    return result


def carry_forward_verified_bulletin(current, previous, now, reason):
    """Conserva evidencia verificada como obsoleta ante fallas transitorias.

    Solo se arrastra un boletín si el JSON anterior contiene una comprobación
    explícita que coincide con su fecha y URL. Nunca se convierte en estado
    numérico actual ni se presenta como una observación fresca.
    """
    previous = previous or {}
    bulletin_date = previous.get('latest_forecast_bulletin_date')
    bulletin_url = previous.get('latest_verified_forecast_bulletin_url')
    checks = previous.get('forecast_catalog_document_checks') or []
    proof = any(
        row.get('document_status') == 'VERIFIED_HYDROLOGICAL_BULLETIN'
        and row.get('catalog_date') == bulletin_date
        and row.get('url') == bulletin_url
        for row in checks
    )
    if not bulletin_date or not bulletin_url or not proof:
        current.update({
            'forecast_bulletin_status':f'{reason}_no_verified_bulletin',
            'forecast_bulletin_stale':True,
        })
        return False

    parsed_date = date.fromisoformat(bulletin_date)
    for key in (
        'latest_forecast_catalog_date',
        'latest_forecast_catalog_url',
        'latest_forecast_bulletin_date',
        'latest_verified_forecast_bulletin_url',
        'forecast_catalog_document_checks',
        'forecast_catalog_integrity_warning',
        'forecast_catalog_last_verified_at',
    ):
        if key in previous:
            current[key] = previous[key]
    current.update({
        'latest_forecast_bulletin_age_days':(now.date()-parsed_date).days,
        'forecast_bulletin_status':f'{reason}_last_verified_bulletin_stale',
        'forecast_bulletin_stale':True,
    })
    return True


def main():
    peru = timezone(timedelta(hours=-5))
    now = datetime.now(peru)
    url = f'{BASE}/datosh/data/{now.year}/{now.month:02d}'
    headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8','Accept':'text/html,application/json,*/*'}

    generated_at=datetime.now(timezone.utc).isoformat()
    try:
        previous_status=json.loads(OUT.read_text(encoding='utf-8'))
    except Exception:
        previous_status={}
    previous_senamhi=previous_status.get('senamhi') or {}

    status={
        'generated_at':generated_at,
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
        r.raise_for_status()
        entries = parse_piura_forecast_entries(r.text)
        catalog_latest = entries[0] if entries else None

        # Verifica el enlace más reciente de cada catálogo. Un rótulo o fecha en
        # la página no demuestra que el PDF sea realmente hidrológico.
        newest_by_cadence = {}
        for entry in entries:
            newest_by_cadence.setdefault(entry['cadence'], entry)
        checks = [inspect_bulletin(entry, headers) for entry in newest_by_cadence.values()]
        verified = [
            check for check in checks
            if check.get('document_status') == 'VERIFIED_HYDROLOGICAL_BULLETIN'
        ]
        verified.sort(key=lambda check: check['catalog_date'], reverse=True)
        latest_verified = verified[0] if verified else None
        latest_date = (
            date.fromisoformat(latest_verified['catalog_date'])
            if latest_verified else None
        )
        mismatches = [
            check for check in checks
            if str(check.get('document_status', '')).startswith('DOCUMENT_MISMATCH')
        ]
        if latest_verified and mismatches:
            bulletin_status = 'catalog_document_mismatch_with_verified_fallback'
        elif latest_verified:
            bulletin_status = 'verified_hydrological_bulletin'
        elif mismatches:
            bulletin_status = 'catalog_document_mismatch_no_verified_bulletin'
        elif entries:
            bulletin_status = 'catalog_entries_not_verified'
        else:
            bulletin_status = 'page_available_piura_section_not_parsed'
        status['senamhi'].update({
            'forecast_page_http_status':r.status_code,
            'forecast_page_access_status':'available' if r.status_code==200 else 'http_error',
            'latest_forecast_catalog_date':catalog_latest['catalog_date'].isoformat() if catalog_latest else None,
            'latest_forecast_catalog_url':catalog_latest['url'] if catalog_latest else None,
            'latest_forecast_bulletin_date':latest_date.isoformat() if latest_date else None,
            'latest_forecast_bulletin_age_days':(now.date()-latest_date).days if latest_date else None,
            'latest_verified_forecast_bulletin_url':latest_verified['url'] if latest_verified else None,
            'forecast_bulletin_status':bulletin_status,
            'forecast_bulletin_stale':False,
            'forecast_catalog_last_verified_at':generated_at if latest_verified else None,
            'forecast_catalog_document_checks':checks,
            'forecast_catalog_integrity_warning':(
                'Una o más entradas del catálogo enlazan documentos no hidrológicos; '
                'sus fechas no se aceptan como evidencia de frescura.'
                if mismatches else None
            ),
        })
        verification_errors = [
            check for check in checks
            if check.get('document_status') == 'DOCUMENT_VERIFICATION_ERROR'
        ]
        if not latest_verified and verification_errors:
            status['senamhi']['forecast_catalog_current_document_checks'] = checks
            carry_forward_verified_bulletin(
                status['senamhi'],
                previous_senamhi,
                now,
                'document_verification_error',
            )
    except Exception as exc:
        status['senamhi'].update({
            'forecast_page_access_status':'access_error',
            'forecast_page_error_type':type(exc).__name__,
            'forecast_page_error':str(exc),
        })
        carry_forward_verified_bulletin(
            status['senamhi'],
            previous_senamhi,
            now,
            'source_unreachable',
        )

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
