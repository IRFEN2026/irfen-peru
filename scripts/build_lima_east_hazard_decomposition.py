#!/usr/bin/env python3
"""Descompone la zona heredada Chosica/Huaycoloro en dos mecanismos v0.8.

No cambia la zona operativa v0.7.1. Formaliza que el cauce principal Huaycoloro
y los flujos de detritos de quebradas locales de Chosica requieren geometrías,
variables y calibraciones distintas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
OUT=SITE/'data/hazard_models/lima_east_decomposition.json'


def load(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default


def replay_case(replay,event_id):
    return next((c for c in (replay or {}).get('cases',[]) if c.get('event_id')==event_id),None)


def compact_replay(case):
    if not case:return None
    legacy=case.get('legacy_sampling_replay') or {}
    poly=case.get('polygon_sampling_replay') or {}
    return {
        'event_id':case.get('event_id'),'date':case.get('date'),'event':case.get('event'),
        'legacy_threat_score':legacy.get('threat_score'),'legacy_threat_class':legacy.get('threat_class'),
        'polygon_threat_score':poly.get('threat_score') if poly else None,
        'polygon_threat_class':poly.get('threat_class') if poly else None,
        'diagnostic':case.get('diagnostic')
    }


def main():
    replay=load(SITE/'data/calibration/historical_replay.json',{})
    huay=compact_replay(replay_case(replay,'HU-2017-03-15'))
    chos=compact_replay(replay_case(replay,'CH-2015-03-23'))
    report={
        'version':'0.8-experimental',
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'production_use':False,
        'legacy_operational_zone_id':'chosica',
        'legacy_zone_name':'Chosica / Huaycoloro',
        'status':'HAZARD_DECOMPOSITION_REQUIRED',
        'reason':'La zona heredada agrupa dos mecanismos espacial e hidrológicamente distintos: desborde/conducción del sistema Huaycoloro y flujos de detritos de quebradas locales de Chosica hacia el río Rímac.',
        'evidence':{
            'official_2015_event_source':{
                'source':'INGEMMET / SIGRID-CENEPRED',
                'url':'https://sigrid4.cenepred.gob.pe/sigridv4/documento/3642',
                'finding':'El evento 23/03/2015 se documenta entre las quebradas Rayos de Sol y Quirio en Lurigancho-Chosica, además de Cashahuacra en Santa Eulalia.'
            },
            'historical_replay':{
                'huaycoloro_2017':huay,
                'chosica_local_2015':chos,
                'interpretation':'La gran diferencia de captura entre ambos eventos es consistente con que no deben calibrarse como un único mecanismo mediante la subcuenca Huaycoloro.'
            }
        },
        'submodels':[
            {
                'id':'huaycoloro_main_channel',
                'name':'Huaycoloro · sistema de cuenca y cauce principal',
                'hazard_type':'basin_runoff_channel_overflow_and_conveyance',
                'geometry_status':'validated_dem_candidate',
                'geometry':'data/watersheds/huaycoloro_watershed.geojson',
                'reference_event':'HU-2017-03-15',
                'reference_event_replay':huay,
                'core_signals':['basin_rain24','basin_rain72','basin_rain7d','forecast24','channel_hydraulic_state'],
                'infrastructure_context':'Canalización 10.5 km y obras asociadas operativas desde 2025.',
                'scientific_gate':'HYDRAULIC_CALIBRATION_REQUIRED',
                'production_use':False
            },
            {
                'id':'chosica_local_debris_flows',
                'name':'Chosica · quebradas locales de flujo de detritos',
                'hazard_type':'short_response_local_debris_flow',
                'geometry_status':'individual_local_catchments_required',
                'priority_quebradas':['Rayos de Sol','Quirio','Pedregal / San Antonio de Pedregal'],
                'reference_event':'CH-2015-03-23',
                'reference_event_replay':chos,
                'core_signals_candidate':['local_catchment_rainfall','short_duration_rainfall_intensity','antecedent_wetness','debris_sediment_condition','forecast_convective_rainfall'],
                'known_model_mismatch':'Applying the Huaycoloro/legacy aggregate to the 23/03/2015 local-debris event produces only Vigilancia, despite documented severe impacts.',
                'next_steps':[
                    'delineate Rayos de Sol/Quirio/Pedregal catchments individually or as justified clusters',
                    'identify local rainfall/station evidence and sub-daily intensity proxies',
                    'build event and non-event catalogue specific to local debris flows',
                    'calibrate thresholds separately from Huaycoloro main channel'
                ],
                'scientific_gate':'LOCAL_CATCHMENTS_AND_EVENT_CALIBRATION_REQUIRED',
                'production_use':False
            }
        ],
        'operational_rule':'No change to v0.7.1 zone or alert calculation. Decomposition is scientific-only until validated and explicitly promoted.'
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
