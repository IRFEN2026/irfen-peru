"""IRFEN v0.9 territorial view (costa norte and Rímac): only admitted, SHA-verified geometry is drawn; quebrada
components are drawn or declared pending with a reason; observations, estimates and forecasts are labelled apart;
missing or old rain is never shown as zero. Offline; the browser part runs where Chromium is available."""
import functools
import hashlib
import http.server
import importlib.util
import json
import re
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
        changed = T.inputs_changed(BUNDLE["inputs"])
        if changed:  # the v0.9 rain and capture workflows rebuild the bundle when an input moves
            self.skipTest(f"inputs changed after the committed bundle: {changed[:5]}")
        self.assertEqual(T.main(["--check"]), 0)

    def test_inputs_cover_every_file_read(self):
        for path in ("site/data/map_layers.json", "config/v09_territory_quebradas_v0_1.json", "data/v09/surveillance/zone_rain_state_v0_1.json",
                     "config/phase2_national_inventory_completeness_audit_v0_1.json", "data/v09/admin_boundaries/latest.json"):
            self.assertIn(path, BUNDLE["inputs"])
        self.assertTrue(any(k.startswith("data/phase2/geometries/") or k.startswith("site/data/phase2/geometries/") for k in BUNDLE["inputs"]))
        self.assertNotIn("site/data/v09/territory_v0_1.json", BUNDLE["inputs"])
        # a geometry generated at deploy time (absent from the repository) is recorded as absent, so its later
        # appearance in a workspace is a detected input change, never a silent difference
        self.assertIn("site/data/hydrology/ana_catacaos_critical_segments_2026.geojson", BUNDLE["inputs"])

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
                self.assertEqual(p["evidence"], "GEOMETRIA_DERIVADA")  # a reproducible D8 node: derived, not official
            if p.get("node_semantics") in ("MONITORING_ANCHOR", "NEAR_CONFLUENCE", "UNRESOLVED") or p["map_category"] == "DOCUMENT_CONTEXT":
                self.assertEqual(p["evidence"], "UBICACION_DOCUMENTAL")  # never presented as official geometry
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

    def test_filterable_inventory_keeps_three_states_apart(self):
        national = {r["inventory_id"]: r for r in json.loads(T.INVENTORY.read_text(encoding="utf-8"))["candidates"]}
        rows = BUNDLE["inventory_rows"]
        self.assertEqual(len({r["id"] for r in rows}), len(rows))
        for r in rows:
            self.assertIn(r["region"], T.INVENTORY_REGIONS)
            self.assertIs(r["map_publishable"], False)  # nothing in the inventory is map-eligible today
            if r["inventory_status"] == "INVENTARIADO":
                n = national[r["id"]]
                self.assertEqual(r["geometry"] == "REPRODUCIBLE", bool(n["reproducible_geometry"].get("exists")))
            else:
                self.assertEqual((r["inventory_status"], r["geometry"]), ("CANDIDATO_NO_INTEGRADO", "SIN_GEOMETRIA"))
                self.assertNotIn(r["id"], national)
        self.assertEqual(sum(1 for r in rows if r["inventory_status"] == "INVENTARIADO"),
                         sum(1 for r in national.values() if T.inventory_region(r, "CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA")))

    def test_data_status_for_the_freshness_strip(self):
        s = BUNDLE["data_status"]
        for k in ("engine_evaluated_at_utc", "imerg_latest_window_end_utc", "goes_latest_scan_end_utc", "geos_latest_cycle_start_utc", "aviso_source_state"):
            self.assertIn(k, s)

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


