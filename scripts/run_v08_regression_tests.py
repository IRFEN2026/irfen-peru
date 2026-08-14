#!/usr/bin/env python3
"""Pruebas de regresión funcionales para IRFEN v0.8.

Se ejecutan en cada deployment. No prueban que los umbrales sean científicamente
válidos; prueban que la arquitectura respete las separaciones y bloqueos
acordados mientras la calibración continúa.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import sys

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
OUT=SITE/'data/test_report.json'
TESTS=[]


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


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
    forecast=load(SITE/'data/forecast/latest.json') if (SITE/'data/forecast/latest.json').exists() else None
    hydraulics=load(SITE/'data/hydraulics/current_infrastructure.json')

    check('formula_zero_is_zero',operational_formula(0,0,0,10,20,30)==0)
    check('formula_thresholds_equal_74',operational_formula(10,20,30,10,20,30)==74,
          'La normalización actual alcanza 100 a 135% de los umbrales provisionales.')
    check('formula_cap_is_100',operational_formula(13.5,27,40.5,10,20,30)==100)

    zones=latest.get('zones',[])
    check('three_pilot_zones_present',{z.get('id') for z in zones}=={'san_ildefonso','chosica','catacaos'})
    for z in zones:
        t=z.get('thresholds_provisional') or {}
        check(f"{z.get('id')}_thresholds_positive",all(float(t.get(k,0))>0 for k in ('rain24','rain72','rain7d')))

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
        check('catacaos_river_state_declared',True,'Existe señal numérica; requiere validación adicional antes de producción.')

    check('hydraulic_inventory_not_production',hydraulics.get('production_use') is False)
    for z in hydraulics.get('zones',[]):
        zid=z.get('zone_id')
        check(f'{zid}_no_production_modifier',z.get('production_modifier') is None)
        check(f'{zid}_no_numeric_attenuation',(z.get('hydrologic_effect') or {}).get('numeric_attenuation_factor') is None)

    if forecast:
        check('forecast_not_production',forecast.get('production_use') is False)
        check('forecast_status_experimental',forecast.get('status')=='experimental_forecast_available')
        for z in forecast.get('zones',[]):
            vals=[z.get(k) for k in ('forecast24_mm','forecast72_mm','forecast120_mm') if z.get(k) is not None]
            check(f"forecast_{z.get('zone_id')}_nonnegative",all(float(v)>=0 for v in vals))
    else:
        check('forecast_dataset_present',False,'No existe forecast/latest.json')

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
