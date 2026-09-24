from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_map_layer_catalog as catalog_builder


class JicamarcaMapCatalogTests(unittest.TestCase):
    def setUp(self):
        catalog = catalog_builder.build_catalog()
        self.units = {
            row["discovery_id"]: row
            for row in catalog["research_discovery_units"]
        }
        self.parent_id = "lima_este_jicamarca_huaycoloro_rioseco_canto_grande"

    def test_parent_is_context_only_and_never_mapped_as_synthetic_ravine(self):
        parent = self.units[self.parent_id]
        self.assertEqual(parent["entity_role"], "CONTEXT_CONTAINER_NON_ACTIVATABLE")
        self.assertFalse(parent["geometry"]["map_eligible"])
        self.assertIsNone(parent["geometry"]["path"])
        self.assertNotEqual(parent["system_name"], "Quebrada Jicamarca")
        self.assertEqual(parent["activation_gate"], "BLOCKED")
        self.assertFalse(parent["production_use"])
        self.assertFalse(parent["production_ready"])
        self.assertFalse(parent["operational_alerting_enabled"])
        self.assertEqual(parent["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
        self.assertIsNone(parent["decision_thresholds"])
        self.assertIsNone(parent["hydraulic_factors"])

    def test_canto_grande_and_media_luna_publish_as_separate_channel_lines(self):
        expected = {
            "canto_grande_channel": "jicamarca_canto_grande_igp_channel.geojson",
            "media_luna_channel": "jicamarca_media_luna_igp_channel.geojson",
        }
        paths = set()
        for component_id, filename in expected.items():
            row = self.units[f"{self.parent_id}__{component_id}"]
            self.assertEqual(row["parent_discovery_id"], self.parent_id)
            self.assertEqual(row["hydrologic_child_id"], "canto_grande_media_luna")
            self.assertEqual(row["entity_role"], "DISCOVERY_LOCAL_CHANNEL_CONTEXT")
            self.assertEqual(row["activation_gate"], "BLOCKED")
            self.assertEqual(row["missing_data_rule"], "UNKNOWN_NOT_LOW_RISK")
            self.assertIsNone(row["decision_thresholds"])
            self.assertIsNone(row["hydraulic_factors"])
            self.assertFalse(row["production_use"])
            self.assertFalse(row["production_ready"])
            self.assertFalse(row["operational_alerting_enabled"])
            self.assertEqual(row["outlet_status"], "MISSING_PENDING_REPRODUCIBLE_OUTLET")
            self.assertEqual(
                row["catchment_geometry_status"],
                "MISSING_PENDING_REPRODUCIBLE_CATCHMENT_POLYGON",
            )
            self.assertTrue(row["routing_status"].startswith("BLOCKED_"))
            geometry = row["geometry"]
            self.assertTrue(geometry["map_eligible"])
            self.assertTrue(geometry["path"].endswith(filename))
            self.assertTrue(geometry["source_metadata"]["research_only_guard"])
            self.assertTrue(
                set(geometry["source_metadata"]["geometry_types"]).issubset(
                    {"LineString", "MultiLineString"}
                )
            )
            self.assertIn("no es polígono de drenaje", geometry["map_disclaimer"])
            paths.add(geometry["path"])
        self.assertEqual(len(paths), 2)

    def test_rejected_rio_seco_and_unresolved_named_jicamarca_are_not_drawn(self):
        forbidden_tokens = ("rio_seco_channel_candidate", "jicamarca_named_channel")
        published_ids = set(self.units)
        for token in forbidden_tokens:
            self.assertFalse(any(token in discovery_id for discovery_id in published_ids))
        jicamarca_rows = [
            row for discovery_id, row in self.units.items()
            if discovery_id.startswith(self.parent_id)
        ]
        for row in jicamarca_rows:
            path = (row.get("geometry") or {}).get("path") or ""
            self.assertNotIn("rio_seco", path.lower())

    def test_channel_lines_do_not_create_outlets_routing_or_event_footprints(self):
        for component_id in ("canto_grande_channel", "media_luna_channel"):
            row = self.units[f"{self.parent_id}__{component_id}"]
            self.assertEqual(row["outlet_status"], "MISSING_PENDING_REPRODUCIBLE_OUTLET")
            self.assertTrue(row["routing_status"].startswith("BLOCKED_"))
            self.assertIn("CHANNEL_LINE_NOT_CATCHMENT_OR_OUTLET", row["geometry"]["representation"])
            self.assertNotIn("footprint", row["geometry"]["representation"].lower())


if __name__ == "__main__":
    unittest.main()
