"""Regression tests for official ANA Cuenca Pisco Phase-2 research geometry."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_pisco_official_geometry.py"
SOURCE_INVENTORY = ROOT / "site/data/phase2/sources/pisco_hydrologic_context/source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/ica_pisco_san_andres_pisco_basin_context.geojson"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/ica_pisco_san_andres.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
MAP = ROOT / "site/data/map_layers.json"
EXPECTED_SHA = "693bcd668bcc5f692a04d516976908757172c6274962e9f4ca0a6c6d9e799e9b"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class PiscoGeometryTests(unittest.TestCase):
    def test_offline_replay_passes_without_network(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--check-only"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frozen_official_source_identity_and_hash(self):
        inv = load(SOURCE_INVENTORY)
        self.assertEqual(inv["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(inv["test_mode"], "TEST_ONLY")
        self.assertFalse(inv["production_use"])
        self.assertFalse(inv["production_ready"])
        self.assertFalse(inv["operational_alerting_enabled"])
        self.assertEqual(inv["activation_gate"], "BLOCKED")
        self.assertEqual(inv["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(inv["decision_thresholds"])
        self.assertIsNone(inv["hydraulic_factors"])
        self.assertEqual(len(inv["sources"]), 1)
        row = inv["sources"][0]
        self.assertEqual(row["official_unit_code"], "13752")
        self.assertEqual(row["official_unit_name"], "Cuenca Pisco")
        self.assertAlmostEqual(float(row["official_area_km2"]), 4208.7453, delta=0.0001)
        self.assertEqual(row["canonical_sha256"], EXPECTED_SHA)
        source = load(ROOT / row["local_path"])
        canonical = (json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), EXPECTED_SHA)

    def test_geometry_is_only_official_pisco_basin_context(self):
        doc = load(GEOMETRY)
        self.assertEqual(doc["properties"]["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(doc["properties"]["test_mode"], "TEST_ONLY")
        self.assertFalse(doc["properties"]["production_use"])
        self.assertFalse(doc["properties"]["production_ready"])
        self.assertFalse(doc["properties"]["operational_alerting_enabled"])
        self.assertEqual(doc["properties"]["activation_gate"], "BLOCKED")
        self.assertEqual(doc["properties"]["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(doc["properties"]["decision_thresholds"])
        self.assertIsNone(doc["properties"]["hydraulic_factors"])
        self.assertEqual(len(doc["features"]), 1)
        feature = doc["features"][0]
        props = feature["properties"]
        self.assertEqual(props["official_hydrologic_unit_code"], "13752")
        self.assertEqual(props["official_hydrologic_unit_name"], "Cuenca Pisco")
        self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})
        self.assertEqual(props["feature_role"], "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT")
        self.assertFalse(props["san_andres_local_drainage_geometry_resolved"])
        self.assertFalse(props["tributary_ravines_geometry_resolved"])
        self.assertFalse(props["event_footprint_asserted"])
        self.assertFalse(props["counts_as_complete_candidate_geometry"])
        self.assertFalse(props["loaded_into_operational_calculation"])
        self.assertFalse(props["carries_alert_values"])
        self.assertFalse(props["carries_risk_classification"])
        self.assertFalse(props["dem_used"])
        self.assertFalse(props["outlet_used"])

    def test_contract_remains_partial_and_fail_closed(self):
        c = load(CONTRACT)
        g = c["assets"]["geometry"]
        self.assertEqual(g["status"], "PARTIAL")
        self.assertEqual(g["path"], GEOMETRY.relative_to(ROOT).as_posix())
        self.assertEqual(c["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(c["test_mode"], "TEST_ONLY")
        self.assertFalse(c["production_use"])
        self.assertFalse(c["production_ready"])
        self.assertFalse(c["alerting_enabled"])
        self.assertFalse(c["operational_alerting_enabled"])
        self.assertEqual(c["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(c["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(c["decision_thresholds"])
        self.assertIsNone(c["hydraulic_factors"])

    def test_map_is_research_context_only(self):
        catalog = {row["candidate_id"]: row for row in load(CATALOG)["zones"]}
        row = catalog["ica_pisco_san_andres"]
        self.assertEqual(row["asset_status"]["geometry"], "PARTIAL")
        self.assertEqual(row["activation_gate"], "BLOCKED")
        self.assertFalse((row.get("promotion_gate") or {}).get("promotion_gate_met"))
        mapped = {row["candidate_id"]: row for row in load(MAP)["research_zones"]}["ica_pisco_san_andres"]
        self.assertTrue(mapped["geometry"]["map_eligible"])
        self.assertFalse(mapped["geometry"]["default_visibility"])
        self.assertEqual(mapped["geometry"]["path"], GEOMETRY.relative_to(ROOT).as_posix())
        self.assertEqual(mapped["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(mapped["production_use"])
        self.assertFalse(mapped["alerting_enabled"])
        self.assertEqual(mapped["validation"]["activation_gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
