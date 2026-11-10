"""IRFEN v0.9 · uh_rain_context: lluvia IMERG Early por unidad hidrográfica ANA (investigación).
Reglas de ventana con series de prueba en memoria (nunca archivadas como observación) y comprobaciones sobre la
captura real archivada: unidades, intervalos, duplicados, validación directa de gránulos, aislamiento y guardas."""
import hashlib
import importlib.util
import json
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("uh_ctx", "scripts/v09_build_uh_rain_context.py")
CAP = _load("uh_cap", "scripts/v09_uh_rain_capture.py")
T0 = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)
H = timedelta(minutes=30)
HAVE_REAL = C.OUT.is_file() and C.HALF.is_file()


def slots(n, skip=(), cover=100.0, depth=0.5):
    return {T0 + H * k: dict(depth_mm=None if cover < C.MIN_COVER_PCT else depth, covered_pct=cover,
                             reason=None if cover >= C.MIN_COVER_PCT else "COBERTURA_ESPACIAL_BAJA")
            for k in range(n) if k not in skip}


class WindowRules(unittest.TestCase):
    """In-memory test series only: they exercise the rules and are never written as observations."""

    def test_complete_window_sums_half_hour_depths(self):
        w = C.window(slots(48), {}, set(), T0 + H * 48, 24)
        self.assertEqual(w["status"], "COMPLETA")
        self.assertEqual(w["accumulation_mm"], 24.0)
        self.assertEqual(w["mean_rate_mm_hr"], 1.0)
        self.assertIsNone(w["minimum_known_mm"])

    def test_one_missing_half_hour_makes_the_window_incomplete_never_zero(self):
        s = slots(48, skip={10})
        w = C.window(s, {}, set(s), T0 + H * 48, 24)
        self.assertEqual(w["status"], "INCOMPLETA")
        self.assertIsNone(w["accumulation_mm"])
        self.assertEqual(w["minimum_known_mm"], 23.5)  # lower bound only
        self.assertIn("NO es el acumulado", w["minimum_known_note"])
        self.assertEqual(w["missing"][0]["reason"], "NO_PUBLICADO_EN_EL_CATALOGO")

    def test_window_without_data_is_unknown(self):
        w = C.window({}, {}, set(), T0 + H * 6, 3)
        self.assertEqual(w["status"], "SIN_DATOS")
        self.assertIsNone(w["accumulation_mm"])
        self.assertIsNone(w["minimum_known_mm"])

    def test_low_spatial_coverage_is_not_a_valid_half_hour(self):
        s = slots(2, cover=80.0)
        w = C.window(s, {}, set(s), T0 + H * 2, 1)
        self.assertEqual(w["status"], "SIN_DATOS")
        self.assertEqual({m["reason"] for m in w["missing"]}, {"COBERTURA_ESPACIAL_BAJA"})

    def test_zero_rain_is_kept_as_an_observed_zero(self):
        w = C.window(slots(6, depth=0.0), {}, set(), T0 + H * 6, 3)
        self.assertEqual((w["status"], w["accumulation_mm"]), ("COMPLETA", 0.0))

    def test_latest_complete_window_skips_gaps(self):
        s = slots(20, skip={18})
        x = C.latest_complete(s, T0 + H * 20, T0, 3)
        self.assertEqual(x["end_utc"], (T0 + H * 18).isoformat())
        self.assertEqual(x["age_hours_before_as_of"], 1.0)


class CaptureHelpers(unittest.TestCase):
    def test_granule_name_gives_a_half_open_half_hour(self):
        m = CAP.parse_name("3B-HHR-E.MS.MRG.3IMERG.20261030-S123000-E125959.0750.V07B.HDF5")
        self.assertEqual(m["start"], datetime(2026, 10, 30, 12, 30, tzinfo=timezone.utc))
        self.assertEqual(m["end"] - m["start"], H)
        self.assertEqual(m["version"], "V07B")

    def test_duplicate_start_keeps_one_granule_with_the_highest_version(self):
        a = "3B-HHR-E.MS.MRG.3IMERG.20261030-S120000-E122959.0720.V07A.HDF5"
        b = "3B-HHR-E.MS.MRG.3IMERG.20261030-S120000-E122959.0720.V07B.HDF5"
        t = CAP.parse_name(a)["start"]
        kept, dups = CAP.dedupe([(t, a, None), (t, b, None)])
        self.assertEqual([k[1] for k in kept], [b])
        self.assertEqual(dups[0]["dropped"], a)


