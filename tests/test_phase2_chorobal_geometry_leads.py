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


def test_chorobal_event_evidence_stays_child_specific():
 p=load(P); s=load(S)
 e17=p['event_ledger']['2017']; e22=p['event_ledger']['2022_chorobal']
 assert e17['child_id']=='chorobal_river_component'
 assert e17['exact_event_date_available'] is False
 assert e17['exact_event_footprint_available'] is False
 assert e17['whole_basin_uniform_activation'] is False
 assert e22['child_id']=='chorobal_river_component'
 assert e22['event_time_local']=='2022-04-03T01:35:00-05:00'
 assert e22['exact_event_footprint_available'] is False
 assert e22['whole_basin_uniform_activation'] is False
 assert s['qa']['chorobal_2017_exact_event_date_resolved'] is False
 assert s['qa']['chorobal_2022_event_date_resolved'] is True
 assert s['qa']['chorobal_2022_event_footprint_resolved'] is False
