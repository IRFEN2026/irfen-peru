import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/'config/phase2_jicamarca_sophy_access_assessment_v0_1.json'

def load():
    return json.loads(CFG.read_text(encoding='utf-8'))

def test_sophy_strict_research_guards_remain_closed():
    c=load()
    assert c['status']=='PUBLIC_PROJECT_METADATA_ONLY_DATA_ACCESS_UNRESOLVED'
    assert c['deployment_status']=='RESEARCH_ONLY'
    assert c['test_mode']=='TEST_ONLY'
    assert c['production_use'] is False
    assert c['production_ready'] is False
    assert c['operational_alerting_enabled'] is False
    assert c['activation_gate']=='BLOCKED'
    assert c['missing_data_rule']=='UNKNOWN_NOT_LOW_RISK'
    assert c['decision_thresholds'] is None
    assert c['hydraulic_factors'] is None

def test_provider_range_discrepancy_is_preserved_not_resolved_by_assumption():
    c=load(); p=c['public_metadata']; a=c['data_access_assessment']
    assert p['reported_range_values_km']==[50,60]
    assert p['current_project_page_observation_range_km']==50
    assert p['historical_2021_publication_max_range_km']==60
    assert p['range_source_discrepancy_status']=='PRESERVE_PROVIDER_VERSION_DIFFERENCE_DO_NOT_RESOLVE_BY_ASSUMPTION'
    assert p['nominal_range_is_verified_event_coverage'] is False
    assert a['range_discrepancy_resolved'] is False
    assert a['event_coverage_verified'] is False
    assert 'treat nominal radar range as verified event coverage' in c['forbidden']

def test_radar_data_access_and_subcatchment_reconstruction_remain_blocked():
    a=load()['data_access_assessment']
    assert a['public_machine_readable_archive_identified'] is False
    assert a['public_research_download_endpoint_identified'] is False
    assert a['documented_api_identified'] is False
    assert a['raw_or_level2_data_retrieved'] is False
    assert a['machine_readable_raw_access_status']=='UNRESOLVED'
    assert a['qa_reproducible'] is False
    assert a['subcatchment_rainfall_reconstruction_allowed'] is False

def test_public_graphical_products_do_not_promote_machine_readable_access():
    c=load(); p=c['public_metadata']; a=c['data_access_assessment']
    assert p['public_graphical_product_evidence_identified'] is True
    assert p['public_graphical_products_are_subcatchment_rainfall_inputs'] is False
    assert a['public_graphical_product_evidence_identified'] is True
    assert a['public_graphical_product_evidence_is_machine_readable_archive'] is False
    assert a['public_machine_readable_archive_identified'] is False
    assert a['documented_api_identified'] is False
    assert a['raw_or_level2_data_retrieved'] is False
    assert a['subcatchment_rainfall_reconstruction_allowed'] is False
    assert 'treat public graphical or illustrative SOPHy products as a reproducible raw or Level-2 archive' in c['forbidden']

def test_attenuation_and_clutter_are_qa_constraints_not_thresholds():
    c=load(); q=c['known_qa_constraints']
    assert q['rain_attenuation_correction_required'] is True
    assert q['ground_clutter_filtering_required'] is True
    assert q['complex_orography_relevant'] is True
    assert q['provider_dbz_value_is_irfen_decision_threshold'] is False
    assert q['published_algorithm_performance_is_event_specific_jicamarca_validation'] is False
    assert 'reinterpret provider 20 dBZ QA finding as an IRFEN decision threshold' in c['forbidden']

def test_bounded_sources_are_official_igp_and_include_current_qa_evidence():
    c=load(); by={x['source_id']:x for x in c['bounded_official_sources']}
    assert {
        'IGP-SOPHY-PROJECT-RESULTS',
        'IGP-SOPHY-IEEE-2021',
        'IGP-SOPHY-ATTENUATION-2024',
        'IGP-SOPHY-GROUND-CLUTTER-2026',
        'IGP-SOPHY-COMPENDIO-2025',
    } <= set(by)
    assert all('igp.gob.pe' in x['url'] for x in by.values())
    compendio=by['IGP-SOPHY-COMPENDIO-2025']
    assert compendio['date_context']=='2025-12'
    claims=' '.join(compendio['bounded_claims'])
    assert 'meteorological graph generation' in claims
    assert 'does not establish a reproducible machine-readable raw or Level-2 archive' in claims
