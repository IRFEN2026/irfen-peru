"""IRFEN v0.9 aviso ↔ surveillance-zone crossing: offline tests.

Avisos come from the real archived INDECI bulletin fixture (SENAMHI ACP lluvias N°282, 2026-10-09), replayed
as an archived document, never as a current event.
"""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
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
        self.assertEqual(len(by_method["DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN"]), 10)  # Tumbes, Lambayeque, La Libertad basins
        self.assertNotIn("BASIN_INTERSECTS_LISTED_PROVINCE", by_method)  # never claimed without official boundaries
        moche = next(l for l in links if l["zone_id"] == "lalibertad_moche")
        self.assertEqual(moche["evidence"]["official_boundaries"], "NOT_AVAILABLE_OR_UNVERIFIED")
        self.assertIn("DESCONOCIDA", moche["caveat_es"])
        piura = next(l for l in links if l["zone_id"] == "piura_province_context:MORROPON")
        self.assertEqual(piura["province_as_printed"], "Morropón")

    def test_quebradas_aviso_outside_the_north_links_nothing(self):
        q = aviso("acp_quebradas_282_2026", "AVISO_CORTO_PLAZO_QUEBRADAS")
        self.assertEqual(q["current"]["departments"], ["CAJAMARCA", "HUANUCO", "UCAYALI"])
        self.assertEqual(X.links_for_aviso(q, ZONES["zones"], None), [])

    def test_surveillance_list_only_active_avisos_and_vigente_first(self):
        vig, fut, old = aviso(), aviso(), aviso()
        fut["aviso_key"], old["aviso_key"] = "SENAMHI-ACP-LLUVIAS-2026-283", "SENAMHI-ACP-LLUVIAS-2026-200"
        fut["current"] = dict(fut["current"], departments=["TUMBES"], provinces_by_department={"TUMBES": ["Tumbes"]},
                              validity_start="2026-10-10T13:00:00-05:00", validity_end="2026-10-11T13:00:00-05:00")
        old["current"] = dict(old["current"], validity_start="2026-10-01T13:00:00-05:00", validity_end="2026-10-02T13:00:00-05:00")
        reg = dict(avisos={vig["aviso_key"]: vig, fut["aviso_key"]: fut, old["aviso_key"]: old})
        out = X.surveillance_list(reg, ZONES, None, NOW_VIGENTE, "AL_DIA")
        keys = {a["aviso_key"] for r in out["surveillance_zones"] for a in r["avisos"]}
        self.assertNotIn("SENAMHI-ACP-LLUVIAS-2026-200", keys)  # expired avisos are not active surveillance
        self.assertEqual(out["aviso_links"]["SENAMHI-ACP-LLUVIAS-2026-200"]["status"], "VENCIDO")  # but stay traceable
        self.assertFalse(out["aviso_links"]["SENAMHI-ACP-LLUVIAS-2026-200"]["in_surveillance"])
        self.assertTrue(out["surveillance_zones"][0]["any_vigente"])
        self.assertEqual(out["statuses_valid_until_utc"], "2026-10-10T18:00:00+00:00")  # next validity edge
        self.assertIn("No es una puntuación de riesgo", out["ordering_note_es"])
        for key, value in X.GUARDS.items():
            self.assertEqual(out[key], value)
        self.assertFalse(out["map_publishable"])
        for r in out["surveillance_zones"]:
            self.assertIn("official_level_note", r["avisos"][0])
            self.assertNotIn("risk", json.dumps(r).lower())


NOW_VIGENTE = datetime(2026, 10, 9, 20, 0, tzinfo=timezone.utc)


class TemporalUpdate(unittest.TestCase):
    """Statuses are re-evaluated from the documented validity with the clock, never taken from a stale field."""

    def test_stored_vigente_is_expired_by_the_clock(self):
        a = aviso(status="VIGENTE")  # stored status says VIGENTE ...
        reg = dict(avisos={a["aviso_key"]: a})
        after = datetime(2026, 10, 10, 18, 0, 1, tzinfo=timezone.utc)  # ... but validity ended at 13:00 Lima
        out = X.surveillance_list(reg, ZONES, None, after, "AL_DIA")
        self.assertEqual(out["surveillance_zones"], [])
        self.assertEqual(out["aviso_links"][a["aviso_key"]]["status"], "VENCIDO")
        self.assertEqual(len(out["aviso_links"][a["aviso_key"]]["links"]), 15)  # history keeps its territorial links
        self.assertIsNone(out["statuses_valid_until_utc"])
        before = X.surveillance_list(reg, ZONES, None, datetime(2026, 10, 9, 17, 59, tzinfo=timezone.utc), "AL_DIA")
        self.assertEqual({a["status"] for r in before["surveillance_zones"] for a in r["avisos"]}, {"FUTURO"})

    def test_unknown_validity_stays_under_surveillance_with_a_note(self):
        a = aviso()
        a["current"].pop("validity_start")
        a["current"].pop("validity_end")
        out = X.surveillance_list(dict(avisos={a["aviso_key"]: a}), ZONES, None, NOW_VIGENTE, "AL_DIA")
        self.assertEqual(len(out["surveillance_zones"]), 15)
        self.assertTrue(all("DESCONOCIDO" in " ".join(r["missing_data"]) for r in out["surveillance_zones"]))

    def test_failed_source_marks_the_list_possibly_incomplete(self):
        a = aviso()
        out = X.surveillance_list(dict(avisos={a["aviso_key"]: a}), ZONES, None, NOW_VIGENTE, "DESACTUALIZADA")
        self.assertTrue(out["possibly_incomplete"])
        self.assertEqual(out["source_state"], "DESACTUALIZADA")
        self.assertIn("desactualizada", out["reader_rule_es"])


