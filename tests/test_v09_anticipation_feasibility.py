"""IRFEN v0.9 · viabilidad de la anticipación experimental de crecidas (protocolo v0.3). Sin red.

Comprueba que el protocolo exige datos subdiarios medidos y lluvia disponible en t, que el arnés no tiene fugas
temporales y separa episodios, que con los datos archivados (medias diarias) el resultado es NO_EVALUABLE, y que las
cuencas binacionales experimentales siguen las mismas reglas que #459. Las series de juguete de `Harness` son
sintéticas y SOLO prueban el código: nunca se usan como observaciones."""
import importlib.util
import io
import json
import re
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A = _load("ah", "scripts/v09_anticipation_harness.py")
N = _load("nc", "scripts/v09_north_catchments.py")
F = _load("hf", "scripts/v09_imerg_halfhour_feasibility.py")
PROTO = A.load_protocol()
NC = json.loads(N.OUT.read_text(encoding="utf-8"))
FE = json.loads(F.OUT.read_text(encoding="utf-8"))
EV = json.loads(A.OUT.read_text(encoding="utf-8"))
H = 3600


def _toy(seed, rain_drives):
    """SYNTHETIC toy series for code tests only (not observations)."""
    rng = np.random.default_rng(seed)
    t0 = int(datetime.fromisoformat("2029-12-25T00:00:00+00:00").timestamp())
    n = 48 * 200
    tr = t0 + np.arange(n) * 1800
    r = np.where(rng.random(n) < 0.03, rng.gamma(2, 4, n), 0.0)
    kern = np.zeros(40)
    kern[16:28] = 1 / 12
    src = r if rain_drives else rng.permutation(r)
    q = 20 + np.convolve(np.convolve(src, kern)[:n] * 30, np.exp(-np.arange(200) / 40.0))[:n] * 0.2 + rng.normal(0, 0.5, n)
    T = A.Series("Q_TOY", "CAUDAL_O_NIVEL_MEDIDO", tr[::2], q[::2], H)
    R = A.Series("R_TOY", "LLUVIA_REGISTRADA", tr, r, 4 * H, product="GPM_3IMERGHHE")
    eps = [dict(id=f"E{i}", start=f"2030-0{1 + 2 * i}-01T00:00:00+00:00", end=f"2030-0{1 + 2 * i}-15T00:00:00+00:00") for i in range(3)]
    return T, R, eps


class Protocol(unittest.TestCase):
    def test_protocol_requires_subdaily_measured_targets_and_available_rain(self):
        req = PROTO["target_requirements"]
        self.assertEqual(req["max_time_step_hours"], 1)
        self.assertFalse(req["daily_means_allowed"])
        self.assertFalse(req["disaggregation_of_daily_values_allowed"])
        self.assertEqual(PROTO["horizons_hours"], [3, 6, 12, 24])
        self.assertIsNone(PROTO["availability_latency_hours"]["IMERG_FINAL"])
        self.assertIsNone(PROTO["decision_thresholds"])
        self.assertTrue(PROTO["fixed_before_any_subdaily_comparison"])
        doc = (ROOT / "qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md").read_text(encoding="utf-8")
        self.assertIn("Versión 0.3", doc)

    def test_out_of_scope_downstream_of_poechos(self):
        p = next(x for x in PROTO["upstream_pairs"] if x["target"] == "AGUAS_ABAJO_DE_POECHOS")
        self.assertIsNone(p["upstream"])
        self.assertIn("FUERA_DE_ALCANCE", p["regime_rule"])


