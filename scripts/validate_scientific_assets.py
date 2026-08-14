#!/usr/bin/env python3
"""Puertas automáticas de seguridad científica para IRFEN v0.8."""
from pathlib import Path
import json
import sys
from shapely.geometry import shape

ROOT=Path(__file__).resolve().parents[1]; SITE=ROOT/'site'; ERRORS=[]; WARNINGS=[]

def load(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:ERRORS.append(f'JSON inválido {path}: {exc}');return None

def check_watershed(zone_id,geo_name,val_name):
    gp=SITE/'data/watersheds'/geo_name;vp=SITE/'data/watersheds'/val_name
    if not gp.exists() or not vp.exists():WARNINGS.append(f'{zone_id}: activos de cuenca aún no disponibles');return
    geo,val=load(gp),load(vp)
    if not geo or not val:return
    try:
        geom=shape(geo['geometry'])
        if geom.is_empty or not geom.is_valid:ERRORS.append(f'{zone_id}: GeoJSON vacío o inválido')
    except Exception as exc:ERRORS.append(f'{zone_id}: geometría no legible: {exc}')
    if geo.get('properties',{}).get('production_ready') is not False:ERRORS.append(f'{zone_id}: polígono debe seguir production_ready=false')
    if val.get('production_ready') is not False:ERRORS.append(f'{zone_id}: validación debe seguir production_ready=false')
    status=str(val.get('status','')).upper();err=val.get('relative_area_error_pct')
    if status=='PASS' and (err is None or float(err)>15):ERRORS.append(f'{zone_id}: PASS incompatible con error de área {err}%')
    topo=val.get('topology_check')
    if topo and status=='PASS' and topo.get('status')!='CONSISTENT':ERRORS.append(f'{zone_id}: PASS con topología no consistente')
    if val.get('decision')=='candidate_for_hydraulic_review':
        hyd=val.get('hydraulic_context') or val.get('hydraulic_context_2026') or {}
        if 'REQUIRED' not in str(hyd.get('status','')):ERRORS.append(f'{zone_id}: falta puerta hidráulica requerida')

def check_latest_contract():
    data=load(SITE/'data/latest.json');
    if not data:return
    for z in data.get('zones',[]):
        exp=z.get('experimental_polygon')
        if exp and exp.get('production_use') is not False:ERRORS.append(f"{z.get('id')}: experimental_polygon no puede ser productivo")

def check_history_contract():
    data=load(SITE/'data/history.json');
    if not data:return
    for e in data.get('events',[]):
        exp=e.get('experimental_polygon')
        if exp and exp.get('production_use') is not False:ERRORS.append(f"{e.get('id')}: histórico experimental no puede ser productivo")

def check_forecast_contract():
    p=SITE/'data/forecast/latest.json'
    if not p.exists():WARNINGS.append('forecast: dataset experimental aún no disponible');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('forecast: production_use debe permanecer false')
    for z in data.get('zones',[]):
        for key in ('forecast24_mm','forecast72_mm','forecast120_mm'):
            v=z.get(key)
            if v is not None and float(v)<0:ERRORS.append(f"forecast {z.get('zone_id')}: {key} negativo")
        if z.get('zone_id')=='catacaos' and z.get('sampling_method')!='provisional_weighted_operational_sampling_areas':ERRORS.append('Catacaos: forecast debe seguir espacialmente provisional')

def check_forecast_verification():
    p=SITE/'data/forecast/verification.json'
    if not p.exists():WARNINGS.append('forecast verification: aún no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('forecast verification: production_use debe ser false')
    forbidden={'bias_correction_factor','operational_correction','calibrated_threshold','production_modifier'}
    if forbidden.intersection(data.keys()):ERRORS.append('forecast verification: contiene campos de corrección operativa prohibidos')
    if int(data.get('total_pairs',0))<0:ERRORS.append('forecast verification: total_pairs inválido')
    for row in data.get('pairs',[]):
        if float(row.get('forecast_mm',0))<0 or float(row.get('observed_imerg_mm',0))<0:ERRORS.append('forecast verification: precipitación negativa')

def check_hydraulic_inventory():
    p=SITE/'data/hydraulics/current_infrastructure.json'
    if not p.exists():WARNINGS.append('hydraulics: inventario no disponible');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('hydraulics: production_use debe ser false')
    expected={'san_ildefonso','chosica','catacaos'};zones=data.get('zones',[]);present={z.get('zone_id') for z in zones}
    if expected-present:ERRORS.append(f'hydraulics: faltan zonas {sorted(expected-present)}')
    for z in zones:
        zid=z.get('zone_id');gate=z.get('scientific_gate') or {};effect=z.get('hydrologic_effect') or {}
        if z.get('production_modifier') is not None:ERRORS.append(f'hydraulics {zid}: production_modifier debe ser null')
        if effect.get('numeric_attenuation_factor') is not None:ERRORS.append(f'hydraulics {zid}: no se admite atenuación numérica sin calibrar')
        if zid in {'san_ildefonso','chosica'} and gate.get('status')!='HYDRAULIC_CALIBRATION_REQUIRED':ERRORS.append(f'hydraulics {zid}: falta puerta hidráulica')
        if zid=='catacaos' and gate.get('status')!='RIVER_STATE_REQUIRED':ERRORS.append('hydraulics catacaos: falta puerta RIVER_STATE_REQUIRED')

def check_piura_reference_model():
    p=SITE/'data/hydrology/piura_reference_model.json'
    if not p.exists():WARNINGS.append('Piura reference model: aún no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('Piura reference model: production_use debe ser false')
    if data.get('model_status')!='reference_harmonization_required':ERRORS.append('Piura reference model: debe exigir homologación')
    st=data.get('station_reference') or {}
    if st.get('use')!='upstream_station_reference_only':ERRORS.append('Puente Ñácara debe seguir marcado como referencia aguas arriba')
    for e in data.get('historical_event_flows',[]):
        if e.get('use')!='historical_event_reference_only' or e.get('location_status')!='not_harmonized_to_puente_nacara':ERRORS.append('Piura: caudal histórico no debe considerarse homologado')
    for d in data.get('design_references',[]):
        if d.get('use')!='design_reference_only':ERRORS.append('Piura: referencia de diseño mal etiquetada')

def check_catacaos_document_context():
    p=SITE/'data/hydrology/catacaos_official_context.geojson'
    if not p.exists():WARNINGS.append('Catacaos context: capa documental aún no disponible');return
    data=load(p)
    if not data:return
    if (data.get('properties') or {}).get('production_use') is not False:ERRORS.append('Catacaos context: producción debe ser false')
    for f in data.get('features',[]):
        props=f.get('properties') or {}
        if props.get('context_only') is not True or props.get('is_hazard_polygon') is not False or props.get('production_use') is not False:ERRORS.append(f"Catacaos context {props.get('id')}: no puede presentarse como peligro")
        try:
            g=shape(f.get('geometry'))
            if g.is_empty or not g.is_valid:ERRORS.append(f"Catacaos context {props.get('id')}: geometría inválida")
        except Exception as exc:ERRORS.append(f'Catacaos context: geometría no legible {exc}')

def check_experimental_state():
    p=SITE/'data/experimental_state.json'
    if not p.exists():ERRORS.append('experimental_state: archivo requerido no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('experimental_state: production_use debe ser false')
    rules=data.get('rules') or {}
    for key in ('no_composite_risk_score','no_hydraulic_attenuation_without_calibration','catacaos_requires_river_state','threshold_crossings_are_test_signals_only'):
        if rules.get(key) is not True:ERRORS.append(f'experimental_state: regla {key} debe ser true')
    expected={'san_ildefonso','chosica','catacaos'};zones=data.get('zones',[]);present={z.get('zone_id') for z in zones}
    if expected-present:ERRORS.append(f'experimental_state: faltan zonas {sorted(expected-present)}')
    forbidden={'alert','alert_level','final_alert','operational_alert','production_score'}
    for z in zones:
        zid=z.get('zone_id')
        if z.get('production_use') is not False:ERRORS.append(f'experimental_state {zid}: production_use debe ser false')
        if forbidden.intersection(z.keys()):ERRORS.append(f'experimental_state {zid}: campos de alerta prohibidos')
        if (z.get('hydraulic_gate') or {}).get('production_modifier') is not None:ERRORS.append(f'experimental_state {zid}: modificador hidráulico prohibido')
        if zid=='catacaos' and z.get('river_state_available') is not True and 'numeric_river_state_required' not in set(z.get('blockers') or []):ERRORS.append('Catacaos debe bloquearse sin estado numérico del río')

def check_frontend_contract():
    text=(SITE/'index.html').read_text(encoding='utf-8') if (SITE/'index.html').exists() else ''
    start=text.find('function calc(z)');end=text.find('function bar(',start);block=text[start:end] if start>=0 and end>start else ''
    if not block:ERRORS.append('No se localizó function calc(z)')
    elif any(x in block for x in ('experimental_polygon','forecast','hydraulic','experimental_state','river_state')):ERRORS.append('calc(z) consume campos experimentales')

def check_manifest():
    data=load(SITE/'data/scientific_status.json')
    if not data:return
    for z in data.get('zones',[]):
        if z.get('production_ready') is not False:ERRORS.append(f"Manifest {z.get('id')}: production_ready debe ser false")

def main():
    check_watershed('san_ildefonso','san_ildefonso_watershed.geojson','san_ildefonso_validation.json')
    check_watershed('chosica','huaycoloro_watershed.geojson','huaycoloro_validation.json')
    check_latest_contract();check_history_contract();check_forecast_contract();check_forecast_verification();check_hydraulic_inventory();check_piura_reference_model();check_catacaos_document_context();check_experimental_state();check_frontend_contract();check_manifest()
    for w in WARNINGS:print('WARNING:',w)
    if ERRORS:
        for e in ERRORS:print('ERROR:',e)
        print(f'Validación científica FALLÓ: {len(ERRORS)} error(es)');return 1
    print(f'Validación científica OK · {len(WARNINGS)} advertencia(s)');return 0

if __name__=='__main__':sys.exit(main())
