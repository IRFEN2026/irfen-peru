"""QHuay1 candidate package: exact ANA coordinate, guarded Point, withheld.

NEAR_CONFLUENCE only. The point is tied to the frozen source PDF once CI has
archived it; until then the package must say so explicitly.
"""
import importlib.util
import json
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "config/phase2_rimac_jicamarca_qhuay1_candidate_package_v0_1.json"
ANCHOR = ROOT / "config/phase2_ana_qhuay1_near_confluence_monitoring_anchor_v0_1.json"
CATALOG = ROOT / "site/data/map_layers.json"
RECON = ROOT / "config/phase2_rimac_jicamarca_map_semantic_reconciliation_v0_1.json"
ARCHIVE_MANIFEST = ROOT / "site/data/phase2/sources/rimac_jicamarca_v0_1/archive_manifest_v0_1.json"
GUARDS = {
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


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def utm18s_to_wgs84(easting, northing):
    """Krueger 4th-order inverse transverse Mercator, WGS84, zone 18 south."""
    a, f, k0 = 6378137.0, 1 / 298.257223563, 0.9996
    n = f / (2 - f)
    big_a = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64 + n ** 6 / 256)
    beta = [0, n / 2 - 2 * n ** 2 / 3 + 37 * n ** 3 / 96 - n ** 4 / 360,
            n ** 2 / 48 + n ** 3 / 15 - 437 * n ** 4 / 1440,
            17 * n ** 3 / 480 - 37 * n ** 4 / 840, 4397 * n ** 4 / 161280]
    delta = [0, 2 * n - 2 * n ** 2 / 3 - 2 * n ** 3 + 116 * n ** 4 / 45,
             7 * n ** 2 / 3 - 8 * n ** 3 / 5 - 227 * n ** 4 / 45,
             56 * n ** 3 / 15 - 136 * n ** 4 / 35, 4279 * n ** 4 / 630]
    xi = (northing - 10_000_000.0) / (k0 * big_a)
    eta = (easting - 500_000.0) / (k0 * big_a)
    xp = xi - sum(beta[j] * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j in range(1, 5))
    ep = eta - sum(beta[j] * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j in range(1, 5))
    chi = math.asin(math.sin(xp) / math.cosh(ep))
    lat = chi + sum(delta[j] * math.sin(2 * j * chi) for j in range(1, 5))
    lon = math.radians(18 * 6 - 183) + math.atan2(math.sinh(ep), math.cos(xp))
    return math.degrees(lon), math.degrees(lat)


