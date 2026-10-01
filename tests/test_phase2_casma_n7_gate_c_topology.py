"""Tests for the Casma N7 Gate C topology QA (research only, offline).

1. The committed report is reproduced byte-for-byte from the frozen Gate A
   capture and keeps Gate B / equivalence / map publication untouched.
2. Every detector fires on a synthetic defect injected into a clean
   Pfafstetter-shaped fixture (so a clean result is not vacuous).
3. Tampering with a frozen input byte fails closed.
4. The ellipsoidal-area implementation matches an analytic reference.
"""
import copy
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/qa_phase2_casma_n7_gate_c_topology.py"
CONTRACT = ROOT / "config/phase2_casma_n7_gate_c_topology_contract_v0_1.json"
REPORT = ROOT / "site/data/phase2/source_assessments/casma_n7_gate_c_topology_report_v0_1.json"
ADJUDICATION = ROOT / "site/data/phase2/source_assessments/casma_n7_gate_c_adjudication_v0_1.json"
GATES = ROOT / "site/data/phase2/source_assessments/casma_minam_recovery_gate_adjudication_v0_1.json"


def load_module():
    spec = importlib.util.spec_from_file_location("casma_gate_c_qa", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


QA = load_module()
CONTRACT_DOC = json.loads(CONTRACT.read_text(encoding="utf-8"))


def clean_fixture():
    """Nine noded clockwise units: interbasins 1,3,5,7,9 along a main stem
    (y 0..2) and tributaries 2,4,6,8 above (y 2..4) straddling their flanking
    interbasins. Satisfies every required Pfafstetter adjacency."""
    polys = {}
    for k, digit in enumerate((1, 3, 5, 7, 9)):
        x = 2.0 * k
        polys[f"137596{digit}"] = [[(x, 0.0), (x, 2.0), (x + 1, 2.0), (x + 2, 2.0), (x + 2, 0.0), (x, 0.0)]]
    for j, digit in enumerate((2, 4, 6, 8)):
        x = 2.0 * j + 1
        polys[f"137596{digit}"] = [[(x, 2.0), (x, 4.0), (x + 2, 4.0), (x + 2, 2.0), (x + 1, 2.0), (x, 2.0)]]
    return polys


def clean_attributes(polys):
    return {code: {"CODIGO": code, "NIVEL7": code, "NIVEL": 7} for code in polys}


def run(polys, attributes=None, clockwise=True):
    result = QA.run_dataset(CONTRACT_DOC, "fixture", polys, attributes if attributes is not None else clean_attributes(polys), [], clockwise)
    return result, {a["code"] for a in result["anomalies"]}


class CommittedReportTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_report_is_reproduced_byte_for_byte(self):
        recomputed = QA.canonical(QA.evaluate(CONTRACT))
        self.assertEqual(recomputed, REPORT.read_text(encoding="utf-8"))

    def test_fail_closed_guards_and_untouched_gates(self):
        for key, value in QA.SAFE.items():
            self.assertEqual(self.report[key], value, key)
            self.assertEqual(CONTRACT_DOC[key], value, key)
        self.assertEqual(self.report["gate_b_lineage_equivalence"], "NOT_ESTABLISHED")
        self.assertFalse(self.report["historical_geometry_equivalence_to_Uh_pfas100"])
        self.assertFalse(self.report["map_publication_authorized"])
        self.assertFalse(self.report["map_eligible_as_research_context"])
        gates = json.loads(GATES.read_text(encoding="utf-8"))
        self.assertEqual(gates["gate_b_lineage_equivalence"]["current_status"], "NOT_ESTABLISHED")
        self.assertFalse(gates["gate_c_topology_map"]["map_publication_authorized"])

    def test_c6d_follows_the_preregistered_rule(self):
        source = CONTRACT_DOC["checks"]["C6_PARENT_COHERENCE"]["external_parent_source"]
        prereg_path = ROOT / source["preregistration"]
        prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
        capture = json.loads((ROOT / source["capture_manifest"]).read_text(encoding="utf-8"))
        c6d = self.report["c6d_external_parent"]
        self.assertEqual(c6d["reasons"], [])
        self.assertEqual(c6d["preregistration_sha256"], QA.sha256_file(prereg_path))
        self.assertEqual(c6d["preregistration_sha256"], capture["preregistration_sha256_at_capture"])
        self.assertEqual(c6d["comparison_module_sha256"], prereg["comparison_module_sha256"])
        self.assertFalse(capture["derived_from_children"])
        m = c6d["metrics"]
        self.assertEqual(m["M1_threshold_m"], prereg["tolerance"]["tau_m"])
        self.assertAlmostEqual(m["M2_threshold"], prereg["tolerance"]["sdr_bound"], places=6)
        self.assertEqual(m["M1_pass"], m["M1_p90_boundary_distance_m"] <= prereg["tolerance"]["tau_m"])
        self.assertEqual(m["M2_pass"], m["M2_symmetric_difference_ratio"] <= prereg["tolerance"]["sdr_bound"])
        self.assertEqual(c6d["status"], "PASS" if (m["M1_pass"] and m["M2_pass"]) else "FAIL")
        self.assertEqual(self.report["parent_coherence_subchecks"]["C6d_EXTERNAL_PARENT_POLYGON"], c6d["status"])
        statuses = set(self.report["checks"].values())
        expected = "FAIL" if "FAIL" in statuses else ("NOT_PASS_PENDING" if "NOT_EVALUABLE" in statuses else "PASS")
        self.assertEqual(self.report["gate_c_status"], expected)

    def test_both_datasets_were_checked_on_all_frozen_vertices(self):
        manifest = json.loads((ROOT / CONTRACT_DOC["inputs"]["gate_a_manifest"]).read_text(encoding="utf-8"))
        native_vertices = 0
        for row in manifest["features"]:
            doc = json.loads((ROOT / row["native_archive_path"]).read_bytes())
            native_vertices += sum(len(r) for r in doc["features"][0]["geometry"]["rings"])
        for dataset in ("native_storage_crs", "normalized_publication_crs"):
            self.assertEqual(self.report["datasets"][dataset]["vertex_count"], native_vertices)
            self.assertTrue(self.report["datasets"][dataset]["union"]["union_area_identity_exact"])
        self.assertEqual(self.report["datasets"]["native_storage_crs"]["orientation"]["shell_orientation"], "CW")

    def test_adjudication_is_bound_to_report(self):
        adj = json.loads(ADJUDICATION.read_text(encoding="utf-8"))
        self.assertEqual(adj["report_sha256"], QA.sha256_file(REPORT))
        self.assertEqual(adj["gate_c_status"], self.report["gate_c_status"])
        self.assertEqual(adj["checks"], self.report["checks"])
        self.assertEqual(adj["blocking_anomaly_count"], self.report["anomaly_count"])
        self.assertFalse(adj["map_publication_authorized"])
        self.assertFalse(adj["gate_b_modified"])
        self.assertFalse(adj["historical_geometry_equivalence_to_Uh_pfas100"])


class DetectorTests(unittest.TestCase):
    def test_clean_fixture_passes_every_check(self):
        result, codes = run(clean_fixture())
        self.assertEqual(codes, set())
        self.assertEqual(set(result["checks"].values()), {"PASS"})
        self.assertEqual(result["union"]["reduced_boundary_loops"], 1)
        self.assertTrue(result["union"]["union_area_identity_exact"])
        self.assertEqual(result["pfafstetter"]["additional_adjacencies"], ["1375962-1375964", "1375964-1375966", "1375966-1375968"])

    def test_unclosed_ring(self):
        polys = clean_fixture()
        polys["1375961"][0][-1] = (0.0, 0.5)
        self.assertIn("RING_NOT_CLOSED", run(polys)[1])

    def test_repeated_vertices(self):
        polys = clean_fixture()
        ring = polys["1375969"][0]
        ring.insert(2, ring[1])
        self.assertIn("REPEATED_CONSECUTIVE_VERTEX", run(polys)[1])
        polys = clean_fixture()
        polys["1375969"][0] = [(8.0, 0.0), (8.0, 2.0), (9.0, 2.0), (10.0, 2.0), (9.0, 2.0), (10.0, 0.0), (8.0, 0.0)]
        self.assertIn("REPEATED_VERTEX_SELF_TOUCH", run(polys)[1])

    def test_orientation(self):
        polys = clean_fixture()
        polys["1375965"][0] = list(reversed(polys["1375965"][0]))
        codes = run(polys)[1]
        self.assertIn("MIXED_SHELL_ORIENTATION", codes)
        self.assertIn("SAME_DIRECTION_SHARED_EDGE", codes)
        all_ccw = {c: [list(reversed(r)) for r in rings] for c, rings in clean_fixture().items()}
        self.assertIn("ESRI_SHELL_NOT_CLOCKWISE", run(all_ccw)[1])
        self.assertEqual(run(all_ccw, clockwise=False)[1], set())

    def test_self_crossing_and_spike(self):
        polys = clean_fixture()
        polys["1375961"][0] = [(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0), (0.0, 0.0)]
        self.assertIn("SELF_PROPER", run(polys)[1])
        polys = clean_fixture()
        polys["1375961"][0] = [(0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (2.0, 2.0), (2.0, 0.0), (3.0, 0.0), (2.5, 0.0), (0.0, 0.0)]
        codes = run(polys)[1]
        self.assertIn("SPIKE_FOLD_BACK", codes)
        self.assertIn("SELF_COLLINEAR_OVERLAP", codes)

    def test_sibling_overlap(self):
        polys = clean_fixture()
        polys["1375961"][0] = [(0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (2.0, 2.0), (2.5, 1.0), (2.0, 0.0), (0.0, 0.0)]
        # Unit 1 bulges into unit 3 without crossing any unit-3 edge: only the
        # directed-edge winding certificate can see this overlap.
        result, codes = run(polys)
        self.assertEqual(result["checks"]["C4_SIBLING_OVERLAP"], "FAIL")
        overlap = [a for a in result["anomalies"] if a["code"] == "OVERLAP_REGION"]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0]["units"], ["1375961", "1375963"])
        self.assertAlmostEqual(overlap[0]["detail"]["area2_abs"] / 2, 0.5)
        polys = clean_fixture()
        polys["1375961"][0] = [(0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (2.0, 2.0), (2.0, 1.5), (2.5, 1.0), (2.0, 0.5), (2.0, 0.0), (0.0, 0.0)]
        self.assertIn("T_JUNCTION_NON_NODED", run(polys)[1])
        polys = clean_fixture()
        # Edge (2,2)-(2.5,-0.5) crosses unit 3's bottom edge at (2.4, 0).
        polys["1375961"][0] = [(0.0, 0.0), (0.0, 2.0), (1.0, 2.0), (2.0, 2.0), (2.5, -0.5), (0.0, 0.0)]
        self.assertIn("PROPER_CROSSING", run(polys)[1])
        polys = clean_fixture()
        polys["1375961"] = [[(8.0, 0.0), (8.0, 2.0), (9.0, 2.0), (10.0, 2.0), (10.0, 0.0), (8.0, 0.0)]]
        codes = run(polys)[1]
        self.assertIn("SAME_DIRECTION_SHARED_EDGE", codes)

    def test_non_noded_shared_boundary(self):
        polys = clean_fixture()
        polys["1375962"][0] = [(1.0, 2.0), (1.0, 4.0), (3.0, 4.0), (3.0, 2.0), (1.0, 2.0)]
        result, codes = run(polys)
        self.assertIn("T_JUNCTION_NON_NODED", codes)
        self.assertEqual(result["checks"]["C5_UNION_GAPS"], "FAIL")

    def test_internal_gap_is_reported_with_area(self):
        polys = clean_fixture()
        polys["1375963"][0] = [(2.0, 0.0), (2.0, 2.0), (3.0, 1.5), (4.0, 2.0), (4.0, 0.0), (2.0, 0.0)]
        result, codes = run(polys)
        self.assertIn("UNEXPLAINED_GAP", codes)
        gap = [a for a in result["anomalies"] if a["code"] == "UNEXPLAINED_GAP"][0]
        self.assertAlmostEqual(gap["detail"]["area2_abs"] / 2, 0.5)
        self.assertEqual(result["parent_coherence_subchecks"]["C6b_UNION_SIMPLY_CONNECTED"], "FAIL")

    def test_pfafstetter_completeness_and_adjacency(self):
        polys = clean_fixture()
        del polys["1375969"]
        codes = run(polys)[1]
        self.assertIn("PFAFSTETTER_CHILD_SET_MISMATCH", codes)
        self.assertIn("REQUIRED_PFAFSTETTER_ADJACENCY_MISSING", codes)
        polys = clean_fixture()
        attrs = clean_attributes(polys)
        attrs["1375964"]["NIVEL"] = 6
        self.assertIn("PFAFSTETTER_ATTRIBUTE_MISMATCH", run(polys, attrs)[1])

    def test_exact_predicates_do_not_use_epsilon(self):
        a, b = (0.0, 0.0), (1e8, 1e8 + 1)
        c = (5e7, 5e7 + 0.5)
        self.assertEqual(QA.orient(a, b, c), 0)
        above = (5e7, math.nextafter(5e7 + 0.5, math.inf))
        below = (5e7, math.nextafter(5e7 + 0.5, -math.inf))
        self.assertEqual(QA.orient(a, b, above), 1)
        self.assertEqual(QA.orient(a, b, below), -1)
        self.assertEqual(QA.segment_relation((0.0, 0.0), (2.0, 0.0), (1.0, 0.0), (1.0, 1.0))[0], "TOUCH")


class TamperTests(unittest.TestCase):
    FILES = [
        "config/phase2_casma_n7_gate_c_topology_contract_v0_1.json",
        "config/phase2_casma_minam_n7_recovery_contract_v0_1.json",
        "scripts/qa_phase2_casma_n7_gate_c_topology.py",
        "scripts/recover_phase2_casma_minam_n7.py",
        "site/data/phase2/geometries/ancash_casma_n7_minam_official_v0_1.geojson",
        "site/data/phase2/source_assessments/casma_minam_n7_recovery_manifest_v0_1.json",
        "config/phase2_casma_n6_parent_c6d_preregistration_v0_1.json",
        "scripts/c6d_parent_comparison.py",
        "scripts/capture_phase2_casma_n6_parent.py",
        "site/data/phase2/source_assessments/casma_n6_parent_capture_manifest_v0_1.json",
    ]

    def copy_tree(self):
        tmp = Path(tempfile.mkdtemp())
        for rel in self.FILES:
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, tmp / rel)
        for archive in ("data/phase2/source_archive/casma_minam_n7", "data/phase2/source_archive/casma_n6_parent"):
            shutil.copytree(ROOT / archive, tmp / archive)
        return tmp

    def run_write(self, tmp):
        proc = subprocess.run([sys.executable, "scripts/qa_phase2_casma_n7_gate_c_topology.py", "--write"], cwd=tmp, capture_output=True, text=True)
        report = json.loads((tmp / CONTRACT_DOC["outputs"]["report_path"]).read_text(encoding="utf-8"))
        return proc, report

    def test_parent_byte_change_makes_c6d_not_evaluable(self):
        tmp = self.copy_tree()
        try:
            target = tmp / "data/phase2/source_archive/casma_n6_parent/137596.native.json"
            raw = target.read_bytes()
            target.write_bytes(raw.replace(b"Cuenca Casma", b"Cuenca Casmb", 1))
            proc, report = self.run_write(tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(report["parent_coherence_subchecks"]["C6d_EXTERNAL_PARENT_POLYGON"], "NOT_EVALUABLE")
            self.assertEqual(report["gate_c_status"], "NOT_PASS_PENDING")
            self.assertTrue(any("PARENT_CAPTURE_VERIFY_FAILED" in r for r in report["c6d_external_parent"]["reasons"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_post_capture_tolerance_change_cannot_pass(self):
        tmp = self.copy_tree()
        try:
            path = tmp / "config/phase2_casma_n6_parent_c6d_preregistration_v0_1.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["tolerance"]["tau_m"] = 1000.0
            path.write_text(json.dumps(doc), encoding="utf-8")
            proc, report = self.run_write(tmp)
            self.assertEqual(report["parent_coherence_subchecks"]["C6d_EXTERNAL_PARENT_POLYGON"], "NOT_EVALUABLE")
            self.assertNotEqual(report["gate_c_status"], "PASS")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_single_coordinate_change_fails_closed(self):
        tmp = self.copy_tree()
        try:
            target = tmp / "data/phase2/source_archive/casma_minam_n7/1375965.native.json"
            raw = target.read_bytes()
            first = json.loads(raw)["features"][0]["geometry"]["rings"][0][1]
            needle = json.dumps(first[0]).encode()
            self.assertIn(needle, raw)
            target.write_bytes(raw.replace(needle, json.dumps(first[0] + 1.0).encode(), 1))
            (tmp / "site/data/phase2/source_assessments").mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(
                [sys.executable, "scripts/qa_phase2_casma_n7_gate_c_topology.py", "--write"],
                cwd=tmp, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 1, proc.stderr)
            report = json.loads((tmp / CONTRACT_DOC["outputs"]["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["gate_c_status"], "FAIL")
            self.assertEqual(report["checks"]["C0_INPUT_INTEGRITY"], "FAIL")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AreaImplementationTests(unittest.TestCase):
    def test_albers_matches_analytic_ellipsoidal_cell_area(self):
        lon1, lon2, lat1, lat2 = -78.0, -77.0, -10.0, -9.0
        analytic = QA.WGS84_A**2 * math.radians(lon2 - lon1) * abs(QA._q(lat2) - QA._q(lat1)) / 2
        steps = 2000
        edge = [(lon1 + (lon2 - lon1) * i / steps, lat1) for i in range(steps)]
        edge += [(lon2, lat1 + (lat2 - lat1) * i / steps) for i in range(steps)]
        edge += [(lon2 - (lon2 - lon1) * i / steps, lat2) for i in range(steps)]
        edge += [(lon1, lat2 - (lat2 - lat1) * i / steps) for i in range(steps)]
        edge.append(edge[0])
        albers = QA.planar_area([QA.albers_xy(lon, lat) for lon, lat in edge])
        self.assertLess(abs(albers - analytic) / analytic, 1e-8)

    def test_utm_inverse_matches_adjudicated_vertex(self):
        lon, lat = QA.utm18s_inverse(154685.88190000039, 8973906.0050000008)
        self.assertAlmostEqual(lon, -78.142525993906602, places=9)
        self.assertAlmostEqual(lat, -9.2687765987241661, places=9)


if __name__ == "__main__":
    unittest.main()
