"""IRFEN v0.9 · vista privada unificada de vigilancia costera (site/v09/vigilancia.html + surveillance_view_v0_1.json).

Comprueba guardas, reproducibilidad del paquete, cobertura Tumbes–Tacna, ventanas de lluvia sin ceros inventados,
atribución de avisos a SENAMHI vía INDECI/COEN, separación de fenómenos, fechas y calidad por fuente, puerta de
publicación y, si hay Chromium, el recorrido en escritorio y móvil."""
import importlib.util
import io
import json
import os
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("sv", "scripts/v09_build_surveillance_view.py")
D = json.loads(B.OUT.read_text(encoding="utf-8"))
PAGE = (ROOT / "site/v09/vigilancia.html").read_text(encoding="utf-8")


class Bundle(unittest.TestCase):
    def test_rebuilds_byte_for_byte(self):
        # Research Preview 1 freeze: every released file and input matches the SHA-256 recorded in the manifest.
        # When the PR is validated merged with a newer `main`, the bot's captures change some inputs: that is not the
        # frozen release, so the reproducibility checks are skipped (they hold on the tag itself).
        import hashlib
        cand = ROOT / "research/v09/V091_CANDIDATE_MANIFEST.json"  # v0.9.1 candidate (post-freeze branch) takes precedence
        man = json.loads((cand if cand.is_file() else ROOT / "research/v09/RESEARCH_PREVIEW_1_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertFalse(man["public_alerting"] or man["predictive_engine_enabled"] or man["merged_into_main"])
        outputs = {"site/v09/vigilancia.html", "site/data/v09/surveillance_view_v0_1.json",
                   "research/v09/private_demo/irfen_vigilancia_privada.html", "scripts/v09_build_surveillance_view.py",
                   "scripts/v09_build_surveillance_demo.py", "qa/replay_tools/v09_surveillance_view_smoke.py",
                   "scripts/v09_extract_reference_basemap.py", "data/v09/sources/natural_earth_reference/peru_reference_v0_1.json",
                   "research/v09/private_demo/irfen_vigilancia_privada_v091.html", "scripts/v09_ign_hydrography_capture.py",
                   "scripts/v09_ign_hydro_coverage_report.py", "data/v09/research/hydro/ign_coastal_coverage_v0_1.json",
                   "scripts/v09_build_semaforo.py", "data/v09/research/semaforo/semaforo_v0_1.json", "config/v09_semaforo_rules_v0_1.json",
                   "config/v09_semaforo_systems_v0_1.json", "config/v09_semaforo_confirmations_v0_1.json"}
        sha = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in man["files"]}
        moved = [rel for rel in man["files"] if rel not in outputs and sha[rel] != man["files"][rel]]
        if moved:
            self.skipTest(f"inputs newer than the frozen Research Preview 1: {moved[:4]}")
        for rel in man["files"]:
            self.assertEqual(sha[rel], man["files"][rel], rel)
        with redirect_stdout(io.StringIO()):
            if (ROOT / "scripts/v09_build_semaforo.py").is_file():
                self.assertEqual(_load("sem", "scripts/v09_build_semaforo.py").main(["--check"]), 0)
            self.assertEqual(B.main(["--check"]), 0)

    def test_guards(self):
        for k, v in B.GUARDS.items():
            self.assertEqual(D[k], v, k)
        self.assertFalse(D["predictive_engine_enabled"])
        self.assertFalse(D["notifications_enabled"])
        self.assertIn("no significa ausencia de peligro", D["disclaimer_es"])
        sm = D.get("semaforo", {})
        if sm.get("status") == "OK":  # experimental semáforo: never an official alert, never predictive, no thresholds
            for k in ("official_alert", "public_alerting", "notifications_enabled", "predictive", "merged_into_main"):
                self.assertIs(sm[k], False, k)
                self.assertIs(sm["rules"].get(k, False), False, k)
            self.assertEqual((sm["deployment_status"], sm["test_mode"]), ("RESEARCH_ONLY", "TEST_ONLY"))
            self.assertEqual([x["code"] for x in sm["rules"]["states"]], ["ROJO", "AMARILLO", "VERDE", "GRIS"])
            self.assertIn("Ni la lluvia ni un aviso producen rojo", sm["rules"]["states"][0]["rule_es"])
            self.assertIn("no garantiza", PAGE)  # a verified report says the event happened, not that it is still active
            self.assertIn("no evidencia de crecida ni de activación", sm["rules"]["states"][1]["rule_es"])
            self.assertIn("Un aviso regional vigente no cambia el gris", sm["rules"]["states"][3]["rule_es"])
            self.assertIn("nunca se convierte en verde", sm["rules"]["states"][3]["rule_es"])
            self.assertIs(sm["rules"]["territorial_context"]["affects_colour"], False)
            self.assertEqual(sm["rules"]["flood_evidence"]["status"], "NO_DISPONIBLE")
            for c in sm["confirmations"]["confirmations"]:  # the only way to red: a sourced, verified record
                self.assertTrue(c.get("source_url") and c.get("source_title") and c.get("observed_at_utc"), c)
            self.assertIn("no es una alerta oficial", PAGE)
            self.assertIn('register("semaforo","Semáforo de seguimiento (experimental, no oficial)"', PAGE)
            self.assertIn("window.IRFEN_SEMAFORO_EVAL", PAGE)

    def test_whole_coast_tumbes_to_tacna(self):
        self.assertEqual(D["coast_departments"][0], "TUMBES")
        self.assertEqual(D["coast_departments"][-1], "TACNA")
        self.assertEqual(len(D["coast_departments"]), 11)
        self.assertEqual(set(D["departments"]), set(D["coast_departments"]))
        if D["admin"]["status"] == "OK":
            self.assertEqual({f["properties"]["id"] for f in D["admin"]["departments"]["features"]}, set(D["coast_departments"]))
            self.assertEqual(D["admin"]["source"]["legal_status"], "REFERENTIAL_CENSUS_LIMITS_NOT_LEGAL_DEMARCATION")

    def test_ign_hydrography_is_reference_not_hazard(self):
        h = D["hydro_ign"]
        if h["status"] != "OK":
            self.skipTest("no IGN capture")
        self.assertTrue(h["source"]["complete"])
        self.assertIn("No es zona inundable", h["source"]["note"])
        feats = h["lines"]["features"]
        self.assertGreater(len(feats), 500)
        for f in feats:
            p = f["properties"]
            self.assertIn(p["c"], ("RP", "RS", "QH", "QS", "RX"))
            self.assertTrue(set(p["d"]) <= set(D["coast_departments"]) and p["d"])
            self.assertIn(p["r"], ("P", "I"))
            if p["n"]:
                self.assertNotRegex(p["n"], r"[a-zñ][ÁÉÍÓÚÑ]")  # IGN casing normalised for display; raw name kept
        for dep in ("LA LIBERTAD", "ANCASH", "LIMA", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"):
            self.assertGreater(sum(h["per_department"][dep]["by_class"].values()), 20, dep)
        cov = _load("cov", "scripts/v09_ign_hydro_coverage_report.py")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cov.main(["--check"]), 0)
        self.assertIn('register("hydro","Ríos y quebradas IGN 1:500.000 (incorporados)"', PAGE)
        self.assertIn("no es zona inundable ni indicador de peligro", PAGE)

    def test_rain_windows_never_invent_zeros(self):
        self.assertEqual(D["rain"]["windows_h"], [1, 3, 6, 24, 72])
        c = D["rain"]["coast"]
        if c["status"] == "OK":
            for k, w in c["windows"].items():
                if w["status"] == "COMPLETA":
                    self.assertEqual(len(w["values"]), len(c["cells"]))
                    self.assertEqual(w["half_hours"][0], w["half_hours"][1])
                else:
                    self.assertIsNone(w["values"])
            for dep, st in c["department_stats"].items():
                for w in st.values():
                    if w["valid_cells"] < w["cells"]:
                        self.assertIsNone(w["mean_mm"])
        for f in D["rain"]["north_zones"]["zones"]["features"]:
            for w in f["properties"]["windows"].values():
                self.assertEqual(w["mm"] is None, w["status"] != "COMPLETA")

    def test_avisos_attributed_and_classified(self):
        self.assertTrue(D["avisos"])
        for a in D["avisos"]:
            self.assertIn("SENAMHI reproducido por INDECI/COEN", a["attribution"])
            self.assertIn(a["category"], ("LLUVIA_INTENSA", "ACTIVACION_QUEBRADAS", "METEOROLOGICO", "OTRO"))
            if a["url"]:
                self.assertTrue(a["url"].startswith("https://portal.indeci.gob.pe/"), a["url"])
            if not a["level"]:
                self.assertTrue(a["level_note"])

    def test_three_phenomena_and_gaps_are_declared(self):
        self.assertEqual({p["id"] for p in D["phenomena"]}, {"CRECIDA_RIO", "INUNDACION_PLUVIAL", "ACTIVACION_QUEBRADAS"})
        self.assertTrue(D["rivers"]["realtime_flow"].startswith("NO_DISPONIBLE"))
        self.assertTrue(D["rivers"]["hydrological_avisos"].startswith("NO_INTEGRADOS"))
        self.assertGreaterEqual(len(D["pending"]), 5)
        for s in D["sources"]:
            self.assertTrue(s["quality"])

    def test_river_history_is_measured_daily_mean_only(self):
        for h in D["rivers"]["history"]:
            self.assertIn("CAUDAL_MEDIO_DIARIO", h["statistic"])
        for t in D["rivers"]["anticipation_status"]:
            self.assertIn(t["status"], ("NO_EVALUABLE", "FUERA_DE_ALCANCE"))

    def test_settlements_are_documentary_locations(self):
        self.assertIn("no es la quebrada", D["quebradas"]["ana_source"]["note"])
        self.assertGreater(len(D["quebradas"]["ana_points"]), 500)
        sm = D.get("semaforo", {})
        if sm.get("status") != "OK":
            return
        # semáforo checkpoints sit on documented geometry only: an IGN vertex (rivers) or an ANA documentary point (quebradas)
        import gzip
        from datetime import timedelta
        ign = json.loads(gzip.decompress((ROOT / "data/v09/sources/ign_hidrografia_500k/rios_quebradas_costa.geojson.gz").read_bytes()))
        verts = {(round(x, 5), round(y, 5)) for f in ign["features"] for ln in ([f["geometry"]["coordinates"]] if f["geometry"]["type"] == "LineString"
                                                                                   else f["geometry"]["coordinates"]) for x, y, *_ in ln}
        ana = {(p["lon"], p["lat"]) for p in D["quebradas"]["ana_points"]}
        lam = [c for c in sm["checkpoints"] if c["department"] == "LAMBAYEQUE"]
        self.assertEqual({c["system_id"] for c in lam if c["type"] == "rio"}, {"LA_LECHE", "CHANCAY_REQUE", "ZANA"})
        self.assertEqual({c["sector"] for c in lam if c["type"] == "rio"}, {"alto", "medio", "bajo"})
        for s in next(c for c in sm["coverage"] if c["department"] == "LAMBAYEQUE")["river_systems"]:
            # upstream/downstream only from physical evidence (mouth on the coast or HydroSHEDS flow accumulation), never east→west
            self.assertTrue(s["orientation"]["status"].startswith("VERIFICADA"), s)
            self.assertTrue(set(s["orientation"]["evidence"]) <= {"DESEMBOCADURA", "RED_DE_FLUJO_HYDROSHEDS"} and s["orientation"]["evidence"])
        self.assertTrue(all(c["sector_verified"] for c in lam if c["type"] == "rio"))
        self.assertTrue(any(c["type"] in ("quebrada", "mixto") for c in lam))
        self.assertLessEqual(len(sm["checkpoints"]), 60)  # not saturating the map
        for c in sm["checkpoints"]:
            for k in ("id", "name", "type", "system", "department", "lat", "lon", "sources", "limitations", "location_basis", "state_at_cutoff"):
                self.assertIn(k, c)
            self.assertIn(c["type"], ("rio", "quebrada", "mixto"))
            self.assertIn((c["lon"], c["lat"]), verts if c["type"] == "rio" else ana, c["id"])
            self.assertEqual(c["location_kind"], "CAUCE_IGN" if c["type"] == "rio" else "POBLADO_ANA")
            if c["location_kind"] == "POBLADO_ANA":
                self.assertIn("no un punto del cauce", c["location_basis"])
            if c["type"] != "rio":
                self.assertTrue(c["members"] and all(m.startswith("ANA2017-") for m in c["members"]))
        self.assertEqual({c["department"] for c in sm["coverage"]}, set(D["coast_departments"]))
        # logic: red only with a verified confirmation; missing or stale data never turns green
        sem = _load("sem", "scripts/v09_build_semaforo.py")
        S = dict(rules=sm["rules"], confirmations=[], aviso_check_utc=sm["aviso_check_utc"], avisos=sm["avisos"], rain_refs=sm["rain_refs"])
        cut = sem.iso(sm["cutoff_utc"])
        regional_stale = 0
        for c in sm["checkpoints"]:
            self.assertEqual(sem.evaluate(c, S, cut)["state"], c["state_at_cutoff"]["state"])
            for h in (0, 13, 72, 24 * 40):
                t = cut + timedelta(hours=h)
                full, bare = sem.evaluate(c, S, t), sem.evaluate(dict(c, avisos=[]), S, t)
                self.assertEqual(full["state"], bare["state"], (c["id"], h))  # avisos are context: they never change the colour
                if h:
                    self.assertEqual(full["state"], "GRIS", (c["id"], h))  # stale local data → grey, even with a regional aviso in force
                    regional_stale += bool(full["context"]["vigentes"])
                if full["state"] == "AMARILLO":
                    self.assertEqual(full["rule"], "LLUVIA_SATELITAL")
            self.assertNotEqual(sem.evaluate(dict(c, avisos=[], rain_ref=None), S, cut)["state"], "VERDE")
            self.assertNotEqual(sem.evaluate(c, S, cut + timedelta(days=40))["state"], "ROJO")
        self.assertGreater(regional_stale, 0)  # the audited case (regional aviso in force, local data stale) is exercised
        river = next(c for c in sm["checkpoints"] if c["type"] == "rio")
        fake = dict(system_id=river["system_id"], verified=True, source_kind="OFICIAL", observed_at_utc=cut.isoformat())
        self.assertEqual(sem.evaluate(river, dict(S, confirmations=[fake]), cut)["state"], "ROJO")
        self.assertNotEqual(sem.evaluate(river, dict(S, confirmations=[dict(fake, verified=False)]), cut)["state"], "ROJO")
        self.assertNotEqual(sem.evaluate(river, dict(S, confirmations=[fake]), cut + timedelta(hours=73))["state"], "ROJO")


class Page(unittest.TestCase):
    def test_guards_disclaimers_and_safety(self):
        self.assertIn('<meta name="robots" content="noindex,nofollow">', PAGE)
        self.assertIn("La ausencia de datos no significa ausencia de peligro", PAGE)
        self.assertIn('D.activation_gate!=="BLOCKED"', PAGE)
        self.assertIn("intervalos de visualización, no umbrales", PAGE)
        self.assertIn("IRFEN no emite avisos", PAGE)
        self.assertNotRegex(PAGE, r"\binnerHTML\s*=\s*[^;]*\b(a|p|s|f)\.(description|name|phenomenon)\b(?![^;]*safe)")
        self.assertIn('rel="noopener noreferrer"', PAGE)
        self.assertNotIn("Notification", PAGE)
        self.assertNotIn("navigator.serviceWorker", PAGE)

    def test_scripts_only_pinned_leaflet_with_integrity(self):
        srcs = re.findall(r'<script src="([^"]+)"', PAGE)
        self.assertEqual(srcs, ["https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"])
        self.assertIn('integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="', PAGE)

    def test_inline_bundle_supported_for_single_file_demo(self):
        self.assertIn('document.getElementById("bundle")', PAGE)
        self.assertIn("../data/v09/surveillance_view_v0_1.json", PAGE)

    def test_internal_links_exist(self):
        for href in set(re.findall(r'href="([a-z_]+\.html)', PAGE)):
            self.assertTrue((ROOT / "site/v09" / href).is_file(), href)

    def test_publication_gate_withholds_the_view(self):
        g = _load("gate", "scripts/v09_pages_publication_gate.py")
        self.assertIn("site/v09/vigilancia.html", g.TERRITORY_PATHS)
        self.assertIn("site/data/v09/surveillance_view_v0_1.json", g.TERRITORY_PATHS)
        cfg = json.loads((ROOT / "config/v09_public_demo_v0_1.json").read_text(encoding="utf-8"))
        self.assertIsNot(cfg.get("publish_v09_territory"), True)


@unittest.skipUnless(importlib.util.find_spec("playwright"), "playwright not installed")
class Browser(unittest.TestCase):
    def test_desktop_and_mobile_journey(self):
        smoke = _load("smoke", "qa/replay_tools/v09_surveillance_view_smoke.py")
        local = os.environ.get("IRFEN_LOCAL_LEAFLET")
        out = Path(os.environ.get("IRFEN_SMOKE_OUT", "/tmp/irfen_surveillance_smoke"))
        try:
            rep = smoke.run(out, Path(local) if local else None)
        except Exception as e:  # noqa: BLE001
            if "Executable doesn't exist" in str(e):
                self.skipTest("Chromium not installed")
            raise
        for r in rep["runs"]:
            self.assertEqual(r["errors"], [], r["name"])
            self.assertEqual(r["broken_internal_links"], [], r["name"])
            self.assertFalse(r["checks"]["overflow_x"], r["name"])
            self.assertEqual(r["checks"]["summary_rows"], 11)
            self.assertTrue(r["checks"]["leaflet"], "Leaflet not loaded (network to unpkg?)")
            self.assertGreater(r["checks"]["aviso_highlight_links"], 0)
            self.assertEqual(r["checks"]["river_chart"], 1)
            sm = r["checks"].get("semaforo")
            if sm:
                self.assertEqual(sm["js_vs_python"]["mismatches"], 0, sm["js_vs_python"]["first"])
                self.assertEqual(len(set(sm["selfcheck"].split("/"))), 1, sm["selfcheck"])
                self.assertTrue(sm["guard"] and sm["popup_fields"] and sm["pending_dep_msg"])


if __name__ == "__main__":
    unittest.main()
