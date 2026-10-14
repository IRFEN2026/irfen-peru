"""IRFEN v0.9 territorial view (costa norte and Rímac): only admitted, SHA-verified geometry is drawn; quebrada
components are drawn or declared pending with a reason; observations, estimates and forecasts are labelled apart;
missing or old rain is never shown as zero. Offline; the browser part runs where Chromium is available."""
import functools
import hashlib
import http.server
import importlib.util
import json
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_build_territory_bundle", ROOT / "scripts/v09_build_territory_bundle.py")
T = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)
BUNDLE = json.loads(T.OUT.read_text(encoding="utf-8"))
CATALOG = json.loads(T.MAP_LAYERS.read_text(encoding="utf-8"))["map_semantics"]
FEATS = BUNDLE["geometries"]["features"]
HTML = (ROOT / "site/v09/territorio.html").read_text(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as _p:
        _p.chromium.launch(args=["--no-proxy-server"]).close()
    BROWSER = True
except Exception:  # noqa: BLE001
    BROWSER = False


class Bundle(unittest.TestCase):
    def test_guards_and_reproducible(self):
        for k, v in T.GUARDS.items():
            self.assertEqual(BUNDLE[k], v, k)
        inputs_now = {k: T.sha(p) for k, p in (("map_layers", T.MAP_LAYERS), ("registry", T.REGISTRY), ("zones", T.ZONES), ("rain_state", T.RAIN_STATE),
                                                ("imerg_v08", T.IMERG_V08), ("goes_v08", T.GOES_V08), ("geos_v08", T.GEOS_V08),
                                                ("cendehua", T.CENDEHUA), ("inventory", T.INVENTORY))}
        if BUNDLE["inputs"] != inputs_now:
            self.skipTest("an input changed after the committed bundle; the v0.9 workflows rebuild it")
        self.assertEqual(T.main(["--check"]), 0)

    def test_only_admitted_or_verified_geometry_is_drawn(self):
        admitted = {f["entity_id"]: f for f in CATALOG["features"] if f.get("map_eligible")}
        withheld = {e["entity"] for e in CATALOG["entities"] if not e.get("map_eligible")}
        zones = {z["zone_id"]: z for z in json.loads(T.ZONES.read_text(encoding="utf-8"))["zones"]}
        for f in FEATS:
            p = f["properties"]
            self.assertNotIn(p["id"], withheld, p["id"])
            if p["semantic_role"] == "V09_SURVEILLANCE_BASIN":
                z = zones[p["id"].split("#")[0]]
                self.assertEqual(hashlib.sha256((ROOT / z["geometry_path"]).read_bytes()).hexdigest(), z["geometry_sha256"])
            elif p["semantic_role"] == "INEI_REFERENTIAL_PROVINCE":
                self.assertEqual(p["layer"], "contexto")
            else:
                self.assertIn(p["id"], admitted, p["id"])
                src = admitted[p["id"]]
                self.assertEqual(hashlib.sha256((ROOT / "site" / src["path"]).read_bytes()).hexdigest(), src["file_sha256"])

    def test_layer_semantics(self):
        for f in FEATS:
            p = f["properties"]
            if p["map_category"] == "REGULATORY_FAJA_MARGINAL":
                self.assertEqual(p["layer"], "contexto")  # a faja marginal is not a channel nor an affected area
            if p["map_category"] == "DOCUMENT_CONTEXT":
                self.assertEqual(p["layer"], "contexto")
                self.assertFalse(p["default_visible"])
            if p["semantic_role"] in ("DEM_D8_CANDIDATE_CATCHMENT", "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED"):
                self.assertEqual((p["layer"], p["evidence"]), ("areas_colectoras", "GEOMETRIA_CANDIDATA"))
            if p["semantic_role"] == "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED":
                self.assertFalse(p["default_visible"])
            if p.get("node_semantics") == "REPRODUCIBLE_DERIVED":
                self.assertEqual(p["evidence"], "GEOMETRIA_CANDIDATA")
            self.assertIn(p["region"], ("costa_norte", "rimac"))
        rimac_parents = {f["properties"]["parent_id"] for f in FEATS if f["properties"]["region"] == "rimac"}
        self.assertFalse({"lima_norte_chillon_bajo", "lima_sur_mala", "lima_este_lurin_cieneguilla"} & rimac_parents)

    def test_quebradas_components_drawn_or_pending(self):
        ids = {f["properties"]["id"] for f in FEATS}
        for q in BUNDLE["quebradas"]:
            for key in ("catchment", "channel", "discharge", "exposure"):
                c = q["components"][key]
                self.assertTrue(set(c["drawn"]) <= ids, q["quebrada_id"])
                self.assertEqual(c["missing_from_catalogue"], [], f"{q['quebrada_id']} {key} references a non-admitted entity")
                if not c["drawn"]:
                    self.assertTrue((q.get("pending") or {}).get(key), f"{q['quebrada_id']}: empty {key} without a reason")
                    self.assertEqual(q["component_status"][key], "PENDIENTE")
            for alt in q["components"].get("catchment_alternatives", {}).get("drawn", []):
                self.assertNotIn(alt, q["components"]["catchment"]["drawn"])  # an alternative is never the catchment

    def test_main_basin_is_never_a_quebrada_catchment(self):
        basin_roles = {"OFFICIAL_ANA_HYDROGRAPHIC_UNIT", "CURRENT_INSTITUTIONAL_N7_HYDROGRAPHIC_UNIT", "V09_SURVEILLANCE_BASIN"}
        roles = {f["properties"]["id"]: f["properties"]["semantic_role"] for f in FEATS}
        for q in BUNDLE["quebradas"]:
            for c in q["components"]["catchment"]["drawn"]:
                if roles[c] in basin_roles:  # only an official unit that carries the quebrada's own name
                    self.assertEqual(q.get("catchment_kind"), "OFFICIAL_ANA_UNIT_NAMED_AFTER_THE_QUEBRADA", q["quebrada_id"])

    def test_rain_carries_its_evidence_class(self):
        for zr in BUNDLE["zone_rain"].values():
            self.assertEqual((zr["imerg"]["evidence"], zr["goes"]["evidence"], zr["geos"]["evidence"]),
                             ("ESTIMACION_SATELITAL", "ESTIMACION_NO_VALIDADA", "PRONOSTICO"))
            for a in zr["avisos"]:
                self.assertEqual(a["evidence"], "AVISO_OFICIAL")
            for w in zr["imerg"]["windows"].values():
                self.assertTrue("accum_mm" in w or w.get("status") == "NO_DISPONIBLE")
        hua = next(q for q in BUNDLE["quebradas"] if q["quebrada_id"] == "huaycoloro")
        self.assertEqual(hua["rain_v08"]["in_situ"]["evidence"], "OBSERVACION_IN_SITU")
        self.assertIsNone(hua["rain_v08"]["in_situ"].get("coordinates"))

    def test_inventory_matches_the_national_inventory(self):
        rows = json.loads(T.INVENTORY.read_text(encoding="utf-8"))
        rows = rows.get("rows") or next(v for v in rows.values() if isinstance(v, list) and v and isinstance(v[0], dict) and "inventory_id" in v[0])
        for r in BUNDLE["inventory"]:
            if r["region"] == "costa_norte":
                n = sum(1 for x in rows if x["department"] == r["zone"])
            else:
                n = sum(1 for x in rows if x["corridor"] == "CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA")
            self.assertEqual(r["quebradas_identificadas"], n, r["zone"])
            self.assertEqual(r["geometrias_pendientes"]["quebradas_sin_geometria"],
                             r["quebradas_identificadas"] - r["quebradas_con_geometria_reproducible_en_inventario"])
        self.assertEqual([r["zone"] for r in BUNDLE["inventory"]], ["Tumbes", "Piura", "Lambayeque", "La Libertad", "Rímac (Carretera Central)"])


class Page(unittest.TestCase):
    def test_shared_rules_identical_to_the_panel(self):
        index = (ROOT / "site/v09/index.html").read_text(encoding="utf-8")
        block = index[index.index("/* SHARED-RULES-BEGIN"):index.index("/* SHARED-RULES-END */") + len("/* SHARED-RULES-END */")]
        self.assertIn(block, (ROOT / "site/v09/shared_rules.js").read_text(encoding="utf-8"))

    def test_page_is_self_contained_and_honest(self):
        self.assertIn('<script src="shared_rules.js"></script>', HTML)
        self.assertNotIn("http://", HTML.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", HTML)
        self.assertIn("no es lluvia cero", HTML)
        self.assertIn("escala visual, no umbral", HTML)
        self.assertIn('name="robots" content="noindex"', HTML)
        self.assertIn("imergUsableAt(", HTML)


@unittest.skipUnless(BROWSER, "Playwright/Chromium not installed; runs in workflow v09-dashboard-browser-test.yml")
class Browser(unittest.TestCase):
    def test_navigation_both_regions(self):
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT / "site")))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        origin = f"http://127.0.0.1:{srv.server_port}/"
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(args=["--no-proxy-server"])
                page = b.new_page(viewport=dict(width=1400, height=1000))
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin) else r.abort())
                page.goto(origin + "v09/territorio.html")
                page.wait_for_selector("#map svg path")
                page.click("[data-q=bocapan]")
                self.assertGreater(page.locator("#map .hl").count(), 0)
                self.assertIn("área colectora", page.inner_text("#detail").lower())
                page.click("nav [data-region=rimac]")
                page.click("[data-q=quirio]")
                detail = page.inner_text("#detail").lower()
                self.assertIn("pendiente", detail)  # Quirio has no selected catchment: declared, not drawn
                self.assertIn("no son el área colectora", detail)
                self.assertEqual(page.locator("#map .hl").count(), 5)  # 3 alternatives + anchor + D8 node
                page.click("[data-q=huaycoloro]")
                self.assertIn("observación in situ", page.inner_text("#detail").lower())
                page.click("nav [data-view=inventario]")
                self.assertIn("quebradas identificadas", page.inner_text("#inv-table").lower())
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
