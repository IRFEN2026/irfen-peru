import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "lambayeque_hydrology", ROOT / "scripts" / "build_lambayeque_hydrologic_units.py"
)
hydrology = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(hydrology)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LambayequeHydrologicMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = load(hydrology.INVENTORY_V2)
        cls.validation = load(hydrology.VALIDATION)
        cls.children = {
            child["candidate_id"]: child
            for child in cls.inventory["hydrologic_child_units"]
        }
        cls.contracts = {
            path.stem: load(path)
            for path in hydrology.CONTRACT_DIR.glob("*.json")
        }
        cls.geometries = {
            candidate_id: load(ROOT / child["geometry_path"])
            for candidate_id, child in cls.children.items()
        }

    def test_identity_and_versioned_count_contract(self):
        self.assertEqual(self.inventory["version"], "phase-2-candidate-inventory-v0.2")
        self.assertEqual(len(self.inventory["candidates"]), 18)
        self.assertEqual(set(self.children), {
            "lambayeque_chancay_lambayeque_chongoyape",
            "lambayeque_zana_oyotun",
        })
        migration = self.inventory["migration"]
        self.assertEqual(migration["legacy_registered_candidate_count_before"], 18)
        self.assertEqual(migration["legacy_registered_candidate_count_after"], 18)
        self.assertFalse(migration["children_counted_as_additional_phase2_candidates"])
        self.assertEqual(migration["operational_candidate_count"], 0)
        parent = next(
            row for row in self.inventory["candidates"]
            if row["candidate_id"] == migration["legacy_candidate_id"]
        )
        self.assertEqual(parent["entity_role"], "HISTORICAL_NON_ACTIVABLE_GROUPER")
        self.assertEqual(parent["geometry_policy"], "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR")
        self.assertEqual(set(parent["hydrologic_children"]), set(self.children))

    def test_official_identity_codes_are_distinct(self):
        expected = {
            "lambayeque_chancay_lambayeque_chongoyape": ("Chancay-Lambayeque", "13776"),
            "lambayeque_zana_oyotun": ("Zaña", "137754"),
        }
        observed = {
            cid: (child["hydrologic_system"], child["official_hydrologic_unit_code"])
            for cid, child in self.children.items()
        }
        self.assertEqual(observed, expected)
        self.assertEqual(len({code for _, code in observed.values()}), 2)

    def test_geometry_crs_validity_and_hashes(self):
        validation_by_id = {row["candidate_id"]: row for row in self.validation["units"]}
        for cid, collection in self.geometries.items():
            self.assertEqual(collection["properties"]["crs"], "EPSG:4326")
            self.assertFalse(collection["properties"]["production_use"])
            self.assertFalse(collection["properties"]["default_visibility"])
            self.assertEqual(collection["properties"]["activation_gate"], "BLOCKED")
            self.assertEqual(len(collection["features"]), 1)
            feature = collection["features"][0]
            geom = shape(feature["geometry"])
            self.assertTrue(geom.is_valid)
            self.assertFalse(geom.is_empty)
            self.assertEqual(geom.geom_type, "Polygon")
            self.assertFalse(feature["properties"]["district_boundary_used"])
            self.assertFalse(feature["properties"]["dem_used"])
            self.assertIsNone(feature["properties"]["outlet"])
            row = validation_by_id[cid]
            self.assertEqual(digest(ROOT / row["output_path"]), row["output_sha256"])
            self.assertLess(row["area_relative_difference_pct"], 1.0)

    def test_topology_has_no_overlap_or_artificial_link(self):
        to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32717", always_xy=True).transform
        polygons = [
            transform(to_utm, shape(collection["features"][0]["geometry"]))
            for collection in self.geometries.values()
        ]
        intersection = polygons[0].intersection(polygons[1])
        self.assertAlmostEqual(intersection.area, 0.0, places=2)
        self.assertFalse(polygons[0].overlaps(polygons[1]))
        self.assertTrue(polygons[0].touches(polygons[1]))
        self.assertGreater(intersection.length, 100_000)
        separation = self.validation["separation"]
        self.assertFalse(separation["interior_overlap"])
        self.assertFalse(separation["artificial_link_created"])
        self.assertFalse(self.validation["artificial_connector_used"])

    def test_outlet_and_d8_are_explicitly_not_applicable_without_dem(self):
        self.assertFalse(self.validation["dem_used"])
        self.assertFalse(self.validation["d8_topology_applicable"])
        for contract in self.contracts.values():
            self.assertFalse(contract["geometry"]["dem_used"])
            self.assertFalse(contract["geometry"]["artificial_connector_used"])
            self.assertFalse(contract["outlet"]["used"])
            self.assertFalse(contract["outlet"]["required"])
            self.assertIsNone(contract["outlet"]["coordinates"])

    def test_source_inventory_locks_every_download(self):
        inventory = load(hydrology.SOURCE_INVENTORY)
        self.assertFalse(inventory["private_sources_as_primary_evidence"])
        self.assertGreaterEqual(len(inventory["sources"]), 10)
        for source in inventory["sources"]:
            self.assertTrue(str(source["url"]).startswith("https://"))
            self.assertTrue(source["source_id"])
            self.assertRegex(source["retrieved_at"], r"^2026-08-(20|21)T")
            self.assertGreater(source["size_bytes"], 0)
            self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
            self.assertIn("OFFICIAL", source["evidence_tier"])
            if source["local_path"]:
                path = ROOT / source["local_path"]
                self.assertEqual(path.stat().st_size, source["size_bytes"])
                self.assertEqual(digest(path), source["sha256"])
        self.assertTrue(all(not source["used_as_primary_evidence"]
                            for source in inventory["discovery_only_sources"]))

    def test_critical_reaches_are_lines_not_basin_boundaries(self):
        reaches = load(hydrology.REACHES_OUT)
        self.assertEqual(len(reaches["features"]), 14)
        self.assertFalse(reaches["properties"]["production_use"])
        self.assertFalse(reaches["properties"]["default_visibility"])
        self.assertEqual(reaches["properties"]["activation_gate"], "BLOCKED")
        for feature in reaches["features"]:
            self.assertEqual(shape(feature["geometry"]).geom_type, "LineString")
            self.assertFalse(feature["properties"]["is_basin_boundary"])
            self.assertFalse(feature["properties"]["is_channel_centerline"])
            self.assertFalse(feature["properties"]["is_inundation_extent"])
            self.assertEqual(feature["properties"]["review_status"], "REVIEW_ONLY")
            self.assertEqual(feature["properties"]["activation_gate"], "BLOCKED")
        self.assertTrue(self.validation["critical_reaches"]["all_inside_assigned_ana_unit"])
        self.assertLess(self.validation["critical_reaches"]["max_crs_roundtrip_error_m"], 0.01)

    def test_child_contracts_are_fail_closed(self):
        self.assertEqual(set(self.contracts), set(self.children))
        for cid, contract in self.contracts.items():
            self.assertEqual(contract["candidate_id"], cid)
            self.assertEqual(contract["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(contract["review_status"], "REVIEW_ONLY")
            self.assertFalse(contract["production_use"])
            self.assertFalse(contract["production_ready"])
            self.assertFalse(contract["operational_alerting_enabled"])
            self.assertIsNone(contract["decision_thresholds"])
            self.assertIsNone(contract["hydraulic_factors"])
            self.assertEqual(contract["validation"]["activation_gate"], "BLOCKED")
            self.assertFalse(contract["validation"]["promotion_allowed"])
            self.assertFalse(contract["validation"]["counts_as_operational_candidate"])

    def test_general_map_does_not_include_new_units(self):
        map_catalog = load(ROOT / "site/data/map_layers.json")
        encoded = json.dumps(map_catalog, ensure_ascii=False)
        for cid in self.children:
            self.assertNotIn(cid, encoded)

    def test_builder_reproduces_committed_outputs(self):
        before = {
            path: digest(path)
            for path in [
                hydrology.INVENTORY_V2,
                hydrology.SOURCE_INVENTORY,
                hydrology.VALIDATION,
                hydrology.REACHES_OUT,
                *[ROOT / child["geometry_path"] for child in self.children.values()],
                *hydrology.CONTRACT_DIR.glob("*.json"),
            ]
        }
        hydrology.build_outputs()
        self.assertEqual(before, {path: digest(path) for path in before})


if __name__ == "__main__":
    unittest.main()
