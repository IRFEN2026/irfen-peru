import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'site/data/validation/phase2_discovery_packages/lalibertad_chao_huamanzaña_chorobal.json'
S=ROOT/'site/data/phase2/sources/lalibertad_chao_huamanzana_chorobal_official_evidence_v0_1.json'
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def test_chorobal_faja_leads_fail_closed():
 p=load(P); s=load(S); c={x['child_id']:x for x in p['hydrologic_children']}['chorobal_river_component']; g=c['geometry']
 assert {x['source_id'] for x in g['official_geometry_leads']}=={'ANA-SIGRID-CHOROBAL-RA133-2008','ANA-SIGRID-CHOROBAL-RA158-2008'}
 assert g['path'] is None and g['outlet_status']=='UNRESOLVED'
 assert g['faja_marginal_is_channel_geometry'] is False
 assert g['faja_marginal_is_subcatchment_geometry'] is False
 assert g['faja_marginal_is_event_footprint'] is False
 assert s['qa']['chorobal_outlet_resolved'] is False
