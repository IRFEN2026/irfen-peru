"""Fail-closed regression for unresolved separate La Leche geometry."""
from __future__ import annotations
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"site/data/validation/phase2_research_evidence/la_leche_geometry_discovery_20260923.json"
CONTRACT=ROOT/"site/data/validation/phase2_zone_contracts/lambayeque_motupe_la_leche_pitipo.json"
GEOMETRY=ROOT/"site/data/phase2/geometries/lambayeque_motupe_la_leche_pitipo_motupe_basin_context.geojson"
MAP=ROOT/"site/data/map_layers.json"

def load(p): return json.loads(p.read_text(encoding="utf-8"))

class TestLaLecheGeometryGap(unittest.TestCase):
 def test_discovery_is_bounded_and_fail_closed(self):
  d=load(EVIDENCE)
  self.assertEqual(d["deployment_status"],"RESEARCH_ONLY")
  self.assertEqual(d["test_mode"],"TEST_ONLY")
  self.assertFalse(d["production_use"]); self.assertFalse(d["production_ready"]); self.assertFalse(d["operational_alerting_enabled"])
  self.assertEqual(d["activation_gate"],"BLOCKED"); self.assertEqual(d["missing_data_rule"],"UNKNOWN_NOT_LOW_RISK")
  self.assertIsNone(d["decision_thresholds"]); self.assertIsNone(d["hydraulic_factors"])
  self.assertEqual(d["discovery_status"],"NO_REPRODUCIBLE_SEPARATE_GEOMETRY_FROM_TESTED_OFFICIAL_ENDPOINTS")
  checks=d["official_endpoint_checks"]
  self.assertEqual(checks[0]["result"],"NETWORK_TIMEOUT_NO_SCIENTIFIC_INFERENCE")
  self.assertEqual(checks[1]["result"],"ZERO_FEATURES_FOR_EXACT_CODE_IN_THIS_LAYER")
  self.assertEqual(checks[1]["feature_count"],0)
  self.assertEqual(checks[1]["raw_response_sha256"],"ed778c73ea51338d6576fb5992b189f2b94d9f3d5e199f46c1af520d6b0b3e6c")
  self.assertEqual(checks[1]["canonical_response_sha256"],"6d6b80a88dc60e65991d34024fe7cf2eb86531ffba8b75efb697fe0a601f2799")

 def test_no_separate_geometry_is_invented(self):
  d=load(EVIDENCE); decision=d["current_geometry_decision"]
  self.assertIsNone(decision["la_leche_separate_geometry_path"]); self.assertIsNone(decision["pitipo_geometry_path"])
  self.assertEqual(decision["local_ravine_geometry_paths"],[]); self.assertEqual(decision["map_action"],"KEEP_EXISTING_MOTUPE_CONTEXT_ONLY")
  self.assertFalse(decision["counts_as_complete_candidate_geometry"]); self.assertFalse(decision["artificial_connector_used"])
  g=load(GEOMETRY); self.assertEqual(len(g["features"]),1)
  p=g["features"][0]["properties"]
  self.assertEqual(p["official_hydrologic_unit_code"],"137772")
  self.assertFalse(p["separate_la_leche_basin_polygon_asserted"]); self.assertFalse(p["pitipo_hydrologic_polygon_asserted"]); self.assertFalse(p["watercourse_line_geometry_materialized"])

 def test_contract_and_map_maturity_do_not_change(self):
  c=load(CONTRACT); self.assertEqual(c["contract_status"],"DRAFT"); self.assertEqual(c["assets"]["geometry"]["status"],"PARTIAL")
  self.assertEqual(c["assets"]["geometry"]["path"],GEOMETRY.relative_to(ROOT).as_posix())
  self.assertIn(EVIDENCE.relative_to(ROOT).as_posix(),c["validation"]["review_evidence"])
  self.assertEqual(c["validation"]["activation_gate"],"BLOCKED"); self.assertEqual(c["missing_data_rule"],"UNKNOWN_NOT_LOW_RISK")
  self.assertIsNone(c["decision_thresholds"]); self.assertIsNone(c["hydraulic_factors"]); self.assertFalse(c["production_use"]); self.assertFalse(c["operational_alerting_enabled"])
  layer=next(x for x in load(MAP)["research_zones"] if x["candidate_id"]=="lambayeque_motupe_la_leche_pitipo")
  self.assertTrue(layer["geometry"]["map_eligible"]); self.assertFalse(layer["geometry"]["default_visibility"])
  self.assertEqual(layer["geometry"]["path"],GEOMETRY.relative_to(ROOT).as_posix())
  self.assertEqual(layer["geometry"]["source_metadata"]["feature_count"],1)
  self.assertFalse(layer["production_use"]); self.assertFalse(layer["alerting_enabled"]); self.assertEqual(layer["validation"]["activation_gate"],"BLOCKED")

if __name__=="__main__": unittest.main()
