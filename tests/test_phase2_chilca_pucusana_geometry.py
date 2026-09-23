import json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'site/data/validation/phase2_zone_contracts/lima_sur_chilca_pucusana.json'
G=ROOT/'site/data/phase2/geometries/lima_sur_chilca_pucusana_chilca_basin_context.geojson'
V=ROOT/'site/data/phase2/geometries/lima_sur_chilca_pucusana_geometry_validation.json'
S=ROOT/'site/data/phase2/sources/chilca_pucusana_hydrologic_context/source_inventory.json'
M=ROOT/'site/data/map_layers.json'
class ChilcaPucusanaGeometryTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.c=json.loads(C.read_text());cls.g=json.loads(G.read_text());cls.v=json.loads(V.read_text());cls.s=json.loads(S.read_text())
 def test_replay(self): subprocess.run([sys.executable,'scripts/probe_chilca_pucusana_official_geometry.py','--check-only'],cwd=ROOT,check=True,capture_output=True,text=True)
 def test_guards(self):
  c=self.c
  self.assertEqual(c['deployment_status'],'RESEARCH_ONLY');self.assertEqual(c['test_mode'],'TEST_ONLY');self.assertFalse(c['production_use']);self.assertFalse(c['production_ready']);self.assertFalse(c['operational_alerting_enabled']);self.assertEqual(c['validation']['activation_gate'],'BLOCKED');self.assertEqual(c['missing_data_rule'],'UNKNOWN_NOT_LOW_RISK');self.assertIsNone(c['decision_thresholds']);self.assertIsNone(c['hydraulic_factors'])
 def test_partial_chilca_only(self):
  v=self.v;self.assertEqual(v['official_unit']['code'],'1375532');self.assertEqual(v['official_unit']['name'],'Cuenca Chilca');self.assertFalse(v['counts_as_complete_candidate_geometry']);self.assertFalse(v['artificial_connector_used']);self.assertEqual(v['component_resolution']['pucusana_hydrologic_identity'],'UNRESOLVED_NO_GEOMETRY_DRAWN');self.assertEqual(v['component_resolution']['local_ravines'],'UNRESOLVED_NO_GEOMETRY_DRAWN');self.assertEqual(v['component_resolution']['event_footprint'],'NOT_ASSERTED');self.assertEqual(v['component_resolution']['hydraulic_capacity'],'UNKNOWN')
  f=self.g['features'][0];self.assertEqual(f['properties']['official_hydrologic_unit_code'],'1375532');self.assertFalse(f['properties']['pucusana_identity_resolved']);self.assertFalse(f['properties']['local_ravines_geometry_resolved']);self.assertFalse(f['properties']['event_footprint_resolved']);self.assertFalse(f['properties']['dem_used']);self.assertFalse(f['properties']['outlet_used'])
 def test_source_and_map(self):
  s=self.s['sources'][0];self.assertEqual(s['official_unit_code'],'1375532');self.assertEqual(s['official_unit_name'],'Cuenca Chilca');self.assertGreater(s['official_area_km2'],0);self.assertEqual(self.c['assets']['geometry']['status'],'PARTIAL');self.assertEqual(self.c['assets']['geometry']['path'],G.relative_to(ROOT).as_posix())
  r=[x for x in json.loads(M.read_text())['research_zones'] if x['candidate_id']=='lima_sur_chilca_pucusana'][0];self.assertTrue(r['geometry']['map_eligible']);self.assertFalse(r['geometry']['default_visibility']);self.assertEqual(r['deployment_status'],'RESEARCH_ONLY');self.assertFalse(r['production_use']);self.assertFalse(r['alerting_enabled']);self.assertEqual(r['validation']['activation_gate'],'BLOCKED')
if __name__=='__main__': unittest.main()
