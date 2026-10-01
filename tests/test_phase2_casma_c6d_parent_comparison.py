"""Synthetic and self-consistency tests for the preregistered C6d comparison.

Written together with the comparison module and before any parent geometry
was retrieved. They pin the behaviour the preregistration relies on.
"""
import importlib.util
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts/c6d_parent_comparison.py"
QA_SCRIPT = ROOT / "scripts/qa_phase2_casma_n7_gate_c_topology.py"
PREREG = ROOT / "config/phase2_casma_n6_parent_c6d_preregistration_v0_1.json"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


C6D = load(MODULE, "c6d_parent_comparison")


def square(x0, y0, size, cw=False):
    ring = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size), (x0, y0)]
    return list(reversed(ring)) if cw else ring


class IntersectionAreaTests(unittest.TestCase):
    def test_partial_overlap(self):
        r = C6D.intersection_area([square(0, 0, 10)], [square(5, 5, 10)], 4.0)
        self.assertAlmostEqual(r["area"], 25.0, places=9)

    def test_identical_shared_boundary_counts_once(self):
        r = C6D.intersection_area([square(0, 0, 10)], [square(0, 0, 10, cw=True)], 4.0)
        self.assertAlmostEqual(r["area"], 100.0, places=9)
        self.assertEqual(r["shared_same_direction_pieces"], 4)

    def test_adjacent_polygons_have_zero_intersection(self):
        r = C6D.intersection_area([square(0, 0, 10)], [square(10, 0, 10)], 4.0)
        self.assertAlmostEqual(r["area"], 0.0, places=9)
        self.assertEqual(r["shared_opposite_direction_pieces"], 1)

    def test_containment_disjoint_and_hole(self):
        self.assertAlmostEqual(C6D.intersection_area([square(0, 0, 10)], [square(2, 2, 3)], 4.0)["area"], 9.0)
        self.assertAlmostEqual(C6D.intersection_area([square(0, 0, 1)], [square(5, 5, 1)], 4.0)["area"], 0.0)
        holed = [square(0, 0, 10), list(reversed(square(4, 4, 2)))]
        self.assertAlmostEqual(C6D.intersection_area(holed, [square(0, 0, 10)], 4.0)["area"], 96.0)
        self.assertAlmostEqual(C6D.intersection_area(holed, [square(3, 3, 4)], 4.0)["area"], 12.0)

    def test_collinear_partial_overlap(self):
        r = C6D.intersection_area([square(0, 0, 10)], [[(0, 2), (0, 8), (-5, 8), (-5, 2), (0, 2)]], 4.0)
        self.assertAlmostEqual(r["area"], 0.0, places=9)


class DistanceAndDecisionTests(unittest.TestCase):
    def prereg(self, tau=50.8, sdr=0.01):
        return {
            "local_frame_origin_lonlat": [-78.0, -9.46],
            "intersection_grid_cell_m": 2000.0,
            "distance_grid_cell_m": 250.0,
            "metrics": {"M1_p90_boundary_distance": {"densification_spacing_m": 5.0}},
            "tolerance": {"tau_m": tau, "sdr_bound": sdr},
        }

    def lonlat_square(self, lon0, lat0, size_deg):
        return [(lon0, lat0), (lon0 + size_deg, lat0), (lon0 + size_deg, lat0 + size_deg), (lon0, lat0 + size_deg), (lon0, lat0)]

    def test_identical_geometry_passes_with_zero_metrics(self):
        ring = self.lonlat_square(-78.05, -9.5, 0.1)
        out = C6D.compare(ring, [list(reversed(ring))], self.prereg())
        self.assertEqual(out["decision"], "PASS")
        self.assertAlmostEqual(out["M1_p90_boundary_distance_m"], 0.0, places=6)
        self.assertAlmostEqual(out["M2_symmetric_difference_ratio"], 0.0, places=12)

    def test_shift_within_and_beyond_tolerance(self):
        ring = self.lonlat_square(-78.05, -9.5, 0.1)
        metres_per_deg_lat = C6D.local_frame(-78.0, -9.46)(0.0, -9.46 + 1)[1]
        for shift_m, expected in [(30.0, "PASS"), (80.0, "FAIL")]:
            with self.subTest(shift_m=shift_m):
                d = shift_m / metres_per_deg_lat
                parent = [(x, y + d) for x, y in ring]
                out = C6D.compare(ring, [parent], self.prereg(sdr=1.0))
                self.assertEqual(out["decision"], expected)
                self.assertLessEqual(out["M1_p90_boundary_distance_m"], shift_m + 1e-6)
                self.assertGreater(out["M1_p90_boundary_distance_m"], 0.0)
                self.assertAlmostEqual(out["report_only"]["hausdorff_m"], shift_m, delta=0.05)

    def test_area_criterion_fails_independently(self):
        ring = self.lonlat_square(-78.05, -9.5, 0.1)
        parent = self.lonlat_square(-78.05, -9.5, 0.09)
        out = C6D.compare(ring, [parent], self.prereg(tau=1e9, sdr=0.01))
        self.assertTrue(out["M1_pass"])
        self.assertFalse(out["M2_pass"])
        self.assertEqual(out["decision"], "FAIL")
        self.assertAlmostEqual(out["M2_symmetric_difference_ratio"], (0.01 - 0.0081) / 0.0081, delta=2e-3)

    def test_percentile_nearest_rank(self):
        self.assertEqual(C6D.nearest_rank_percentile(list(range(1, 11)), 90), 9)
        self.assertEqual(C6D.nearest_rank_percentile([5.0], 90), 5.0)


class RealUnionSelfConsistencyTests(unittest.TestCase):
    def test_frozen_union_against_itself_passes_under_preregistration(self):
        qa = load(QA_SCRIPT, "gate_c_for_c6d")
        manifest = json.loads((ROOT / "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json").read_text(encoding="utf-8"))
        native, _, _ = qa.native_polygons(qa.load_native(manifest))
        _, reduced, _, _ = qa.edge_topology(native)
        cycles, _ = qa.extract_cycles(reduced)
        loop = max(cycles, key=len)
        union = [qa.utm18s_inverse(x, y) for x, y in loop]
        prereg = json.loads(PREREG.read_text(encoding="utf-8"))
        out = C6D.compare(union, [union], prereg)
        self.assertEqual(out["decision"], "PASS")
        self.assertAlmostEqual(out["M1_p90_boundary_distance_m"], 0.0, places=6)
        self.assertAlmostEqual(out["M2_symmetric_difference_ratio"], 0.0, places=9)
        self.assertAlmostEqual(out["report_only"]["area_parent_km2"], prereg["children_union_reference"]["area_km2"], places=5)


if __name__ == "__main__":
    unittest.main()
