import json
import subprocess
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_norte_chillon_bajo.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_norte_chillon_bajo_chillon_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_norte_chillon_bajo_geometry_validation.json"
SOURCE_INVENTORY = ROOT / "site/data/phase2/sources/chillon_bajo_hydrologic_context/source_inventory.json"
MAP_CATALOG = ROOT / "site/data/map_layers.json"


class ChillonBajoGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        cls.source_inventory = json.loads(SOURCE_INVENTORY.read_text(encoding="utf-8"))

    def test_frozen_source_replays_exactly(self):
        subprocess.run([sys.executable, "scripts/probe_chillon_bajo_official_geometry.py", "--check-only"], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_scientific_guards_remain_closed(self):
        c=self.contract
        self.assertEqual(c["deployment_status"],"RESEARCH_ONLY")
        self.assertEqual(c["test_mode"],"TEST_ONLY")
        self.assertFalse(c["production_use"]); self.assertFalse(c["production_ready"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertEqual(c["validation"]["activation_gate"],"BLOCKED")
        self.assertEqual(c["missing_data_rule"],"UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(c["decision_thresholds"]); self.assertIsNone(c["hydraulic_factors"])

    def test_geometry_is_partial_whole_basin_context_only(self):
        v=self.validation
        self.assertEqual(v["status"],"PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY")
        self.assertEqual(v["official_unit"]["code"],"137556")
        self.assertEqual(v["official_unit"]["name"],"Cuenca Chillón")
        self.assertFalse(v["counts_as_complete_candidate_geometry"])
        self.assertFalse(v["artificial_connector_used"])
        self.assertEqual(v["component_resolution"]["lower_river_reaches"],"UNRESOLVED_NO_GEOMETRY_DRAWN")
        self.assertEqual(v["component_resolution"]["tributary_ravines"],"UNRESOLVED_NO_GEOMETRY_DRAWN")
        self.assertEqual(v["component_resolution"]["event_footprint"],"NOT_ASSERTED")
        self.assertEqual(v["component_resolution"]["hydraulic_capacity"],"UNKNOWN")
        self.assertEqual(v["component_resolution"]["negative_controls"],"NOT_ASSERTED")
        f=self.geometry["features"][0]
        self.assertIn(f["geometry"]["type"],{"Polygon","MultiPolygon"})
        self.assertEqual(f["properties"]["official_hydrologic_unit_code"],"137556")
        self.assertFalse(f["properties"]["counts_as_complete_candidate_geometry"])
        self.assertFalse(f["properties"]["event_footprint_resolved"])
        self.assertFalse(f["properties"]["lower_river_reaches_geometry_resolved"])
        self.assertFalse(f["properties"]["tributary_ravines_geometry_resolved"])
        self.assertFalse(f["properties"]["dem_used"]); self.assertFalse(f["properties"]["outlet_used"])

    def test_source_identity_and_map_catalog_are_linked(self):
        source=self.source_inventory["sources"][0]
        self.assertEqual(source["official_unit_code"],"137556")
        self.assertEqual(source["official_unit_name"],"Cuenca Chillón")
        self.assertGreater(source["official_area_km2"],0)
        self.assertEqual(self.contract["assets"]["geometry"]["status"],"PARTIAL")
        self.assertEqual(self.contract["assets"]["geometry"]["path"],GEOMETRY.relative_to(ROOT).as_posix())
        rows=[r for r in json.loads(MAP_CATALOG.read_text(encoding="utf-8"))["research_zones"] if r["candidate_id"]=="lima_norte_chillon_bajo"]
        self.assertEqual(len(rows),1); row=rows[0]
        self.assertTrue(row["geometry"]["map_eligible"]); self.assertFalse(row["geometry"]["default_visibility"])
        self.assertEqual(row["deployment_status"],"RESEARCH_ONLY"); self.assertFalse(row["production_use"]); self.assertFalse(row["alerting_enabled"])
        self.assertEqual(row["validation"]["activation_gate"],"BLOCKED")


if __name__ == "__main__": unittest.main()
