import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only.geojson"
VAL = ROOT / "site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only_validation.json"
SNAP = ROOT / "site/data/phase2/sources/w1_remaining_geometry_source_snapshot.json"
CATALOG = ROOT / "site/data/phase2/w1_remaining_geometry_catalog.json"
GENERAL_MAP = ROOT / "site/data/map_layers.json"
CONTRACTS = ROOT / "site/data/validation/phase2_zone_contracts"
BUILDER = ROOT / "scripts/build_w1_remaining_geometries.py"
UNRESOLVED = "UNRESOLVED_OFFICIAL_SOURCE_CONFLICT"
EXPECTED_HITOS = [("P5 MI",300596.0,8706636.0),("P4 MI",300633.0,8706553.0),("P3 MI",300654.0,8706452.0),("P2 MI",300663.0,8706419.0),("P1 MI",300657.0,8706370.0),("HI-8",300653.0,8706336.0),("HI-9",300603.0,8706197.0),("HI-10",300575.0,8706134.0),("HI-11",300538.0,8706064.0),("HI-12",300540.0,8705985.0),("HI-13",300552.0,8705916.0),("HI-14",300576.0,8705852.0),("HI-15",300573.0,8705785.0),("HI-16",300546.0,8705693.0),("HI-17",300493.0,8705560.0),("HI-18",300452.0,8705420.0),("HI-19",300411.0,8705312.0),("HI-20",300361.0,8705198.0)]

def sha256(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical_sha256(value): return hashlib.sha256((json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",", ":"))+"\n").encode()).hexdigest()