class Isolation(unittest.TestCase):
    def test_nothing_operational_reads_the_territory_view(self):
        # the builder, the Pages publication gate (it removes the view) and the independent QA verifier (it reads
        # the bundle) are the only scripts allowed to name it; none of them feeds the rain engine or the panel
        allowed = {"v09_build_territory_bundle.py", "v09_pages_publication_gate.py", "v09_territory_independent_qa.py"}
        for path in (ROOT / "scripts").glob("*.py"):
            if path.name not in allowed:
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("v09_build_territory_bundle", text, path.name)
                self.assertNotIn("territory_v0_1.json", text, path.name)
        self.assertNotIn("territory_v0_1.json", (ROOT / "site/v09/index.html").read_text(encoding="utf-8"))

    def test_workflows_rebuild_it_without_blocking_capture(self):
        for wf in ("v09-rain-north.yml", "v09-senamhi-avisos-capture.yml"):
            text = (ROOT / ".github/workflows" / wf).read_text(encoding="utf-8")
            step = text[text.index("name: Territorial view bundle"):]
            step = step[:step.index("- name:", 1)] if "- name:" in step[1:] else step
            self.assertIn("continue-on-error: true", step, wf)
            self.assertIn("v09_build_territory_bundle.py --check", step, wf)
        # The private integration QA checks rebuilt artifacts and never commits: a bot commit would become the PR head
        # and every pull_request workflow of the PR would wait as `action_required` (the loop seen on #403).
        qa = (ROOT / ".github/workflows/v09-private-integrated-qa.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n", qa)
        for forbidden in ("contents: write", "git push", "git commit", "git config user", "--write-manifest", "github-actions[bot]@"):
            self.assertNotIn(forbidden, qa, forbidden)
        self.assertIn("python scripts/verify_phase2_test_collection.py", qa)
        self.assertIn("actions/upload-artifact@", qa)
        self.assertIn("v09_build_territory_bundle.py --check", qa)


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


    def test_cover_page_and_shared_navigation_are_static_and_honest(self):
        """Portada v0.9 (resumen.html) + navegación común (nav.js): mismas URL, sin dependencias externas, sin
        afirmaciones de completitud, guardas leídas de los datos y la portada sujeta a la puerta territorial."""
        cover = (ROOT / "site/v09/resumen.html").read_text(encoding="utf-8")
        nav = (ROOT / "site/v09/nav.js").read_text(encoding="utf-8")
        index = (ROOT / "site/v09/index.html").read_text(encoding="utf-8")
        for page in (cover, HTML, index):
            self.assertIn('<script src="nav.js"></script>', page)
            self.assertIn('<div id="irfen-nav"></div>', page)
        for href in re.findall(r'href: "([^"#]+)', nav):
            self.assertTrue((ROOT / "site/v09" / href).is_file(), href)
        for text in (cover, nav):
            self.assertNotIn("https://", text)
            self.assertNotIn("http://", text.replace("http://www.w3.org/2000/svg", ""))
            self.assertNotRegex(text.lower(), r"inventario (nacional |territorial )?completo|(?<!no un )censo completo")
        self.assertEqual(nav.count("no es alerta"), 1)
        self.assertNotIn("no es alerta", cover.lower())  # the notice is shown once, by the shared bar
        self.assertIn('name="robots" content="noindex"', cover)
        self.assertIn('<script src="shared_rules.js"></script>', cover)
        for rule in ("imergUsableAt(", "geosWindowsAt(", "avisoStatusAt("):
            self.assertIn(rule, cover)
        self.assertIn("territory_v0_1.json", cover)
        self.assertNotIn("territory_v0_1.json", nav)
        for key in T.GUARDS:
            self.assertIn(f'"{key}"', cover)
        self.assertIn("no es un nivel oficial", cover)
        spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts/v09_pages_publication_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertIn("site/v09/resumen.html", gate.TERRITORY_PATHS)
        self.assertNotIn("site/v09/nav.js", gate.TERRITORY_PATHS)  # the panel uses it too


    def test_cover_indicators_need_real_window_coverage(self):
        """QA #6476218149: a recent timestamp alone never makes the cover indicators green. IMERG needs complete 6 h
        and 24 h windows per zone; GEOS-CF needs the hours that are actually available from now. SYNTHETIC zones."""
        import shutil
        import subprocess
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required (GitHub runners provide it)")
        cover = (ROOT / "site/v09/resumen.html").read_text(encoding="utf-8")
        block = cover[cover.index("/* COVER-RULES-BEGIN"):cover.index("/* COVER-RULES-END */")]
        rules = (ROOT / "site/v09/shared_rules.js").read_text(encoding="utf-8")
        now = "2026-10-27T15:00:00Z"
        full = lambda **w: dict(windows={"6h": dict(accum_mm=1.2), "24h": dict(accum_mm=0.0), **w})
        im = lambda end, **w: dict(imerg=dict(window_end_utc=end, **full(**w)))
        hours = lambda first, n: [dict(valid_time_utc=f"2026-10-27T{h:02d}:30:00Z" if h < 24 else f"2026-10-28T{h - 24:02d}:30:00Z", precip_mm=0.1)
                                  for h in range(first, first + n)]
        ge = lambda start, hrs: dict(geos=dict(status="CALCULADO", dataset_time_start=start, hourly=hrs))
        cases = {
            "imerg_complete": ("imerg", [im("2026-10-27T10:00:00Z")] * 3, "2026-10-27T10:00:00Z", "COMPLETE"),
            "imerg_partial_24h": ("imerg", [im("2026-10-27T10:00:00Z"), im("2026-10-27T10:00:00Z", **{"24h": dict(status="NO_DISPONIBLE")})],
                                  "2026-10-27T10:00:00Z", "PARTIAL"),
            "imerg_no_complete_window": ("imerg", [im("2026-10-27T10:00:00Z", **{"6h": dict(status="NO_DISPONIBLE"), "24h": dict(status="NO_DISPONIBLE")})] * 2,
                                         "2026-10-27T10:00:00Z", "NO_COMPLETE_WINDOW"),
            "imerg_zero_is_complete_only_if_calculated": ("imerg", [im("2026-10-27T10:00:00Z", **{"24h": dict(accum_mm=0.0, status="NO_DISPONIBLE")})],
                                                          "2026-10-27T10:00:00Z", "PARTIAL"),
            "imerg_zone_window_in_future": ("imerg", [im("2026-10-27T10:00:00Z"), im("2026-10-27T18:00:00Z")], "2026-10-27T10:00:00Z", "PARTIAL"),
            "imerg_latest_in_future": ("imerg", [im("2026-10-27T18:00:00Z")], "2026-10-27T18:00:00Z", "FUTURE"),
            "imerg_stale": ("imerg", [im("2026-10-26T10:00:00Z")], "2026-10-26T10:00:00Z", "STALE"),
            "imerg_no_date": ("imerg", [im("2026-10-27T10:00:00Z")], None, "NO_DATE"),
            "geos_recent_cycle_zero_hours": ("geos", [ge("2026-10-27T09:30:00Z", [])] * 2, "2026-10-27T09:30:00Z", "NO_USABLE_FORECAST"),
            "geos_recent_cycle_full": ("geos", [ge("2026-10-27T09:30:00Z", hours(15, 30))] * 2, "2026-10-27T09:30:00Z", "COMPLETE"),
            "geos_recent_cycle_short": ("geos", [ge("2026-10-27T09:30:00Z", hours(15, 30)), ge("2026-10-27T09:30:00Z", hours(15, 8))],
                                        "2026-10-27T09:30:00Z", "PARTIAL"),
            "geos_hours_not_from_now": ("geos", [ge("2026-10-27T09:30:00Z", hours(18, 30))], "2026-10-27T09:30:00Z", "NO_USABLE_FORECAST"),
            "geos_cycle_in_future": ("geos", [ge("2026-10-27T20:30:00Z", hours(21, 30))], "2026-10-27T20:30:00Z", "FUTURE"),
            "geos_cycle_stale": ("geos", [ge("2026-10-24T09:30:00Z", hours(15, 30))], "2026-10-24T09:30:00Z", "STALE"),
            "geos_no_date": ("geos", [ge("2026-10-27T09:30:00Z", hours(15, 30))], None, "NO_DATE"),
        }
        runner = """
const input = JSON.parse(require("fs").readFileSync(0, "utf8")), t = Date.parse(input.now), out = {};
for (const [name, [kind, zones, ts]] of Object.entries(input.cases))
  out[name] = (kind === "imerg" ? coverImergState : coverGeosState)(zones, ts, t, DEFAULT_FRESHNESS).state;
process.stdout.write(JSON.stringify(out));"""
        res = subprocess.run([node, "-e", rules + "\n" + block + runner], input=json.dumps(dict(now=now, cases={k: v[:3] for k, v in cases.items()})),
                             capture_output=True, text=True, check=True, timeout=60)
        got = json.loads(res.stdout)
        self.assertEqual(got, {k: v[3] for k, v in cases.items()})
        self.assertNotIn("hourly:[]", cover.replace(" ", ""))  # never fake an empty forecast to read a status


