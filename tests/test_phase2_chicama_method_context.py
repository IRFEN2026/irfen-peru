import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'site/data/validation/phase2_research_evidence/lalibertad_chicama_method_hydraulic_context_20260925.json'
def test_chicama_assessment_is_fail_closed():
 o=json.loads(P.read_text(encoding='utf-8'))
 assert o['status']=='RESEARCH_ONLY_SOURCE_ASSESSMENT'
 assert o['production_use'] is False
 assert o['operational_alerting_enabled'] is False
 assert o['activation_gate']=='BLOCKED'
 assert o['dem_method']['import_mastergis_geometry'] is False
