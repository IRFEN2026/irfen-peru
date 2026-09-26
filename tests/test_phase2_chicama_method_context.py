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


def test_chicama_event_evidence_remains_mainstem_specific():
 o=json.loads(P.read_text(encoding='utf-8'))
 e=o['event_evidence']
 assert e['2026_02_13_huabalito']['status']=='POSITIVE_DATED_MAINSTEM_OVERFLOW_EVIDENCE'
 assert e['2026_02_13_huabalito']['exact_footprint_available'] is False
 assert e['2026_02_17_pampas_jaguey_la_botella']['status']=='POSITIVE_DATED_MAINSTEM_OVERFLOW_EVIDENCE'
 assert e['2026_02_17_pampas_jaguey_la_botella']['exact_footprint_available'] is False
 assert o['observation_leads']['station_salinar']['numeric_series_archived'] is False
 assert o['map_policy']['cartavio_is_exposure_node_not_basin'] is True
 assert o['map_policy']['santiago_de_cao_is_exposure_node_not_basin'] is True
