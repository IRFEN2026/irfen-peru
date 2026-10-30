"""IRFEN v0.9 · investigación hidrológica: unidades hidrográficas ANA y cauces oficiales por nombre (Tumbes, Piura).
Reproducible sin red; vocabulario cerrado; sin efecto en lluvia, prioridad ni mapa."""
import gzip
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_hydro_association", ROOT / "scripts/v09_hydro_association.py")
H = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(H)
D = json.loads(H.OUT.read_text(encoding="utf-8"))
REQUESTS = [r for p in sorted(H.SRC.glob("requests_*.json")) for r in json.loads(p.read_text(encoding="utf-8"))]
UH_REL = {"UH_QUE_CONTIENE_AL_CENTRO_POBLADO", "FUERA_DE_TODA_UH_DEL_PACIFICO"}
CH_REL = {"NOMBRE_COINCIDE_CERCA", "NOMBRE_COINCIDE_LEJOS", "SIN_LINEA_OFICIAL_CON_ESE_NOMBRE",
          "QUEBRADA_SIN_NOMBRE_EN_EL_CUADRO", "FUENTE_NO_DISPONIBLE"}


class Reproducible(unittest.TestCase):
    def test_rebuilds_from_archived_official_responses(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(H.main(["--check"]), 0)
        archived = {r["file"]: r for r in REQUESTS if r.get("file")}
        for p in sorted(H.SRC.glob("*.gz")):
            self.assertIn(p.name, archived)
            self.assertEqual(hashlib.sha256(gzip.decompress(p.read_bytes())).hexdigest(), archived[p.name]["sha256"], p.name)

    def test_guards(self):
        for k, v in H.GUARDS.items():
            self.assertEqual(D[k], v, k)
        self.assertIn("no son conectividad hidráulica", D["purpose_es"])


class Vocabulary(unittest.TestCase):
    def test_closed_relations_and_no_invented_geometry(self):
        for r in D["points"]:
            self.assertIn(r["uh_relation"], UH_REL)
            self.assertNotIn("geometry", r)
            if r["department"] in H.FUNCTIONAL:
                for src in ("ANA", "IGN"):
                    self.assertIn(r["official_channel_by_name"][src]["relation"], CH_REL)
            else:
                self.assertNotIn("official_channel_by_name", r)

    def test_uh_membership_rederived(self):
        uh, _ = H.load_parts("uh_layer8_pacific")
        by_code = {f["properties"]["CODIGO"]: f for f in uh}
        for r in D["points"][::7]:
            if r["uh_relation"] == "UH_QUE_CONTIENE_AL_CENTRO_POBLADO":
                self.assertTrue(H.B.in_geometry(r["lon"], r["lat"], by_code[r["uh_code"]]["geometry"]), r["id"])

    def test_counts_are_consistent(self):
        pts = json.loads(H.POINTS.read_text(encoding="utf-8"))["points"]
        admitted = [p for p in pts if p["status"] == "ADMITIDA_UBICACION_DOCUMENTAL"]
        self.assertEqual(len(D["points"]), len(admitted))
        for dep, s in D["summary_by_department"].items():
            self.assertEqual(s["admitted"], s["in_uh"] + s["outside_uh"], dep)


class SourceRegistry(unittest.TestCase):
    def test_registry_is_derived_from_the_request_logs(self):
        R = importlib.util.module_from_spec(importlib.util.spec_from_file_location(
            "reg", ROOT / "scripts/v09_hydro_source_registry.py"))
        R.__spec__.loader.exec_module(R)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(R.main(["--check"]), 0)
        reg = json.loads(R.OUT.read_text(encoding="utf-8"))
        by = {s["stage"]: s for s in reg["sources"]}
        self.assertEqual(by["uh"]["verdict"], "UTILIZABLE")
        self.assertEqual(by["uh"]["features_recovered"], D["uh_features"])
        for s in reg["sources"]:
            for k in ("service", "crs", "license", "represents", "coverage", "request_log"):
                self.assertTrue(s[k], (s["stage"], k))
            if s["verdict"] != "UTILIZABLE":  # a blocked source contributes nothing and is never read as a negative
                self.assertEqual(s["features_recovered"], 0)
                self.assertEqual(s["data_files"], [])

    def test_unavailable_channel_sources_are_unknown_not_negative(self):
        for r in D["points"]:
            for src, v in (r.get("official_channel_by_name") or {}).items():
                if v["relation"] == "FUENTE_NO_DISPONIBLE":
                    self.assertNotIn("distance_m", v)


class Isolation(unittest.TestCase):
    def test_not_used_by_rain_priority_or_site(self):
        for script in ("v09_zone_rain_engine.py", "v09_build_dashboard_data.py", "v09_build_territory_bundle.py",
                       "v09_imerg_north_archive.py", "v09_aviso_zone_crossing.py"):
            text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            self.assertNotIn("hydro_association", text, script)
            self.assertNotIn("ana_hydrographic_units", text, script)
        self.assertFalse(str(H.OUT.relative_to(ROOT)).startswith("site/"))


if __name__ == "__main__":
    unittest.main()