INV_SPEC = importlib.util.spec_from_file_location("v09_build_inventory_view", ROOT / "scripts/v09_build_inventory_view.py")
INV = importlib.util.module_from_spec(INV_SPEC)
INV_SPEC.loader.exec_module(INV)
INV_VIEW = json.loads(INV.OUT.read_text(encoding="utf-8"))
MASTER = json.loads(INV.MASTER.read_text(encoding="utf-8"))
INV_HTML = (ROOT / "site/v09/inventario.html").read_text(encoding="utf-8")


class InventoryMasterView(unittest.TestCase):
    """P0-B: read-only view of the national documentary inventory (site/v09/inventario.html). Every row of the master
    in main, nothing added from open PRs, no geometry or coordinates, nothing publishable."""

    def test_view_is_rebuilt_from_the_master_only(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):  # keep the verbose test log one line per test
            self.assertEqual(INV.main(["--check"]), 0)
        self.assertEqual(INV_VIEW["source"]["path"], "config/phase2_national_inventory_completeness_audit_v0_1.json")
        self.assertEqual(INV_VIEW["source"]["sha256"], hashlib.sha256(INV.MASTER.read_bytes()).hexdigest())
        self.assertEqual(INV_VIEW["other_inputs"], [])
        code = (ROOT / "scripts/v09_build_inventory_view.py").read_text(encoding="utf-8").split('"""', 2)[2]  # code, not docstring
        self.assertEqual(sorted(re.findall(r'ROOT / "([^"]+)"', code)),
                         ["config/phase2_national_inventory_completeness_audit_v0_1.json", "site/data/v09/inventory_master_v0_1.json"])
        for other in ("reconciliation", "ledger", "territory_v0_1", "inventory_annotations", "write_text(json.dumps(doc"):
            self.assertFalse(other in code, other)
        self.assertEqual(code.count(".write_text("), 1)  # only the view is written; the master is never touched

    def test_every_master_row_once_and_nothing_else(self):
        ids = [r["inventory_id"] for r in MASTER["candidates"]]
        self.assertEqual(len(ids), 400)
        self.assertEqual([r["id"] for r in INV_VIEW["rows"]], ids)
        self.assertEqual(len(set(ids)), len(ids))
        s = INV_VIEW["summary"]
        self.assertEqual(s["rows"], 400)
        count = lambda k: {v: sum(1 for r in MASTER["candidates"] if r[k] == v) for v in {r[k] for r in MASTER["candidates"]}}
        self.assertEqual(s["corridors"], count("corridor"))
        self.assertEqual(s["departments"], count("department"))
        self.assertEqual(s["identity_state"], count("suggested_state"))
        alias_ids = {i for g in INV_VIEW["alias_groups"] for i in g["inventory_ids"]}
        self.assertLessEqual(alias_ids, set(ids))  # alias groups never introduce rows

    def test_fields_are_copied_not_reinterpreted(self):
        for m, r in zip(MASTER["candidates"], INV_VIEW["rows"]):
            self.assertEqual(r["name"], m["documentary_name"])
            self.assertEqual(r["variants"], m.get("name_variants_observed") or [])
            for a, b in (("department", "department"), ("province", "province"), ("district", "district"), ("corridor", "corridor"),
                         ("parent_basin_or_system", "parent_basin_or_system"), ("row_role", "row_role")):
                self.assertEqual(r[a], m.get(b), (r["id"], a))
            self.assertEqual(r["identity"]["state"], m["suggested_state"])
            self.assertEqual(r["identity"]["flags"], m.get("state_flags") or [])
            self.assertEqual(r["events"]["verified"], m.get("verified_event_dates") or [])
            self.assertEqual(r["events"]["leads_unverified"], m.get("event_lead_dates_unverified") or [])
            self.assertEqual([e["source_id"] for e in r["evidence"]], [e.get("source_id") for e in m.get("evidence") or []])
            self.assertEqual([e["url"] for e in r["evidence"]], [e.get("url") for e in m.get("evidence") or []])
            self.assertEqual([e["text_verified"] for e in r["evidence"]], [e.get("source_text_verified") is True for e in m.get("evidence") or []])
            for e in r["evidence"]:
                self.assertIn(e["source_id"], INV_VIEW["sources"])

    def test_nothing_publishable_no_coordinates_no_priority(self):
        for k, v in INV.EXPECTED.items():
            self.assertEqual(INV_VIEW[k], v, k)
        self.assertIs(INV_VIEW["map_publishable"], False)
        self.assertIs(INV_VIEW["public_alerting"], False)
        self.assertEqual(INV_VIEW["summary"]["map_eligible"], 0)
        self.assertTrue(all(r["map"]["eligible"] is False for r in INV_VIEW["rows"]))
        forbidden = {"coordinates", "geometry_coordinates", "geojson", "easting_m", "northing_m", "latitude", "longitude", "lat", "lon",
                     "source_reference_point", "priority", "bbox", "centroid"}
        def walk(node):
            if isinstance(node, dict):
                self.assertFalse(forbidden & set(node), forbidden & set(node))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(INV_VIEW)
        # the master has ANA population reference points; the view only says the source gives one
        with_point = sum(1 for m in MASTER["candidates"] for e in m.get("evidence") or [] if e.get("source_reference_point"))
        self.assertGreater(with_point, 0)
        self.assertEqual(sum(1 for r in INV_VIEW["rows"] for e in r["evidence"] if e["source_gives_reference_point"]), with_point)

    def test_geometry_outlet_and_blocking_are_separate_and_agree_with_the_viewer(self):
        geo = INV_VIEW["summary"]["geometry"]
        self.assertEqual(geo, {"REPRODUCIBLE": 3, "SOLO_INDICIO": 20, "SIN_GEOMETRIA": 377})
        same = {"REPRODUCIBLE": "REPRODUCIBLE", "SOLO_INDICIO": "PENDIENTE", "SIN_GEOMETRIA": "SIN_GEOMETRIA"}
        viewer = {r["id"]: r for r in BUNDLE["inventory_rows"]}
        rows = {r["id"]: r for r in INV_VIEW["rows"]}
        self.assertLessEqual(set(viewer), set(rows))
        for i, v in viewer.items():
            self.assertEqual(same[rows[i]["geometry"]["state"]], v["geometry"], i)
        for m in MASTER["candidates"]:
            r = rows[m["inventory_id"]]
            self.assertEqual(r["geometry"]["state"] == "REPRODUCIBLE", (m.get("reproducible_geometry") or {}).get("exists") is True)
            self.assertEqual(r["outlet"]["state"] == "ACREDITADO", (m.get("reproducible_outlet_or_confluence") or {}).get("exists") is True)
            reasons = r["map"]["blocking_reasons"]
            self.assertTrue(reasons, r["id"])
            self.assertLessEqual(set(reasons), set(INV_VIEW["blocking_reasons_es"]))
            self.assertIn("QA_INDEPENDIENTE_PENDIENTE", reasons)
            self.assertEqual("SIN_GEOMETRIA_REPRODUCIBLE" in reasons, r["geometry"]["state"] == "SIN_GEOMETRIA")
            self.assertEqual("GEOMETRIA_SOLO_INDICIO" in reasons, r["geometry"]["state"] == "SOLO_INDICIO")
            self.assertEqual("OUTLET_NO_ACREDITADO" in reasons, r["outlet"]["state"] != "ACREDITADO")
            self.assertEqual("CUENCA_PADRE_NO_DOCUMENTADA" in reasons, not m.get("parent_basin_or_system"))
            if r["identity"]["alias_groups"] or r["unnamed_in_source"]:
                self.assertIn("IDENTIDAD_POR_ADJUDICAR", reasons)

    def test_builder_refuses_a_master_with_changed_guards(self):
        import tempfile
        doc = dict(MASTER, production_use=True)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "master.json"
            p.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(SystemExit):
                INV.build(p)

    def test_page_is_static_read_only_and_draws_nothing(self):
        page = INV_HTML
        self.assertIn('<script src="nav.js"></script>', page)
        self.assertIn('<div id="irfen-nav"></div>', page)
        self.assertIn('name="robots" content="noindex"', page)
        self.assertIn("../data/v09/inventory_master_v0_1.json", page)
        self.assertNotRegex(page, r"https?://(?!/)")  # no external resource; source URLs come from the data
        for drawn in ("<svg", "<canvas", "leaflet", "L.map", "<img", "getContext("):
            self.assertNotIn(drawn, page)
        self.assertNotIn("no es alerta", page.lower())  # shown once, by the shared bar
        self.assertNotRegex(page.lower(), r"inventario (nacional |territorial )?completo|censo completo|todas las quebradas del per")
        self.assertIn("map_publishable", page)
        for key in INV.GUARD_KEYS:
            self.assertIn(f'"{key}"', page)
        self.assertNotIn("priority", page)
        self.assertIn('rel="noopener noreferrer"', page)
        nav = (ROOT / "site/v09/nav.js").read_text(encoding="utf-8")
        self.assertIn('href: "inventario.html"', nav)
        spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts/v09_pages_publication_gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertIn("site/v09/inventario.html", gate.TERRITORY_PATHS)
        self.assertIn("site/data/v09/inventory_master_v0_1.json", gate.TERRITORY_PATHS)


