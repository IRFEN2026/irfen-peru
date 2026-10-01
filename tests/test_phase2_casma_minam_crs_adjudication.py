"""Regression guard for the Casma MINAM native-CRS adjudication (PR #344).

Recomputes, without third-party dependencies, that the 4326 vertex returned
when outSR is omitted is the WGS84 / UTM zone 18S inverse projection of the
32718 vertex returned with outSR=32718, and pins that the mechanism requests
the declared storage CRS and never accepts the map SR as native.
"""
import hashlib
import importlib.util
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADJ = ROOT / "site/data/phase2/source_assessments/casma_minam_crs_adjudication_v0_1.json"
CONTRACT = ROOT / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"
GATES = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"
SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"


def utm18s_inverse(easting, northing):
    """WGS84 UTM zone 18S -> (lon, lat) degrees, Krueger 6th-order series."""
    a = 6378137.0
    f = 1 / 298.257223563
    n = f / (2 - f)
    k0, lon0, fe, fn = 0.9996, math.radians(-75.0), 500000.0, 10000000.0
    big_a = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64 + n**6 / 256)
    beta = [
        None,
        n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96 - n**4 / 360 - 81 * n**5 / 512 + 96199 * n**6 / 604800,
        n**2 / 48 + n**3 / 15 - 437 * n**4 / 1440 + 46 * n**5 / 105 - 1118711 * n**6 / 3870720,
        17 * n**3 / 480 - 37 * n**4 / 840 - 209 * n**5 / 4480 + 5569 * n**6 / 90720,
        4397 * n**4 / 161280 - 11 * n**5 / 504 - 830251 * n**6 / 7257600,
        4583 * n**5 / 161280 - 108847 * n**6 / 3991680,
        20648693 * n**6 / 638668800,
    ]
    xi = (northing - fn) / (k0 * big_a)
    eta = (easting - fe) / (k0 * big_a)
    xp = xi - sum(beta[j] * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j in range(1, 7))
    ep = eta - sum(beta[j] * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j in range(1, 7))
    chi = math.asin(math.sin(xp) / math.cosh(ep))
    e = math.sqrt(f * (2 - f))
    t = math.tan(chi)
    tau = t
    for _ in range(20):
        s = math.sinh(e * math.atanh(e * tau / math.sqrt(1 + tau**2)))
        tp = tau * math.sqrt(1 + s**2) - s * math.sqrt(1 + tau**2)
        tau += (t - tp) / (math.sqrt(1 + tp**2) * math.sqrt(1 + tau**2)) * (
            1 + (1 - e**2) * tau**2
        ) / ((1 - e**2) * math.sqrt(1 + tau**2))
    return math.degrees(lon0 + math.atan2(math.sinh(ep), math.cos(xp))), math.degrees(math.atan(tau))


class CasmaMinamCrsAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.adj = json.loads(ADJ.read_text(encoding="utf-8"))
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_fail_closed_guards(self):
        for key, value in {
            "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY",
            "production_use": False, "production_ready": False,
            "operational_alerting_enabled": False, "activation_gate": "BLOCKED",
            "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
            "decision_thresholds": None, "hydraulic_factors": None,
        }.items():
            self.assertEqual(self.adj[key], value, key)

    def test_storage_crs_matches_contract_and_map_sr_is_not_native(self):
        meta = self.adj["frozen_metadata_evidence"]
        expected = self.contract["source"]["expected_source_wkid"]
        self.assertEqual(meta["source_spatial_reference"]["wkid"], expected)
        self.assertEqual(meta["extent_spatial_reference"]["wkid"], 4326)
        self.assertNotEqual(meta["extent_spatial_reference"]["wkid"], expected)
        self.assertEqual(self.adj["live_observations_not_byte_frozen"]["mapserver_spatial_reference"]["wkid"], 4326)
        findings = self.adj["findings"]
        self.assertEqual(findings["storage_crs_per_official_metadata"], expected)
        self.assertFalse(findings["wkid_4326_accepted_as_native"])
        self.assertTrue(findings["omitting_outSR_returns_map_sr_4326"])

    def test_map_sr_vertex_is_exact_projection_of_storage_vertex(self):
        variants = self.adj["query_variants_code_1375961"]
        native = [v for v in variants if v.get("outSR") == 32718 and v["f"] == "json"][0]
        mapped = [v for v in variants if v.get("outSR") is None and v["f"] == "json"][0]
        self.assertEqual(native["returned_sr"], 32718)
        self.assertEqual(mapped["returned_sr"], 4326)
        lon, lat = utm18s_inverse(*native["first_vertex"])
        d_east_m = (lon - mapped["first_vertex"][0]) * 111320 * math.cos(math.radians(lat))
        d_north_m = (lat - mapped["first_vertex"][1]) * 110574
        self.assertLess(abs(d_east_m), 0.001)
        self.assertLess(abs(d_north_m), 0.001)
        for v in variants:
            self.assertEqual(v["first_vertex"], native["first_vertex"] if v.get("outSR") == 32718 else mapped["first_vertex"])

    def test_adjudication_matches_frozen_metadata_bytes(self):
        meta = self.adj["frozen_metadata_evidence"]
        path = ROOT / meta["path"]
        if not path.is_file():
            self.skipTest("Gate A capture not present in this checkout")
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta["sha256"])
        doc = json.loads(raw)
        self.assertEqual(doc["sourceSpatialReference"], meta["source_spatial_reference"])
        self.assertEqual(doc["extent"]["spatialReference"], meta["extent_spatial_reference"])
        self.assertEqual("spatialReference" in doc, meta["top_level_spatial_reference_present"])
        self.assertEqual(doc["currentVersion"], meta["current_version"])
        self.assertEqual(doc["supportsDatumTransformation"], meta["supports_datum_transformation"])

    def test_frozen_native_capture_is_storage_crs_and_projects_to_geojson(self):
        manifest_path = ROOT / "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json"
        if not manifest_path.is_file():
            self.skipTest("Gate A capture not present in this checkout")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["crs_provenance"]["native_request_outSR"], 32718)
        self.assertFalse(manifest["crs_provenance"]["map_spatial_reference_accepted_as_native"])
        checked = 0
        for row in manifest["features"]:
            native = json.loads((ROOT / row["native_archive_path"]).read_bytes())
            self.assertEqual(native["spatialReference"]["wkid"], 32718, row["code"])
            geo = json.loads((ROOT / row["raw_archive_path"]).read_bytes())["features"][0]["geometry"]
            polys = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
            observed = sorted((round(x, 9), round(y, 9)) for poly in polys for ring in poly for x, y in ring)
            pts = [p for ring in native["features"][0]["geometry"]["rings"] for p in ring]
            projected = sorted((round(lon, 9), round(lat, 9)) for lon, lat in (utm18s_inverse(x, y) for x, y in pts))
            self.assertEqual(projected, observed, row["code"])
            checked += len(pts)
        self.assertEqual(checked, self.adj["frozen_capture_confirmation"]["native_vertices_checked"])

    def test_mechanism_requests_storage_crs_and_gates_are_untouched(self):
        spec = importlib.util.spec_from_file_location("casma_crs_mechanism", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        url = module.native_query_url(self.contract, "1375961", 32718)
        self.assertIn("outSR=32718", url)
        self.assertNotIn("datumTransformation", url)
        with self.assertRaises(module.RecoveryError):
            module.native_query_url(self.contract, "1375961", 4326)
        adjust = self.adj["mechanism_adjustment"]
        self.assertFalse(adjust["gate_a_relaxed"])
        self.assertFalse(adjust["gate_b_modified"])
        self.assertFalse(adjust["geometry_promoted"])
        gates = json.loads(GATES.read_text(encoding="utf-8"))
        self.assertEqual(gates["gate_b_lineage_equivalence"]["current_status"], "NOT_ESTABLISHED")
        self.assertFalse(gates["gate_b_lineage_equivalence"]["historical_geometry_equivalence_to_Uh_pfas100"])


if __name__ == "__main__":
    unittest.main()
