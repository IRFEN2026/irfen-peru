import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'site/data/phase2/source_assessments/casma_ana_idep_secondary_vector_service_v0_1.json'


def test_ana_idep_secondary_source_is_fail_closed():
    d=json.loads(DOC.read_text(encoding='utf-8'))
    assert d['deployment_status']=='RESEARCH_ONLY'
    assert d['test_mode']=='TEST_ONLY'
    assert d['production_use'] is False
    assert d['production_ready'] is False
    assert d['operational_alerting_enabled'] is False
    assert d['activation_gate']=='BLOCKED'
    assert d['missing_data_rule']=='UNKNOWN_NOT_LOW_RISK'
    assert d['decision_thresholds'] is None
    assert d['hydraulic_factors'] is None
    assert d['source']['geometry_type']=='esriGeometryPolygon'
    assert d['source']['service_spatial_reference_wkid']==3857
    assert 'geoJSON' in d['source']['supported_query_formats']
    assert d['exact_target_codes']==[
        '1375961','1375962','1375963','1375964','1375965',
        '1375966','1375967','1375968','1375969'
    ]
    rel=d['relation_to_primary_candidate']
    assert rel['exact_per_code_geometry_frozen'] is False
    assert rel['raw_response_sha256_frozen'] is False
    assert rel['geometry_equivalence_to_minam_proven'] is False
    sci=d['scientific_disposition']
    assert sci['metadata_is_geometry'] is False
    assert sci['pdf_digitization_allowed'] is False
    assert sci['map_eligible'] is False
