"""Triage of the 113 ANA 2016 Tumbes map labels (documentary QA, RESEARCH_ONLY / TEST_ONLY). Offline.

None of the labels becomes an inventory row or a geometry; the approximate label position is a triage aid, validated
against the same map's own table, and never admissible as geometry."""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phase2_tumbes_map_label_triage", ROOT / "scripts/phase2_tumbes_map_label_triage.py")
T = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)
DOC = json.loads(T.OUT.read_text(encoding="utf-8"))
REVIEW = json.loads(T.REVIEW.read_text(encoding="utf-8"))
CLASSES = {"CANDIDATO_CORROBORADO_SEGUNDA_FUENTE", "CANDIDATO_SOLO_ROTULO_ANA_2016", "POSIBLE_DUPLICADO_POR_ADJUDICAR",
           "POSIBLEMENTE_FUERA_DE_TUMBES", "SIN_POSICION_EN_EL_MAPA"}


class Triage(unittest.TestCase):
    def test_guards(self):
        for k, v in T.GUARDS.items():
            self.assertEqual(DOC[k], v, k)

    def test_every_map_label_candidate_is_triaged_once(self):
        expected = {c["candidate_id"] for c in REVIEW["new_candidates"] if c["evidence_scale"] == "MAP_LABEL_ONLY"}
        got = [r["candidate_id"] for r in DOC["rows"]]
        self.assertEqual(sorted(got), sorted(expected))
        self.assertEqual(len(got), 113)
        self.assertEqual(sum(v for k, v in DOC["counts"].items() if k != "labels"), 113)

    def test_rows_are_blocked_and_never_geometry(self):
        for r in DOC["rows"]:
            self.assertIn(r["classification"], CLASSES)
            self.assertEqual(r["source_sha256"], T.MAP["sha256"])
            self.assertTrue(r["map_block"].startswith("BLOQUEADO"))
            self.assertIn("no es cauce", r["location_basis"])
            self.assertFalse({"geometry", "coordinates", "outlet", "catchment"} & set(r))

    def test_georeference_is_validated_against_the_maps_own_table(self):
        g, v = DOC["georeference"], DOC["georeference_validation"]
        self.assertGreaterEqual(g["e_ticks"], 4)
        self.assertGreaterEqual(g["n_ticks"], 3)
        self.assertLess(g["max_tick_residual_m"], 50)
        self.assertEqual(v["points_compared"], 44)
        self.assertLess(v["p90_error_m"], 1500)  # sub-kilometre median: good enough for triage, not for geometry

    def test_utm_inverse(self):
        lon, lat = T.utm17s_to_lonlat(500000, 9600000)  # central meridian of zone 17
        self.assertAlmostEqual(lon, -81.0, places=6)
        self.assertAlmostEqual(lat, -3.61888, places=4)  # 400 km / k0 of meridian arc south of the equator


if __name__ == "__main__":
    unittest.main()