@unittest.skipUnless(HAVE_REAL, "real capture not archived yet")
class RealCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.D = json.loads(C.OUT.read_text(encoding="utf-8"))
        cls.HALF = json.loads(C.HALF.read_text(encoding="utf-8"))

    def test_rebuilds_byte_for_byte(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(["--check"]), 0)
        for name, digest in self.D["inputs"].items():
            if digest:
                p = next(x for x in (C.UNITS, C.UNITS_GEO, C.HALF, C.VALID, C.AVISOS, C.NORTH, C.PROVINCES) if x.name == name)
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest, name)

    def test_guards(self):
        for k, v in C.GUARDS.items():
            self.assertEqual(self.D[k], v, k)

    def test_intervals_units_and_no_duplicates(self):
        v = self.D["validation"]
        self.assertEqual(v["duplicate_starts_in_series"], 0)
        self.assertEqual(v["interval_lengths_s"], [1800.0])
        self.assertTrue(all(u.lower() in ("mm/hr", "mm h-1", "mm/hour") for u in v["units_seen"]))
        for g in self.HALF["granules"]:
            self.assertRegex(g["file_sha256"], r"^[0-9a-f]{64}$")
            m = CAP.parse_name(g["granule"])
            self.assertEqual(m["start"].isoformat(), g["start_utc"])
            for code, x in g["units_values"].items():
                if x["rate_mm_hr"] is not None:
                    self.assertAlmostEqual(x["depth_30min_mm"], x["rate_mm_hr"] * 0.5, places=4)
                    self.assertGreaterEqual(x["rate_mm_hr"], 0.0)

    def test_direct_granule_reads_agree(self):
        checks = self.D["validation"]["direct_granule_checks"]
        self.assertGreaterEqual(len(checks), 1)
        for c in checks:
            self.assertTrue(c["ok"], c)

    def test_windows_never_turn_missing_into_zero(self):
        for u in self.D["units"]:
            for w in u["observation"]["windows"]:
                if w["status"] != "COMPLETA":
                    self.assertIsNone(w["accumulation_mm"])
                    self.assertEqual(w["half_hours_valid"] + w["missing_count"], w["half_hours_expected"])
                else:
                    self.assertEqual(w["half_hours_valid"], w["half_hours_expected"])

    def test_context_blocks_stay_separate(self):
        for u in self.D["units"]:
            self.assertEqual(set(u) >= {"observation", "territorial_inference", "official_context", "unknowns"}, True)
            self.assertIn("no causalidad hidráulica", u["territorial_inference"]["relation"])
            for a in u["official_context"]["avisos"]:
                self.assertIn(a["relation"], ("PROVINCIA_LISTADA_INTERSECA_LA_UH", "DEPARTAMENTO_LISTADO_SIN_PROVINCIAS"))
                self.assertIn("no huella", a["caveat"])
            if u["headwaters_outside_peru"]:
                self.assertIn("CABECERA_FUERA_DE_PERU_NO_REPRESENTADA", u["unknowns"]["items"])

    def test_view_is_self_contained_and_outside_site(self):
        html = C.HTML.read_text(encoding="utf-8")
        self.assertFalse(str(C.HTML.relative_to(ROOT)).startswith("site/"))
        self.assertIsNone(re.search(r"(src|href)=\"https?://", html))
        self.assertIn("No es una alerta", html)


class ResearchUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = _load("uh_units", "scripts/v09_build_research_uh_units.py")
        cls.D = json.loads(cls.U.OUT_JSON.read_text(encoding="utf-8"))

    def test_rebuilds_byte_for_byte(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.U.main(["--check"]), 0)

    def test_units_follow_the_declared_rules(self):
        codes = [u["code"] for u in self.D["units"]]
        self.assertEqual(codes[:4], ["1378", "138", "13778", "13779"])
        for u in self.D["units"]:
            full = u["imerg"]["cells_fully_inside"]
            self.assertEqual(u["imerg"]["resolution"], "SUFICIENTE" if full >= 10 else "MARGINAL" if full else "INSUFICIENTE")
            self.assertEqual(u["international_boundary"]["headwaters_outside_peru"], u["code"] in ("1394", "13952", "138"))
            self.assertLess(abs(u["area_km2_spherical"] / u["area_km2_ana"] - 1), 0.02, u["code"])  # ANA area attribute check
            s = u["settlements"]
            self.assertEqual(s["count"], len(s["points"]))
            self.assertEqual(s["near_uh_boundary"], sum(p["near_boundary"] for p in s["points"]))
            g = u["territorial_uncertainty"]["grade"]
            if u["imerg"]["resolution"] == "INSUFICIENTE" or s["share_near_boundary"] > 0.25:
                self.assertEqual(g, "ALTA")
            elif u["imerg"]["resolution"] == "MARGINAL" or u["international_boundary"]["headwaters_outside_peru"] or s["near_uh_boundary"]:
                self.assertEqual(g, "MEDIA")
            else:
                self.assertEqual(g, "BAJA")


class Isolation(unittest.TestCase):
    def test_engine_and_priority_do_not_read_the_research_product(self):
        for script in ("v09_zone_rain_engine.py", "v09_build_dashboard_data.py", "v09_build_territory_bundle.py",
                       "v09_imerg_north_archive.py", "v09_aviso_zone_crossing.py"):
            text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            for token in ("uh_rain", "uh_units", "research/"):
                self.assertNotIn(token, text, (script, token))

    def test_capture_never_writes_operational_files(self):
        text = (ROOT / "scripts/v09_uh_rain_capture.py").read_text(encoding="utf-8")
        self.assertNotIn("data/v09/rain", text.replace("data/v09/rain/…", ""))
        self.assertIn("research/uh_rain", text)


if __name__ == "__main__":
    unittest.main()
