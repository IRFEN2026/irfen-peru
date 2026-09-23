import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_map_layer_catalog as catalog_builder


class DiscoveryMapComponentTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog_builder.build_catalog()
        self.units = {
            row["discovery_id"]: row
            for row in self.catalog["research_discovery_units"]
        }

    def test_huarmey_culebras_parent_remains_unmapped_grouper(self):
        parent = self.units["ancash_huarmey_culebras"]
        self.assertFalse(parent["geometry"]["map_eligible"])
        self.assertIsNone(parent["geometry"]["path"])
        self.assertEqual(
            parent["geometry"]["status"],
            "MISSING_NO_REPRODUCIBLE_GEOMETRY",
        )

    def test_huarmey_and_culebras_are_separate_research_only_children(self):
        expected = {
            "ancash_huarmey_culebras__huarmey": ("137594", "Cuenca Huarmey"),
            "ancash_huarmey_culebras__culebras": ("1375952", "Cuenca Culebras"),
        }
        paths = set()
        for discovery_id, (code, name) in expected.items():
            row = self.units[discovery_id]
            self.assertEqual(row["parent_discovery_id"], "ancash_huarmey_culebras")
            self.assertEqual(row["system_name"], name)
            self.assertEqual(row["hydrologic_identity"]["ana_unit_code"], code)
            self.assertEqual(row["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(row["test_mode"], "TEST_ONLY")
            self.assertFalse(row["production_use"])
            self.assertFalse(row["production_ready"])
            self.assertFalse(row["operational_alerting_enabled"])
            self.assertEqual(row["activation_gate"], "BLOCKED")
            self.assertEqual(row["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(row["decision_thresholds"])
            self.assertIsNone(row["hydraulic_factors"])
            geometry = row["geometry"]
            self.assertTrue(geometry["map_eligible"])
            self.assertTrue(geometry["source_metadata"]["research_only_guard"])
            self.assertTrue(geometry["path"].startswith("site/data/phase2/geometries/"))
            self.assertNotIn("..", Path(geometry["path"]).parts)
            paths.add(geometry["path"])
        self.assertEqual(len(paths), 2)

    def test_catalog_guardrails_forbid_discovery_composite(self):
        guardrails = self.catalog["guardrails"]
        self.assertTrue(guardrails["discovery_child_geometries_remain_separate"])
        self.assertTrue(guardrails["discovery_parent_composite_geometry_forbidden"])
        summary = self.catalog["summary"]
        self.assertGreaterEqual(summary["research_discovery_child_units_registered"], 2)
        self.assertEqual(
            summary["research_discovery_units_registered"],
            summary["research_discovery_parent_units_registered"]
            + summary["research_discovery_child_units_registered"],
        )


if __name__ == "__main__":
    unittest.main()
