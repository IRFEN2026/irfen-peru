#!/usr/bin/env python3
"""Evalúa si 11/02/2012 puede asignarse al evento Huaycoloro/Jicamarca.

La decisión se basa en coocurrencia/proximidad dentro de la página 61 del
informe IGP 2023. Guarda métricas y booleanos, no el texto del informe. No
modifica el catálogo histórico; produce evidencia para una decisión posterior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import tempfile

import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'site/data/calibration/huaycoloro_2012_date_resolution.json'
URL='https://repositorio.igp.gob.pe/bitstreams/7ab825b4-0aca-4275-95a8-4243998bbe4c/download'
ITEM='https://repositorio.igp.gob.pe/items/58daab07-5d95-49d2-9d8b-e1fc0bd57111'
PAGE=61
DATE_PATTERNS=[r'11\s+de\s+febrero\s+(?:de\s+)?2012',r'11[/-]0?2[/-]2012']
PLACE_TERMS=['huaycoloro','jicamarca','cajamarquilla']
EVENT_TERMS=['flujo de detritos','huaico','huayco','quebrada','activación','activacion','desborde','evento','ocurrió','ocurrio','afectó','afecto']
RAIN_TERMS=['lluvia','precipitación','precipitacion']


def norm(text):
    return re.sub(r'\s+',' ',text or '').strip()


def spans_for_patterns(text,patterns,regex=False):
    out=[]
    for p in patterns:
        if regex:
            it=re.finditer(p,text,re.I)
        else:
            it=re.finditer(re.escape(p),text,re.I)
        for m in it:out.append((m.start(),m.end(),m.group(0)))
    return sorted(out)


def min_gap(a,b):
    if not a or not b:return None
    best=None
    for x in a:
        for y in b:
            if x[1]<y[0]:g=y[0]-x[1]
            elif y[1]<x[0]:g=x[0]-y[1]
            else:g=0
            best=g if best is None or g<best else best
    return best


def sentence_ranges(text):
    ranges=[];start=0
    for m in re.finditer(r'(?<=[.!?;])\s+(?=[A-ZÁÉÍÓÚÑ0-9])',text):
        end=m.start();
        if end>start:ranges.append((start,end))
        start=m.end()
    if start<len(text):ranges.append((start,len(text)))
    return ranges


def sentence_ids(spans,ranges):
    ids=set()
    for s in spans:
        for i,(a,b) in enumerate(ranges):
            if s[0]>=a and s[0]<b:ids.add(i);break
    return ids


def main():
    report={
        'version':'0.8-experimental','generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,'candidate_date':'2012-02-11','source_item':ITEM,
        'source_page':PAGE,'status':'starting','validated_event_date':False,
        'warning':'Resolución automática basada en estructura textual; requiere criterios estrictos y no modifica el catálogo por sí sola.'
    }
    try:
        r=requests.get(URL,headers={'User-Agent':'Mozilla/5.0 IRFEN-research/0.8'},timeout=(20,180))
        r.raise_for_status()
        with tempfile.TemporaryDirectory(prefix='irfen_huay2012_') as td:
            pdf=Path(td)/'igp.pdf';pdf.write_bytes(r.content)
            reader=PdfReader(str(pdf))
            raw=reader.pages[PAGE-1].extract_text() or ''
            text=norm(raw);low=text.lower()
            date_spans=spans_for_patterns(text,DATE_PATTERNS,regex=True)
            place_spans=spans_for_patterns(text,PLACE_TERMS)
            event_spans=spans_for_patterns(text,EVENT_TERMS)
            rain_spans=spans_for_patterns(text,RAIN_TERMS)
            ranges=sentence_ranges(text)
            d_ids=sentence_ids(date_spans,ranges);p_ids=sentence_ids(place_spans,ranges);e_ids=sentence_ids(event_spans,ranges);r_ids=sentence_ids(rain_spans,ranges)
            same_date_place=sorted(d_ids&p_ids)
            same_date_event=sorted(d_ids&e_ids)
            same_all=sorted(d_ids&p_ids&e_ids)
            date_place_gap=min_gap(date_spans,place_spans)
            date_event_gap=min_gap(date_spans,event_spans)
            place_event_gap=min_gap(place_spans,event_spans)

            # Evidencia fuerte: fecha y lugar están en la misma unidad textual y
            # hay término de evento en esa misma unidad. Evidencia media: fecha
            # y lugar <250 caracteres, además de término de evento <250 caracteres.
            strong=bool(same_all)
            medium=(date_place_gap is not None and date_place_gap<=250 and date_event_gap is not None and date_event_gap<=250 and place_event_gap is not None and place_event_gap<=250)
            confidence='high_structural_match' if strong else 'medium_proximity_match' if medium else 'insufficient'
            decision='DATE_CAN_BE_PROMOTED_WITH_SOURCE_NOTE' if strong else 'DATE_REQUIRES_MANUAL_OR_SECOND_SOURCE_CONFIRMATION'
            report.update({
                'status':'resolved','page_text_length_chars':len(text),
                'date_occurrence_count':len(date_spans),'place_occurrence_count':len(place_spans),'event_term_occurrence_count':len(event_spans),'rain_term_occurrence_count':len(rain_spans),
                'place_terms_present':sorted({p for p in PLACE_TERMS if p in low}),
                'event_terms_present':sorted({p for p in EVENT_TERMS if p in low}),
                'rain_terms_present':sorted({p for p in RAIN_TERMS if p in low}),
                'min_date_place_gap_chars':date_place_gap,'min_date_event_gap_chars':date_event_gap,'min_place_event_gap_chars':place_event_gap,
                'same_sentence_date_place':bool(same_date_place),'same_sentence_date_event':bool(same_date_event),'same_sentence_date_place_event':strong,
                'structural_confidence':confidence,'decision':decision,
                'validated_event_date':strong,
                'criteria':{
                    'promotion_requires_same_sentence_date_place_event':True,
                    'medium_proximity_threshold_chars':250,
                    'text_excerpt_stored':False
                }
            })
    except Exception as exc:
        report.update({'status':'error','error_type':type(exc).__name__,'error':str(exc)})
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
