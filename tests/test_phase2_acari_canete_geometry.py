"""Regression tests for official ANA basin-context geometry in Phase 2."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_acari_canete_official_geometry.py"
SOURCE_INVENTORY = ROOT / "site/data/phase2/sources/acari_canete_hydrologic_context/source_inventory.json"
CATALOG = ROOT / "site/data/phase2/catalog.json"
MAP = ROOT / "site/data/map_layers.json"

EXPECTED = {
    "arequipa_acari_san_agustin": "site/data/phase2/geometries/arequipa_acari_san_agustin_acari_basin_context.geojson",
    "lima_sur_canete": "site/data/phase2/geometries/lima_sur_canete_canete_basin_context.geojson",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AcariCaneteGeometryTests(unittest.TestCase):
    def test_offline_replay_passes_without_network(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-only"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frozen_source_hashes_and_official_identity_are_present(self):
        inventory = load(SOURCE_INVENTORY)
        self.assertEqual(inventory["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(inventory["test_mode"], "TEST_ONLY")
        self.assertFalse(inventory["production_use"])
        self.assertFalse(inventory["production_ready"])
        self.assertFalse(inventory["operational_alerting_enabled"])
        self.assertEqual(inventory["activation_gate"], "BLOCKED")
        self.assertEqual(inventory["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(inventory["decision_thresholds"])
        self.assertIsNone(inventory["hydraulic_factors"])
        by_id = {row["candidate_id"]: row for row in inventory["sources"]}
        self.assertEqual(set(by_id), set(EXPECTED))
        for candidate_id, row in by_id.items():
            source_path = ROOT / row["local_path"]
            source = load(source_path)
            canonical = (json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), row["canonical_sha256"])
            self.assertTrue(row["official_unit_code"])
            self.assertGreater(row["official_area_km2"], 0)
            self.assertEqual(source["features"][0]["properties"]["NOMBRE"], row["official_unit_name"])

    def test_normalized_geometries_are_context_only_and_fail_closed(self):
        for candidate_id, rel in EXPECTED.items():
            document = load(ROOT / rel)
            self.assertEqual(document["type"], "FeatureCollection")
            self.assertEqual(document["properties"]["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(document["properties"]["test_mode"], "TEST_ONLY")
            self.assertFalse(document["properties"]["production_use"])
            self.assertFalse(document["properties"]["production_ready"])
            self.assertFalse(document["properties"]["operational_alerting_enabled"])
            self.assertEqual(document["properties"]["activation_gate"], "BLOCKED")
            self.assertEqual(document["properties"]["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(document["properties"]["decision_thresholds"])
            self.assertIsNone(document["properties"]["hydraulic_factors"])
            self.assertEqual(len(document["features"]), 1)
            feature = document["features"][0]
            props = feature["properties"]
            self.assertEqual(props["candidate_id"], candidate_id)
            self.assertIn(feature["geometry"]["type"], {"Polygon", "MultiPolygon"})
            self.assertEqual(props["feature_role"], "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT")
            self.assertEqual(props["hydrologic_role"], "OFFICIAL_BASIN_BOUNDARY_NOT_EVENT_FOOTPRINT")
            self.assertFalse(props["counts_as_complete_candidate_geometry"])
            self.assertFalse(props["loaded_into_operational_calculation"])
            self.assertFalse(props["carries_alert_values"])
            self.assertFalse(props["carries_risk_classification"])
            self.assertFalse(props["district_boundary_used"])
            self.assertFalse(props["dem_used"])
            self.assertFalse(props["outlet_used"])
            self.assertIsNone(props["decision_thresholds"])
            self.assertIsNone(props["hydraulic_factors"])

    def test_contracts_link_partial_geometry_without_promotion(self):
        for candidate_id, rel in EXPECTED.items():
            contract = load(ROOT / f"site/data/validation/phase2_zone_contracts/{candidate_id}.json")
            geom = contract["assets"]["geometry"]
            self.assertEqual(geom["status"], "PARTIAL")
            self.assertEqual(geom["path"], rel)
            self.assertTrue((ROOT / rel).is_file())
            self.assertEqual(contract["deployment_status"], "RESEARCH_ONLY")
            self.assertFalse(contract["production_use"])
            self.assertFalse(contract["alerting_enabled"])
            self.assertEqual(contract["validation"]["activation_gate"], "BLOCKED")
            self.assertEqual(contract["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(contract["decision_thresholds"])
            self.assertIsNone(contract["hydraulic_factors"])

    def test_catalog_and_map_do_not_inflate_maturity(self):
        catalog = {row["candidate_id"]: row for row in load(CATALOG)["zones"]}
        map_zones = {row["candidate_id"]: row for row in load(MAP)["research_zones"]}
        for candidate_id, rel in EXPECTED.items():
            row = catalog[candidate_id]
            self.assertEqual(row["activation_gate"], "BLOCKED")
            self.assertEqual(row["asset_status"]["geometry"], "PARTIAL")
            self.assertEqual(row["asset_readiness"]["geometry"]["data_presence"], "PRESENT")
            self.assertFalse((row.get("promotion_gate") or {}).get("promotion_gate_met"))
            mapped = map_zones[candidate_id]
            self.assertTrue(mapped["map_eligible"])
            self.assertFalse(mapped["default_visibility"])
            self.assertEqual(mapped["geometry_path"], rel)
            self.assertEqual(mapped["deployment_status"], "RESEARCH_ONLY")
            self.assertFalse(mapped["loaded_into_operational_calculation"])
            self.assertFalse(mapped["carries_alert_values"])
            self.assertFalse(mapped["carries_risk_classification"])


if __name__ == "__main__":
    unittest.main()
