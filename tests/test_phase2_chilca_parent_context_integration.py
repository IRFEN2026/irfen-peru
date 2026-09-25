import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "site/data/validation/phase2_zone_contracts/lima_sur_chilca_pucusana.json"
GEOMETRY = ROOT / "site/data/phase2/geometries/lima_sur_chilca_pucusana_chilca_basin_context.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/lima_sur_chilca_pucusana_geometry_validation.json"
SNAPSHOT = ROOT / "site/data/phase2/sources/chilca_pucusana_hydrologic_context/ana_cuenca_chilca_1375532.geojson"
SOURCE_INVENTORY = ROOT / "site/data/phase2/sources/chilca_pucusana_hydrologic_context/source_inventory.json"
MAP = ROOT / "site/data/map_layers.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class ChilcaParentContextIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = load(CONTRACT)
        cls.geometry = load(GEOMETRY)
        cls.validation = load(VALIDATION)
        cls.snapshot = load(SNAPSHOT)
        cls.source_inventory = load(SOURCE_INVENTORY)
        cls.map = load(MAP)

    def test_strict_phase2_guards_remain_fail_closed(self):
        expected = {
            "deployment_status": "RESEARCH_ONLY",
            "test_mode": "TEST_ONLY",
            "production_use": False,
            "production_ready": False,
            "operational_alerting_enabled": False,
            "activation_gate": "BLOCKED",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "decision_thresholds": None,
            "hydraulic_factors": None,
        }
        for key, value in expected.items():
            self.assertEqual(self.contract[key], value)
            self.assertEqual(self.validation[key], value)
            self.assertEqual(self.source_inventory[key], value)

    def test_parent_context_does_not_promote_candidate_or_children(self):
        parent = self.contract["assets"]["parent_context_geometry"]
        self.assertEqual(parent["role"], "PARENT_HYDROLOGIC_CONTEXT_ONLY_NON_ACTIVATABLE")
        self.assertFalse(parent["counts_as_complete_candidate_geometry"])
        self.assertFalse(parent["counts_as_child_geometry"])
        self.assertFalse(parent["counts_as_event_footprint"])
        self.assertFalse(parent["parent_activation_eligible"])
        self.assertFalse(parent["candidate_wide_sampling_ready"])
        self.assertFalse(parent["approximate_geometry_used"])
        self.assertFalse(parent["synthetic_union_used"])
        self.assertEqual(self.contract["assets"]["geometry"]["status"], "MISSING")
        self.assertIsNone(self.contract["hierarchy_binding"]["parent_activation_state"])
        self.assertFalse(self.contract["hierarchy_binding"]["child_evidence_promotes_parent_activation"])
        for unit in self.contract["local_units"]:
            self.assertIsNone(unit["activation_state"])

    def test_exact_ana_parent_geometry_and_snapshot_hashes_are_frozen(self):
        parent = self.contract["assets"]["parent_context_geometry"]
        self.assertEqual(sha256(GEOMETRY), parent["sha256"])
        self.assertEqual(sha256(GEOMETRY), self.validation["normalized_geometry_sha256"])
        self.assertEqual(sha256(SNAPSHOT), parent["source_snapshot_sha256"])
        self.assertEqual(sha256(SNAPSHOT), self.validation["source_snapshot_sha256"])
        self.assertEqual(self.validation["official_unit"]["code"], "1375532")
        self.assertEqual(self.validation["official_unit"]["name"], "Cuenca Chilca")
        self.assertFalse(self.validation["counts_as_complete_candidate_geometry"])
        self.assertFalse(self.validation["artificial_connector_used"])

    def test_geometry_is_parent_context_not_event_or_activation_layer(self):
        props = self.geometry["properties"]
        self.assertEqual(props["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(props["test_mode"], "TEST_ONLY")
        self.assertFalse(props["production_use"])
        self.assertFalse(props["production_ready"])
        self.assertFalse(props["operational_alerting_enabled"])
        self.assertEqual(props["activation_gate"], "BLOCKED")
        feature = self.geometry["features"][0]["properties"]
        self.assertEqual(feature["feature_role"], "OFFICIAL_HYDROLOGIC_UNIT_RESEARCH_CONTEXT")
        self.assertEqual(feature["hydrologic_role"], "OFFICIAL_CHILCA_BASIN_BOUNDARY_NOT_COMPOSITE_CHILCA_PUCUSANA")
        self.assertFalse(feature["counts_as_complete_candidate_geometry"])
        self.assertFalse(feature["event_footprint_resolved"])
        self.assertFalse(feature["local_ravines_geometry_resolved"])
        self.assertFalse(feature["pucusana_identity_resolved"])
        self.assertIsNone(feature["outlet"])

    def test_map_keeps_candidate_unmapped_and_parent_context_grey(self):
        zone = next(row for row in self.map["research_zones"] if row["candidate_id"] == "lima_sur_chilca_pucusana")
        self.assertFalse(zone["geometry"]["map_eligible"])
        self.assertIsNone(zone["geometry"]["path"])
        layer = next(row for row in self.map["research_component_layers"] if row["layer_id"] == "lima_sur_chilca_parent_basin_context_1375532")
        self.assertEqual(layer["candidate_id"], "lima_sur_chilca_pucusana")
        self.assertEqual(layer["deployment_status"], "RESEARCH_ONLY")
        self.assertEqual(layer["activation_gate"], "BLOCKED")
        self.assertFalse(layer["production_use"])
        self.assertFalse(layer["production_ready"])
        self.assertFalse(layer["operational_alerting_enabled"])
        self.assertFalse(layer["default_visibility"])
        self.assertFalse(layer["counts_as_complete_candidate_geometry"])
        self.assertFalse(layer["candidate_wide_sampling_ready"])
        self.assertFalse(layer["loaded_into_operational_calculation"])
        self.assertFalse(layer["carries_alert_values"])
        self.assertFalse(layer["carries_risk_classification"])
        self.assertEqual(layer["style"]["color"], "#64748b")
        self.assertEqual(layer["source_metadata"]["sha256"], sha256(GEOMETRY))
        self.assertTrue(layer["source_metadata"]["research_only_guard"])

    def test_source_inventory_forbids_composite_or_operational_inference(self):
        forbidden = " ".join(self.source_inventory["forbidden"]).lower()
        self.assertIn("composite chilca-pucusana", forbidden)
        self.assertIn("event footprint", forbidden)
        self.assertIn("hydraulic capacity", forbidden)
        self.assertIn("negative controls", forbidden)
        self.assertIn("risk levels or alerts", forbidden)

if __name__ == "__main__":
    unittest.main()
