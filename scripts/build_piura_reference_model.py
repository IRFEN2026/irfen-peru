#!/usr/bin/env python3
"""Construye referencias hidrológicas trazables para Catacaos/Bajo Piura.

No deriva umbrales nuevos. Mantiene separados valores de eventos, umbral de una
estación aguas arriba y caudales de diseño hasta homologar ubicación, datum,
periodo y significado hidráulico.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
OUT=SITE/'data/hydrology/piura_reference_model.json'


def load(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default


def main():
    events=load(ROOT/'config/historical_events.json',{'events':[]})
    source=load(SITE/'data/hydrology/piura_source_status.json',{})
    hydraulics=load(SITE/'data/hydraulics/current_infrastructure.json',{'zones':[]})

    hist=[]
    for e in events.get('events',[]):
        if e.get('zone_id')!='catacaos' or e.get('flow_m3s') is None:continue
        hist.append({
            'event_id':e.get('id'),'date':e.get('date'),'year':e.get('year'),
            'event':e.get('event'),'flow_m3s':e.get('flow_m3s'),
            'source':e.get('source'),'source_url':e.get('url'),
            'location_status':'not_harmonized_to_puente_nacara',
            'use':'historical_event_reference_only'
        })

    sen=(source.get('senamhi') or {})
    hyd=next((z for z in hydraulics.get('zones',[]) if z.get('zone_id')=='catacaos'),{})
    design=[]
    for c in hyd.get('known_components',[]):
        if c.get('design_flow_m3s') is not None:
            design.append({
                'component_type':c.get('type'),'design_flow_m3s':c.get('design_flow_m3s'),
                'status':c.get('status'),'details':c.get('details'),
                'use':'design_reference_only'
            })

    report={
        'version':'0.8-experimental',
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'zone_id':'catacaos',
        'production_use':False,
        'model_status':'reference_harmonization_required',
        'principle':'No comparar directamente caudales de ubicaciones o significados distintos sin homologación hidráulica.',
        'station_reference':{
            'station':sen.get('station','Puente Ñacara'),
            'station_id':sen.get('station_id','47E0415A'),
            'river':sen.get('river','Río Piura'),
            'red_threshold_m3s':sen.get('reference_red_threshold_m3s'),
            'threshold_date':sen.get('reference_threshold_date'),
            'source_url':sen.get('reference_advisory_url'),
            'use':'upstream_station_reference_only',
            'warning':'No representa por sí solo umbral de desborde en Catacaos.'
        },
        'historical_event_flows':hist,
        'design_references':design,
        'required_harmonization':[ 
            'identificar ubicación/gauge exacto de cada caudal histórico',
            'relacionar Puente Ñácara con Tambogrande/Piura urbana/Bajo Piura mediante tiempos de tránsito y aportes',
            'verificar capacidad hidráulica actual del tramo urbano y Bajo Piura',
            'incorporar defensas, puntos de desborde y llanura de inundación',
            'validar con eventos posteriores a intervenciones recientes'
        ],
        'next_operational_gate':'automatic_numeric_river_state_plus_location_harmonization'
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
