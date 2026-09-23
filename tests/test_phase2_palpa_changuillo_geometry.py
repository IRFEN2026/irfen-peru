"""Regression tests for official ANA Cuenca Grande Phase-2 research context."""
from __future__ import annotations
import hashlib,json,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/probe_palpa_changuillo_official_geometry.py"
SOURCE_INV=ROOT/"site/data/phase2/sources/palpa_changuillo_hydrologic_context/source_inventory.json"
GEOMETRY=ROOT/"site/data/phase2/geometries/ica_palpa_changuillo_grande_basin_context.geojson"
CONTRACT=ROOT/"site/data/validation/phase2_zone_contracts/ica_palpa_changuillo.json"
CATALOG=ROOT/"site/data/phase2/catalog.json"
MAP=ROOT/"site/data/map_layers.json"
EXPECTED_SHA="3ac91009d90eaf5f245fb0d481b7fb0777f1d8265b081bc23601f83bf6b3de70"
def load(p): return json.loads(p.read_text(encoding="utf-8"))
class PalpaChanguilloGeometryTests(unittest.TestCase):
 def test_offline_replay(self):
  r=subprocess.run([sys.executable,str(SCRIPT),"--check-only"],cwd=ROOT,capture_output=True,text=True); self.assertEqual(r.returncode,0,r.stdout+r.stderr)
 def test_frozen_source(self):
  inv=load(SOURCE_INV); self.assertEqual(inv["activation_gate"],"BLOCKED"); self.assertEqual(inv["missing_data_rule"],"UNKNOWN_NOT_LOW_RISK")
  self.assertFalse(inv["production_use"]); self.assertFalse(inv["production_ready"]); self.assertFalse(inv["operational_alerting_enabled"])
  self.assertIsNone(inv["decision_thresholds"]); self.assertIsNone(inv["hydraulic_factors"])
  row=inv["sources"][0]; self.assertEqual(row["official_unit_code"],"1372"); self.assertEqual(row["official_unit_name"],"Cuenca Grande"); self.assertEqual(row["canonical_sha256"],EXPECTED_SHA)
  src=load(ROOT/row["local_path"]); canonical=(json.dumps(src,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode(); self.assertEqual(hashlib.sha256(canonical).hexdigest(),EXPECTED_SHA)
 def test_context_only(self):
  d=load(GEOMETRY); self.assertEqual(d["properties"]["activation_gate"],"BLOCKED"); self.assertEqual(len(d["features"]),1)
  p=d["features"][0]["properties"]; self.assertEqual(p["feature_role"],"OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT"); self.assertEqual(p["official_hydrologic_unit_code"],"1372")
  self.assertFalse(p["local_river_reaches_geometry_resolved"]); self.assertFalse(p["local_ravines_geometry_resolved"]); self.assertFalse(p["counts_as_complete_candidate_geometry"])
  self.assertFalse(p["loaded_into_operational_calculation"]); self.assertFalse(p["carries_alert_values"]); self.assertFalse(p["carries_risk_classification"])
 def test_contract_and_map_remain_partial(self):
  c=load(CONTRACT); g=c["assets"]["geometry"]; self.assertEqual(g["status"],"PARTIAL"); self.assertEqual(g["path"],GEOMETRY.relative_to(ROOT).as_posix()); self.assertEqual(c["validation"]["activation_gate"],"BLOCKED")
  self.assertIsNone(c["decision_thresholds"]); self.assertIsNone(c["hydraulic_factors"]); self.assertEqual(c["missing_data_rule"],"UNKNOWN_NOT_LOW_RISK")
  z={r["candidate_id"]:r for r in load(CATALOG)["zones"]}["ica_palpa_changuillo"]; self.assertEqual(z["asset_status"]["geometry"],"PARTIAL"); self.assertEqual(z["activation_gate"],"BLOCKED")
  m={r["candidate_id"]:r for r in load(MAP)["research_zones"]}["ica_palpa_changuillo"]; self.assertTrue(m["geometry"]["map_eligible"]); self.assertFalse(m["geometry"]["default_visibility"]); self.assertFalse(m["production_use"]); self.assertFalse(m["alerting_enabled"]); self.assertEqual(m["validation"]["activation_gate"],"BLOCKED")
if __name__=="__main__": unittest.main()