@unittest.skipUnless(BROWSER, "Playwright/Chromium not installed; runs in workflow v09-dashboard-browser-test.yml")
class Browser(unittest.TestCase):
    def test_cover_page_states_map_and_navigation(self):
        """Portada en escritorio y móvil: tres indicadores con estados al día / antiguo / fecha posterior al reloj /
        sin dato; mapas de cobertura dibujados solo con geometrías del paquete; navegación a mapa, inventario y panel."""
        import shutil
        import tempfile
        from datetime import datetime, timedelta

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        ds = BUNDLE["data_status"]
        parse = lambda s: datetime.fromisoformat(str(s).replace("Z", "+00:00")[:26] + ("" if "+" in str(s)[19:] else "+00:00"))
        imerg_end = parse(ds["imerg_latest_window_end_utc"])
        feature_ids = {f["properties"]["id"] for f in BUNDLE["geometries"]["features"]}
        no_geo = next(r for r in BUNDLE["inventory_rows"] if r["geometry"] == "SIN_GEOMETRIA")
        with_geo = next(r for r in BUNDLE["inventory_rows"] if r["geometry"] == "REPRODUCIBLE")
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"
            shutil.copytree(ROOT / "site/v09", site / "v09")
            (site / "data/v09").mkdir(parents=True)
            shutil.copy(T.OUT, site / "data/v09/territory_v0_1.json")
            shutil.copy(ROOT / "site/data/v09/dashboard_v0_1.json", site / "data/v09/dashboard_v0_1.json")
            shutil.copy(INV.OUT, site / "data/v09/inventory_master_v0_1.json")
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            origin = f"http://127.0.0.1:{srv.server_port}/"
            try:
                with sync_playwright() as p:
                    b = p.chromium.launch(args=["--no-proxy-server"])
                    errors = []
                    def open_cover(at, viewport):
                        page = b.new_page(viewport=viewport)
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                        page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin) else r.abort())
                        page.clock.install(time=at)
                        page.goto(origin + "v09/resumen.html")
                        page.wait_for_selector("#status .st")
                        page.wait_for_selector("#maps svg")
                        return page
                    imerg_state = lambda page: page.get_attribute("#status .st:nth-child(2)", "data-state")
                    for name, vp in (("desktop", dict(width=1440, height=900)), ("mobile", dict(width=390, height=844))):
                        page = open_cover(imerg_end + timedelta(hours=1), vp)
                        self.assertEqual(page.locator("#status .st").count(), 3, name)
                        self.assertEqual(imerg_state(page), "ok", name)
                        self.assertEqual(page.inner_text("body").lower().count("no es alerta"), 1, name)
                        self.assertNotIn("hace -", page.inner_text("body"))
                        drawn = page.eval_on_selector_all("#maps [data-feature]", "els => els.map(e => e.dataset.feature)")
                        self.assertTrue(drawn and set(drawn) <= feature_ids, name)  # nothing outside the bundle geometries
                        self.assertNotIn(no_geo["id"], drawn)
                        self.assertEqual(page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth"), 0, name)
                        self.assertEqual(page.text_content("[data-guard=map_publishable]"), "false")  # inside the closed «Método» block
                        page.close()
                    # observation stamped after this device's clock: never shown as current; old data: "Antiguo"
                    page = open_cover(imerg_end - timedelta(hours=2), dict(width=1440, height=900))
                    self.assertEqual(imerg_state(page), "bad")
                    self.assertIn("fecha posterior a la hora de este equipo", page.inner_text("#status"))
                    page.close()
                    # SYNTHETIC degraded bundle: recent IMERG with incomplete windows and a recent GEOS-CF cycle without
                    # hours: neither indicator may read as available
                    degraded = json.loads(T.OUT.read_text(encoding="utf-8"))
                    for i, z in enumerate(degraded["zone_rain"].values()):
                        if i % 2:
                            z["imerg"]["windows"]["24h"] = {"status": "NO_DISPONIBLE", "reason": "SYNTHETIC: half hour missing"}
                        z["geos"]["hourly"] = []
                    cycle = parse(ds["geos_latest_cycle_start_utc"])
                    (site / "data/v09/territory_v0_1.json").write_text(json.dumps(degraded), encoding="utf-8")
                    page = open_cover(max(imerg_end, cycle) + timedelta(hours=1), dict(width=1440, height=900))
                    self.assertEqual(imerg_state(page), "partial")
                    self.assertIn("no es cero", page.inner_text("#status .st:nth-child(2)"))
                    self.assertEqual(page.get_attribute("#status .st:nth-child(3)", "data-state"), "none")
                    self.assertIn("Sin previsión utilizable", page.inner_text("#status .st:nth-child(3)"))
                    page.close()
                    shutil.copy(T.OUT, site / "data/v09/territory_v0_1.json")
                    page = open_cover(imerg_end + timedelta(days=2), dict(width=1440, height=900))
                    self.assertEqual(imerg_state(page), "old")
                    # navigation: inventory deep link, searches with and without geometry, region link, panel
                    page.click("#irfen-nav a[data-section=inventario]")
                    page.wait_for_selector("body[data-ready='1']")
                    self.assertTrue(page.url.endswith("v09/inventario.html"))
                    self.assertEqual(page.get_attribute("#irfen-nav a[data-section=inventario]", "aria-current"), "page")
                    page.goto(origin + "v09/territorio.html#inventario")  # the viewer keeps its regional list
                    page.wait_for_selector("#rows-table tr")
                    self.assertFalse(page.is_hidden("#view-inventario"))
                    self.assertEqual(page.get_attribute("#irfen-nav a[data-section=mapa]", "aria-current"), "page")
                    for row, label in ((with_geo, "reproducible"), (no_geo, "sin geometr")):
                        page.fill("#f-text", row["id"].split("_")[-1])
                        page.wait_for_timeout(150)
                        hit = page.locator("#rows-table tr", has_text=row["id"])
                        self.assertEqual(hit.count(), 1, row["id"])
                        self.assertIn(label, hit.inner_text().lower())
                    self.assertIn("publicables en mapa: 0", page.inner_text("#f-count"))
                    page.goto(origin + "v09/resumen.html")
                    page.wait_for_selector("#maps a[data-region=rimac]")
                    page.click("#maps a[data-region=rimac]")
                    page.wait_for_selector("#map svg path")
                    self.assertEqual(page.get_attribute('nav [data-region="rimac"]', "aria-selected"), "true")
                    page.click("#irfen-nav a[data-section=lluvia]")
                    page.wait_for_selector("#chips .chip")
                    self.assertTrue(page.url.endswith("index.html"))
                    self.assertEqual(errors, [])
                    b.close()
            finally:
                srv.shutdown()
                srv.server_close()  # no open socket left to warn inside the next test's output
                # collect what Playwright / the server leave behind now, so no ResourceWarning lands in the output of
                # the next test (the browser workflow checks that output line by line)
                import gc
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    gc.collect()

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
                self.assertGreater(page.locator("#map rect.hl").count(), 0)  # the D8 node is drawn as a derived (square) marker
                page.click("[data-q=huaycoloro]")
                detail = page.inner_text("#detail").lower()
                self.assertIn("observación in situ", detail)
                self.assertIn("calculada sobre", detail)  # what each rain value is computed over
                self.assertIn("qué falta", detail)
                # zoom and pan through the viewBox; region reset restores the full frame
                vb = lambda: [float(x) for x in page.get_attribute("#map svg", "viewBox").split()]
                page.click("#zfit"); full = vb()
                page.click("#zin"); self.assertLess(vb()[2], full[2])
                page.mouse.move(700, 400); page.mouse.wheel(0, 400); page.click("#zfit"); self.assertEqual(vb(), full)
                # selection directly on the map: a quebrada label is clickable
                page.click("#map [data-qpin=quirio]")
                self.assertTrue(page.inner_text("#detail").startswith("Quebrada Quirio"))
                self.assertLess(vb()[2], full[2])  # the view fits the selection
                # freshness strip: one chip per source, each with an age
                chips = page.locator("#status .st")
                self.assertEqual(chips.count(), 5)
                self.assertIn("IMERG Early", chips.nth(0).inner_text())
                # inventory with filters; candidates (if the review ledger is present) are never "publicable"
                page.click("nav [data-view=inventario]")
                self.assertIn("quebradas identificadas", page.inner_text("#inv-table").lower())
                total = int(page.inner_text("#f-count").split(" de ")[1].split()[0])
                page.select_option("#f-region", "Rímac")
                rimac = int(page.inner_text("#f-count").split()[0])
                self.assertTrue(0 < rimac < total)
                page.select_option("#f-geometry", "REPRODUCIBLE")
                self.assertEqual(int(page.inner_text("#f-count").split()[0]), 3)
                page.select_option("#f-geometry", ""); page.fill("#f-text", "huaycoloro")
                self.assertIn("huaycoloro", page.inner_text("#rows-table").lower())
                self.assertIn("publicables en mapa: 0", page.inner_text("#f-count"))
                self.assertEqual(errors, [])
                b.close()
        finally:
            srv.shutdown()


    def test_data_update_keeps_state_and_old_data_is_never_zero(self):
        """A new bundle is picked up after 5 min without losing region, selection or zoom; when the IMERG window
        is older than the freshness limit the values disappear (hatched, 'no disponible'), never 0."""
        import shutil
        import tempfile
        from datetime import datetime, timedelta

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"
            shutil.copytree(ROOT / "site/v09", site / "v09")
            (site / "data/v09").mkdir(parents=True)
            target = site / "data/v09/territory_v0_1.json"
            shutil.copy(T.OUT, target)
            imerg_end = datetime.fromisoformat(BUNDLE["data_status"]["imerg_latest_window_end_utc"].replace("Z", "+00:00"))
            start = imerg_end + timedelta(hours=1)  # one hour after the latest IMERG window: data current
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            origin = f"http://127.0.0.1:{srv.server_port}/"
            try:
                with sync_playwright() as p:
                    b = p.chromium.launch(args=["--no-proxy-server"])
                    page = b.new_page(viewport=dict(width=1400, height=1000))
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin) else r.abort())
                    page.clock.install(time=start)
                    page.goto(origin + "v09/territorio.html")
                    page.wait_for_selector("#map svg path")
                    page.click("[data-q=bocapan]")
                    self.assertIn("mm acumulados", page.inner_text("#detail"))
                    page.click("#zin"); vb = page.get_attribute("#map svg", "viewBox")
                    # a new bundle appears on the server: the page picks it up at the next 5-min refresh
                    newer = json.loads(target.read_text(encoding="utf-8"))
                    newer["built_at_utc"] = (start + timedelta(minutes=4)).isoformat()
                    target.write_text(json.dumps(newer), encoding="utf-8")
                    page.clock.run_for(5 * 60 * 1000 + 2000)
                    page.wait_for_function("document.querySelector('#status').innerText.includes('hace 1 min') || document.querySelector('#status').innerText.includes('hace 2 min')")
                    self.assertTrue(page.inner_text("#detail").startswith("Quebrada Bocapán"))  # selection kept
                    self.assertEqual(page.get_attribute("#map svg", "viewBox"), vb)  # zoom kept
                    # 13 h later the IMERG window is past its freshness limit: no value, hatch, chip marked old
                    page.clock.run_for(13 * 3600 * 1000)
                    detail = page.inner_text("#detail")
                    self.assertNotIn("mm acumulados", detail)
                    self.assertIn("no disponible", detail)
                    self.assertGreater(page.locator('#map path[fill="url(#hatch)"]').count(), 0)
                    self.assertIn("old", page.get_attribute("#status .st:first-child", "class"))
                    self.assertEqual(errors, [])
                    # Clock BEHIND the data (observations stamped after this device's time): nothing is shown as
                    # current, no negative age, no rain value; the strip says why.
                    shutil.copy(ROOT / "site/data/v09/dashboard_v0_1.json", site / "data/v09/dashboard_v0_1.json")
                    goes_end = datetime.fromisoformat(BUNDLE["data_status"]["goes_latest_scan_end_utc"].replace("Z", "+00:00"))
                    early = b.new_page(viewport=dict(width=1400, height=1000))
                    early.on("pageerror", lambda e: errors.append(str(e)))
                    early.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin) else r.abort())
                    early.clock.install(time=goes_end - timedelta(hours=2))
                    early.goto(origin + "v09/territorio.html")
                    early.wait_for_selector("#status .st")
                    strip = early.inner_text("#status")
                    self.assertNotIn("hace -", strip)
                    self.assertIn("fecha posterior a la hora de este equipo", strip)
                    for chip in early.query_selector_all("#status .st"):
                        if "posterior" in chip.inner_text():
                            self.assertIn("old", chip.get_attribute("class"), chip.inner_text())
                    early.goto(origin + "v09/index.html")
                    early.wait_for_selector("#chips .chip")
                    early.wait_for_timeout(500)
                    body = early.inner_text("body")
                    self.assertNotIn("hace -", body)
                    self.assertGreater(early.locator("[data-future='1']").count(), 0)
                    self.assertEqual(errors, [])
                    b.close()
            finally:
                srv.shutdown()

    def test_national_inventory_rows_filters_and_fichas(self):
        """P0-B en escritorio y móvil: las 400 filas del maestro, búsqueda y filtros, ficha de una fila con geometría
        reproducible y de una sin GIS (fuera del visor), alias por comprobar enlazados, enlace profundo, paginación,
        nada dibujado y nada publicable. Funciona también si la puerta retira el paquete territorial."""
        import shutil
        import tempfile

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        rows = INV_VIEW["rows"]
        viewer_ids = {r["id"] for r in BUNDLE["inventory_rows"]}
        with_geo = next(r for r in rows if r["geometry"]["state"] == "REPRODUCIBLE")
        no_gis = next(r for r in rows if r["geometry"]["state"] == "SIN_GEOMETRIA" and r["id"] not in viewer_ids
                      and any(e["url"] for e in r["evidence"]))
        aliased = next(r for r in rows if r["identity"]["alias_groups"])
        group = INV_VIEW["alias_groups"][aliased["identity"]["alias_groups"][0]]
        other = next(i for i in group["inventory_ids"] if i != aliased["id"])
        leads = sum(1 for r in rows if r["events"]["leads_unverified"])
        lima = INV_VIEW["summary"]["departments"]["Lima"]
        with tempfile.TemporaryDirectory() as d:
            site = Path(d) / "site"
            shutil.copytree(ROOT / "site/v09", site / "v09")
            (site / "data/v09").mkdir(parents=True)
            for name in ("territory_v0_1.json", "dashboard_v0_1.json", "inventory_master_v0_1.json"):
                shutil.copy(ROOT / "site/data/v09" / name, site / "data/v09" / name)
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            origin = f"http://127.0.0.1:{srv.server_port}/"
            try:
                with sync_playwright() as p:
                    b = p.chromium.launch(args=["--no-proxy-server"])
                    errors = []

                    def open_inv(viewport, hash_="", track=True):
                        page = b.new_page(viewport=viewport)
                        if track:
                            page.on("pageerror", lambda e: errors.append(str(e)))
                            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                        page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin) else r.abort())
                        page.goto(origin + "v09/inventario.html" + hash_)
                        page.wait_for_selector("body[data-ready='1']")
                        return page

                    shown = lambda page: int(page.inner_text("#n-shown"))
                    overflow = lambda page: page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                    drawn_in = lambda page, sel: page.locator(f"{sel} svg, {sel} canvas, {sel} img").count()
                    for name, vp in (("desktop", dict(width=1440, height=900)), ("mobile", dict(width=390, height=844))):
                        page = open_inv(vp)
                        self.assertEqual(shown(page), 400, name)
                        self.assertIn("de 400 registros documentales", page.inner_text("#count"))
                        self.assertEqual(page.inner_text("#n-map"), "0")
                        self.assertEqual(page.locator("#rows tbody tr").count(), 50, name)  # paginated
                        self.assertEqual(page.get_attribute("#irfen-nav a[data-section=inventario]", "aria-current"), "page")
                        self.assertEqual(page.inner_text("body").lower().count("no es alerta"), 1, name)
                        self.assertLessEqual(overflow(page), 1, name)
                        self.assertEqual(drawn_in(page, "main"), 0, name)
                        self.assertEqual(page.text_content("[data-guard=map_publishable]"), "false")  # inside the closed <details>
                        # filters
                        page.select_option("#f-geo", "REPRODUCIBLE")
                        self.assertEqual(shown(page), 3, name)
                        page.click("#f-clear")
                        self.assertEqual(shown(page), 400)
                        page.select_option("#f-dep", "Lima")
                        self.assertEqual(shown(page), lima)
                        page.select_option("#f-evt", "LEAD")
                        self.assertEqual(shown(page), sum(1 for r in rows if r["department"] == "Lima" and r["events"]["leads_unverified"]))
                        page.click("#f-clear")
                        page.select_option("#f-evt", "LEAD")
                        self.assertEqual(shown(page), leads)
                        page.select_option("#f-block", "SIN_GEOMETRIA_REPRODUCIBLE")
                        self.assertEqual(shown(page), sum(1 for r in rows if r["events"]["leads_unverified"]
                                                          and "SIN_GEOMETRIA_REPRODUCIBLE" in r["map"]["blocking_reasons"]))
                        page.click("#f-clear")
                        page.click("#next")
                        self.assertIn("Página 2", page.inner_text("#pager"))
                        self.assertEqual(page.get_attribute("#rows tbody tr", "data-id"), rows[50]["id"])
                        # ficha of a row with reproducible geometry, opened from a search
                        page.fill("#f-q", with_geo["name"])
                        page.click(f"#rows [data-open='{with_geo['id']}']")
                        page.wait_for_selector("#ficha:not([hidden])")
                        self.assertIn(with_geo["id"], page.url)
                        geo_txt = page.inner_text("#ficha [data-section=geometria]")
                        self.assertIn("Reproducible", geo_txt)
                        reasons = page.eval_on_selector_all("#ficha-reasons li", "els => els.map(e => e.dataset.reason)")
                        self.assertEqual(reasons, with_geo["map"]["blocking_reasons"])
                        self.assertNotIn("SIN_GEOMETRIA_REPRODUCIBLE", reasons)
                        self.assertEqual(page.locator("#ficha [data-viewer-link]").count(), 1)
                        self.assertEqual(drawn_in(page, "#ficha"), 0)
                        self.assertLessEqual(overflow(page), 1, name)
                        page.keyboard.press("Escape")
                        self.assertTrue(page.is_hidden("#ficha"))
                        self.assertNotIn("#id=", page.url)
                        page.close()
                        # deep link: a row without GIS, outside the viewer regions
                        page = open_inv(vp, "#id=" + no_gis["id"])
                        self.assertTrue(page.is_visible("#ficha"))
                        self.assertEqual(page.inner_text("#ficha-title"), no_gis["name"])
                        self.assertEqual(page.locator("#ficha [data-section=procedencia] .ev").count(), len(no_gis["evidence"]))
                        self.assertGreater(page.locator("#ficha [data-section=procedencia] a[rel='noopener noreferrer']").count(), 0)
                        reasons = page.eval_on_selector_all("#ficha-reasons li", "els => els.map(e => e.dataset.reason)")
                        self.assertIn("SIN_GEOMETRIA_REPRODUCIBLE", reasons)
                        self.assertIn("OUTLET_NO_ACREDITADO", reasons)
                        self.assertIn("Fuera de las regiones del visor", page.inner_text("#ficha [data-section=visor]"))
                        self.assertIn("Sin geometría", page.inner_text("#ficha [data-section=geometria]"))
                        self.assertEqual(drawn_in(page, "#ficha"), 0)
                        for section in ("identidad", "ubicacion", "procedencia", "alias", "geometria", "outlet", "eventos", "bloqueo", "visor"):
                            self.assertEqual(page.locator(f"#ficha [data-section={section}]").count(), 1, section)
                        page.close()
                        # pending aliases: shown as «por comprobar» and linked, never merged
                        page = open_inv(vp, "#id=" + aliased["id"])
                        self.assertGreater(page.locator("#ficha [data-alias-group]").count(), 0)
                        page.click(f"#ficha [data-section=alias] a[href='#id={other}']")
                        page.wait_for_function(f"document.getElementById('ficha-title').textContent !== {json.dumps(aliased['name'])}")
                        self.assertEqual(page.inner_text("#ficha-title"), next(r["name"] for r in rows if r["id"] == other))
                        self.assertEqual(shown(page), 400)  # still 400: an alias is not a new row
                        page.close()
                    # the territorial bundle withheld by the publication gate: the inventory still works, nothing in the viewer
                    page = open_inv(dict(width=1440, height=900), track=False)
                    page.close()
                    page = b.new_page()
                    page.route("**/territory_v0_1.json", lambda r: r.fulfill(status=404, body=""))
                    page.route("**/*", lambda r: r.fallback() if r.request.url.startswith(origin) else r.abort())
                    page.goto(origin + "v09/inventario.html#id=" + with_geo["id"])
                    page.wait_for_selector("body[data-ready='1']")
                    self.assertEqual(shown(page), 400)
                    self.assertIn("Fuera de las regiones del visor", page.inner_text("#ficha [data-section=visor]"))
                    self.assertIn("(0)", page.inner_text("#f-viewer option[value=IN]"))
                    self.assertEqual(errors, [])
                    b.close()
            finally:
                srv.shutdown()
                srv.server_close()
                import gc
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    gc.collect()

if __name__ == "__main__":
    unittest.main()
