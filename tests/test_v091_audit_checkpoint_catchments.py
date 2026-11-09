"""Independent audit of checkpoint ↔ contributing-area associations (RESEARCH_ONLY / TEST_ONLY).

Real-data checks recompute everything from the archived HydroSHEDS rasters; the archive-integrity checks use SYNTHETIC
archives to prove that duplicates, gaps, future times, malformed rows and stale data are detected."""
import importlib.util
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v091_audit_cc", ROOT / "scripts/v091_audit_checkpoint_catchments.py")
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
UTC = timezone.utc


class RealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = A.build(None, None, datetime(2026, 11, 9, 15, tzinfo=UTC))
        cls.committed = json.loads(A.OUT.read_text(encoding="utf-8"))

    def test_reproduces_committed_audit(self):
        for k in ("hydrorivers", "connectivity", "problem_points", "ana"):
            self.assertEqual(json.loads(json.dumps(self.d[k])), self.committed[k], k)

    def test_never_declares_scientific_validation(self):
        self.assertEqual(self.d["scientific_validation"], "NO_VALIDADA")
        self.assertFalse(self.d["public_alerting"] or self.d["notifications_enabled"] or self.d["production_use"])

    def test_ana_points_have_no_invented_hydrology(self):
        self.assertEqual(self.d["ana"]["total"], 398)
        self.assertEqual(self.d["ana"]["with_invented_hydrology"], [])
        self.assertNotIn("catchment", self.d["ana"]["rain_refs"])

    def test_every_pair_of_consecutive_points_is_connected_by_the_d8_path(self):
        self.assertTrue(self.d["connectivity"])
        self.assertTrue(all(x["d8_path_passes_downstream_point"] for x in self.d["connectivity"]))

    def test_hydrorivers_mismatches_are_explained_by_position_not_by_another_river(self):
        verdicts = {x["verdict"] for x in self.d["hydrorivers"]}
        self.assertFalse(verdicts & {"TRAMO_DISTINTO", "REVISAR"}, verdicts)
        supe = next(x for x in self.d["hydrorivers"] if x["id"] == "LIM-R-SUPE-ALTO")
        self.assertEqual(supe["verdict"], "COHERENTE_AGUAS_ARRIBA_DEL_TRAMO")  # ratio 0.65 is position, not an area error

    def test_problem_points_stay_unassociated_with_evidence(self):
        pp = {p["id"]: p for p in self.d["problem_points"]}
        for pid in ("TUM-R-ZARUMILLA-MEDIO", "LIM-R-RIMAC-ALTO", "ARE-R-TAMBO-BAJO"):
            self.assertEqual(pp[pid]["inventory_status"], "NO_VERIFICADA")
        self.assertGreater(pp["TUM-R-ZARUMILLA-MEDIO"]["main_stem"]["main_stem_from_upstream_point"]["distance_km"], 1.0)
        self.assertGreater(pp["ARE-R-TAMBO-BAJO"]["main_stem"]["main_stem_from_upstream_point"]["distance_km"], 1.0)
        self.assertEqual(pp["ICA-R-SAN_JUAN-BAJO"]["inventory_status"], "ASOCIACION_INCONSISTENTE")
        self.assertGreater(pp["ICA-R-SAN_JUAN-BAJO"]["main_stem"]["main_stem_from_upstream_point"]["distance_km"], 3.0)
        expected = {"TUM-R-ZARUMILLA-MEDIO": "Cuenca Zarumilla", "LIM-R-RIMAC-ALTO": "Cuenca Rímac", "ARE-R-TAMBO-BAJO": "Cuenca Tambo",
                    "ICA-R-SAN_JUAN-BAJO": "Cuenca San Juan", "PIU-R-PIURA-BAJO": "Cuenca Piura"}
        for pid, name in expected.items():  # official ANA unit = the named river's basin (river identity, not channel position)
            self.assertEqual(pp[pid]["ana_official_unit"]["point"]["nombre"], name, pid)
        piura = pp["PIU-R-PIURA-BAJO"]
        self.assertLess(piura["main_stem"]["main_stem_from_upstream_point"]["distance_km"], 0.5)
        self.assertGreater(piura["d8_outlet_to_nearest_ign_end_km"], 10)  # the 1:500k line does not end at the modelled mouth


class ArchiveIntegrity(unittest.TestCase):
    T0 = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)

    def archive(self, times, n=2, rows=None):
        return dict(targets=[dict(checkpoint_id=f"P{i}") for i in range(n)],
                    granules=[dict(time_utc=t.isoformat(), rate_mm_hr=(rows or {}).get(k, [0.1] * n), covered_pct=[100.0] * n)
                              for k, t in enumerate(times)])

    def test_clean_archive(self):
        times = [self.T0 + timedelta(minutes=30 * k) for k in range(6)]
        r = A.audit_archive(self.archive(times), ["P0", "P1"], self.T0 + timedelta(hours=4))
        self.assertEqual((r["gaps"], r["duplicates"], r["future"], r["malformed_rows"]), ([], [], [], []))
        self.assertEqual(r["freshness"], "RECIENTE")
        self.assertTrue(r["targets_match_geometry_config"])

    def test_gap_duplicate_future_malformed_and_stale_are_detected(self):
        times = [self.T0, self.T0, self.T0 + timedelta(hours=2), self.T0 + timedelta(hours=30)]
        arch = self.archive(times)
        arch["granules"][2]["rate_mm_hr"] = [0.1]  # wrong length
        r = A.audit_archive(arch, ["P1", "P0"], self.T0 + timedelta(hours=10))
        self.assertTrue(r["duplicates"] and r["gaps"] and r["future"] and r["malformed_rows"])
        self.assertFalse(r["targets_match_geometry_config"])
        old = A.audit_archive(self.archive([self.T0]), None, self.T0 + timedelta(hours=13))
        self.assertEqual(old["freshness"], "CADUCADA")

    def test_null_with_coverage_and_off_grid_times(self):
        arch = self.archive([self.T0, self.T0 + timedelta(minutes=45)])
        arch["granules"][0]["rate_mm_hr"] = [None, 0.2]
        r = A.audit_archive(arch, None, self.T0 + timedelta(hours=2))
        self.assertEqual(r["null_with_positive_coverage"], 1)
        self.assertTrue(r["off_half_hour_grid"])


class Geometry(unittest.TestCase):
    def test_segment_distance(self):
        self.assertAlmostEqual(A.seg_km((0.0, 0.01), (-0.01, 0.0), (0.01, 0.0)), 0.01 * 111.32, places=3)
        self.assertAlmostEqual(A.seg_km((0.02, 0.0), (-0.01, 0.0), (0.01, 0.0)), 0.01 * 111.32, places=3)


if __name__ == "__main__":
    unittest.main()
