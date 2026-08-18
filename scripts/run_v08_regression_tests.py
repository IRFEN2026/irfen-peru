#!/usr/bin/env python3
"""Pruebas de regresión funcionales para IRFEN v0.8.

Verifican integridad arquitectónica y las puertas acordadas. No demuestran que
los umbrales sean científicamente válidos ni autorizan promoción a producción.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

from build_v08_scorecard import external_validation_gate, final_release_audit_gate, review_after_utc_day_close, target_window_gate
from review_shadow_outcome import apply_review

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
    piura_field=load(SITE/'data/hydrology/piura_2026_field_evidence.json')
    pedregal=optional(SITE/'data/calibration/pedregal_ana_validation.json')
    pedregal_hh=optional(SITE/'data/calibration/pedregal_2015_imerg_halfhour.json')
    pedregal_ground=optional(SITE/'data/calibration/pedregal_ground_evidence_2015.json')
    si_hh=optional(SITE/'data/calibration/san_ildefonso_imerg_halfhour_events.json')
    wis2=optional(SITE/'data/stations/senamhi_wis2_discovery.json')
    idesep=optional(SITE/'data/stations/senamhi_idesep_discovery.json')
    open_data=optional(SITE/'data/stations/senamhi_open_data_catalog.json')
    imerg_early=optional(SITE/'data/calibration/imerg_early_live_archive.json')
    phase2=load(ROOT/'config/phase2_candidate_inventory_v0_1.json')
    phase2_events=load(SITE/'data/phase2/research_events.json')
    closeout_contract=load(ROOT/'config/v08_closeout_contract.json')
    external_contract=load(ROOT/'config/v08_external_validation_contract.json')
    external_ledger=load(SITE/'data/validation/v08_external_evidence.json')
    closeout_scorecard=optional(SITE/'data/v08_scorecard.json')
    publish_workflow=(ROOT/'.github/workflows/publish-committed-data.yml').read_text(encoding='utf-8')
    smoke_workflow=(ROOT/'.github/workflows/live-smoke-test.yml').read_text(encoding='utf-8')
    glofas_current=optional(SITE/'data/hydrology/glofas_catacaos_current.json')
    pprrd=optional(SITE/'data/hydrology/catacaos_pprrd_2026_discovery.json')
    official_outcomes=optional(SITE/'data/validation/official_outcome_evidence.json')
    shadow_runs=optional(SITE/'data/validation/shadow_runs.json')
    cendehua=optional(SITE/'data/stations/igp_cendehua_access_probe.json')
    cendehua_archive=optional(SITE/'data/stations/igp_cendehua_huaycoloro_archive.json')

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

    # Evidencia de campo 2026: contexto trazable, nunca capacidad ni bajo riesgo.
    field_safety=piura_field.get('safety') or {}
    field_observations=piura_field.get('observations') or []
    check('piura_field_evidence_not_production',piura_field.get('production_use') is False and piura_field.get('production_ready') is False)
    check('piura_field_evidence_candidate_only',piura_field.get('status')=='OFFICIAL_FIELD_EVIDENCE_CANDIDATE_REVIEW')
    check('piura_field_evidence_has_dated_controls',len(field_observations)>=4 and all(row.get('observation_date') for row in field_observations))
    check('piura_field_evidence_sources_are_official',all(str(row.get('source_url','')).startswith('https://www.gob.pe/institucion/') for row in field_observations))
    check('piura_field_evidence_preserves_senamhi_peak',any(float((row.get('reported_values') or {}).get('reported_peak_at_19_40_m3_s',0))==854.66 for row in field_observations))
    check('piura_field_evidence_never_validates_capacity',field_safety.get('hydraulic_capacity_validated') is False)
    check('piura_field_evidence_never_validates_transfer',field_safety.get('hydraulic_transfer_to_catacaos_validated') is False)
    check('piura_field_evidence_never_infers_no_impact',field_safety.get('absence_of_impact_validated') is False)
    check('piura_field_evidence_never_promotes_thresholds',field_safety.get('threshold_promotion_allowed') is False and field_safety.get('hydraulic_factor_promotion_allowed') is False)
    check('piura_field_evidence_missing_not_low_risk',field_safety.get('missing_data_is_low_risk') is False)
    check('piura_field_evidence_does_not_close_gate',field_safety.get('counts_toward_closeout') is False and (piura_field.get('decision_gate') or {}).get('status')=='HUMAN_TECHNICAL_REVIEW_REQUIRED')

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
        check('imerg_probe_cadence_count_nonnegative',int(summary.get('probe_interval_count',0))>=0)
        cadence_gap=summary.get('probe_gap_max_hours')
        check('imerg_probe_cadence_gap_nonnegative',cadence_gap is None or float(cadence_gap)>=0)

    # Expansión: preparación documental sin activar zonas ni inventar puntuaciones.
    check('phase2_inventory_not_production',phase2.get('production_use') is False)
    check('phase2_inventory_research_only',phase2.get('deployment_status')=='RESEARCH_ONLY')
    candidates=phase2.get('candidates') or []
    check('phase2_inventory_first_wave_size',8<=len(candidates)<=12)
    check('phase2_inventory_outside_lima_majority',sum(c.get('inside_lima_metropolitana') is False for c in candidates)>=len(candidates)/2)
    check('phase2_inventory_no_numeric_scores',all(c.get('priority_score') is None for c in candidates))
    check('phase2_inventory_no_activation',all(c.get('deployment_status')=='RESEARCH_ONLY' for c in candidates))
    check('phase2_inventory_has_official_evidence',all(c.get('official_sources') for c in candidates))

    # Eventos de oportunidad: útiles para reanálisis, nunca para activar o cerrar v0.8.
    event_summary=phase2_events.get('summary') or {}
    event_guards=phase2_events.get('guardrails') or {}
    research_events=phase2_events.get('items') or []
    check('phase2_events_not_production',phase2_events.get('production_use') is False)
    check('phase2_events_research_only',phase2_events.get('deployment_status')=='RESEARCH_ONLY')
    check('phase2_events_no_operational_activations',int(event_summary.get('operational_activations',-1))==0)
    check('phase2_events_do_not_count_toward_v08',all(e.get('counts_toward_v08_closeout') is False for e in research_events))
    check('phase2_events_cannot_activate_zones',all(e.get('operational_zone_activation') is False for e in research_events))
    check('phase2_events_missing_not_low_risk',event_guards.get('missing_data_is_not_low_risk') is True)
    check('phase2_events_unverified_are_blocked',all(
        e.get('event_confirmed') is True or str(e.get('analysis_status','')).startswith('BLOCKED_')
        for e in research_events
    ))

    # PPRRD Catacaos: evidencia documental trazable, nunca capacidad ni umbral.
    check('catacaos_pprrd_present',pprrd is not None)
    if pprrd:
        check('catacaos_pprrd_not_production',pprrd.get('production_use') is False)
        check(
            'catacaos_pprrd_numeric_candidates_unvalidated',
            all(row.get('validated_meaning') is False for row in pprrd.get('numeric_candidates',[])),
        )
    external_by_zone={row.get('zone_id'):row for row in external_ledger.get('pilots',[])}
    catacaos_external={
        row.get('evidence_id'):row
        for row in (external_by_zone.get('catacaos') or {}).get('items',[])
    }
    pprrd_path='site/data/hydrology/catacaos_pprrd_2026_discovery.json'
    mapped_ids={
        'current_channel_capacity_and_critical_levels',
        'current_floodplain_and_defense_condition',
        'observed_river_state_to_impact_review',
    }
    check(
        'catacaos_pprrd_mapped_without_acceptance',
        all(
            pprrd_path in (catacaos_external.get(item_id) or {}).get('internal_artifacts',[])
            and (catacaos_external.get(item_id) or {}).get('status') != 'ACCEPTED'
            for item_id in mapped_ids
        ),
    )

    # Evidencia diaria: se publica para auditoría, pero nunca se autoclasifica.
    check('official_outcome_evidence_present',official_outcomes is not None)
    if official_outcomes:
        outcome_records=official_outcomes.get('records') or []
        check('official_outcome_evidence_not_production',official_outcomes.get('production_use') is False)
        check('official_outcome_evidence_not_ready',official_outcomes.get('production_ready') is False)
        check('official_outcome_evidence_human_review_only',official_outcomes.get('decision_use')=='HUMAN_REVIEW_INPUT_ONLY')
        check('official_outcome_evidence_count_matches',int(official_outcomes.get('record_count',-1))==len(outcome_records))
        captures=[capture for record in outcome_records for capture in record.get('captures',[])]
        check('official_outcome_evidence_has_captures',bool(captures))
        check('official_outcome_evidence_never_auto_labels',all(capture.get('outcome_label') is None for capture in captures))
        check('official_outcome_evidence_never_counts_directly',all(capture.get('counts_toward_closeout') is False for capture in captures))
        sources=[source for capture in captures for source in capture.get('sources',[])]
        check(
            'official_outcome_evidence_three_sources_per_capture',
            all(len(capture.get('sources',[]))==3 for capture in captures),
        )
        supplemental_sources=[
            source
            for capture in captures
            for source in capture.get('supplemental_sources',[])
        ]
        allowed_supplemental_source_ids={
            'anin_san_ildefonso_news',
            'igp_cendehua_huaycoloro_monitor',
            'pechp_piura_news',
        }
        check(
            'official_outcome_supplemental_sources_are_bounded',
            all(
                len(capture.get('supplemental_sources',[]))<=len(allowed_supplemental_source_ids)
                and {
                    source.get('source_id')
                    for source in capture.get('supplemental_sources',[])
                }.issubset(allowed_supplemental_source_ids)
                for capture in captures
            )
            and all(
                source.get('source_id') in allowed_supplemental_source_ids
                for source in supplemental_sources
            ),
        )
        check(
            'official_outcome_missing_stays_unknown_not_zero',
            all(source.get('unknown_not_zero') is True for source in sources if source.get('capture_status')!='CAPTURED'),
        )
    check('shadow_runs_present',shadow_runs is not None)
    if shadow_runs:
        shadow_records=shadow_runs.get('records') or []
        check('shadow_runs_not_production',shadow_runs.get('production_use') is False)
        check('shadow_runs_count_matches',int(shadow_runs.get('record_count',-1))==len(shadow_records))
        uncertain_reviews=[
            record.get('outcome_verification') or {}
            for record in shadow_records
            if (record.get('outcome_verification') or {}).get('label')=='UNCERTAIN'
        ]
        check(
            'shadow_uncertain_never_counts_toward_closeout',
            all(review.get('counts_toward_closeout') is False for review in uncertain_reviews),
        )

    # Scorecard de cierre: hitos discretos, acumulativos y sin efecto operativo.
    check('closeout_contract_not_production',closeout_contract.get('production_use') is False)
    check(
        'archived_publish_explicitly_dispatches_full_smoke',
        'actions: write' in publish_workflow
        and 'gh workflow run live-smoke-test.yml' in publish_workflow,
    )
    check(
        'archived_publish_retries_pages_propagation_with_unique_queries',
        'for attempt in 1 2 3 4 5 6' in publish_workflow
        and 'attempt=${attempt}' in publish_workflow
        and 'freshness_ok=false' in publish_workflow
        and 'test "$freshness_ok" = true' in publish_workflow,
    )
    check(
        'live_smoke_avoids_duplicate_archived_publish_trigger',
        'IRFEN - Publicar datos experimentales archivados' not in smoke_workflow,
    )
    check(
        'live_smoke_requires_catacaos_pprrd_research_asset',
        'data/hydrology/catacaos_pprrd_2026_discovery.json' in smoke_workflow
        and "pprrd.get('production_use') is False" in smoke_workflow
        and "candidate.get('validated_meaning') is False" in smoke_workflow,
    )
    check(
        'live_smoke_requires_cendehua_test_only_assets',
        'data/stations/igp_cendehua_access_probe.json' in smoke_workflow
        and 'data/stations/igp_cendehua_huaycoloro_archive.json' in smoke_workflow
        and "ground_signal.get('automatic_outcome_label') is None" in smoke_workflow
        and "cendehua_gate.get('absence_of_provider_activity_is_none') is False" in smoke_workflow
        and "cendehua_gate.get('human_review_required') is True" in smoke_workflow,
    )
    check(
        'live_smoke_requires_fail_closed_human_review_queue',
        "shadow_review_workflow.get('automatic_classification_forbidden') is True" in smoke_workflow
        and "external_review_workflow.get('automatic_acceptance_forbidden') is True" in smoke_workflow
        and "ground.get('can_support_none_classification_by_itself') is False" in smoke_workflow,
    )
    readiness_js=(SITE/'v08-readiness.js').read_text(encoding='utf-8')
    check(
        'readiness_exposes_human_review_workflows_without_auto_decision',
        'Abrir revisión diaria' in readiness_js
        and 'Abrir revisión científica/hidráulica' in readiness_js
        and 'human_review_workflows' in readiness_js,
    )
    check('closeout_contract_exact_pilots',closeout_contract.get('pilot_zone_ids')==['san_ildefonso','chosica','catacaos'])
    check('closeout_contract_fixed_milestones',closeout_contract.get('milestone_percentages')==[25,50,75,100])
    shadow_contract=closeout_contract.get('shadow_validation') or {}
    check('closeout_contract_shadow_requires_event_day',int(shadow_contract.get('minimum_verified_event_days',0))>=1)
    check('closeout_contract_shadow_requires_none_days',int(shadow_contract.get('minimum_verified_none_days',0))>=1)
    shadow_acceptance=shadow_contract.get('acceptance_rules') or {}
    shadow_capture=shadow_contract.get('snapshot_capture') or {}
    check('closeout_shadow_requires_named_human_reviewer',shadow_acceptance.get('named_human_reviewer_required') is True)
    check('closeout_shadow_forbids_automatic_classification',shadow_acceptance.get('automatic_classification_forbidden') is True)
    check('closeout_shadow_requires_pre_outcome_capture_window',shadow_acceptance.get('pre_outcome_capture_window_required') is True)
    check('closeout_shadow_capture_delay_is_bounded',0<int(shadow_capture.get('latest_eligible_capture_delay_minutes',0))<=120)
    shadow_workflow=(ROOT/'.github/workflows/shadow-validation.yml').read_text(encoding='utf-8')
    check('closeout_shadow_schedule_starts_near_utc_day_open','cron: "10 0 * * *"' in shadow_workflow)
    retry_crons=shadow_capture.get('redundant_retry_crons_utc') or []
    check('closeout_shadow_redundant_capture_attempts_declared',retry_crons==['50 0 * * *','30 1 * * *'])
    check('closeout_shadow_redundant_capture_attempts_scheduled',all(f'cron: "{cron}"' in shadow_workflow for cron in retry_crons))
    check('closeout_shadow_capture_runs_are_serialized','cancel-in-progress: false' in shadow_workflow)
    check('closeout_shadow_publish_only_after_new_snapshot',"if: steps.persist.outputs.changed == 'true'" in shadow_workflow)
    check(
        'closeout_shadow_cendehua_signal_never_auto_classifies',
        "cendehua.get('automatic_outcome_label') is None" in shadow_workflow
        and "cendehua.get('can_support_none_classification_by_itself') is False" in shadow_workflow
        and "observation.get('irfen_outcome_label') is None" in shadow_workflow,
    )
    check('closeout_shadow_none_requires_comprehensive_coverage',shadow_acceptance.get('none_requires_comprehensive_coverage') is True)
    check('closeout_contract_release_completion_explicit',closeout_contract.get('release_completion_marker')=='Release status: COMPLETE')
    check('closeout_contract_catacaos_supplemental_imerg_release_gate',(closeout_contract.get('imerg_early') or {}).get('supplemental_release_target_ids')==['catacaos'])
    check('closeout_shadow_review_protocol_present',(ROOT/'docs/SHADOW_OUTCOME_REVIEW_PROTOCOL.md').is_file())
    check('closeout_shadow_review_tool_present',(ROOT/'scripts/review_shadow_outcome.py').is_file())
    premature_review={
        'snapshot_date_utc':'2026-08-14',
        'outcome_verification':{'reviewed_at':'2026-08-14T23:59:59+00:00'},
    }
    check('closeout_shadow_rejects_review_before_utc_day_close',review_after_utc_day_close(premature_review) is False)
    premature_review['outcome_verification']['reviewed_at']='2026-08-15T00:00:00Z'
    check('closeout_shadow_accepts_review_at_utc_day_close',review_after_utc_day_close(premature_review) is True)
    synthetic_archive={
        'production_use':False,
        'production_ready':False,
        'records':[{
            'snapshot_date_utc':'2026-08-14',
            'production_use':False,
            'outcome_verification':{'status':'PENDING_REAL_WORLD_OUTCOME_REVIEW'},
        }],
    }
    review_args=(
        synthetic_archive,
        '2026-08-14',
        'UNCERTAIN',
        ['https://www.senamhi.gob.pe/main.php?p=aviso-24H'],
        'Revisión sintética para comprobar trazabilidad.',
    )
    apply_review(*review_args,reviewed_at='2026-08-15T00:00:00Z')
    silent_overwrite_rejected=False
    try:
        apply_review(*review_args,reviewed_at='2026-08-16T00:00:00Z')
    except ValueError:
        silent_overwrite_rejected=True
    check('closeout_shadow_rejects_silent_review_overwrite',silent_overwrite_rejected)
    apply_review(
        *review_args,
        reviewed_at='2026-08-16T00:00:00Z',
        replace_existing_review=True,
    )
    synthetic_record=synthetic_archive['records'][0]
    check(
        'closeout_shadow_explicit_replacement_preserves_history',
        len(synthetic_record.get('outcome_verification_history') or [])==1,
    )
    check('closeout_final_audit_rejects_missing_shadow',final_release_audit_gate(False,True,True) is False)
    check('closeout_final_audit_rejects_scientific_blockers',final_release_audit_gate(True,False,True) is False)
    check('closeout_final_audit_rejects_incomplete_release',final_release_audit_gate(True,True,False) is False)
    check('closeout_final_audit_accepts_all_prerequisites',final_release_audit_gate(True,True,True) is True)
    synthetic_windows={
        'catacaos':{
            '3h':{'available':True,'continuous':True},
            '6h':{'available':True,'continuous':True},
            '24h':{'available':False,'continuous':False},
        }
    }
    synthetic_passed,_=target_window_gate(synthetic_windows,['catacaos'],['3h','6h','24h'])
    check('closeout_catacaos_supplemental_window_rejects_incomplete_24h',synthetic_passed is False)
    synthetic_windows['catacaos']['24h']={'available':True,'continuous':True}
    synthetic_passed,_=target_window_gate(synthetic_windows,['catacaos'],['3h','6h','24h'])
    check('closeout_catacaos_supplemental_window_accepts_complete_3h_6h_24h',synthetic_passed is True)
    external_passed,external_detail=external_validation_gate(external_contract,external_ledger,['san_ildefonso','chosica','catacaos'])
    check('external_validation_contract_not_production',external_contract.get('production_use') is False)
    check('external_validation_ledger_not_production',external_ledger.get('production_use') is False)
    check('external_validation_exact_pilots',set(external_detail)=={'san_ildefonso','chosica','catacaos'})
    check('external_validation_missing_evidence_stays_blocked',external_passed is False)
    check('external_validation_candidates_prepared',sum(x.get('candidate_count',0) for x in external_detail.values())>=1)
    check('external_validation_candidates_not_accepted',sum(x.get('accepted_count',0) for x in external_detail.values())==0)
    candidate_items=[
        item
        for pilot in external_ledger.get('pilots',[])
        for item in pilot.get('items',[])
        if item.get('status') in {'CANDIDATE_REVIEW','PARTIAL_CANDIDATE_REVIEW'}
    ]
    check('external_validation_candidates_have_official_sources',bool(candidate_items) and all(item.get('official_sources') for item in candidate_items))
    check('external_validation_no_automatic_acceptance',(external_contract.get('acceptance_rules') or {}).get('automatic_acceptance_forbidden') is True)
    check('external_validation_no_threshold_promotion',(external_contract.get('acceptance_rules') or {}).get('threshold_or_hydraulic_factor_promotion')=='FORBIDDEN')
    check('external_validation_review_tool_exists',(ROOT/'scripts/review_v08_external_evidence.py').exists())
    check('external_validation_review_protocol_exists',(ROOT/'docs/V08_EXTERNAL_EVIDENCE_REVIEW_PROTOCOL.md').exists())
    check('cendehua_probe_present',cendehua is not None)
    if cendehua:
        signal=cendehua.get('huaycoloro_ground_signal') or {}
        check('cendehua_probe_not_production',cendehua.get('production_use') is False and cendehua.get('production_ready') is False)
        check('cendehua_never_auto_labels_outcome',signal.get('automatic_outcome_label') is None and signal.get('human_review_required') is True)
        if int(signal.get('station_count',0))>0:
            check('cendehua_archive_present_when_signal_found',cendehua_archive is not None)
    if cendehua_archive:
        gate=cendehua_archive.get('scientific_gate') or {}
        check('cendehua_archive_test_only',cendehua_archive.get('integration_mode')=='TEST_ONLY' and cendehua_archive.get('production_use') is False)
        check('cendehua_archive_never_maps_false_to_none',gate.get('absence_of_provider_activity_is_none') is False)
        check('cendehua_archive_human_review_required',gate.get('automatic_event_or_none_classification') is False and gate.get('human_review_required') is True)
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
