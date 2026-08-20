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
    data=load(SITE/'data/latest.json')
    if not data:return
    for z in data.get('zones',[]):
        exp=z.get('experimental_polygon')
        if exp and exp.get('production_use') is not False:ERRORS.append(f"{z.get('id')}: experimental_polygon no puede ser productivo")

def check_history_contract():
    data=load(SITE/'data/history.json')
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
    if int(data.get('total_pairs',0))!=len(data.get('pairs',[])):ERRORS.append('forecast verification: total_pairs no coincide con evidencia persistida')
    for row in data.get('pairs',[]):
        if float(row.get('forecast_mm',0))<0 or float(row.get('observed_imerg_mm',0))<0:ERRORS.append('forecast verification: precipitación negativa')

def check_observed_imerg_archive():
    p=SITE/'data/forecast/observed_imerg_daily.json'
    if not p.exists():ERRORS.append('observed IMERG archive: archivo acumulativo requerido no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('observed IMERG archive: production_use debe ser false')
    expected_contract=(
        'append_only_by_zone_method_valid_date; first_audited_value_wins; '
        'conflicting_revisions_are_logged_without_overwrite'
    )
    if data.get('retention_contract')!=expected_contract:ERRORS.append('observed IMERG archive: contrato append-only inválido')
    if int(data.get('record_count',-1))!=len(data.get('records',[])):ERRORS.append('observed IMERG archive: record_count inconsistente')
    run170_artifact='88c0cd15ebbde7a9b789cacf4720c81e946e31d46f60546275fcac1dad851d9b'
    run170_verification='f4a79332710e8531e588b1f56222933e710439f38627c28a988ee7d11970ae1b'
    pinned=[row for row in data.get('seed_provenance',[]) if row.get('artifact_sha256')==run170_artifact]
    if len(pinned)!=1:ERRORS.append('observed IMERG archive: procedencia única del artefacto #170 ausente')
    elif pinned[0].get('verification_sha256')!=run170_verification:ERRORS.append('observed IMERG archive: hash de verification #170 inválido')
    expected={
        ('san_ildefonso','validated_dem_polygon'),
        ('chosica','validated_dem_polygon'),
        ('catacaos','provisional_weighted_operational_sampling_areas'),
    }
    seen=set()
    observation_keys=set()
    for record in data.get('records',[]):
        key=(record.get('zone_id'),record.get('sampling_method'))
        if key not in expected:ERRORS.append(f'observed IMERG archive: contrato espacial inesperado {key}')
        if key in seen:ERRORS.append(f'observed IMERG archive: registro duplicado {key}')
        seen.add(key)
        dates=set()
        for row in record.get('series',[]):
            day=row.get('date');rain=row.get('rain_mm')
            if not day or rain is None:ERRORS.append(f'observed IMERG archive {key}: fecha o lluvia ausente');continue
            if day in dates:ERRORS.append(f'observed IMERG archive {key}: fecha duplicada {day}')
            dates.add(day)
            observation_key=(*key,day)
            if observation_key in observation_keys:ERRORS.append(f'observed IMERG archive: clave duplicada {observation_key}')
            observation_keys.add(observation_key)
            if float(rain)<0:ERRORS.append(f'observed IMERG archive {key}: precipitación negativa')
    if seen!=expected:ERRORS.append(f'observed IMERG archive: contratos faltantes {sorted(expected-seen)}')
    for row in data.get('revision_candidates',[]):
        key=(row.get('zone_id'),row.get('sampling_method'))
        if key not in expected:ERRORS.append(f'observed IMERG archive: revisión con contrato inesperado {key}')
        if row.get('disposition')!='LOGGED_NOT_OVERWRITTEN_PENDING_SCIENTIFIC_REVIEW':ERRORS.append('observed IMERG archive: revisión sin disposición fail-closed')
        if row.get('production_use') is not False:ERRORS.append('observed IMERG archive: revisión no puede ser productiva')

def check_forecast_historical_daily():
    p=SITE/'data/forecast/historical_daily.json'
    if not p.exists():WARNINGS.append('forecast historical daily: aún no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('forecast historical daily: production_use debe ser false')
    for row in data.get('records',[]):
        zid=row.get('zone_id')
        if zid not in {'san_ildefonso','chosica','catacaos'}:ERRORS.append(f'forecast historical daily: zona inesperada {zid}')
        if row.get('production_use') is not False:ERRORS.append(f'forecast historical daily {zid}: registro no experimental')
        if int(row.get('hour_count',0))!=24:ERRORS.append(f'forecast historical daily {zid}: día incompleto')
        if float(row.get('forecast_mm',-1))<0:ERRORS.append(f'forecast historical daily {zid}: precipitación inválida')
        if not row.get('issue_time') or not row.get('source_dataset'):ERRORS.append(f'forecast historical daily {zid}: procedencia incompleta')

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

def check_ana_catacaos_segments():
    gp=SITE/'data/hydrology/ana_catacaos_critical_segments_2026.geojson'
    vp=SITE/'data/hydrology/ana_catacaos_critical_segments_2026_validation.json'
    if not gp.exists() or not vp.exists():WARNINGS.append('ANA Catacaos 2026: segmentos validados aún no generados');return
    geo,val=load(gp),load(vp)
    if not geo or not val:return
    if (geo.get('properties') or {}).get('production_use') is not False:ERRORS.append('ANA Catacaos: GeoJSON debe ser experimental')
    if val.get('production_use') is not False:ERRORS.append('ANA Catacaos: validación debe ser experimental')
    features=geo.get('features',[])
    if val.get('status')=='PASS' and not features:ERRORS.append('ANA Catacaos: PASS sin segmentos publicados')
    if int(val.get('published_segment_count',-1))!=len(features):ERRORS.append('ANA Catacaos: conteo de segmentos no coincide con validación')
    for f in features:
        props=f.get('properties') or {}
        if props.get('production_use') is not False:ERRORS.append('ANA Catacaos: segmento no puede ser productivo')
        if props.get('geometry_status')!='PASS':ERRORS.append(f"ANA Catacaos {props.get('sector')}: solo PASS puede publicarse")
        if props.get('is_flood_polygon') is not False or props.get('is_inundation_extent') is not False:ERRORS.append(f"ANA Catacaos {props.get('sector')}: tramo no puede etiquetarse como inundación")
        if (f.get('geometry') or {}).get('type')!='LineString':ERRORS.append(f"ANA Catacaos {props.get('sector')}: geometría debe ser LineString")
        try:
            g=shape(f.get('geometry'))
            if g.is_empty or not g.is_valid:ERRORS.append(f"ANA Catacaos {props.get('sector')}: geometría inválida")
        except Exception as exc:ERRORS.append(f'ANA Catacaos: geometría no legible {exc}')
        diff=props.get('length_relative_difference_pct')
        if diff is None or float(diff)>15:ERRORS.append(f"ANA Catacaos {props.get('sector')}: diferencia de longitud >15%")
    for row in val.get('validations',[]):
        if row.get('status')!='PASS' and row.get('geometry_publication')!='withheld_to_avoid_false_alignment':ERRORS.append(f"ANA Catacaos {row.get('sector')}: REVIEW/FAIL debe quedar retenido")

def check_historical_replay():
    p=SITE/'data/calibration/historical_replay.json'
    if not p.exists():WARNINGS.append('Historical replay: aún no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('Historical replay: production_use debe ser false')
    forbidden={'new_thresholds','calibrated_thresholds','threshold_update','production_thresholds','production_modifier'}
    if forbidden.intersection(data.keys()):ERRORS.append('Historical replay: no puede escribir umbrales/calibración productiva')
    if (data.get('interpretation_gate') or {}).get('status')!='CALIBRATION_REQUIRED':ERRORS.append('Historical replay: debe mantener CALIBRATION_REQUIRED')
    for case in data.get('cases',[]):
        if case.get('production_use') is not False:ERRORS.append(f"Historical replay {case.get('event_id')}: debe ser experimental")
        for block in (case.get('legacy_sampling_replay'),case.get('polygon_sampling_replay')):
            if not block:continue
            score=block.get('threat_score')
            if score is None or not 0<=float(score)<=100:ERRORS.append(f"Historical replay {case.get('event_id')}: amenaza fuera de rango")

def check_senamhi_wis2_discovery():
    p=SITE/'data/stations/senamhi_wis2_discovery.json'
    if not p.exists():WARNINGS.append('SENAMHI WIS2: descubrimiento aún no disponible');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False:ERRORS.append('SENAMHI WIS2: production_use debe ser false')
    if int(data.get('station_count',0))<0:ERRORS.append('SENAMHI WIS2: station_count inválido')
    for zid,stations in (data.get('nearest_stations') or {}).items():
        for s in stations:
            if float(s.get('distance_km',0))<0:ERRORS.append(f'SENAMHI WIS2 {zid}: distancia negativa')

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
    elif any(x in block for x in ('experimental_polygon','forecast','hydraulic','experimental_state','river_state','senamhi_wis2')):ERRORS.append('calc(z) consume campos experimentales')

def check_manifest():
    data=load(SITE/'data/scientific_status.json')
    if not data:return
    for z in data.get('zones',[]):
        if z.get('production_ready') is not False:ERRORS.append(f"Manifest {z.get('id')}: production_ready debe ser false")

def main():
    check_watershed('san_ildefonso','san_ildefonso_watershed.geojson','san_ildefonso_validation.json')
    check_watershed('chosica','huaycoloro_watershed.geojson','huaycoloro_validation.json')
    check_latest_contract();check_history_contract();check_forecast_contract();check_forecast_verification();check_observed_imerg_archive();check_forecast_historical_daily();check_hydraulic_inventory();check_piura_reference_model();check_catacaos_document_context();check_ana_catacaos_segments();check_historical_replay();check_senamhi_wis2_discovery();check_experimental_state();check_frontend_contract();check_manifest()
    for w in WARNINGS:print('WARNING:',w)
    if ERRORS:
        for e in ERRORS:print('ERROR:',e)
        print(f'Validación científica FALLÓ: {len(ERRORS)} error(es)');return 1
    print(f'Validación científica OK · {len(WARNINGS)} advertencia(s)');return 0

if __name__=='__main__':sys.exit(main())
