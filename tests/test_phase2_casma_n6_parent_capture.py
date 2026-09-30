"""Offline tests for the N6 parent capture (no network).

Before the capture exists they check the fail-closed validators and that a
failing refresh writes nothing; once the capture is committed they also verify
it offline.
"""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/capture_phase2_casma_n6_parent.py"


def load():
    spec = importlib.util.spec_from_file_location("casma_parent_capture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


M = load()
PREREG = M.load_prereg()


def response(code="137596", nivel6="137596", wkid=4326, n=1, closed=True, extra=None):
    ring = [[-78.0, -9.0], [-77.5, -9.0], [-77.5, -9.5], [-78.0, -9.0 if closed else -9.1]]
    feat = {"attributes": {"OBJECTID": 1, "CODIGO": code, "NIVEL6": nivel6, "NOMBRE": "Cuenca Casma"}, "geometry": {"rings": [ring]}}
    doc = {"spatialReference": {"wkid": wkid, "latestWkid": wkid}, "features": [feat] * n}
    doc.update(extra or {})
    return doc


def metadata(wkid=4326, geometry="esriGeometryPolygon", drop=None):
    fields = [{"name": f} for f in PREREG["source"]["query"]["outFields"].split(",") if f != drop]
    return {"currentVersion": 11.2, "name": "Unidades Hidrográficas", "geometryType": geometry,
            "sourceSpatialReference": {"wkid": wkid, "latestWkid": wkid},
            "extent": {"spatialReference": {"wkid": 102100, "latestWkid": 3857}}, "fields": fields}


class ParentCaptureValidationTests(unittest.TestCase):
    def test_query_requests_storage_crs_and_no_generalisation(self):
        url = M.query_url(PREREG)
        self.assertIn("outSR=4326", url)
        self.assertIn("CODIGO", url)
        self.assertIn("137596", url)
        self.assertIn("f=json", url)
        for forbidden in PREREG["source"]["forbidden_query_parameters"]:
            self.assertNotIn(forbidden, url)
        self.assertIn("idep.gob.pe", url)

    def test_valid_response_and_metadata(self):
        info = M.validate_response(PREREG, response())
        self.assertEqual(info["ring_count"], 1)
        meta = M.validate_metadata(PREREG, metadata())
        self.assertEqual(meta["layer_source_spatial_reference"]["wkid"], 4326)

    def test_fail_closed_cases(self):
        cases = [
            (response(wkid=102100), "PARENT_RESPONSE_WKID_DRIFT"),
            (response(n=2), "PARENT_FEATURE_COUNT"),
            (response(n=0), "PARENT_FEATURE_COUNT"),
            (response(code="1375961"), "PARENT_IDENTITY_MISMATCH"),
            (response(nivel6="137595"), "PARENT_IDENTITY_MISMATCH"),
            (response(closed=False), "PARENT_RING_NOT_CLOSED"),
            (response(extra={"exceededTransferLimit": True}), "PARENT_TRANSFER_LIMIT_EXCEEDED"),
            ({"error": {"code": 500}}, "PARENT_QUERY_SERVICE_ERROR"),
        ]
        for doc, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(M.ParentCaptureError, message):
                    M.validate_response(PREREG, doc)
        for meta, message in [
            (metadata(wkid=102100), "PARENT_SOURCE_WKID_DRIFT"),
            (metadata(geometry="esriGeometryPoint"), "PARENT_GEOMETRY_TYPE"),
            (metadata(drop="NIVEL6"), "PARENT_FIELDS_MISSING"),
        ]:
            with self.subTest(message=message):
                with self.assertRaisesRegex(M.ParentCaptureError, message):
                    M.validate_metadata(PREREG, meta)

    def test_failed_refresh_writes_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        saved = (M.ARCHIVE, M.MANIFEST, M.R.fetch_response)
        try:
            M.ARCHIVE = tmp / "archive"
            M.MANIFEST = tmp / "manifest.json"
            bodies = [json.dumps(metadata()).encode(), json.dumps(response(n=2)).encode()]
            M.R.fetch_response = lambda url, accept, max_bytes=15_000_000: (bodies.pop(0), {"requested_url": url})
            with self.assertRaisesRegex(M.ParentCaptureError, "PARENT_FEATURE_COUNT"):
                M.refresh()
            self.assertFalse(any(tmp.rglob("*")))
        finally:
            M.ARCHIVE, M.MANIFEST, M.R.fetch_response = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_preregistration_is_consistent_and_unfitted(self):
        self.assertEqual(M.R.sha256_file(ROOT / PREREG["comparison_module_path"]), PREREG["comparison_module_sha256"])
        self.assertFalse(PREREG["tolerance"]["fitted_to_parent"])
        tau = PREREG["tolerance"]["tau_m"]
        self.assertAlmostEqual(tau, 0.02 * 0.0254 * 100000, places=9)
        ref = PREREG["children_union_reference"]
        self.assertAlmostEqual(PREREG["tolerance"]["sdr_bound"], tau * ref["perimeter_local_frame_m"] / (ref["area_km2"] * 1e6), places=9)
        self.assertEqual(PREREG["source"]["query"]["outSR"], PREREG["crs_rules"]["layer_source_spatial_reference_wkid_required"])


class FrozenParentCaptureTests(unittest.TestCase):
    def test_frozen_capture_verifies_offline(self):
        if not M.MANIFEST.is_file():
            self.skipTest("parent capture not yet frozen")
        manifest = M.verify()
        self.assertEqual(manifest["preregistration_sha256_at_capture"], M.R.sha256_file(M.PREREG))
        self.assertFalse(manifest["derived_from_children"])
        self.assertFalse(manifest["comparison_metrics_computed_at_capture"])
        self.assertIn(4326, {manifest["crs"]["response_spatial_reference"].get("wkid"), manifest["crs"]["response_spatial_reference"].get("latestWkid")})
        self.assertEqual(manifest["identity"]["CODIGO"].strip(), "137596")


if __name__ == "__main__":
    unittest.main()