class Harness(unittest.TestCase):
    def test_daily_means_are_not_evaluable(self):
        s = A.Series("D", "CAUDAL_O_NIVEL_MEDIDO", np.arange(0, 30 * 86400, 86400), np.ones(30), 0, statistic="MEDIA_DIARIA")
        self.assertIn("MEDIAS_DIARIAS", A.check_target(s, PROTO))
        s2 = A.Series("D2", "CAUDAL_O_NIVEL_MEDIDO", np.arange(0, 30 * 86400, 86400), np.ones(30), 0)
        self.assertIn("PASO_TEMPORAL_INSUFICIENTE", A.check_target(s2, PROTO))
        s3 = A.Series("A", "CAUDAL_APROXIMADO", np.arange(0, 300 * H, H), np.ones(300), 0)
        self.assertIn("CATEGORIA_NO_ADMITIDA", A.check_target(s3, PROTO))

    def test_imerg_final_is_rejected_as_predictor(self):
        for prod in ("GPM_3IMERGHH", "GPM_3IMERGDF", "IMERG_FINAL"):
            self.assertIn("IMERG_FINAL_PROHIBIDO", A.check_rain(A.Series("R", "LLUVIA_REGISTRADA", np.arange(3) * 1800, np.zeros(3), 0, product=prod)))
        self.assertIsNone(A.check_rain(A.Series("R", "LLUVIA_REGISTRADA", np.arange(3) * 1800, np.zeros(3), 0, product="GPM_3IMERGHHE")))

    def test_features_only_use_data_available_at_issue_time(self):
        T, R, eps = _toy(3, True)
        D, used = A.design(T, None, R, A.episode_times(eps[0], 6, 6), 6, 6)
        self.assertGreater(len(D), 100)
        self.assertTrue(all(u <= t for u, t in zip(used, D[:, -1].astype(int))))
        r, tr = A.rain_accum(R, int(D[0, -1]), 6)
        self.assertLessEqual(tr, int(D[0, -1]) - 4 * H)  # IMERG Early latency respected
        v, tv = A.last_available(T, int(D[0, -1]))
        self.assertLessEqual(tv + H, int(D[0, -1]))  # telemetry latency respected

    def test_incomplete_rain_is_unknown_not_zero(self):
        t = np.arange(0, 48) * 1800
        vals = np.ones(48)
        vals[40] = np.nan
        R = A.Series("R", "LLUVIA_REGISTRADA", t, vals, 0, product="GPM_3IMERGHHE")
        self.assertTrue(np.isnan(A.rain_accum(R, int(t[-1]), 6)[0]))

    def test_episodes_must_be_separated(self):
        with self.assertRaises(A.ProtocolError):
            A.check_episodes([dict(id="a", start="2030-01-01T00:00:00+00:00", end="2030-01-20T00:00:00+00:00"),
                              dict(id="b", start="2030-01-23T00:00:00+00:00", end="2030-02-10T00:00:00+00:00")])

    def test_signal_is_detected_and_noise_gives_a_negative_result(self):
        proto = dict(PROTO, horizons_hours=[6], rain_accumulations_hours=[6])
        T, R, eps = _toy(1, True)
        good = A.evaluate_pair(T, None, R, eps, proto)["results"]["h6_k6"]
        self.assertEqual(good["verdict"], "MEJORA_DEMOSTRABLE")
        T, R, eps = _toy(1, False)
        bad = A.evaluate_pair(T, None, R, eps, proto)["results"]["h6_k6"]
        self.assertEqual(bad["verdict"], "RESULTADO_NEGATIVO_O_NO_CONCLUYENTE")

    def test_current_archive_gives_no_evaluable_and_rebuilds(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(["--check"]), 0)
        for t in EV["targets"]:
            self.assertIn(t["status"], ("NO_EVALUABLE", "FUERA_DE_ALCANCE"), t)
        self.assertIsNone(EV["decision_thresholds"])


