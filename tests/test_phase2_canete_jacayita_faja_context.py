"""Regression tests for official Jacayita faja-margin Phase-2 context."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site/data/phase2/sources/canete_jacayita_faja_context/ana_jacayita_faja_hitos_v0_1.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_sur_canete_jacayita_faja_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_sur_canete_jacayita_faja_context_validation.json"
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_canete.json"
MAP = ROOT / "site/data/map_layers.json"
BUILDER = ROOT / "scripts/build_canete_jacayita_faja_context.py"
MAP_BUILDER = ROOT / "scripts/build_map_layer_catalog.py"
TERRITORIAL_JS = ROOT / "site/v08-territorial.js"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestCaneteJacayitaFajaContext(unittest.TestCase):
    def test_exact_replay_and_frozen_provenance(self):
        subprocess.run([sys.executable, str(BUILDER), "--check-only"], cwd=ROOT, check=True)
        subprocess.run([sys.executable, str(MAP_BUILDER), "--check-only"], cwd=ROOT, check=True)
        validation = load(VALIDATION)
        self.assertEqual(validation["source_snapshot_sha256"], hashlib.sha256(SOURCE.read_bytes()).hexdigest())
        self.assertEqual(validation["normalized_geometry_sha256"], hashlib.sha256(GEOMETRY.read_bytes()).hexdigest())
        self.assertEqual(validation["status"], "PASS_PARTIAL_OFFICIAL_JACAYITA_FAJA_CONTEXT_GEOMETRY")

    def test_source_and_geometry_are_fail_closed(self):
        source = load(SOURCE)
        self.assertEqual(source["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(source["test_mode"], "TEST_ONLY")
        self.assertFalse(source["production_use"])
        self.assertFalse(source["production_ready"])
        self.assertFalse(source["operational_alerting_enabled"])
        self.assertEqual(source["activation_gate"], "BLOCKED")
        self.assertEqual(source["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(source["decision_thresholds"])
        self.assertIsNone(source["hydraulic_factors"])
        self.assertEqual(source["source"]["source_id"], "ANA-JACAYITA-FAJA-RD0396-2025")
        self.assertEqual(source["source_interpretation"]["approved_hito_counts"]["total"], 62)

        geometry = load(GEOMETRY)
        self.assertEqual(geometry["type"], "FeatureCollection")
        self.assertEqual(len(geometry["features"]), 4)
        self.assertEqual({f["geometry"]["type"] for f in geometry["features"]}, {"LineString"})
        self.assertEqual([f["properties"]["hito_count"] for f in geometry["features"]], [21, 22, 10, 9])
        self.assertEqual({f["properties"]["branch"] for f in geometry["features"]}, {"MAIN_CHANNEL", "APORTANTE_1"})
        for feature in geometry["features"]:
            p = feature["properties"]
            self.assertEqual(p["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(p["test_mode"], "TEST_ONLY")
            self.assertFalse(p["production_use"])
            self.assertFalse(p["production_ready"])
            self.assertFalse(p["alerting_enabled"])
            self.assertEqual(p["activation_gate"], "BLOCKED")
            self.assertEqual(p["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(p["decision_thresholds"])
            self.assertIsNone(p["hydraulic_factors"])
            self.assertTrue(p["not_catchment"])
            self.assertTrue(p["not_event_footprint"])
            self.assertTrue(p["not_historical_hydraulic_capacity"])
            self.assertTrue(p["not_observed_event"])
            self.assertFalse(p["counts_as_complete_candidate_geometry"])
            self.assertFalse(p["artificial_connector_used"])

    def test_contract_keeps_basin_and_jacayita_separate(self):
        contract = load(CONTRACT)
        self.assertEqual(contract["contract_status"], "DRAFT")
        self.assertEqual(contract["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(contract["test_mode"], "TEST_ONLY")
        self.assertFalse(contract["production_use"])
        self.assertFalse(contract["production_ready"])
        self.assertFalse(contract["operational_alerting_enabled"])
        self.assertEqual(contract["validation"]["activation_gate"], "BLOCKED")
        self.assertEqual(contract["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(contract["decision_thresholds"])
        self.assertIsNone(contract["hydraulic_factors"])
        geom = contract["assets"]["geometry"]
        self.assertEqual(geom["status"], "PARTIAL")
        self.assertEqual(geom["path"], "site/data/phase2/geometries/lima_sur_canete_canete_basin_context.geojson")
        self.assertEqual(len(geom["component_layers"]), 1)
        component = geom["component_layers"][0]
        self.assertEqual(component["path"], GEOMETRY.relative_to(ROOT).as_posix())
        self.assertFalse(component["counts_as_complete_candidate_geometry"])
        self.assertFalse(component["candidate_wide_sampling_ready"])

    def test_map_publishes_component_as_separate_research_layer(self):
        catalog = load(MAP)
        layers = catalog.get("research_component_layers") or []
        jacayita = next(x for x in layers if x["layer_id"] == "lima_sur_canete_jacayita_faja_2025")
        self.assertEqual(jacayita["candidate_id"], "lima_sur_canete")
        self.assertEqual(jacayita["deployment_status"], "RESEARCH_ONLY")
        self.assertFalse(jacayita["production_use"])
        self.assertFalse(jacayita["production_ready"])
        self.assertFalse(jacayita["operational_alerting_enabled"])
        self.assertFalse(jacayita["loaded_into_operational_calculation"])
        self.assertFalse(jacayita["carries_alert_values"])
        self.assertFalse(jacayita["carries_risk_classification"])
        self.assertFalse(jacayita["default_visibility"])
        self.assertEqual(jacayita["source_metadata"]["feature_count"], 4)
        self.assertEqual(jacayita["source_metadata"]["geometry_types"], ["LineString"])
        parent = next(x for x in catalog["research_zones"] if x["candidate_id"] == "lima_sur_canete")
        self.assertEqual(parent["geometry"]["path"], "site/data/phase2/geometries/lima_sur_canete_canete_basin_context.geojson")
        self.assertEqual(parent["geometry"]["source_metadata"]["feature_count"], 1)
        js = TERRITORIAL_JS.read_text(encoding="utf-8")
        self.assertIn("maps.research_component_layers", js)
        self.assertIn("context_component:", js)


if __name__ == "__main__":
    unittest.main()
