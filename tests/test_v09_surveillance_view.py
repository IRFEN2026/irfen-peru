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

    def test_flow_spearman_is_deterministic_and_symmetric_with_ties(self):
        sem = _load("sem_spearman", "scripts/v09_build_semaforo.py")
        up, down = [5, 5, 5, 9, 9, 12, 12, 12], [12, 12, 12, 9, 9, 5, 5, 5]
        # the same series read in either direction gives the same strength with opposite sign (average ranks); the old
        # ordinal ranks gave +1.0 upward but -0.786 downward for this very series, depending on the tie order
        ru, rd = sem.spearman(list(range(8)), up), sem.spearman(list(range(8)), down)
        self.assertAlmostEqual(ru, -rd, places=12)
        self.assertAlmostEqual(ru, 0.944911182523068, places=12)  # standard Spearman with ties (scipy.stats.spearmanr)
        self.assertEqual(sem.spearman(list(range(6)), [1, 2, 3, 4, 5, 6]), 1.0)
        ys = [3, 1, 3, 3, 2, 2, 7, 1, 3, 3, 5, 5]
        r = sem.spearman(list(range(len(ys))), ys)
        self.assertAlmostEqual(r, -sem.spearman(list(range(len(ys))), [-v for v in ys]), places=12)  # symmetric
        self.assertEqual(len({sem.spearman(list(range(len(ys))), ys) for _ in range(20)}), 1)
        self.assertEqual(list(sem._avg_ranks([2, 1, 2, 3])), [1.5, 0.0, 1.5, 3.0])
        self.assertNotIn("np.argsort(np.argsort(", (ROOT / "scripts/v09_build_semaforo.py").read_text(encoding="utf-8"))

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
            self.assertEqual([x["code"] for x in sm["rules"]["states"]], ["ROJO", "NARANJA", "AMARILLO", "VERDE", "GRIS"])
            self.assertIs(next(x for x in sm["rules"]["states"] if x["code"] == "NARANJA")["operational"], False)
            self.assertIn("Ni la lluvia ni un aviso producen rojo", sm["rules"]["states"][0]["rule_es"])
            self.assertIn("no garantiza", PAGE)  # a verified report says the event happened, not that it is still active
            self.assertIn("no evidencia de crecida ni de activación", next(x for x in sm["rules"]["states"] if x["code"] == "AMARILLO")["rule_es"])
            self.assertIn("Un aviso regional vigente no cambia el gris", next(x for x in sm["rules"]["states"] if x["code"] == "GRIS")["rule_es"])
            self.assertIn("nunca se convierte en verde", next(x for x in sm["rules"]["states"] if x["code"] == "GRIS")["rule_es"])
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

    def test_recent_rain_summary_is_per_catchment_for_the_11_departments(self):
        cr = D["rain"]["catchments"]
        self.assertEqual(cr["status"], "OK")
        self.assertEqual(set(cr["departments"]), set(D["coast_departments"]))
        self.assertEqual(sum(len(v) for v in cr["departments"].values()), 134)
        self.assertIn("No es una media departamental", cr["note_es"])
        self.assertEqual(cr["kind"], "ESTIMACION_SATELITAL")
        for dep, rows in cr["departments"].items():
            self.assertTrue(rows, dep)  # every coastal department has at least one delineated river catchment
            for r in rows:
                for k, v in r["windows"].items():
                    self.assertEqual(v is None, not r["complete"][k], (r["id"], k))  # incomplete -> null, never 0

    def test_river_points_without_a_verified_catchment_are_named_and_carry_no_rain(self):
        cr = D["rain"]["catchments"]
        named = {x["id"]: dep for dep, rows in cr["without_catchment"].items() for x in rows}
        rivers = {c["id"] for c in D["semaforo"]["checkpoints"] if c["type"] == "rio"}
        listed = {r["id"] for rows in cr["departments"].values() for r in rows}
        self.assertEqual(set(named), rivers - listed)
        self.assertEqual(named, {"TUM-R-ZARUMILLA-MEDIO": "TUMBES", "LIM-R-RIMAC-ALTO": "LIMA",
                                 "ICA-R-SAN_JUAN-BAJO": "ICA", "ARE-R-TAMBO-BAJO": "AREQUIPA"})
        for rows in cr["without_catchment"].values():
            for x in rows:
                self.assertNotIn("windows", x)  # no rain value is attached, unknown is not 0 mm
                self.assertIn("pendiente de verificación", x["reason_es"])

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
        # the whole coast is in the pilot (Tumbes–Tacna); saturation is handled in the page (department aggregates at national
        # zoom, checked in the browser test), never by dropping documented points
        self.assertEqual({c["department"] for c in sm["checkpoints"]}, set(D["coast_departments"]))
        self.assertTrue(all(c["status"] == "PILOTO_ACTIVO" for c in sm["coverage"]))
        zone_kind = {f["properties"]["zone_id"]: f["properties"].get("kind") for f in D["rain"]["north_zones"]["zones"]["features"]}
        for c in sm["checkpoints"]:  # an administrative (province) mean never colours a point
            if (c.get("rain_ref") or "").startswith("zone:"):
                self.assertEqual(zone_kind[c["rain_ref"][5:]], "BASIN", c["id"])
        for dep, rivers in (("TUMBES", {"TUMBES", "ZARUMILLA"}), ("PIURA", {"PIURA", "CHIRA"})):
            pts = [c for c in sm["checkpoints"] if c["department"] == dep and c["type"] == "rio"]
            self.assertEqual({c["system_id"] for c in pts}, rivers)
        hyd = json.loads((ROOT / "data/v09/research/semaforo/checkpoint_hydrology_v0_1.json").read_text(encoding="utf-8"))
        delineated = {r["id"] for r in hyd["checkpoints"] if r["q3_contributing_area"]["status"] == "APORTACION_DELIMITADA_EXPERIMENTAL"}
        for c in sm["checkpoints"]:
            if c["type"] != "rio":
                self.assertFalse((c.get("rain_ref") or "").startswith("catchment:"), c["id"])  # population points: never a catchment
                continue
            ref = c.get("rain_ref")
            if ref and ref.startswith("catchment:"):
                # a river uses only the live rain of its OWN delineated contributing area (hash-locked capture target)
                self.assertEqual(ref, "catchment:" + c["id"])
                self.assertIn(c["id"], delineated)
            elif c["department"] not in ("LAMBAYEQUE", "LA LIBERTAD"):
                # no own area and no basin zone: grey with the reason, never the local cell
                self.assertIsNone(ref, c["id"])
                self.assertEqual(c["state_at_cutoff"]["state"], "GRIS", c["id"])
                self.assertTrue(any("gris" in x for x in c["limitations"]), c["id"])
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
        fake = dict(system_id=river["system_id"], verified=True, source_kind="OFICIAL", observed_at_utc=cut.isoformat(),
                    source_url="https://portal.indeci.gob.pe/ejemplo")
        self.assertEqual(sem.evaluate(river, dict(S, confirmations=[fake]), cut)["state"], "ROJO")
        self.assertNotEqual(sem.evaluate(river, dict(S, confirmations=[dict(fake, source_url=None)]), cut)["state"], "ROJO")  # no source: pending
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
            # the department summary shows recent rain per contributing area, never a departmental mean of an old snapshot
            self.assertNotIn("media / máx", r["checks"]["summary_header"])
            self.assertIn("por cuenca aportante", r["checks"]["summary_header"])
            self.assertEqual(r["checks"]["summary_freshness_tags"], 11)
            self.assertTrue(set(r["checks"]["summary_freshness_states"]) <= {"RECIENTE", "CADUCADA", "AUSENTE", "FECHA_INCONSISTENTE"})
            self.assertEqual((r["checks"]["summary_historical_sections"], r["checks"]["summary_historical_open"]), (1, False))
            self.assertGreaterEqual(r["checks"]["summary_caveat"], 1)
            cr = D["rain"]["catchments"]
            self.assertEqual(r["checks"]["dept_catchment_rows"], len(cr["departments"]["PIURA"]))
            self.assertTrue(r["checks"]["leaflet"], "Leaflet not loaded (network to unpkg?)")
            self.assertGreater(r["checks"]["aviso_highlight_links"], 0)
            self.assertEqual(r["checks"]["river_chart"], 1)
            sm = r["checks"].get("semaforo")
            if sm:
                self.assertEqual(sm["js_vs_python"]["mismatches"], 0, sm["js_vs_python"]["first"])
                self.assertEqual(len(set(sm["selfcheck"].split("/"))), 1, sm["selfcheck"])
                self.assertTrue(sm["guard"] and sm["popup_fields"] and sm["pending_dep_msg"])
                # national scale: one aggregate per department, no individual points; a department shows its points
                ndep = len({c["department"] for c in D["semaforo"]["checkpoints"]})
                self.assertEqual((sm["national_aggregates"], sm["national_points"]), (ndep, 0))
                self.assertEqual(sm["dep_aggregates"], 0)
                self.assertEqual(sm["dep_points"], sum(c["department"] == "LIMA" for c in D["semaforo"]["checkpoints"]))
                self.assertGreater(sm["catchment_outline"], 0)


if __name__ == "__main__":
    unittest.main()
