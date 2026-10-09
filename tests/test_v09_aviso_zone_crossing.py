"""IRFEN v0.9 aviso ↔ surveillance-zone crossing: offline tests.

Avisos come from the real archived INDECI bulletin fixture (SENAMHI ACP lluvias N°282, 2026-10-09), replayed
as an archived document, never as a current event.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


X = load_module("v09_aviso_zone_crossing", "scripts/v09_aviso_zone_crossing.py")
A = load_module("v09_senamhi_avisos_for_crossing", "scripts/v09_senamhi_avisos.py")
O = load_module("v09_build_zone_admin_overlay", "scripts/v09_build_zone_admin_overlay.py")
FIX = ROOT / "tests/fixtures/v09_senamhi_avisos"
ZONES = json.loads((ROOT / "config/v09_north_surveillance_zones_v0_1.json").read_text(encoding="utf-8"))


def aviso(name="acp_lluvias_282_2026", family="AVISO_CORTO_PLAZO_LLUVIAS", status="VIGENTE"):
    text = (FIX / f"{name}.txt").read_text(encoding="utf-8")
    words = json.loads((FIX / f"{name}.words.json").read_text(encoding="utf-8"))
    obs = A.parse_bulletin(text, words, family, 2026)
    current = {k: obs[k] for k in A.FIELDS_TRACKED if obs.get(k) not in (None, [], "")}
    return dict(aviso_key=A.aviso_key(obs["product"], obs["aviso_number"], obs["aviso_year"]), product=obs["product"],
                status=status, current=current, official_url="https://portal.indeci.gob.pe/emergencias/x/")


class ZonesConfig(unittest.TestCase):
    def test_committed_zones_verify(self):
        self.assertEqual(X.check_zones(ZONES), [])
        self.assertEqual(sum(z["zone_type"] == "BASIN_GEOMETRY" for z in ZONES["zones"]), 10)
        for key, value in X.GUARDS.items():
            self.assertEqual(ZONES[key], value)

    def test_tampered_or_invented_geometry_is_rejected(self):
        cfg = copy.deepcopy(ZONES)
        cfg["zones"][0]["geometry_sha256"] = "0" * 64
        piura = next(z for z in cfg["zones"] if z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN")
        piura["geometry_path"] = "site/data/phase2/geometries/invented_piura_basin.geojson"
        errors = X.check_zones(cfg)
        self.assertTrue(any("SHA-256 mismatch" in e for e in errors))
        self.assertTrue(any("must not carry a basin geometry" in e for e in errors))


class CrossingWithoutOfficialBoundaries(unittest.TestCase):
    def test_real_rain_aviso_relations(self):
        links = X.links_for_aviso(aviso(), ZONES["zones"], None)
        by_method = {}
        for l in links:
            by_method.setdefault(l["relation_method"], []).append(l["zone_id"])
        self.assertEqual(sorted(by_method["LISTED_PROVINCE_CONTEXT_NO_BASIN"]),
                         ["piura_province_context:" + p for p in ("AYABACA", "HUANCABAMBA", "MORROPON", "PIURA", "SULLANA")])
        self.assertEqual(len(by_method["REGISTERED_DEPARTMENT_LISTED"]), 10)  # Tumbes, Lambayeque, La Libertad basins
        self.assertNotIn("BASIN_INTERSECTS_LISTED_PROVINCE", by_method)  # never claimed without official boundaries
        moche = next(l for l in links if l["zone_id"] == "lalibertad_moche")
        self.assertEqual(moche["evidence"]["official_boundaries"], "NOT_AVAILABLE")
        self.assertIn("DESCONOCIDA", moche["caveat_es"])
        piura = next(l for l in links if l["zone_id"] == "piura_province_context:MORROPON")
        self.assertEqual(piura["province_as_printed"], "Morropón")

    def test_quebradas_aviso_outside_the_north_links_nothing(self):
        q = aviso("acp_quebradas_282_2026", "AVISO_CORTO_PLAZO_QUEBRADAS")
        self.assertEqual(q["current"]["departments"], ["CAJAMARCA", "HUANUCO", "UCAYALI"])
        self.assertEqual(X.links_for_aviso(q, ZONES["zones"], None), [])

    def test_surveillance_list_only_active_avisos_and_vigente_first(self):
        vig, fut, old = aviso(), aviso(status="FUTURO"), aviso(status="VENCIDO")
        fut["aviso_key"], old["aviso_key"] = "SENAMHI-ACP-LLUVIAS-2026-283", "SENAMHI-ACP-LLUVIAS-2026-200"
        fut["current"] = dict(fut["current"], departments=["TUMBES"], provinces_by_department={"TUMBES": ["Tumbes"]})
        reg = dict(avisos={vig["aviso_key"]: vig, fut["aviso_key"]: fut, old["aviso_key"]: old})
        out = X.surveillance_list(reg, ZONES, None)
        keys = {a["aviso_key"] for r in out["surveillance_zones"] for a in r["avisos"]}
        self.assertNotIn("SENAMHI-ACP-LLUVIAS-2026-200", keys)  # expired avisos are not active surveillance
        self.assertIn("SENAMHI-ACP-LLUVIAS-2026-200", out["aviso_links"])  # but stay traceable
        self.assertTrue(out["surveillance_zones"][0]["any_vigente"])
        self.assertIn("No es una puntuación de riesgo", out["ordering_note_es"])
        for key, value in X.GUARDS.items():
            self.assertEqual(out[key], value)
        self.assertFalse(out["map_publishable"])
        for r in out["surveillance_zones"]:
            self.assertIn("official_level_note", r["avisos"][0])
            self.assertNotIn("risk", json.dumps(r).lower())


class CrossingWithOfficialOverlay(unittest.TestCase):
    OVERLAY = dict(boundary_source=dict(sha256="b" * 64), zones=[
        dict(zone_id="lalibertad_jequetepeque", intersections=[
            dict(department="CAJAMARCA", province="CONTUMAZA", area_km2=900.0, zone_fraction=0.23),
            dict(department="LA LIBERTAD", province="PACASMAYO", area_km2=700.0, zone_fraction=0.18)]),
        dict(zone_id="lalibertad_moche", intersections=[
            dict(department="LA LIBERTAD", province="TRUJILLO", area_km2=400.0, zone_fraction=0.19)]),
    ])

    def test_spatial_relation_uses_listed_provinces_across_departments(self):
        a = aviso()
        a["current"]["provinces_by_department"]["CAJAMARCA"] = ["Contumazá"]
        links = {l["zone_id"]: l for l in X.links_for_aviso(a, ZONES["zones"], self.OVERLAY)}
        jeq = links["lalibertad_jequetepeque"]
        self.assertEqual(jeq["relation_method"], "BASIN_INTERSECTS_LISTED_PROVINCE")
        self.assertEqual([(h["department"], h["province"]) for h in jeq["evidence"]["intersections"]], [("CAJAMARCA", "CONTUMAZA")])
        self.assertEqual(jeq["evidence"]["boundary_source_sha256"], "b" * 64)
        moche = links["lalibertad_moche"]  # Trujillo is not listed by the aviso
        self.assertEqual(moche["relation_method"], "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES")
        self.assertEqual(links["lalibertad_chicama"]["relation_method"], "REGISTERED_DEPARTMENT_LISTED")  # no overlay row


try:
    import pyproj  # noqa: F401
    import shapely  # noqa: F401
    HAVE_GEO = True
except ImportError:  # the PR gate installs both (requirements.txt)
    HAVE_GEO = False


@unittest.skipUnless(HAVE_GEO, "shapely/pyproj not installed")
class OverlayBuilder(unittest.TestCase):
    PROV = dict(institution="TEST", dataset_title="synthetic squares", obtained_from="test", obtained_at_utc="2026-10-10T00:00:00Z",
                crs="EPSG:4326", department_field="NOMBDEP", province_field="NOMBPROV")

    def square(self, x0, y0, x1, y1):
        return dict(type="Polygon", coordinates=[[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_root = O.ROOT
        O.ROOT = Path(self.tmp.name)
        basin = dict(type="FeatureCollection", features=[dict(type="Feature", properties={}, geometry=self.square(-79.0, -8.0, -78.8, -7.8))])
        raw = json.dumps(basin).encode()
        (O.ROOT / "b.geojson").write_bytes(raw)
        self.zones = dict(zones=[dict(zone_id="z", zone_type="BASIN_GEOMETRY", geometry_path="b.geojson", geometry_sha256=O.sha256_bytes(raw))])
        self.bounds = dict(type="FeatureCollection", features=[
            dict(type="Feature", properties=dict(NOMBDEP="LA LIBERTAD", NOMBPROV="TRUJILLO"), geometry=self.square(-79.2, -8.2, -78.9, -7.6)),
            dict(type="Feature", properties=dict(NOMBDEP="LA LIBERTAD", NOMBPROV="OTUZCO"), geometry=self.square(-78.9, -8.2, -78.5, -7.6)),
            dict(type="Feature", properties=dict(NOMBDEP="LAMBAYEQUE", NOMBPROV="CHICLAYO"), geometry=self.square(-80.0, -7.0, -79.5, -6.5))])

    def tearDown(self):
        O.ROOT = self.saved_root
        self.tmp.cleanup()

    def test_intersections_and_fractions(self):
        out = O.build_overlay(self.bounds, self.PROV, self.zones, "c" * 64)
        z = out["zones"][0]
        self.assertEqual([(r["department"], r["province"]) for r in z["intersections"]], [("LA LIBERTAD", "OTUZCO"), ("LA LIBERTAD", "TRUJILLO")])
        self.assertAlmostEqual(sum(r["zone_fraction"] for r in z["intersections"]), 1.0, places=2)
        self.assertAlmostEqual(z["intersections"][0]["zone_fraction"], 0.5, places=2)
        self.assertEqual(out["boundary_source"]["sha256"], "c" * 64)

    def test_fail_closed_on_bad_inputs(self):
        bad = copy.deepcopy(self.bounds)
        bad["features"][0]["geometry"] = dict(type="Polygon", coordinates=[[[-79, -8], [-78, -7], [-78, -8], [-79, -7], [-79, -8]]])  # bow-tie
        with self.assertRaises(ValueError):
            O.build_overlay(bad, self.PROV, self.zones, "c" * 64)
        projected = copy.deepcopy(self.bounds)
        projected["features"][0]["geometry"] = self.square(700000, 9100000, 710000, 9110000)
        with self.assertRaises(ValueError):
            O.build_overlay(projected, self.PROV, self.zones, "c" * 64)
        with self.assertRaises(ValueError):
            O.build_overlay(self.bounds, dict(self.PROV, institution=None), self.zones, "c" * 64)
        with self.assertRaises(ValueError):
            O.build_overlay(self.bounds, dict(self.PROV, crs="EPSG:32717"), self.zones, "c" * 64)


class CommittedOutput(unittest.TestCase):
    def test_committed_links_are_current(self):
        self.assertEqual(X.main(["--check"]), 0)
