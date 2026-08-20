import importlib.util
import json
from pathlib import Path
import unittest

from shapely.geometry import Point, shape


ROOT = Path(__file__).resolve().parents[1]
GEOJSON = ROOT / "site/data/phase2/geometries/w1_santa_eulalia_rimac.geojson"
VALIDATION = ROOT / "site/data/phase2/geometries/w1_santa_eulalia_rimac_validation.json"
SNAPSHOT = ROOT / "site/data/phase2/sources/w1_santa_eulalia_rimac_source_snapshot.json"
SPEC = importlib.util.spec_from_file_location(
    "w1_geometry", ROOT / "scripts/build_w1_santa_eulalia_rimac.py"
)
w1 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(w1)

EXPECTED_RIMAC_2022_POINTS = [
    ("MI-185", 302884.3486, 8674552.054),
    ("MI-185-A", 302925.8088, 8674563.498),
    ("MI-185-B", 302973.9473, 8674565.606),
    ("MI-204", 306937.1071, 8675632.580),
    ("MI-205", 307039.1380, 8675614.107),
    ("MI-208", 307471.1743, 8675775.057),
    ("MI-208-A", 307515.3496, 8675795.065),
    ("MI-209", 307689.8613, 8675834.833),
    ("MI-210", 307784.0087, 8675850.531),
    ("MI-212", 308265.6149, 8675998.591),
    ("MI-213", 308492.5317, 8676005.705),
    ("MI-214", 308670.7782, 8676006.863),
    ("MI-215", 308794.2942, 8676012.699),
    ("MI-215-A", 308882.3438, 8676048.163),
    ("MI-216", 308938.6247, 8676078.572),
    ("MI-218", 309174.4945, 8676169.131),
    ("MI-219", 309264.7498, 8676224.805),
    ("MI-220", 309352.3417, 8676261.003),
    ("MI-220-A", 309413.4058, 8676278.228),
    ("MI-221", 309502.0385, 8676298.901),
]