class W1RemainingGeometryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.g=json.loads(GEO.read_text()); cls.v=json.loads(VAL.read_text()); cls.s=json.loads(SNAP.read_text()); cls.c=json.loads(CATALOG.read_text())
 def test_literal_18_official_codes_and_utm_coordinates(self):
  p=self.g['features'][0]['properties']; actual=[(code,xy[0],xy[1]) for code,xy in zip(p['source_hitos'],p['source_utm'])]; self.assertEqual(actual,EXPECTED_HITOS); self.assertEqual(p['source_hito_count'],18)
 def test_constructor_reproduces_all_versioned_outputs(self):
  subprocess.run([sys.executable,str(BUILDER),'--check-only'],cwd=ROOT,check=True,capture_output=True,text=True)
 def test_crs_topology_coverage_and_no_artificial_links(self):
  f=self.g['features'][0]; p=f['properties']; geom=shape(f['geometry']); inv=Transformer.from_crs('EPSG:4326','EPSG:32718',always_xy=True)
  self.assertEqual(self.g['properties']['source_crs'],'EPSG:32718'); self.assertEqual(self.g['properties']['output_crs'],'EPSG:4326'); self.assertEqual(len(f['geometry']['coordinates']),18); self.assertTrue(geom.is_simple); self.assertFalse(geom.is_ring); self.assertFalse(p['artificial_links'])
  for (_,e,n),(lon,lat) in zip(EXPECTED_HITOS,f['geometry']['coordinates']):
   re,rn=inv.transform(lon,lat); self.assertLess(abs(re-e),.01); self.assertLess(abs(rn-n),.01); self.assertTrue(-82<lon<-68 and -19<lat<1)
  self.assertFalse(self.v['coverage_checks']['full_faja_polygon_available'])
 def test_official_bank_conflict_must_remain_unresolved(self):
  z=next(r for r in self.s['zones'] if r['candidate_id']=='lima_norte_huerta_vieja'); conflict=z['official_source_conflict']; assignments={z['bank_assignment'],self.g['properties']['bank_assignment'],self.g['features'][0]['properties']['bank_assignment'],self.v['bank_assignment_check']['bank_assignment'],self.c['layers'][0]['bank_assignment']}
  self.assertEqual(assignments,{UNRESOLVED}); self.assertEqual(conflict['technical_report_016_2024_conclusion'],'21 hitos margen derecha; 18 hitos margen izquierda'); self.assertEqual(conflict['eighteen_point_table_title'],'Margen derecha'); self.assertEqual(conflict['eighteen_point_table_codes'],'P…MI / HI'); self.assertFalse(self.v['bank_assignment_check']['definitive_bank_assignment_permitted'])
  for forbidden in ('RIGHT','LEFT','MARGEN_DERECHA','MARGEN_IZQUIERDA'): self.assertNotIn(forbidden,assignments)
 def test_entity_scope_cannot_be_reinterpreted(self):
  p=self.g['features'][0]['properties']; self.assertEqual(p['entity_type'],'FAJA_MARGINAL_HITO_SEQUENCE'); self.assertEqual(self.g['features'][0]['geometry']['type'],'LineString')
  for k in ('not_a_watershed','not_a_faja_polygon','not_a_hazard_extent','not_an_inundation_polygon'): self.assertTrue(p[k]); self.assertTrue(self.v['entity_checks'][k])
 def test_hash_chain_and_source_byte_metadata(self):
  layer=self.c['layers'][0]; self.assertEqual(self.g['properties']['source_snapshot_sha256'],sha256(SNAP)); self.assertEqual(self.v['source_snapshot_sha256'],sha256(SNAP)); self.assertEqual(layer['source_snapshot_sha256'],sha256(SNAP)); self.assertEqual(self.v['geometry_sha256'],sha256(GEO)); self.assertEqual(layer['geometry_sha256'],sha256(GEO)); self.assertEqual(layer['validation_sha256'],sha256(VAL))
  payload={'crs':'EPSG:32718','points':[{'id':c,'easting':e,'northing':n} for c,e,n in EXPECTED_HITOS]}; coord=canonical_sha256(payload); self.assertEqual(self.g['properties']['coordinate_payload_sha256'],coord); self.assertEqual(self.v['coordinate_payload_sha256'],coord); self.assertEqual(layer['coordinate_payload_sha256'],coord)
  docs={r['snapshot_id']:r for r in self.s['downloaded_documents']}; huerta=docs['SIGRID-19291-HUERTA-VIEJA']; self.assertEqual(layer['source_pdf_sha256'],huerta['sha256']); self.assertEqual(self.v['source_pdf_sha256'],huerta['sha256']); self.assertEqual(self.g['features'][0]['properties']['source_pdf_sha256'],huerta['sha256'])
  for d in docs.values(): self.assertRegex(d['sha256'],r'^[0-9a-f]{64}$'); self.assertGreater(d['byte_size'],0); self.assertTrue(d['direct_url'].startswith('https://')); self.assertTrue(d['captured_at'].endswith('Z'))
 def test_nonretrieved_sources_are_not_reproducible_evidence(self):
  for z in self.s['zones']:
   for source in z['official_sources']:
    if source['retrieval_status']=='METADATA_ONLY_NOT_REPRODUCIBLY_RETRIEVED': self.assertIsNone(source.get('sha256')); self.assertIsNone(source.get('byte_size'))
  lamb=next(r for r in self.s['zones'] if r['candidate_id']=='lambayeque_chongoyape_oyotun_zana')
  for source in lamb['official_sources']:
   if source['source_id'].startswith('ANA-'): self.assertIsNone(source['direct_url'])
 def test_cartography_is_explicitly_withheld(self):
  layer=self.c['layers'][0]; self.assertFalse(layer['map_eligible_research_only']); self.assertFalse(layer['default_visibility']); self.assertEqual(layer['map_integration'],'WITHHELD_FROM_GENERAL_MAP_UNTIL_TERRITORIAL_GEOMETRY_IS_DEFENSIBLE'); self.assertEqual(self.c['summary']['map_eligible_research_only'],0); self.assertNotIn('w1_huerta_vieja_faja_margin_review_only',GENERAL_MAP.read_text())
 def test_huerta_main_contract_stays_missing_blocked(self):
  c=json.loads((CONTRACTS/'lima_norte_huerta_vieja.json').read_text()); self.assertEqual(c['assets']['geometry']['status'],'MISSING'); self.assertIsNone(c['assets']['geometry']['path']); self.assertEqual(c['validation']['activation_gate'],'BLOCKED')
 def test_four_zone_decisions_and_operational_guards_fail_closed(self):
  zones={r['candidate_id']:r for r in self.s['zones']}; self.assertEqual(zones['lima_norte_huerta_vieja']['materialization_status'],'PARTIAL_REVIEW_ONLY')
  for cid in ('lima_sur_malanche','lambayeque_chongoyape_oyotun_zana','arequipa_acari_san_agustin'): self.assertEqual(zones[cid]['materialization_status'],'BLOCKED')
  for cid in zones:
   c=json.loads((CONTRACTS/f'{cid}.json').read_text()); self.assertEqual(c['deployment_status'],'RESEARCH_ONLY'); self.assertIs(c['production_use'],False); self.assertIs(c['alerting_enabled'],False); self.assertIsNone(c['decision_thresholds']); self.assertIsNone(c['hydraulic_factors']); self.assertEqual(c['validation']['activation_gate'],'BLOCKED')
  self.assertIs(self.g['properties']['production_use'],False); self.assertIs(self.g['properties']['production_ready'],False); self.assertIs(self.g['properties']['operational_alerting_enabled'],False); self.assertIs(self.v['activation_permitted'],False)
if __name__=='__main__': unittest.main()