class TestQhuay1CandidatePackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = load(PACKAGE)
        cls.anchor = load(ANCHOR)
        cls.point_doc = load(ROOT / cls.pkg["point_artifact"]["path"])

    def test_guards(self):
        for key, value in GUARDS.items():
            self.assertEqual(self.pkg[key], value, key)
        props = self.point_doc["properties"]
        for key in ("production_use", "production_ready", "operational_alerting_enabled"):
            self.assertIs(props[key], False, key)
        self.assertEqual(props["deployment_status"], "RESEARCH_ONLY")
        self.assertIs(props["map_eligible"], False)

    def test_point_is_the_exact_source_coordinate(self):
        features = self.point_doc["features"]
        self.assertEqual(len(features), 1)
        feature = features[0]
        self.assertEqual(feature["geometry"]["type"], "Point")
        props = feature["properties"]
        anchor = self.anchor["monitoring_anchor"]
        self.assertEqual((props["source_easting_m"], props["source_northing_m"]),
                         (anchor["easting_m"], anchor["northing_m"]))
        art = self.pkg["point_artifact"]
        self.assertEqual((art["source_easting_m"], art["source_northing_m"]), (287433, 8670443))
        self.assertEqual(art["offset_applied_m"], 0)
        self.assertIs(art["snapped"], False)
        lon, lat = utm18s_to_wgs84(art["source_easting_m"], art["source_northing_m"])
        self.assertAlmostEqual(lon, feature["geometry"]["coordinates"][0], places=7)
        self.assertAlmostEqual(lat, feature["geometry"]["coordinates"][1], places=7)
        self.assertEqual(feature["geometry"]["coordinates"], [art["wgs84_lon"], art["wgs84_lat"]])
        for key in ("production_use", "production_ready", "alerting_enabled", "loaded_into_operational_calculation",
                    "carries_alert_values", "carries_risk_classification", "is_flow_gauge", "is_stage_gauge",
                    "is_outlet", "is_exact_confluence", "may_be_labeled_exact_confluence"):
            self.assertIs(props[key], False, key)

    @unittest.skipUnless(importlib.util.find_spec("pyproj"), "pyproj not installed")
    def test_transform_matches_pyproj(self):
        from pyproj import Transformer
        lon, lat = Transformer.from_crs("EPSG:32718", "EPSG:4326", always_xy=True).transform(287433, 8670443)
        coords = self.point_doc["features"][0]["geometry"]["coordinates"]
        self.assertLess(abs(lon - coords[0]), 1e-7)
        self.assertLess(abs(lat - coords[1]), 1e-7)

    def test_semantics_never_exact_official(self):
        self.assertEqual(self.pkg["node_semantics"]["candidate"], "NEAR_CONFLUENCE")
        self.assertIs(self.pkg["node_semantics"]["exact_official"], False)
        self.assertIs(self.pkg["node_semantics"]["may_be_labeled_exact_confluence"], False)
        for key, value in self.pkg["observation_semantics"].items():
            if key != "station_role":
                self.assertIs(value, False, key)

    def test_withheld_in_committed_catalog(self):
        sem = load(CATALOG)["map_semantics"]
        self.assertNotIn("qhuay1_near_confluence_anchor", {r["entity_id"] for r in sem["features"]})
        withheld = {r["entity_id"]: r for r in sem["withheld_repository_geometries"]}
        row = withheld["qhuay1_near_confluence_anchor"]
        self.assertEqual(row["type"], "NODE")
        self.assertIs(row["map_eligible"], False)
        self.assertIs(row["research_only_guard"], True)
        self.assertIn("NEAR_CONFLUENCE", row["reason_if_withheld"])
        self.assertIn("EXACT_OFFICIAL", row["reason_if_withheld"])
        self.assertIs(self.pkg["map"]["map_eligible_today"], False)

    def test_pdf_hash_and_verification_are_consistent_with_archive(self):
        pdf = self.pkg["source_pdf"]
        verification = self.pkg["coordinate_verification"]
        record = None
        if ARCHIVE_MANIFEST.is_file():
            record = load(ARCHIVE_MANIFEST)["groups"].get(pdf["archive_group_id"])
        frozen = record is not None and record["status"] == "FROZEN"
        if pdf["sha256"] is None:
            self.assertEqual(pdf["sha256_status"], "PENDING_CI_FREEZE")
            self.assertEqual(verification["status"], "PENDING_FROZEN_PDF_TEXT_CHECK")
            return
        self.assertTrue(frozen, "package pins a PDF hash the archive does not hold")
        self.assertEqual(pdf["sha256"], record["sha256"])
        self.assertEqual(pdf["sha256_status"], "FROZEN_IN_SOURCE_ARCHIVE")
        if verification["status"] == "VERIFIED_IN_FROZEN_PDF":
            text = verification["verified_text"]
            self.assertRegex(text, r"QHuay\s*1|QHUAY\s*1")
            self.assertRegex(re.sub(r"[\s.,]", "", text), r"287433")
            self.assertRegex(re.sub(r"[\s.,]", "", text), r"8670443")
            self.assertIsInstance(verification["verified_page"], int)

    def test_reconciliation_points_at_package(self):
        recon = load(RECON)
        row = next(r for r in recon["line_elements"] if r["element_id"] == "qhuay1_near_confluence_anchor")
        self.assertEqual(row["candidate_package"], "config/phase2_rimac_jicamarca_qhuay1_candidate_package_v0_1.json")
        self.assertIs(row["map_eligible_today"], False)
        self.assertEqual(row["node_semantics"], "NEAR_CONFLUENCE")


if __name__ == "__main__":
    unittest.main()
