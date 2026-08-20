#!/usr/bin/env python3
"""Puertas automáticas de seguridad científica para IRFEN v0.8."""
from pathlib import Path
import json
import sys
from shapely.geometry import shape

try:
    from verify_geos_against_imerg import canonical_sha256
except ImportError:
    from scripts.verify_geos_against_imerg import canonical_sha256

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
    expected={'san_ildefonso','chosica','catacaos'}
    if set(data.get('pilot_zone_ids') or [])!=expected:ERRORS.append('forecast verification: deben existir exactamente los tres pilotos')
    by_zone=data.get('by_zone') or {}
    if set(by_zone)!=expected:ERRORS.append('forecast verification: by_zone no coincide con los tres pilotos')
    if int(data.get('total_pairs',0))!=sum(int((by_zone.get(z) or {}).get('n',0)) for z in expected):ERRORS.append('forecast verification: total no coincide con suma por piloto')
    provenance=data.get('provenance') or {}
    if provenance.get('fallback_used') is not False:ERRORS.append('forecast verification: fallback científico prohibido')
    if 'HISTORY_ONLY' not in str(provenance.get('acquisition_mode','')):ERRORS.append('forecast verification: no usa exclusivamente el histórico dedicado')
    if (data.get('monotonicity') or {}).get('silent_decrease_forbidden') is not True:ERRORS.append('forecast verification: falta guarda contra disminuciones silenciosas')
    pair_keys=set()
    for row in data.get('pairs',[]):
        if float(row.get('forecast_mm',0))<0 or float(row.get('observed_imerg_mm',0))<0:ERRORS.append('forecast verification: precipitación negativa')
        key=(row.get('zone_id'),row.get('sampling_method'),row.get('snapshot_generated_at'),row.get('valid_date_utc'),row.get('forecast_record_kind'))
        if key in pair_keys:ERRORS.append(f'forecast verification: par duplicado {key}')
        pair_keys.add(key)

def check_imerg_verification_history():
    p=SITE/'data/forecast/imerg_verification_history.json'
    if not p.exists():ERRORS.append('IMERG verification history: archivo dedicado requerido no generado');return
    data=load(p)
    if not data:return
    if data.get('production_use') is not False or data.get('production_ready') is not False:ERRORS.append('IMERG verification history: guardas TEST_ONLY inválidas')
    retention=data.get('retention_policy') or {}
    if retention.get('mode')!='APPEND_ONLY':ERRORS.append('IMERG verification history: retención no es APPEND_ONLY')
    if retention.get('deduplication_key')!=['zone_id','sampling_method','valid_date_utc']:ERRORS.append('IMERG verification history: clave de deduplicación inválida')
    if retention.get('tombstone_creation_policy')!='MANUAL_REVIEWED_COMMIT_ONLY':ERRORS.append('IMERG verification history: tombstones no están limitados a commits manuales revisados')
    if retention.get('automatic_tombstone_creation') is not False:ERRORS.append('IMERG verification history: creación automática de tombstones debe estar prohibida')
    durable=data.get('durable_store') or {}
    if durable.get('mode')!='GIT_VERSIONED_REPOSITORY':ERRORS.append('IMERG verification history: falta persistencia durable versionada en Git')
    if durable.get('pages_role')!='OPTIONAL_PUBLISHED_REPLICA_NOT_SOURCE_OF_TRUTH':ERRORS.append('IMERG verification history: Pages no puede ser fuente durable')
    expected={
        ('san_ildefonso','validated_dem_polygon'),
        ('chosica','validated_dem_polygon'),
        ('catacaos','provisional_weighted_operational_sampling_areas'),
    }
    seen=set();contracts=set();evidence_by_id={row.get('evidence_id'):row for row in data.get('source_evidence',[])}
    for row in data.get('observations',[]):
        contract=(row.get('zone_id'),row.get('sampling_method'));key=(*contract,row.get('valid_date_utc'))
        contracts.add(contract)
        if contract not in expected:ERRORS.append(f'IMERG verification history: contrato espacial inesperado {contract}')
        if key in seen:ERRORS.append(f'IMERG verification history: observación duplicada {key}')
        seen.add(key)
        if not key[2] or row.get('observed_imerg_mm') is None or float(row.get('observed_imerg_mm',-1))<0:ERRORS.append(f'IMERG verification history: observación inválida {key}')
        if row.get('provenance_evidence_id') not in evidence_by_id:ERRORS.append(f'IMERG verification history: procedencia ausente {key}')
    if contracts!=expected:ERRORS.append(f'IMERG verification history: contratos faltantes {sorted(expected-contracts)}')
    for row in data.get('withdrawals',[]):
        key=(row.get('zone_id'),row.get('sampling_method'),row.get('valid_date_utc'))
        observation=next((item for item in data.get('observations',[]) if (item.get('zone_id'),item.get('sampling_method'),item.get('valid_date_utc'))==key),None)
        evidence=evidence_by_id.get((observation or {}).get('provenance_evidence_id'))
        required=(row.get('withdrawal_id'),row.get('reason'),row.get('approval_reference'),row.get('approved_by'),row.get('approved_at'),row.get('recorded_at'),row.get('observation_sha256'),row.get('evidence_sha256'))
        if row.get('status')!='APPROVED' or not all(required):ERRORS.append('IMERG verification history: retirada no explícita/aprobada')
        if row.get('creation_mode')!='MANUAL_REVIEWED_COMMIT' or row.get('automatic_creation') is not False:ERRORS.append('IMERG verification history: tombstone automático o no revisado')
        if observation is None or row.get('observation_sha256')!=canonical_sha256(observation):ERRORS.append(f'IMERG verification history: hash de observación inválido en retirada {key}')
        if evidence is None or row.get('evidence_sha256')!=canonical_sha256(evidence):ERRORS.append(f'IMERG verification history: hash de evidencia inválido en retirada {key}')

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
    check_latest_contract();check_history_contract();check_forecast_contract();check_forecast_verification();check_imerg_verification_history();check_forecast_historical_daily();check_hydraulic_inventory();check_piura_reference_model();check_catacaos_document_context();check_ana_catacaos_segments();check_historical_replay();check_senamhi_wis2_discovery();check_experimental_state();check_frontend_contract();check_manifest()
    for w in WARNINGS:print('WARNING:',w)
    if ERRORS:
        for e in ERRORS:print('ERROR:',e)
        print(f'Validación científica FALLÓ: {len(ERRORS)} error(es)');return 1
    print(f'Validación científica OK · {len(WARNINGS)} advertencia(s)');return 0

if __name__=='__main__':sys.exit(main())