class W1SantaEulaliaRimacTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(GEOJSON.read_text(encoding="utf-8"))
        cls.validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
        cls.snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.features = {f["properties"]["unit_id"]: f for f in cls.data["features"]}

    def test_units_are_separate_and_complete(self):
        self.assertEqual(set(self.features), {
            "cashahuacra", "shingolay", "santa_eulalia_faja_2004",
            "rimac_faja_2020", "rimac_left_margin_update_2022",
        })
        self.assertTrue(self.data["properties"]["units_are_separate"])

    def test_every_feature_is_fail_closed_and_hashed(self):
        for feature in self.features.values():
            props = feature["properties"]
            self.assertEqual(props["deployment_status"], "RESEARCH_ONLY")
            self.assertEqual(props["candidate_status"], "REVIEW_ONLY")
            self.assertFalse(props["production_use"])
            self.assertFalse(props["production_ready"])
            self.assertFalse(props["alerting_enabled"])
            self.assertIsNone(props["decision_thresholds"])
            self.assertFalse(props["loaded_into_operational_calculation"])
            self.assertFalse(props["carries_alert_values"])
            self.assertFalse(props["carries_risk_classification"])
            self.assertEqual(props["geometry_sha256"], w1.geometry_hash(shape(feature["geometry"])))

    def test_local_catchments_have_distinct_outlets_and_no_overlap(self):
        cash = self.features["cashahuacra"]
        shing = self.features["shingolay"]
        cash_geom, shing_geom = shape(cash["geometry"]), shape(shing["geometry"])
        self.assertTrue(cash_geom.is_valid)
        self.assertTrue(shing_geom.is_valid)
        cash_outlet = cash["properties"]["outlet"]
        shing_outlet = shing["properties"]["outlet"]
        self.assertTrue(cash_geom.covers(Point(cash_outlet["lon"], cash_outlet["lat"])))
        self.assertTrue(shing_geom.covers(Point(shing_outlet["lon"], shing_outlet["lat"])))
        self.assertNotEqual(cash["properties"]["outlet"], shing["properties"]["outlet"])
        self.assertLessEqual(cash_geom.intersection(shing_geom).area, 1e-12)
        self.assertEqual(cash["properties"]["confidence"], "MEDIUM_CANDIDATE")
        self.assertEqual(shing["properties"]["confidence"], "LOW_CANDIDATE")
        self.assertEqual(shing["properties"]["candidate_status"], "REVIEW_ONLY")

    def test_local_areas_are_dem_catchments_not_orthomosaic_coverage(self):
        expected_areas = {"cashahuacra": 15.088, "shingolay": 0.243}
        for unit_id, expected_area in expected_areas.items():
            coverage = self.features[unit_id]["properties"]["coverage"]
            self.assertEqual(coverage["delineated_area_km2"], expected_area)
            self.assertEqual(
                coverage["area_semantics"],
                "DEM_DERIVED_D8_CATCHMENT_NOT_CENEPRED_ORTHOMOSAIC_COVERAGE",
            )
            self.assertFalse(coverage["is_official_watershed_area"])
            self.assertFalse(coverage["is_cenepred_orthomosaic_coverage_area"])
            self.assertFalse(coverage["cenepred_orthomosaic_area_used_as_catchment_area"])
            self.assertEqual(coverage["source_scope_role"], "OUTLET_SEARCH_ONLY_NOT_WATERSHED")
        self.assertFalse(self.features["shingolay"]["properties"]["outlet"]["official_confirmation"])
        shing_outlet = self.features["shingolay"]["properties"]["outlet"]
        shing_coverage = self.features["shingolay"]["properties"]["coverage"]
        self.assertEqual(shing_outlet["accumulation_cells"], 261)
        self.assertEqual(shing_outlet["accumulation_area_km2"], 0.243)
        self.assertEqual(shing_coverage["catchment_cells"], 261)
        self.assertEqual(shing_coverage["source_scope_area_km2"], 0.041892)

    def test_official_reaches_are_not_mislabeled_as_watersheds(self):
        for unit in ("santa_eulalia_faja_2004", "rimac_faja_2020"):
            props = self.features[unit]["properties"]
            self.assertEqual(props["hydrologic_role"], "official_river_faja_marginal")
            self.assertIsNone(props["outlet"])
            self.assertIn("no es cuenca", props["map_disclaimer"].lower())
        update = self.features["rimac_left_margin_update_2022"]
        self.assertEqual(update["geometry"]["type"], "MultiLineString")
        self.assertEqual(update["properties"]["coverage"]["official_points"], 20)

    def test_rimac_2022_exact_codes_and_official_coordinates(self):
        source_points = self.snapshot["sources"]["ANA-FM-RIMAC-13214"]["updated_left_bank_points"]
        actual = [(row["code"], row["easting_m"], row["northing_m"]) for row in source_points]
        self.assertEqual(actual, EXPECTED_RIMAC_2022_POINTS)
        update = self.features["rimac_left_margin_update_2022"]
        self.assertEqual(update["properties"]["point_codes"], [row[0] for row in EXPECTED_RIMAC_2022_POINTS])
        transformed = [w1.Transformer.from_crs(
            "EPSG:32718", "EPSG:4326", always_xy=True
        ).transform(east, north) for _, east, north in EXPECTED_RIMAC_2022_POINTS]
        self.assertEqual(update["geometry"]["coordinates"], [
            [list(coord) for coord in transformed[:3]],
            [list(coord) for coord in transformed[3:]],
        ])

    def test_rimac_2022_has_two_components_and_forbids_artificial_bridge(self):
        update = self.features["rimac_left_margin_update_2022"]
        self.assertEqual(update["properties"]["component_point_codes"], [
            ["MI-185", "MI-185-A", "MI-185-B"],
            [row[0] for row in EXPECTED_RIMAC_2022_POINTS[3:]],
        ])
        components = update["geometry"]["coordinates"]
        self.assertEqual([len(component) for component in components], [3, 17])
        forbidden = (tuple(components[0][-1]), tuple(components[1][0]))
        actual_segments = {
            (tuple(component[index]), tuple(component[index + 1]))
            for component in components
            for index in range(len(component) - 1)
        }
        self.assertNotIn(forbidden, actual_segments)
        coverage = update["properties"]["coverage"]
        self.assertEqual(coverage["components"], 2)
        self.assertEqual(coverage["main_markers"], 15)
        self.assertEqual(coverage["intermediate_markers"], 5)
        self.assertEqual(
            [(row["from"], row["to"]) for row in coverage["declared_progressive_ranges"]],
            [("39+950", "40+050"), ("44+200", "46+900")],
        )

    def test_rimac_2022_reconciles_document_typos_and_authority(self):
        reconciliation = self.features["rimac_left_margin_update_2022"]["properties"]["document_reconciliation"]
        self.assertEqual(reconciliation["main_markers"], 15)
        self.assertEqual(reconciliation["intermediate_markers"], 5)
        self.assertEqual(reconciliation["total_coordinate_rows"], 20)
        self.assertEqual(reconciliation["official_coordinate_table_page"], 5)
        self.assertEqual(reconciliation["cartographic_annex_page"], 7)
        self.assertEqual(reconciliation["documented_typographical_errors"], [
            {"printed": "MI-2016", "correct": "MI-216"},
            {"printed": "MI-2015-A", "correct": "MI-215-A"},
        ])
        self.assertIn("prevalecen", reconciliation["authoritative_precedence"])

    def test_topology_and_scientific_controls_pass_without_promotion(self):
        checks = self.validation["checks"]
        self.assertTrue(checks["all_geometries_valid"])
        self.assertTrue(checks["coordinates_within_peru_envelope"])
        self.assertTrue(checks["local_units_do_not_overlap"])
        self.assertTrue(checks["cashahuacra"]["downstream_reaches_santa_eulalia_faja"])
        self.assertTrue(checks["shingolay"]["downstream_reaches_santa_eulalia_faja"])
        self.assertEqual(checks["cashahuacra"]["topology_relative_cell_error_pct"], 0.0)
        self.assertEqual(checks["shingolay"]["topology_relative_cell_error_pct"], 0.0)
        self.assertEqual(self.validation["scientific_decision"], "REVIEW_ONLY_GEOMETRIES_MATERIALIZED")
        self.assertFalse(self.validation["production_ready"])
        self.assertTrue(checks["rimac_2022_official_coordinates_exact"])
        self.assertEqual(checks["rimac_2022_component_count"], 2)
        self.assertTrue(checks["rimac_2022_artificial_mi_185_b_to_mi_204_segment_absent"])

    def test_sources_and_dem_are_pinned(self):
        self.assertEqual(self.snapshot["dem"]["expected_sha256"], w1.DEM_SHA256)
        self.assertEqual(len(self.snapshot["dem"]["expected_sha256"]), 64)
        self.assertEqual(len(self.snapshot["sources"]["ANA-FM-RIMAC-13214"]["updated_left_bank_points"]), 20)
        for source_id in (
            "ANA-CASHAHUACRA-VULNERABLE-5769",
            "CENEPRED-RPAS-CASHAHUACRA-SHINGOLAY-5291",
            "ANA-FM-SANTA-EULALIA-6063", "ANA-FM-RIMAC-9803",
        ):
            self.assertEqual(len(self.snapshot["sources"][source_id]["wkt_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
