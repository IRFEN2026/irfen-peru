import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CID = "lambayeque_motupe_la_leche_pitipo"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lambayeque_motupe_la_leche_pitipo.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lambayeque_motupe_la_leche_pitipo_motupe_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lambayeque_motupe_la_leche_pitipo_geometry_validation.json"
SOURCE = ROOT / "site/data/phase2/sources/motupe_la_leche_hydrologic_context/ana_cuenca_motupe_137772.geojson"
INVENTORY = ROOT / "config/phase2_candidate_inventory_v0_2.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
MAP_LAYERS = ROOT / "site/data/map_layers.json"
EXPECTED_SOURCE_SHA = "5b5b59e51cd84809e5f63336147e713a8277b61126e6d65ae1acd53481242b07"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestMotupeLaLecheGeometry(unittest.TestCase):
    def test_generated_assets_are_reproducible_without_network(self):
        subprocess.run(
            [sys.executable, "scripts/probe_motupe_la_leche_official_geometry.py", "--check-only"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, "scripts/build_phase2_catalog.py", "--check-only"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, "scripts/build_map_layer_catalog.py", "--check-only"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_contract_remains_partial_and_fail_closed(self):
        c = load(CONTRACT)
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["alerting_enabled"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertEqual(c["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["assets"]["geometry"]["status"], "PARTIAL")
        self.assertEqual(c["assets"]["geometry"]["path"], GEOMETRY.relative_to(ROOT).as_posix())
        self.assertEqual(c["assets"]["historical_events"]["status"], "MISSING")
        self.assertEqual(c["assets"]["observations"]["status"], "MISSING")
        self.assertEqual(c["assets"]["hydraulic_context"]["status"], "MISSING")

    def test_geometry_is_only_official_motupe_basin_context(self):
        g = load(GEOMETRY)
        self.assertEqual(g["type"], "FeatureCollection")
        self.assertEqual(len(g["features"]), 1)
        self.assertEqual(g["properties"]["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(g["properties"]["production_use"])
        self.assertFalse(g["properties"]["production_ready"])
        self.assertFalse(g["properties"]["operational_alerting_enabled"])
        self.assertEqual(g["properties"]["activation_gate"], "BLOCKED")
        feature = g["features"][0]
        self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})
        p = feature["properties"]
        self.assertEqual(p["official_hydrologic_unit_code"], "137772")
        self.assertEqual(p["official_hydrologic_unit_name"], "Cuenca Motupe")
        self.assertEqual(p["la_leche_watercourse_code"], "1377722")
        self.assertFalse(p["separate_la_leche_basin_polygon_asserted"])
        self.assertFalse(p["pitipo_hydrologic_polygon_asserted"])
        self.assertFalse(p["watercourse_line_geometry_materialized"])
        self.assertFalse(p["loaded_into_operational_calculation"])
        self.assertFalse(p["carries_alert_values"])
        self.assertFalse(p["carries_risk_classification"])
        self.assertIsNone(p["decision_thresholds"])
        self.assertIsNone(p["hydraulic_factors"])

    def test_source_and_validation_hashes_are_frozen(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SOURCE_SHA)
        v = load(VALIDATION)
        self.assertEqual(v["status"], "PASS_PARTIAL_OFFICIAL_HYDROLOGIC_GEOMETRY")
        self.assertEqual(v["source_snapshot_sha256"], EXPECTED_SOURCE_SHA)
        self.assertFalse(v["counts_as_complete_candidate_geometry"])
        self.assertEqual(v["component_resolution"]["local_ravines"], "UNRESOLVED_NO_GEOMETRY_DRAWN")
        self.assertEqual(v["component_resolution"]["pitipo"], "TERRITORIAL_REFERENCE_NOT_HYDROLOGIC_POLYGON")
        self.assertEqual(v["component_resolution"]["rio_motupe_line_geometry"], "NOT_MATERIALIZED")

    def test_inventory_catalog_and_map_do_not_inflate_maturity(self):
        inv = load(INVENTORY)
        row = next(x for x in inv["candidates"] if x["candidate_id"] == CID)
        self.assertEqual(row["deployment_status"], "RESEARCH_ONLY")
        self.assertIn("ANA-IDEP-UH-MOTUPE-137772-20260922", row["official_sources"])
        self.assertIn("ANA-GEOSNIRH-MOTUPE-HYDROGRAPHIC-UNIT-137772", row["official_sources"])

        catalog = load(CATALOG)
        self.assertEqual(len(catalog["zones"]), 18)
        zone = next(x for x in catalog["zones"] if x["candidate_id"] == CID)
        self.assertEqual(zone["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(zone["activation_gate"], "BLOCKED")
        self.assertNotEqual(zone["contract_status"], "APPROVED")

        maps = load(MAP_LAYERS)
        layer = next(x for x in maps["research_zones"] if x["candidate_id"] == CID)
        self.assertEqual(layer["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(layer["production_use"])
        self.assertFalse(layer["alerting_enabled"])
        self.assertTrue(layer["geometry"]["map_eligible"])
        self.assertFalse(layer["geometry"]["default_visibility"])
        self.assertEqual(layer["geometry"]["source_metadata"]["feature_count"], 1)


if __name__ == "__main__":
    unittest.main()
