#!/usr/bin/env python3
"""Pruebas de regresión funcionales para IRFEN v0.8.

Verifican integridad arquitectónica y las puertas acordadas. No demuestran que
los umbrales sean científicamente válidos ni autorizan promoción a producción.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

from build_v08_scorecard import final_release_audit_gate

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
OUT=SITE/'data/test_report.json'
TESTS=[]


def load(path): return json.loads(path.read_text(encoding='utf-8'))
def optional(path): return load(path) if path.exists() else None

def check(name, condition, detail=''):
    ok=bool(condition); TESTS.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail}); return ok

def clamp(x): return max(0,min(1.35,float(x)))
def operational_formula(r24,r72,r7,t24,t72,t7):
    return round(100*(.38*clamp(r24/t24)+.30*clamp(r72/t72)+.32*clamp(r7/t7))/1.35)


def main():
    latest=load(SITE/'data/latest.json')
    state=load(SITE/'data/experimental_state.json')
    forecast=optional(SITE/'data/forecast/latest.json')
    verification=optional(SITE/'data/forecast/verification.json')
    hydraulics=load(SITE/'data/hydraulics/current_infrastructure.json')
    replay=load(SITE/'data/calibration/historical_replay.json')
    ana_geo=load(SITE/'data/hydrology/ana_catacaos_critical_segments_2026.geojson')
    ana_val=load(SITE/'data/hydrology/ana_catacaos_critical_segments_2026_validation.json')
    pedregal=optional(SITE/'data/calibration/pedregal_ana_validation.json')
    pedregal_hh=optional(SITE/'data/calibration/pedregal_2015_imerg_halfhour.json')
    pedregal_ground=optional(SITE/'data/calibration/pedregal_ground_evidence_2015.json')
    si_hh=optional(SITE/'data/calibration/san_ildefonso_imerg_halfhour_events.json')
    wis2=optional(SITE/'data/stations/senamhi_wis2_discovery.json')
    idesep=optional(SITE/'data/stations/senamhi_idesep_discovery.json')
    open_data=optional(SITE/'data/stations/senamhi_open_data_catalog.json')
    imerg_early=optional(SITE/'data/calibration/imerg_early_live_archive.json')
    phase2=load(ROOT/'config/phase2_candidate_inventory_v0_1.json')
    closeout_contract=load(ROOT/'config/v08_closeout_contract.json')
    closeout_scorecard=optional(SITE/'data/v08_scorecard.json')
    glofas_current=optional(SITE/'data/hydrology/glofas_catacaos_current.json')

    # Contrato matemático v0.7.1: nunca cambia como efecto colateral de v0.8.
    check('formula_zero_is_zero',operational_formula(0,0,0,10,20,30)==0)
    check('formula_thresholds_equal_74',operational_formula(10,20,30,10,20,30)==74,
          'La normalización v0.7.1 alcanza 100 a 135% de los umbrales provisionales.')
    check('formula_cap_is_100',operational_formula(13.5,27,40.5,10,20,30)==100)

    zones=latest.get('zones',[])
    check('three_pilot_zones_present',{z.get('id') for z in zones}=={'san_ildefonso','chosica','catacaos'})
    for z in zones:
        t=z.get('thresholds_provisional') or {}
        check(f"{z.get('id')}_thresholds_positive",all(float(t.get(k,0))>0 for k in ('rain24','rain72','rain7d')))

    # Contrato end-to-end: solo recomendaciones TEST_, nunca producción.
    check('experimental_state_not_production',state.get('production_use') is False)
    check('experimental_state_not_production_ready',state.get('production_ready') is False)
    core=state.get('core_test_status') or {}
    check('core_test_status_present',core.get('code') in {'END_TO_END_TEST_MODE_AVAILABLE_WITH_KNOWN_LIMITATIONS','END_TO_END_TEST_MODE_PARTIAL'})
    check('core_never_claims_production_ready',core.get('production_ready') is False)
    check('core_stop_rule_keeps_scope_focused','No ampliar' in str(core.get('stop_rule','')))

    state_by={z.get('zone_id'):z for z in state.get('zones',[])}
    for zid in ('san_ildefonso','chosica','catacaos'):
        z=state_by.get(zid,{})
        rec=z.get('test_recommendation') or {}
        check(f'{zid}_experimental_not_production',z.get('production_use') is False)
        check(f'{zid}_test_recommendation_exists',str(rec.get('code','')).startswith('TEST_'))
        check(f'{zid}_recommendation_test_only',rec.get('mode')=='TEST_ONLY')
        check(f'{zid}_recommendation_not_operational',rec.get('operational_alert') is False)
        check(f'{zid}_recommendation_does_not_modify_thresholds',rec.get('thresholds_modified') is False)
        check(f'{zid}_recommendation_no_hydraulic_modifier',rec.get('hydraulic_modifier_applied') is False)

    # Catacaos: SENAMHI es primario; GloFAS solo categoría secundaria sin m3/s.
    cat=state_by.get('catacaos',{})
    river=cat.get('river_state') or {}
    if cat.get('river_state_available') is not True:
        blockers=cat.get('blockers') or []
        check('catacaos_blocks_without_river_state',any('river_state' in str(x) or 'proxy' in str(x) for x in blockers))
        check('catacaos_readiness_is_blocked','BLOCKED' in str(cat.get('readiness','')))
    else:
        check('catacaos_river_state_declared',river.get('available') is True)
        if river.get('role')=='secondary_modelled_categorical_proxy':
            check('catacaos_glofas_has_no_numeric_value',river.get('value') is None)
            check('catacaos_glofas_has_no_unit',river.get('unit') is None)
            check('catacaos_glofas_role_is_categorical',river.get('proxy_class') in {'MODELLED_20Y_EXCEEDANCE','MODELLED_5Y_EXCEEDANCE','NO_MODELLED_RETURN_PERIOD_EXCEEDANCE'})
            check('catacaos_glofas_not_production',river.get('production_use') is False)

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

    # GloFAS es secundario: una caída remota debe bloquear la señal actual sin
    # derribar la publicación ni convertir la ausencia de datos en bajo riesgo.
    check('glofas_current_present',glofas_current is not None)
    if glofas_current:
        check('glofas_current_not_production',glofas_current.get('production_use') is False)
        check('glofas_current_status_controlled',glofas_current.get('status') in {'available','SOURCE_TEMPORARILY_UNREACHABLE','BLOCKED_BY_PROXY_VALIDATION'})
        if glofas_current.get('status')=='available':
            check('glofas_current_available_not_stale',glofas_current.get('usable_for_experimental_decision') is True and glofas_current.get('stale') is not True)
            check('glofas_current_class_categorical',glofas_current.get('river_proxy_class') in {'MODELLED_20Y_EXCEEDANCE','MODELLED_5Y_EXCEEDANCE','NO_MODELLED_RETURN_PERIOD_EXCEEDANCE'})
        elif glofas_current.get('status')=='SOURCE_TEMPORARILY_UNREACHABLE':
            check('glofas_outage_blocks_current_use',glofas_current.get('usable_for_experimental_decision') is False and glofas_current.get('stale') is True)
            check('glofas_outage_not_false_low_risk',glofas_current.get('river_proxy_class') is None)

    # IMERG Early: la continuidad se mide explícitamente y sigue fuera de producción.
    check('imerg_early_archive_present',imerg_early is not None)
    if imerg_early:
        summary=imerg_early.get('summary') or {}
        check('imerg_early_not_production',imerg_early.get('production_use') is False)
        check('imerg_early_continuity_coverage_range',0<=float(summary.get('continuity_coverage_pct',0))<=100)
        check('imerg_early_missing_slots_nonnegative',int(summary.get('missing_half_hour_slots_within_span',-1))>=0)
        check('imerg_early_tail_not_longer_than_archive',int(summary.get('current_continuous_tail_samples',0))<=int(summary.get('observed_unique_timestamps',0)))

    # Expansión: preparación documental sin activar zonas ni inventar puntuaciones.
    check('phase2_inventory_not_production',phase2.get('production_use') is False)
    check('phase2_inventory_research_only',phase2.get('deployment_status')=='RESEARCH_ONLY')
    candidates=phase2.get('candidates') or []
    check('phase2_inventory_first_wave_size',8<=len(candidates)<=12)
    check('phase2_inventory_outside_lima_majority',sum(c.get('inside_lima_metropolitana') is False for c in candidates)>=len(candidates)/2)
    check('phase2_inventory_no_numeric_scores',all(c.get('priority_score') is None for c in candidates))
    check('phase2_inventory_no_activation',all(c.get('deployment_status')=='RESEARCH_ONLY' for c in candidates))
    check('phase2_inventory_has_official_evidence',all(c.get('official_sources') for c in candidates))

    # Scorecard de cierre: hitos discretos, acumulativos y sin efecto operativo.
    check('closeout_contract_not_production',closeout_contract.get('production_use') is False)
    check('closeout_contract_exact_pilots',closeout_contract.get('pilot_zone_ids')==['san_ildefonso','chosica','catacaos'])
    check('closeout_contract_fixed_milestones',closeout_contract.get('milestone_percentages')==[25,50,75,100])
    shadow_contract=closeout_contract.get('shadow_validation') or {}
    check('closeout_contract_shadow_requires_event_day',int(shadow_contract.get('minimum_verified_event_days',0))>=1)
    check('closeout_contract_shadow_requires_none_days',int(shadow_contract.get('minimum_verified_none_days',0))>=1)
    check('closeout_contract_release_completion_explicit',closeout_contract.get('release_completion_marker')=='Release status: COMPLETE')
    check('closeout_shadow_review_protocol_present',(ROOT/'docs/SHADOW_OUTCOME_REVIEW_PROTOCOL.md').is_file())
    check('closeout_shadow_review_tool_present',(ROOT/'scripts/review_shadow_outcome.py').is_file())
    check('closeout_final_audit_rejects_missing_shadow',final_release_audit_gate(False,True,True) is False)
    check('closeout_final_audit_rejects_scientific_blockers',final_release_audit_gate(True,False,True) is False)
    check('closeout_final_audit_rejects_incomplete_release',final_release_audit_gate(True,True,False) is False)
    check('closeout_final_audit_accepts_all_prerequisites',final_release_audit_gate(True,True,True) is True)
    if closeout_scorecard is not None:
        milestones=closeout_scorecard.get('milestones') or []
        reached=[int(m.get('percentage',0)) for m in milestones if m.get('reached') is True]
        check('closeout_scorecard_not_production',closeout_scorecard.get('production_use') is False and closeout_scorecard.get('production_ready') is False)
        check('closeout_scorecard_fixed_milestones',[m.get('percentage') for m in milestones]==[25,50,75,100])
        check('closeout_scorecard_current_matches_reached',int(closeout_scorecard.get('current_milestone_pct',0))==max(reached,default=0))
        check('closeout_scorecard_reached_is_cumulative',reached==[25,50,75,100][:len(reached)])
        final_milestone=next((m for m in milestones if m.get('percentage')==100),{})
        final_audit=next((c for c in final_milestone.get('checks',[]) if c.get('id')=='final_audit_and_release_documented'),{})
        final_evidence=final_audit.get('evidence') or {}
        final_prerequisites=(
            final_evidence.get('prerequisite_shadow_gate_passed') is True
            and final_evidence.get('prerequisite_scientific_gate_passed') is True
        )
        check(
            'closeout_final_audit_requires_shadow_and_scientific_gates',
            final_audit.get('passed') is not True or final_prerequisites,
        )

    # Replay histórico: documenta brechas, no recalibra automáticamente.
    check('historical_replay_not_production',replay.get('production_use') is False)
    check('historical_replay_calibration_gate',(replay.get('interpretation_gate') or {}).get('status')=='CALIBRATION_REQUIRED')
    cases={c.get('event_id'):c for c in replay.get('cases',[])}
    check('historical_replay_has_core_known_cases',{'SI-2017-03-15','CH-2015-03-23','HU-2017-03-15','PI-2017-03-27'}.issubset(cases))
    ch=cases.get('CH-2015-03-23',{})
    ch_score=(ch.get('legacy_sampling_replay') or {}).get('threat_score')
    check('chosica_2015_known_capture_gap',ch_score is not None and float(ch_score)<40,
          'El evento local severo queda por debajo de Alta con el agregado legado; no se fuerza el umbral.')
    check('chosica_2015_flagged_for_review',ch.get('diagnostic')=='REVIEW_THRESHOLDS_OR_INPUT_SCALE')
    for event_id,c in cases.items():
        for block_name in ('legacy_sampling_replay','polygon_sampling_replay'):
            block=c.get(block_name)
            if block:
                score=float(block.get('threat_score',-1))
                check(f'replay_{event_id}_{block_name}_score_range',0<=score<=100)

    # Pedregal: geometría representativa controlada por ANA, pero señal local viva pendiente.
    check('pedregal_validation_present',pedregal is not None)
    if pedregal:
        gates=pedregal.get('gates') or {}
        check('pedregal_not_production',pedregal.get('production_use') is False and pedregal.get('production_ready') is False)
        check('pedregal_ana_controlled_candidate',pedregal.get('status')=='ANA_CONTROLLED_CANDIDATE')
        check('pedregal_ana_outlet_pass',gates.get('ana_outlet_spatial_control')=='PASS')
        check('pedregal_dem_consistency_pass',gates.get('dem_internal_area_consistency')=='PASS')
        check('pedregal_local_rainfall_still_required',gates.get('historical_local_rainfall_calibration')=='REQUIRED')
    check('pedregal_halfhour_present',pedregal_hh is not None)
    if pedregal_hh:
        check('pedregal_halfhour_not_production',pedregal_hh.get('production_use') is False)
        check('pedregal_halfhour_no_threshold_promotion',(pedregal_hh.get('decision_gate') or {}).get('status')=='REVIEW_AFTER_RESULT')
        check('pedregal_halfhour_complete_coverage',float((pedregal_hh.get('sampling') or {}).get('coverage_pct',0))>=99)
        check('pedregal_halfhour_metrics_present',all((pedregal_hh.get('metrics') or {}).get(k) is not None for k in ('max_1h','max_3h','max_6h','max_24h')))

    # Control terrestre 2015: evidencia diagnóstica, nunca factor automático.
    check('pedregal_ground_evidence_present',pedregal_ground is not None)
    if pedregal_ground:
        diag=pedregal_ground.get('satellite_comparison') or {}
        gate=pedregal_ground.get('decision_gate') or {}
        ground=pedregal_ground.get('ground_rainfall_evidence') or {}
        check('pedregal_ground_not_production',pedregal_ground.get('production_use') is False and pedregal_ground.get('production_ready') is False)
        check('pedregal_ground_event_day_control',pedregal_ground.get('status')=='GROUND_EVENT_DAY_CONTROL_AVAILABLE_DIAGNOSTIC_ONLY')
        check('pedregal_ground_station_is_chosica',ground.get('station')=='Chosica' and ground.get('provider')=='SENAMHI')
        check('pedregal_ground_event_day_positive',float(ground.get('reported_event_day_mm',0))>0)
        check('pedregal_ground_documents_satellite_undercapture',float(diag.get('imerg_to_station_ratio',1))<1)
        check('pedregal_ground_no_auto_bias_correction',gate.get('automatic_bias_correction_allowed') is False)
        check('pedregal_ground_no_threshold_change',gate.get('threshold_change_allowed') is False)
        check('pedregal_ground_no_live_recommendation',gate.get('live_test_recommendation_allowed') is False)
        check('pedregal_ground_requires_more_controls',gate.get('status')=='LOCAL_OR_HIGHER_FIDELITY_SIGNAL_AND_NON_EVENT_CONTROLS_REQUIRED')

    # San Ildefonso: tres contrastes subdiarios son evidencia, no umbral automático.
    check('san_ildefonso_halfhour_controls_present',si_hh is not None)
    if si_hh:
        check('san_ildefonso_halfhour_not_production',si_hh.get('production_use') is False)
        ids={c.get('id') for c in si_hh.get('cases',[])}
        check('san_ildefonso_halfhour_three_reference_cases',{'SI-2017-03-15','SI-2023-03-10','SI-2025-03-29'}.issubset(ids))
        check('san_ildefonso_halfhour_gate_is_review',(si_hh.get('decision_gate') or {}).get('status')=='REVIEW_AFTER_COMPARISON')

    # Lima Este debe permanecer descompuesto y Pedregal no puede declararse live-ready.
    lima=state.get('lima_east_submodels') or {}
    local=(lima.get('chosica_local_debris_flows') or {})
    check('lima_east_submodels_present',bool(lima))
    check('pedregal_submodel_not_live_ready',local.get('live_test_ready') is False)
    check('pedregal_submodel_requires_ground_signal',local.get('blocking_requirement')=='LIVE_LOCAL_OR_GROUND_RAINFALL_SIGNAL_REQUIRED')
    check('lima_submodels_not_production',lima.get('production_use') is False)

    # Tramos ANA Catacaos: líneas de control, nunca extensión de inundación.
    features=ana_geo.get('features',[])
    check('ana_segments_not_production',(ana_geo.get('properties') or {}).get('production_use') is False)
    check('ana_segments_validation_not_production',ana_val.get('production_use') is False)
    check('ana_segments_count_matches_validation',len(features)==int(ana_val.get('published_segment_count',-1)))
    check('ana_segments_minimum_current_reference_set',len(features)>=4)
    for f in features:
        p=f.get('properties') or {}
        check(f"ana_{p.get('sector','unknown')}_line_only",(f.get('geometry') or {}).get('type')=='LineString')
        check(f"ana_{p.get('sector','unknown')}_not_flood_polygon",p.get('is_flood_polygon') is False and p.get('is_inundation_extent') is False)
        check(f"ana_{p.get('sector','unknown')}_geometry_pass",p.get('geometry_status')=='PASS')
        check(f"ana_{p.get('sector','unknown')}_length_control",float(p.get('length_relative_difference_pct',999))<=15)
    withheld=[x for x in ana_val.get('validations',[]) if x.get('status')!='PASS']
    check('ana_review_geometry_is_withheld',all(x.get('geometry_publication')=='withheld_to_avoid_false_alignment' for x in withheld))

    # SENAMHI: cualquier vía descubierta permanece paralela/no productiva.
    for label,data in (('wis2',wis2),('idesep',idesep),('open_data',open_data)):
        if data is not None: check(f'senamhi_{label}_not_production',data.get('production_use') is False)

    failures=[t for t in TESTS if t['status']=='FAIL']
    report={
        'generated_at':datetime.now(timezone.utc).isoformat(),'version':'0.8-experimental','production_use':False,
        'status':'PASS' if not failures else 'FAIL','passed':len(TESTS)-len(failures),'failed':len(failures),'tests':TESTS,
        'note':'Estas pruebas verifican integridad arquitectónica y del modo TEST_ONLY; no validan umbrales para producción.'
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not failures else 1


if __name__=='__main__': sys.exit(main())
