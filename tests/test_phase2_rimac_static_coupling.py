import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_phase2_rimac_static_coupling.py"
SPEC = importlib.util.spec_from_file_location("rimac_static_coupling_validator", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)

MAP_SCRIPT = ROOT / "scripts/build_map_layer_catalog.py"
MAP_SPEC = importlib.util.spec_from_file_location("map_catalog_builder_for_rimac_test", MAP_SCRIPT)
map_mod = importlib.util.module_from_spec(MAP_SPEC)
assert MAP_SPEC and MAP_SPEC.loader
sys.modules[MAP_SPEC.name] = map_mod
MAP_SPEC.loader.exec_module(map_mod)


class TestRimacStaticCoupling(unittest.TestCase):
    def setUp(self):
        self.base = mod.load(mod.BASE_PATH)
        self.v2 = mod.load(mod.V2_PATH)
        self.source = mod.load(mod.SOURCE_PATH)
        self.ext = mod.load(mod.EXT_PATH)
        self.nodes = mod.load(mod.NODES_PATH)

    def test_repository_contract_passes(self):
        report = mod.build_report()
        self.assertEqual(report["status"], "PASS_PHASE2_RIMAC_STATIC_COUPLING_EXTENSION")
        self.assertEqual(report["static_connected_count"], 2)
        self.assertEqual(report["routing_models_run"], 0)
        self.assertIsNone(report["parent_activation_state"])

    def test_outcome_or_postevent_source_use_fails_closed(self):
        source = copy.deepcopy(self.source)
        source["source"]["event_outcomes_used"] = True
        with self.assertRaises(mod.StaticCouplingError):
            mod.validate_source(source)

    def test_static_connectivity_cannot_invent_flow_or_travel_time(self):
        v2 = copy.deepcopy(self.v2)
        row = next(x for x in v2["tributaries"] if x["local_unit_id"] == "quirio")
        row["q_i_t"] = {"invented": 1.0}
        row["travel_time_tau"] = {"minutes": 10}
        with self.assertRaises(mod.StaticCouplingError):
            mod.validate_v2(v2, self.base, self.source)

    def test_d8_intersection_cannot_be_promoted_to_official_surface_confluence(self):
        v2 = copy.deepcopy(self.v2)
        row = next(x for x in v2["tributaries"] if x["local_unit_id"] == "pedregal_san_antonio")
        row["receiver_confluence_or_explicit_missing_status"]["official_surface_confluence_confirmed"] = True
        with self.assertRaises(mod.StaticCouplingError):
            mod.validate_v2(v2, self.base, self.source)

    def test_arbitrary_coupling_probability_is_rejected(self):
        v2 = copy.deepcopy(self.v2)
        v2["collector_coupling_matrix"][2]["coupling_probability"] = 0.9
        with self.assertRaises(mod.StaticCouplingError):
            mod.validate_v2(v2, self.base, self.source)

    def test_existing_cashahuacra_baseline_cannot_be_silently_promoted(self):
        v2 = copy.deepcopy(self.v2)
        row = next(x for x in v2["tributaries"] if x["local_unit_id"] == "cashahuacra")
        row["collector_effect_state"] = "HYDROLOGICALLY_CONNECTED"
        with self.assertRaises(mod.StaticCouplingError):
            mod.validate_v2(v2, self.base, self.source)

    def test_map_nodes_are_exact_points_only(self):
        nodes = copy.deepcopy(self.nodes)
        feature = next(x for x in nodes["features"] if x["properties"]["unit_id"] == "quirio_rimac_d8_intersection")
        feature["geometry"]["coordinates"][0] += 0.001
        with self.assertRaises(mod.StaticCouplingError):
            mod.validate_nodes(nodes, self.source)

    def test_map_catalog_exposes_separate_grey_research_component(self):
        catalog = map_mod.build_catalog()
        layers = {x["layer_id"]: x for x in catalog.get("research_component_layers") or []}
        layer = layers["rimac_static_coupling_nodes_v0_1"]
        self.assertTrue(layer["map_eligible"])
        self.assertFalse(layer["default_visibility"])
        self.assertFalse(layer["carries_risk_classification"])
        self.assertFalse(layer["carries_alert_values"])
        self.assertEqual(layer["style"]["color"], "#64748b")
        self.assertEqual(layer["source_metadata"]["geometry_types"], ["Point"])


if __name__ == "__main__":
    unittest.main()
