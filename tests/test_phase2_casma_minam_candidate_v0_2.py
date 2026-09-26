import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'site/data/phase2/sources/ancash_casma_minam_candidate_v0_2.json'

def test_casma_candidate_is_fail_closed():
    d=json.loads(DOC.read_text(encoding='utf-8'))
    assert d['deployment_status']=='RESEARCH_ONLY'
    assert d['test_mode']=='TEST_ONLY'
    assert d['production_use'] is False
    assert d['activation_gate']=='BLOCKED'
    assert d['geometry_retrieved'] is False
    assert d['map_publication_enabled'] is False
    assert d['query_contract']['exact_query_executed_and_frozen'] is False
    assert d['original_inrena_vector_target']['expected_shapefile']=='Uh_pfas100.shp'