class CrossingWithOfficialOverlay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = X.ROOT
        X.ROOT = Path(self.tmp.name)
        data = b'{"type":"FeatureCollection","features":[]}'
        (X.ROOT / "bounds.geojson").write_bytes(data)
        sha = {z["zone_id"]: z.get("geometry_sha256") for z in ZONES["zones"]}
        self.overlay = dict(boundary_source=dict(sha256=O.sha256_bytes(data), path="bounds.geojson"), zones=[
            dict(zone_id="lalibertad_jequetepeque", geometry_sha256=sha["lalibertad_jequetepeque"], basin_fraction_covered_by_boundaries=1.0,
                 intersections=[dict(department="CAJAMARCA", province="CONTUMAZA", area_km2=900.0, zone_fraction=0.23),
                                dict(department="LA LIBERTAD", province="PACASMAYO", area_km2=700.0, zone_fraction=0.18)]),
            dict(zone_id="lalibertad_moche", geometry_sha256=sha["lalibertad_moche"], basin_fraction_covered_by_boundaries=0.999,
                 intersections=[dict(department="LA LIBERTAD", province="TRUJILLO", area_km2=400.0, zone_fraction=0.19)]),
            dict(zone_id="lalibertad_viru", geometry_sha256=sha["lalibertad_viru"], basin_fraction_covered_by_boundaries=0.62,
                 intersections=[dict(department="LA LIBERTAD", province="TRUJILLO", area_km2=300.0, zone_fraction=0.16)]),
            dict(zone_id="lalibertad_chicama", geometry_sha256="0" * 64, basin_fraction_covered_by_boundaries=1.0,
                 intersections=[dict(department="LA LIBERTAD", province="GRAN CHIMU", area_km2=1.0, zone_fraction=0.5)]),
        ])

    def tearDown(self):
        X.ROOT = self.saved
        self.tmp.cleanup()

    def links(self, overlay):
        a = aviso()
        a["current"]["provinces_by_department"]["CAJAMARCA"] = ["Contumazá"]
        return {l["zone_id"]: l for l in X.links_for_aviso(a, ZONES["zones"], overlay)}

    def test_spatial_positive_and_verified_negative(self):
        links = self.links(self.overlay)
        jeq = links["lalibertad_jequetepeque"]
        self.assertEqual(jeq["relation_method"], "BASIN_INTERSECTS_LISTED_PROVINCE")
        self.assertEqual([(h["department"], h["province"]) for h in jeq["evidence"]["intersections"]], [("CAJAMARCA", "CONTUMAZA")])
        self.assertEqual(jeq["evidence"]["boundary_source_sha256"], self.overlay["boundary_source"]["sha256"])
        self.assertEqual(links["lalibertad_moche"]["relation_method"], "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES")

    def test_incomplete_coverage_never_yields_a_negative(self):
        viru = self.links(self.overlay)["lalibertad_viru"]
        self.assertEqual(viru["relation_method"], "DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN")
        self.assertIn("62.0%", viru["evidence"]["reason"])

    def test_overlay_from_another_geometry_version_is_ignored(self):
        chicama = self.links(self.overlay)["lalibertad_chicama"]  # overlay row says Gran Chimú, but for another geometry
        self.assertEqual(chicama["relation_method"], "DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN")
        _, notes = X.verify_overlay(self.overlay, ZONES["zones"])
        self.assertTrue(any("lalibertad_chicama" in n for n in notes))

    def test_boundary_file_hash_mismatch_discards_the_overlay(self):
        (X.ROOT / "bounds.geojson").write_bytes(b"tampered")
        links = self.links(self.overlay)
        self.assertEqual(links["lalibertad_jequetepeque"]["relation_method"], "DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN")
        self.assertEqual(X.verify_overlay(self.overlay, ZONES["zones"])[0], {})


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
        self.assertEqual(sorted((r["department"], r["province"]) for r in z["intersections"]), [("LA LIBERTAD", "OTUZCO"), ("LA LIBERTAD", "TRUJILLO")])
        self.assertAlmostEqual(sum(r["zone_fraction"] for r in z["intersections"]), 1.0, places=2)
        for r in z["intersections"]:
            self.assertAlmostEqual(r["zone_fraction"], 0.5, places=2)
        self.assertEqual(z["departments"], ["LA LIBERTAD"])
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
    def test_committed_links_replay_from_their_inputs(self):
        # Clock-independent: the build is replayed at the committed evaluated_at_utc. The capture workflow commits the
        # registry and the crossing together; if the registry moved on without its crossing (the gap between a data
        # commit and the next scheduled run), the strict check belongs to that workflow, not to unrelated PRs.
        committed = json.loads(X.OUT.read_text(encoding="utf-8"))
        if committed["inputs"]["registry_sha256"] != X.sha256_bytes(X.REGISTRY.read_bytes()):
            self.skipTest("registry changed after the committed crossing; the capture workflow regenerates and checks it")
        self.assertEqual(X.main(["--check"]), 0)
