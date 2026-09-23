"""Regression tests for official ANA Cuenca Mala Phase-2 research geometry."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/finalize_mala_official_basin.py"
SOURCE_INVENTORY = ROOT / "site/data/phase2/sources/mala_hydrologic_context/source_inventory.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_sur_mala_mala_basin_context.geojson"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_mala.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
MAP = ROOT / "site/data/map_layers.json"
SPATIAL = ROOT / "site/data/phase2/spatial_observation_contracts_v0_1.json"
EXPECTED_SOURCE_SHA256 = "fd2bc3c148689c6a24eaa150a5bcb02c86a2b62117f32c2f06f558dc855eada4"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class MalaGeometryTests(unittest.TestCase):
    def test_offline_replay_passes_without_network(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--check-only"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frozen_source_identity_and_hash(self):
        inv = load(SOURCE_INVENTORY)
        for key, value in {
            "deployment_status":"RESEARCH_ONLY", "test_mode":"TEST_ONLY",
            "production_use":False, "production_ready":False,
            "operational_alerting_enabled":False, "activation_gate":"BLOCKED",
            "missing_data_rule":"UNKNOWN_NOT_LOW_RISK", "decision_thresholds":None,
            "hydraulic_factors":None,
        }.items():
            self.assertEqual(inv[key], value)
        self.assertEqual(len(inv["sources"]), 1)
        row = inv["sources"][0]
        self.assertEqual(row["official_unit_code"], "137552")
        self.assertEqual(row["official_unit_name"], "Cuenca Mala")
        self.assertEqual(row["canonical_sha256"], EXPECTED_SOURCE_SHA256)
        source = load(ROOT / row["local_path"])
        canonical = (json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), EXPECTED_SOURCE_SHA256)

    def test_geometry_is_partial_official_basin_context_only(self):
        doc = load(GEOMETRY)
        props = doc["properties"]
        self.assertEqual(props["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(props["test_mode"], "TEST_ONLY")
        self.assertFalse(props["production_use"])
        self.assertFalse(props["production_ready"])
        self.assertFalse(props["operational_alerting_enabled"])
        self.assertEqual(props["activation_gate"], "BLOCKED")
        self.assertEqual(props["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(props["decision_thresholds"])
        self.assertIsNone(props["hydraulic_factors"])
        self.assertEqual(len(doc["features"]), 1)
        feature = doc["features"][0]
        fp = feature["properties"]
        self.assertEqual(fp["official_hydrologic_unit_code"], "137552")
        self.assertEqual(fp["official_hydrologic_unit_name"], "Cuenca Mala")
        self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})
        self.assertEqual(fp["feature_role"], "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT")
        self.assertFalse(fp["tributary_ravines_geometry_resolved"])
        self.assertFalse(fp["river_reaches_geometry_resolved"])
        self.assertFalse(fp["counts_as_complete_candidate_geometry"])
        self.assertFalse(fp["loaded_into_operational_calculation"])
        self.assertFalse(fp["carries_alert_values"])
        self.assertFalse(fp["carries_risk_classification"])
        self.assertFalse(fp["dem_used"])
        self.assertFalse(fp["outlet_used"])

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
        row = catalog["lima_sur_mala"]
        self.assertEqual(row["asset_status"]["geometry"], "PARTIAL")
        self.assertEqual(row["activation_gate"], "BLOCKED")
        self.assertFalse((row.get("promotion_gate") or {}).get("promotion_gate_met"))
        mapped = {row["candidate_id"]: row for row in load(MAP)["research_zones"]}["lima_sur_mala"]
        self.assertTrue(mapped["geometry"]["map_eligible"])
        self.assertFalse(mapped["geometry"]["default_visibility"])
        self.assertEqual(mapped["geometry"]["path"], GEOMETRY.relative_to(ROOT).as_posix())
        self.assertEqual(mapped["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(mapped["production_use"])
        self.assertFalse(mapped["alerting_enabled"])
        self.assertEqual(mapped["validation"]["activation_gate"], "BLOCKED")

    def test_spatial_contract_treats_mala_as_context_not_candidate_wide_geometry(self):
        spatial = load(SPATIAL)
        row = {r["candidate_id"]: r for r in spatial["candidate_records"]}["lima_sur_mala"]
        self.assertEqual(row["spatial_contract_status"], "NON_CATCHMENT_GEOMETRY_ONLY")
        self.assertEqual(spatial["summary"]["candidate_wide_ready_count"], 0)
        self.assertEqual(spatial["summary"]["non_catchment_geometry_only_count"], 11)
        self.assertEqual(spatial["summary"]["blocked_missing_geometry_count"], 5)
        self.assertEqual(spatial["summary"]["operational_spatial_contract_count"], 0)


if __name__ == "__main__":
    unittest.main()
