import json
from pathlib import Path
import unittest
from pyproj import Transformer
from shapely.geometry import shape
ROOT=Path(__file__).resolve().parents[1]
GEO=ROOT/'site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only.geojson'
VAL=ROOT/'site/data/phase2/geometries/w1_huerta_vieja_faja_margin_review_only_validation.json'
SNAP=ROOT/'site/data/phase2/sources/w1_remaining_geometry_source_snapshot.json'
CONTRACTS=ROOT/'site/data/validation/phase2_zone_contracts'
class W1RemainingGeometryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.g=json.loads(GEO.read_text()); cls.v=json.loads(VAL.read_text()); cls.s=json.loads(SNAP.read_text())
 def test_crs_coordinates_topology_and_no_artificial_links(self):
  f=self.g['features'][0]; geom=shape(f['geometry']); inv=Transformer.from_crs('EPSG:4326','EPSG:32718',always_xy=True)
  self.assertEqual(self.g['properties']['source_crs'],'EPSG:32718'); self.assertEqual(len(f['geometry']['coordinates']),18); self.assertTrue(geom.is_simple); self.assertFalse(geom.is_ring); self.assertFalse(f['properties']['artificial_links'])
  for (e,n),(lon,lat) in zip(f['properties']['source_utm'],f['geometry']['coordinates']):
   re,rn=inv.transform(lon,lat); self.assertLess(abs(re-e),.01); self.assertLess(abs(rn-n),.01); self.assertTrue(-82<lon<-68 and -19<lat<1)
 def test_entity_scope_is_explicit_and_partial(self):
  p=self.g['features'][0]['properties']; self.assertEqual(p['entity_type'],'FAJA_MARGINAL_HITO_SEQUENCE'); self.assertTrue(p['not_a_watershed']); self.assertTrue(p['not_a_faja_polygon']); self.assertTrue(p['not_a_hazard_extent']); self.assertTrue(p['not_an_inundation_polygon']); self.assertFalse(self.v['coverage_checks']['full_faja_polygon_available'])
 def test_four_zone_decisions_fail_closed(self):
  z={x['candidate_id']:x for x in self.s['zones']}; self.assertEqual(z['lima_norte_huerta_vieja']['materialization_status'],'PARTIAL_REVIEW_ONLY')
  for i in ('lima_sur_malanche','lambayeque_chongoyape_oyotun_zana','arequipa_acari_san_agustin'): self.assertEqual(z[i]['materialization_status'],'BLOCKED')
 def test_phase2_operational_activation_is_forbidden(self):
  for i in ('lima_norte_huerta_vieja','lima_sur_malanche','lambayeque_chongoyape_oyotun_zana','arequipa_acari_san_agustin'):
   c=json.loads((CONTRACTS/f'{i}.json').read_text()); self.assertEqual(c['deployment_status'],'RESEARCH_ONLY'); self.assertIs(c['production_use'],False); self.assertIs(c['alerting_enabled'],False); self.assertIsNone(c['decision_thresholds']); self.assertIsNone(c['hydraulic_factors']); self.assertEqual(c['validation']['activation_gate'],'BLOCKED')
  self.assertIs(self.g['properties']['production_use'],False); self.assertIs(self.g['properties']['production_ready'],False); self.assertIs(self.g['properties']['operational_alerting_enabled'],False); self.assertIs(self.v['activation_permitted'],False)
if __name__=='__main__': unittest.main()
