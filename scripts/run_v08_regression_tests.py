#!/usr/bin/env python3
"""Pruebas de regresión funcionales para IRFEN v0.8.

Verifican integridad arquitectónica y los bloqueos acordados. No demuestran que
los umbrales sean científicamente válidos ni autorizan promoción a producción.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
OUT=SITE/'data/test_report.json'
TESTS=[]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def optional(path):
    return load(path) if path.exists() else None


def check(name, condition, detail=''):
    ok=bool(condition)
    TESTS.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    return ok


def clamp(x): return max(0,min(1.35,float(x)))

def operational_formula(r24,r72,r7,t24,t72,t7):
    raw=100*(.38*clamp(r24/t24)+.30*clamp(r72/t72)+.32*clamp(r7/t7))/1.35
    return round(raw)


def main():
    latest=load(SITE/'data/latest.json')
    state=load(SITE/'data/experimental_state.json')
    forecast=optional(SITE/'data/forecast/latest.json')
    verification=optional(SITE/'data/forecast/verification.json')
    hydraulics=load(SITE/'data/hydraulics/current_infrastructure.json')
    replay=load(SITE/'data/calibration/historical_replay.json')
    ana_geo=load(SITE/'data/hydrology/ana_catacaos_critical_segments_2026.geojson')
    ana_val=load(SITE/'data/hydrology/ana_catacaos_critical_segments_2026_validation.json')
    wis2=optional(SITE/'data/stations/senamhi_wis2_discovery.json')
    idesep=optional(SITE/'data/stations/senamhi_idesep_discovery.json')
    open_data=optional(SITE/'data/stations/senamhi_open_data_catalog.json')

    # Contrato matemático v0.7.1.
    check('formula_zero_is_zero',operational_formula(0,0,0,10,20,30)==0)
    check('formula_thresholds_equal_74',operational_formula(10,20,30,10,20,30)==74,
          'La normalización actual alcanza 100 a 135% de los umbrales provisionales.')
    check('formula_cap_is_100',operational_formula(13.5,27,40.5,10,20,30)==100)

    zones=latest.get('zones',[])
    check('three_pilot_zones_present',{z.get('id') for z in zones}=={'san_ildefonso','chosica','catacaos'})
    for z in zones:
        t=z.get('thresholds_provisional') or {}
        check(f"{z.get('id')}_thresholds_positive",all(float(t.get(k,0))>0 for k in ('rain24','rain72','rain7d')))

    # Estado experimental y puerta fluvial.
    check('experimental_state_not_production',state.get('production_use') is False)
    state_by={z.get('zone_id'):z for z in state.get('zones',[])}
    for zid in ('san_ildefonso','chosica','catacaos'):
        z=state_by.get(zid,{})
        check(f'{zid}_experimental_not_production',z.get('production_use') is False)
    cat=state_by.get('catacaos',{})
    if cat.get('river_state_available') is not True:
        check('catacaos_blocks_without_river_state','numeric_river_state_required' in (cat.get('blockers') or []))
        check('catacaos_readiness_is_blocked','BLOCKED' in str(cat.get('readiness','')))
    else:
        check('catacaos_river_state_declared',True,'Existe señal numérica; aún requiere validación hidráulica.')

    # Infraestructura nunca atenúa numéricamente sin calibración.
    check('hydraulic_inventory_not_production',hydraulics.get('production_use') is False)
    for z in hydraulics.get('zones',[]):
        zid=z.get('zone_id')
        check(f'{zid}_no_production_modifier',z.get('production_modifier') is None)
        check(f'{zid}_no_numeric_attenuation',(z.get('hydrologic_effect') or {}).get('numeric_attenuation_factor') is None)

    # Forecast y verificación.
    if forecast:
        check('forecast_not_production',forecast.get('production_use') is False)
        check('forecast_status_experimental',forecast.get('status')=='experimental_forecast_available')
        for z in forecast.get('zones',[]):
            vals=[z.get(k) for k in ('forecast24_mm','forecast72_mm','forecast120_mm') if z.get(k) is not None]
            check(f"forecast_{z.get('zone_id')}_nonnegative",all(float(v)>=0 for v in vals))
    else:
        check('forecast_dataset_present',False,'No existe forecast/latest.json')
    check('forecast_verification_present',verification is not None)
    if verification:
        check('forecast_verification_not_production',verification.get('production_use') is False)
        check('forecast_verification_pairs_nonnegative',int(verification.get('total_pairs',0))>=0)
        check('forecast_verification_min_sample_gate',int(verification.get('minimum_samples_for_initial_review',0))>=30)

    # Replay histórico: documenta la brecha sin recalibrar automáticamente.
    check('historical_replay_not_production',replay.get('production_use') is False)
    check('historical_replay_calibration_gate',(replay.get('interpretation_gate') or {}).get('status')=='CALIBRATION_REQUIRED')
    cases={c.get('event_id'):c for c in replay.get('cases',[])}
    check('historical_replay_has_three_known_cases',{'SI-2017-03-15','CH-2015-03-23','PI-2017-03-27'}.issubset(cases))
    ch=cases.get('CH-2015-03-23',{})
    ch_score=(ch.get('legacy_sampling_replay') or {}).get('threat_score')
    check('chosica_2015_known_capture_gap',ch_score is not None and float(ch_score)<40,
          'El evento conocido queda por debajo de Alta con parámetros actuales; debe seguir visible como brecha de calibración.')
    check('chosica_2015_flagged_for_review',ch.get('diagnostic')=='REVIEW_THRESHOLDS_OR_INPUT_SCALE')
    for event_id,c in cases.items():
        for block_name in ('legacy_sampling_replay','polygon_sampling_replay'):
            block=c.get(block_name)
            if block:
                score=float(block.get('threat_score',-1))
                check(f'replay_{event_id}_{block_name}_score_range',0<=score<=100)

    # Tramos ANA Catacaos: solo líneas validadas y nunca extensión de inundación.
    features=ana_geo.get('features',[])
    check('ana_segments_not_production',(ana_geo.get('properties') or {}).get('production_use') is False)
    check('ana_segments_validation_not_production',ana_val.get('production_use') is False)
    check('ana_segments_count_matches_validation',len(features)==int(ana_val.get('published_segment_count',-1)))
    check('ana_segments_minimum_current_reference_set',len(features)>=4,
          'La fuente ANA 2026 actualmente valida Simbilá, La Legua, Juan de Mori y Monte Sullón.')
    for f in features:
        p=f.get('properties') or {}
        check(f"ana_{p.get('sector','unknown')}_line_only",(f.get('geometry') or {}).get('type')=='LineString')
        check(f"ana_{p.get('sector','unknown')}_not_flood_polygon",p.get('is_flood_polygon') is False and p.get('is_inundation_extent') is False)
        check(f"ana_{p.get('sector','unknown')}_geometry_pass",p.get('geometry_status')=='PASS')
        check(f"ana_{p.get('sector','unknown')}_length_control",float(p.get('length_relative_difference_pct',999))<=15)
    withheld=[x for x in ana_val.get('validations',[]) if x.get('status')!='PASS']
    check('ana_review_geometry_is_withheld',all(x.get('geometry_publication')=='withheld_to_avoid_false_alignment' for x in withheld))

    # SENAMHI: cualquier vía descubierta permanece en validación paralela.
    for label,data in (('wis2',wis2),('idesep',idesep),('open_data',open_data)):
        if data is not None:
            check(f'senamhi_{label}_not_production',data.get('production_use') is False)
    if open_data is not None and open_data.get('status')=='catalog_available_historical_only':
        check('senamhi_open_data_historical_only',open_data.get('source',{}).get('use')=='station_catalog_and_historical_control_only')

    failures=[t for t in TESTS if t['status']=='FAIL']
    report={
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'version':'0.8-experimental',
        'production_use':False,
        'status':'PASS' if not failures else 'FAIL',
        'passed':len(TESTS)-len(failures),
        'failed':len(failures),
        'tests':TESTS,
        'note':'Estas pruebas verifican integridad arquitectónica, no validación científica de umbrales.'
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not failures else 1

if __name__=='__main__':
    sys.exit(main())
