#!/usr/bin/env python3
"""Verifica si el Plan de Contingencia oficial 2023-2025 mantiene reglas de actuación útiles.

Descarga únicamente el PDF enlazado por la página oficial gob.pe de la
Municipalidad de Lurigancho-Chosica y guarda resultados estructurados: páginas,
frases de condición y valores mm/horas. No publica el PDF ni promueve umbrales.
Si el CDN no es accesible desde GitHub, la prueba se cierra como no verificable.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import io, json, re
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/calibration/chosica_plan_2023_2025_thresholds.json'
PAGE='https://www.gob.pe/institucion/munilurigancho/informes-publicaciones/6087112-plan-de-contingencia-ante-lluvias-intensas-lurigancho-chosica-2023-2025'
HEAD={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'}
MAX_BYTES=25*1024*1024


def norm(s): return re.sub(r'\s+',' ',s or '').strip()


def main():
    report={
        'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,'source_page':PAGE,'publisher':'Municipalidad Distrital de Lurigancho-Chosica / gob.pe',
        'purpose':'Verify current official contingency-plan rainfall action conditions before using any historical 2h threshold as an IRFEN reference.',
        'status':'starting','threshold_candidates':[],'relevant_pages':[],
        'promotion_rule':'No value becomes an IRFEN production threshold from this extraction alone.'
    }
    sess=requests.Session(); sess.headers.update(HEAD)
    try:
        p=sess.get(PAGE,timeout=(15,60)); p.raise_for_status()
        soup=BeautifulSoup(p.text,'html.parser')
        links=[]
        for a in soup.find_all('a',href=True):
            href=a['href']
            if '.pdf' in href.lower() or 'cdn.www.gob.pe/uploads/document' in href.lower(): links.append(href)
        if not links:
            # gob.pe a veces deja URL de descarga en HTML/JSON embebido
            links=re.findall(r'https://cdn\.www\.gob\.pe/uploads/document/file/[^"\'<>\\\s]+?\.pdf(?:\?[^"\'<>\\\s]+)?',p.text,re.I)
        links=list(dict.fromkeys(links))
        report['official_pdf_links_found']=links[:10]
        if not links:
            raise RuntimeError('No se encontró enlace PDF oficial en la página gob.pe')
        url=links[0]
        if url.startswith('/'): url='https://www.gob.pe'+url
        headers={**HEAD,'Referer':PAGE}
        r=sess.get(url,headers=headers,timeout=(20,180),stream=True)
        report['pdf_http_status']=r.status_code; report['pdf_final_url']=r.url; report['pdf_content_type']=r.headers.get('content-type')
        r.raise_for_status()
        content=r.content
        if len(content)>MAX_BYTES: raise RuntimeError('PDF excede límite de seguridad')
        if not content.startswith(b'%PDF'): raise RuntimeError('La descarga oficial no devolvió un PDF')
        report['pdf_bytes']=len(content)
        reader=PdfReader(io.BytesIO(content)); report['page_count']=len(reader.pages)
        candidates=[]; relevant=[]
        needles=('momento de actuación','momento de actuacion','condición de alerta','condicion de alerta','umbral','primeras 2 horas','pedregal','activación de quebradas','activacion de quebradas')
        for pageno,page in enumerate(reader.pages,start=1):
            try: text=page.extract_text() or ''
            except Exception: text=''
            if not text.strip(): continue
            low=text.lower(); hits=[n for n in needles if n in low]
            if not hits: continue
            relevant.append({'page':pageno,'categories':hits})
            # Valores mm asociados a ventanas de horas encontrados en la misma página.
            for m in re.finditer(r'(?P<mm>\d{1,3}(?:[.,]\d+)?)\s*mm.{0,120}?(?P<hours>\d{1,2})\s*horas?',norm(text),re.I):
                candidates.append({'page':pageno,'mm_text':m.group('mm'),'hours_text':m.group('hours'),'context':norm(m.group(0))[:300]})
            # Patrones inversos: primeras 2 horas ... 5 mm
            for m in re.finditer(r'(?P<hours>\d{1,2})\s*horas?.{0,120}?(?P<mm>\d{1,3}(?:[.,]\d+)?)\s*mm',norm(text),re.I):
                candidates.append({'page':pageno,'mm_text':m.group('mm'),'hours_text':m.group('hours'),'context':norm(m.group(0))[:300]})
        # dedupe
        seen=set(); uniq=[]
        for c in candidates:
            key=(c['page'],c['mm_text'],c['hours_text'],c['context'])
            if key not in seen: seen.add(key); uniq.append(c)
        report['relevant_pages']=relevant
        report['threshold_candidates']=uniq[:100]
        report['status']='OFFICIAL_PLAN_PARSED_WITH_THRESHOLD_CANDIDATES' if uniq else 'OFFICIAL_PLAN_PARSED_NO_EXPLICIT_MM_HOUR_RULE_FOUND'
    except Exception as exc:
        report['status']='OFFICIAL_PLAN_NOT_MACHINE_VERIFIABLE'
        report['error_type']=type(exc).__name__; report['error']=str(exc)
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'page_count':report.get('page_count'),'candidate_count':len(report.get('threshold_candidates',[])),'relevant_pages':report.get('relevant_pages',[])[:20]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