class Catchments(unittest.TestCase):
    def test_rebuilds_byte_for_byte(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(N.main(["--check"]), 0)

    def test_same_rules_as_pr459_and_no_invented_coordinates(self):
        self.assertEqual(NC["rules"]["snap_cells"], 3)
        self.assertEqual(NC["rules"]["tol_area"], 0.10)
        self.assertFalse(NC["replaces_current_geometry"])
        self.assertFalse(NC["official_geometry"])
        prov = json.loads((N.HS / "provenance.json").read_text(encoding="utf-8"))
        self.assertTrue(prov["dir15"]["same_release_as_pr459"] and prov["acc15"]["same_release_as_pr459"])
        cfg = json.loads(N.STATIONS.read_text(encoding="utf-8"))
        for st in cfg["stations"]:
            c = next(x for x in NC["catchments"] if x["id"] == st["id"])
            if st["lat"] is None:
                self.assertEqual(c["status"], "SIN_COORDENADA_DOCUMENTADA")
                self.assertNotIn("imerg_cells", c)
            else:
                self.assertIn(st["coordinate_source"], cfg["sources"])

    def test_expected_statuses(self):
        by = {c["id"]: c for c in NC["catchments"]}
        self.assertEqual(by["PUENTE_NACARA"]["status"], "VALIDADA_EXPERIMENTAL")
        self.assertEqual(by["EL_CIRUELO"]["status"], "VALIDADA_EXPERIMENTAL")
        self.assertTrue(by["EL_CIRUELO"]["cautions"])  # 9 % below the documented area: flagged
        self.assertEqual(by["EL_TIGRE"]["status"], "CANDIDATA_NO_VALIDADA")  # published point off the main stem
        self.assertGreater(by["EL_TIGRE"]["outlet_diagnostic"]["nearest_matching_pixel_km"], 1.5)
        self.assertEqual(by["TAMBOGRANDE"]["status"], "CONSISTENTE_CON_AREA_INDIRECTA")
        self.assertEqual(by["PUENTE_SANCHEZ_CERRO"]["area_km2_pixels"], 7758.5)  # identical to #459
        for bid, lo, hi in (("TUMBES_DESEMBOCADURA", 0.55, 0.80), ("CHIRA_DESEMBOCADURA", 0.35, 0.50)):
            c = by[bid]
            self.assertEqual(c["status"], "VALIDADA_EXPERIMENTAL_SALIDA_DERIVADA")
            self.assertTrue(all(abs(r["ratio"] - 1) <= 0.10 for r in c["area_ratios"]))
            self.assertTrue(lo <= c["territory"]["share_outside_peruvian_uh"] <= hi)

    def test_point_in_polygon(self):
        ring = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
        m = N.points_in_polygon(np.array([1.0, 3.0, 1.9]), np.array([1.0, 1.0, 0.1]), ring)
        self.assertEqual(m.tolist(), [True, False, True])


class ImergHalfHour(unittest.TestCase):
    def test_rebuilds_and_is_consistent_with_daily_final(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(F.main(["--check"]), 0)
        self.assertEqual(FE["daily_consistency"]["verdict"], "COHERENTE")
        for prod in ("GPM_3IMERGHH", "GPM_3IMERGHHE"):
            for w in FE["coverage"][prod].values():
                self.assertTrue(w["complete"])
        self.assertIn("ORACULO_NO_OPERATIVO", FE["role_in_protocol"]["GPM_3IMERGHH"])
        self.assertTrue(FE["comparison_with_flow"].startswith("NO_REALIZADA"))


class Requests(unittest.TestCase):
    def test_requests_are_unsent_drafts_without_personal_data(self):
        t = (ROOT / "research/v09/requests/SOLICITUDES_DATOS_HIDROMETRICOS_BORRADOR_20261031.md").read_text(encoding="utf-8")
        self.assertIn("NO ENVIADOS", t)
        self.assertIn("[NOMBRE", t)
        self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", t))

    def test_sources_checked_do_not_include_new_automated_senamhi_or_pechp_queries(self):
        s = json.loads((ROOT / "config/v09_anticipation_sources_checked_v0_1.json").read_text(encoding="utf-8"))
        for x in s["sources"]:
            self.assertTrue(x["result"])
            if "runner" in x["method"]:
                self.assertNotRegex(str(x["url"]), r"senamhi|regionpiura|pechp")


if __name__ == "__main__":
    unittest.main()
