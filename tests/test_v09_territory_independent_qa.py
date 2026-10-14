"""Independent QA of the territorial viewer (scripts/v09_territory_independent_qa.py): the verifier passes on the
committed bundle and fails on deliberately broken copies (negative controls), so a PASS is not vacuous. Offline."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_territory_independent_qa", ROOT / "scripts/v09_territory_independent_qa.py")
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)
BUNDLE = json.loads(Q.BUNDLE.read_text(encoding="utf-8"))


def run(check, bundle=None):
    out = []
    check(bundle, out) if bundle is not None else check(out)
    return out[0]


class Committed(unittest.TestCase):
    def test_all_checks_pass(self):
        for check in (Q.check_provenance, Q.check_dem, Q.check_rain_polygon, Q.check_missing_not_zero, Q.check_independence):
            r = run(check, BUNDLE)
            self.assertEqual(r["result"], "PASS", (r["id"], r.get("evidence")))
        self.assertEqual(run(Q.check_pages)["result"], "PASS")


class NegativeControls(unittest.TestCase):
    def mutate(self, fn):
        b = copy.deepcopy(BUNDLE)
        fn(b)
        return b

    def feature(self, b, role):
        return next(f for f in b["geometries"]["features"] if f["properties"]["semantic_role"] == role)

    def test_moved_vertex_fails_provenance(self):
        def fn(b):
            g = self.feature(b, "OFFICIAL_ANA_HYDROGRAPHIC_UNIT")["geometry"]
            ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
            ring[1] = [ring[1][0] + 0.01, ring[1][1]]
        self.assertEqual(run(Q.check_provenance, self.mutate(fn))["result"], "FAIL")

    def test_dem_labelled_official_fails(self):
        def fn(b):
            self.feature(b, "DEM_D8_CANDIDATE_CATCHMENT")["properties"]["evidence"] = "GEOMETRIA_OFICIAL"
        self.assertEqual(run(Q.check_dem, self.mutate(fn))["result"], "FAIL")

    def test_zone_rain_on_another_polygon_fails(self):
        def fn(b):
            f = self.feature(b, "OFFICIAL_ANA_HYDROGRAPHIC_UNIT")
            other = next(z for z in b["zone_rain"] if z != f["properties"].get("v09_zone"))
            f["properties"]["v09_zone"] = other
        self.assertEqual(run(Q.check_rain_polygon, self.mutate(fn))["result"], "FAIL")

    def test_value_on_missing_window_fails(self):
        def fn(b):
            z = next(iter(b["zone_rain"].values()))
            z["imerg"]["windows"]["24h"] = dict(status="NO_DISPONIBLE", accum_mm=0.0)
        self.assertEqual(run(Q.check_missing_not_zero, self.mutate(fn))["result"], "FAIL")

    def test_inventory_drawn_as_feature_fails(self):
        inv_id = json.loads((ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json").read_text(encoding="utf-8"))["candidates"][0]["inventory_id"]
        def fn(b):
            self.feature(b, "OFFICIAL_ANA_HYDROGRAPHIC_UNIT")["properties"]["id"] = inv_id
        self.assertEqual(run(Q.check_independence, self.mutate(fn))["result"], "FAIL")


if __name__ == "__main__":
    unittest.main()
