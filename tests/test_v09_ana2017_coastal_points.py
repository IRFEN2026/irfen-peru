"""IRFEN v0.9 · ubicaciones documentales ANA 2016-2017 (centros poblados vulnerables por activación de quebradas) en la
costa: reproducibilidad, regla de admisión, comprobación independiente contra el maestro, jurisdicción, datum, cifras
con suma de control y aislamiento respecto de la lluvia y la prioridad. Sin red."""
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_build_ana2017_coastal_points", ROOT / "scripts/v09_build_ana2017_coastal_points.py")
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)
D = json.loads(B.OUT.read_text(encoding="utf-8"))
OCR = json.loads(B.OCR.read_text(encoding="utf-8"))
PROVINCES = json.loads(B.PROVINCES.read_text(encoding="utf-8"))["features"]
REVIEW = json.loads(B.VISUAL.read_text(encoding="utf-8"))
EXPECTED_ZONE = {"TUMBES": 17, "PIURA": 17, "LAMBAYEQUE": 17, "LA LIBERTAD": 17, "ANCASH": 18, "LIMA": 18, "ICA": 18,
                 "AREQUIPA": 18, "MOQUEGUA": 19, "TACNA": 19}


class Reproducible(unittest.TestCase):
    def test_rebuilds_byte_for_byte_from_committed_inputs(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(B.main(["--check"]), 0)
        self.assertEqual(D["method"]["ocr_sha256"], hashlib.sha256(B.OCR.read_bytes()).hexdigest())
        record = json.loads(B.RECORD.read_text(encoding="utf-8"))
        self.assertEqual(D["source"]["pdf_sha256"], record["sha256"])
        self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")
        pages = json.loads(B.PAGES_INDEX.read_text(encoding="utf-8"))
        self.assertEqual(pages["pdf_sha256"], record["sha256"])
        for page in pages["pages"]:  # the rendered pages the OCR read are the committed ones
            self.assertEqual(hashlib.sha256((B.SRC / "table_pages_300dpi" / page["file"]).read_bytes()).hexdigest(), page["sha256"])

    def test_guards(self):
        for k, v in B.GUARDS.items():
            self.assertEqual(D[k], v, k)
        self.assertIn("NO la ubicación de la quebrada", D["purpose_es"])
        self.assertIn("No entra en la lluvia ni en la prioridad", D["purpose_es"])


class Admission(unittest.TestCase):
    def test_every_admitted_point_follows_the_rule(self):
        admitted = [p for p in D["points"] if p["status"] == "ADMITIDA_UBICACION_DOCUMENTAL"]
        self.assertGreater(len(admitted), 500)
        prov = {(f["properties"]["NOMBDEP"], f["properties"]["NOMBPROV"]): f for f in PROVINCES}
        for p in admitted:
            u = p["utm"]
            self.assertEqual(len(str(int(u["easting_m"]))), 6, p["id"])  # a printed decimal is kept as printed
            self.assertEqual(len(str(int(u["northing_m"]))), 7, p["id"])
            self.assertEqual(u["zone"], EXPECTED_ZONE[p["department"]], p["id"])  # datum read from the cuadro footer
            self.assertEqual(u["epsg"], f"EPSG:327{u['zone']}")
            self.assertEqual(p["reasons"], [])
            self.assertIn(p["coordinate_basis"], ("OCR_2_DE_3", "OCR_1_DE_3_MAS_TRANSCRIPCION_DEL_MAESTRO",
                                                  "REVISION_VISUAL_MAS_2_RELECTURAS_OCR", "OCR_MAS_REVISION_VISUAL_DE_LA_CELDA"))
            # re-derive the position and the jurisdiction from the original UTM values
            lon, lat = B.utm_to_lonlat(u["easting_m"], u["northing_m"], u["zone"])
            self.assertAlmostEqual(lon, p["lon"], places=5)
            self.assertAlmostEqual(lat, p["lat"], places=5)
            dep = "LIMA" if p["department"] == "LIMA" else p["department"]
            f = prov.get((dep, p["province_inei"])) or prov.get(("CALLAO", p["province_inei"]))
            self.assertIsNotNone(f, p["id"])
            self.assertTrue(B.in_geometry(p["lon"], p["lat"], f["geometry"]), p["id"])
            self.assertTrue(-18.5 < p["lat"] < -3.0 and -81.5 < p["lon"] < -69.0, p["id"])

    def test_each_value_is_backed_by_two_independent_reads(self):
        tables = {int(re.search(r"cuadro(\d+)", t["file"]).group(1)): t for t in OCR["tables"]}
        reviews = {(e["cuadro"], e["row"]): e for e in REVIEW["entries"]}
        for p in D["points"]:
            if p["status"] != "ADMITIDA_UBICACION_DOCUMENTAL":
                continue
            if p["coordinate_basis"] in ("REVISION_VISUAL_MAS_2_RELECTURAS_OCR", "OCR_MAS_REVISION_VISUAL_DE_LA_CELDA"):
                # printed value read by a person + at least two of three OCR re-reads of the isolated row band agree
                e = reviews[(p["cuadro"], p["row"])]
                self.assertTrue(e["coordinates_confirmed_by_two_reads"], p["id"])
                for k, v in e["ocr_recheck"].items():
                    if k in ("este", "norte"):
                        self.assertGreaterEqual(v["ocr_reads_agreeing"], 2, (p["id"], k))
                        self.assertEqual(float(v["printed"]), float(p["utm"]["easting_m" if k == "este" else "northing_m"]))
                continue
            row = next(r for r in tables[p["cuadro"]]["rows"] if r["row_index"] == p["ocr_row_index"])
            reads_e = [B.digits(row["cells"]["este"].get(k, "")) for k in ("read_a", "read_b", "read_c")]
            reads_n = [B.digits(row["cells"]["norte"].get(k, "")) for k in ("read_a", "read_b", "read_c")]
            if p["coordinate_basis"] == "OCR_2_DE_3":
                self.assertGreaterEqual(reads_e.count(str(p["utm"]["easting_m"])), 2, p["id"])
                self.assertGreaterEqual(reads_n.count(str(p["utm"]["northing_m"])), 2, p["id"])
            else:  # one OCR read + the master's independent transcription of the same cuadro row
                self.assertTrue(str(p["utm"]["easting_m"]) in reads_e or str(p["utm"]["northing_m"]) in reads_n, p["id"])
                self.assertTrue(p["inventory_links"] and p["inventory_links"][0]["basis"] == "MISMA_FILA_DEL_CUADRO_EN_EL_MAESTRO")

    def test_independent_transcription_agrees(self):
        """The master transcribed cuadros 9, 11 and 17 by a different reader: every independent OCR value is identical."""
        mc = D["method"]["master_cross_check"]
        self.assertGreaterEqual(mc["rows"], 160)
        self.assertEqual(mc["coordinates_identical"], mc["rows"])
        for p in D["points"]:
            if p["master_transcription_check"]:
                self.assertTrue(p["master_transcription_check"]["matches"], p["id"])

    def test_nothing_doubtful_is_drawn_and_every_gap_is_declared(self):
        for p in D["points"]:
            if p["status"] != "ADMITIDA_UBICACION_DOCUMENTAL":
                self.assertTrue(p["reasons"], p["id"])
        for t in D["tables"]:
            self.assertEqual(t["rows_declared"], B.DECLARED_ROWS[t["cuadro"]])
            self.assertEqual(t["rows"] + len(t["rows_missing"]), t["rows_declared"], t["department"])
            self.assertEqual(sorted(t["rows_visual_review"] + t["rows_missing"]), t["rows_not_read"], t["department"])
            self.assertIn(t["datum_zone"], (17, 18, 19))
        ids = [p["id"] for p in D["points"]]
        self.assertEqual(len(ids), len(set(ids)))  # one point per cuadro row

    def test_exposure_figures_only_with_a_matching_cuadro_total(self):
        for t in D["tables"]:
            ok = t["checksums"]["columns_ok"]
            pts = [p for p in D["points"] if p["cuadro"] == t["cuadro"]]
            for col, key in (("viviendas", "viviendas"), ("hab_directos", "habitantes_directos"), ("hab_indirectos", "habitantes_indirectos")):
                if not ok[col]:
                    self.assertTrue(all(p["exposure"][key] is None for p in pts), (t["department"], col))
                else:
                    self.assertEqual(t["checksums"]["sums_of_rows"][col], t["checksums"]["totals_in_cuadro"][col])

    def test_display_names_only_fix_the_el_misread_and_keep_the_raw_text(self):
        for p in D["points"]:
            for raw_key, shown_key in (("quebrada_ocr", "quebrada_display"), ("centro_poblado_ocr", "centro_poblado_display")):
                raw, shown = p[raw_key], p[shown_key]
                self.assertEqual(shown, B.display_name(raw))
                r_tok, s_tok = raw.split(), shown.split()
                self.assertEqual(len(r_tok), len(s_tok), p["id"])
                for r, d in zip(r_tok, s_tok):
                    if r != d:  # the only allowed change: a misread article becomes «El»
                        self.assertIn(r, ("8", "&", "Ei", "EI", "E1"), p["id"])
                        self.assertEqual(d, "El", p["id"])

    def test_inventory_links_never_add_rows(self):
        master = json.loads(B.MASTER.read_text(encoding="utf-8"))
        ids = {r["inventory_id"] for r in master["candidates"]}
        for p in D["points"]:
            for link in p["inventory_links"]:
                self.assertIn(link["inventory_id"], ids)
                self.assertIn(link["basis"], ("MISMA_FILA_DEL_CUADRO_EN_EL_MAESTRO", "MISMO_NOMBRE_EN_EL_DEPARTAMENTO_POR_COMPROBAR"))
        self.assertEqual(len(master["candidates"]), 400)  # the master is read, never extended

    def test_utm_inverse_matches_pyproj_when_available(self):
        try:
            from pyproj import Transformer
        except ImportError:
            # Reference values (EPSG:32718 Lima, independently known): central meridian and equator are exact.
            self.assertEqual(B.utm_to_lonlat(500000, 10000000, 17), (-81.0, 0.0))
            lon, lat = B.utm_to_lonlat(279280, 8667400, 18)
            self.assertAlmostEqual(lon, -77.0275, places=3)
            self.assertAlmostEqual(lat, -12.0473, places=3)
            return
        for zone, e, n in ((17, 556926, 9601826), (18, 279280, 8667400), (18, 868415, 8185000), (19, 346639, 8084887)):
            x, y = Transformer.from_crs(f"EPSG:327{zone}", "EPSG:4326", always_xy=True).transform(e, n)
            lon, lat = B.utm_to_lonlat(e, n, zone)
            self.assertAlmostEqual(lon, x, places=7)
            self.assertAlmostEqual(lat, y, places=7)


class VisualReviewAndReconciliation(unittest.TestCase):
    """Every row the OCR grid missed is transcribed from the page with a hashed crop, confirmed by OCR re-reads, and the
    declared rows reconcile exactly: declared = admitted + outside province + pending + not read."""

    def test_every_review_is_traceable_to_a_hashed_crop_of_the_page(self):
        for e in REVIEW["entries"]:
            crop = B.SRC / e["crop"]
            self.assertEqual(hashlib.sha256(crop.read_bytes()).hexdigest(), e["crop_sha256"], e["crop"])
            self.assertTrue(e["reason"])
            self.assertIn(e["kind"], ("FILA_NO_LEIDA_TRANSCRITA", "CELDA_CORREGIDA"))
            self.assertEqual(e["page_file"][:3], f"p{e['pdf_page']:02d}")
        for c in REVIEW["control_sample"]["points"]:
            self.assertEqual(hashlib.sha256((B.SRC / c["crop"]).read_bytes()).hexdigest(), c["crop_sha256"])

    def test_reviewed_rows_are_exactly_the_rows_the_ocr_missed(self):
        missed = {(t["cuadro"], n) for t in D["tables"] for n in t["rows_not_read"]}
        transcribed = {(e["cuadro"], e["row"]) for e in REVIEW["entries"] if e["kind"] == "FILA_NO_LEIDA_TRANSCRITA"}
        self.assertEqual(transcribed, missed)
        by_id = {p["id"]: p for p in D["points"]}
        for cu, n in transcribed:
            p = by_id[f"ANA2017-C{cu:02d}-{n:03d}"]
            self.assertEqual(p["text_basis"], "TRANSCRIPCION_VISUAL")
            self.assertIsNone(p["ocr_row_index"])
            self.assertEqual(p["manual_review"]["kind"], "FILA_NO_LEIDA_TRANSCRITA")

    def test_control_sample_outside_the_master_departments_matches(self):
        cs = REVIEW["control_sample"]
        self.assertEqual(cs["coincide"], len(cs["points"]))
        self.assertGreaterEqual(len(cs["points"]), 28)
        by_id = {p["id"]: p for p in D["points"]}
        self.assertTrue({"LA LIBERTAD", "ANCASH", "LIMA", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"} <= {c["department"] for c in cs["points"]})
        for c in cs["points"]:
            p = by_id[c["id"]]
            self.assertEqual((c["easting_m"], c["northing_m"]), (p["utm"]["easting_m"], p["utm"]["northing_m"]))
            self.assertEqual(p["coordinate_basis"], "OCR_2_DE_3")

    def test_declared_rows_reconcile_without_adjusting_figures(self):
        from collections import Counter
        status = Counter(p["status"] for p in D["points"])
        declared = sum(B.DECLARED_ROWS.values())
        missing = sum(len(t["rows_missing"]) for t in D["tables"])
        self.assertEqual(declared, 638)
        self.assertEqual(status["ADMITIDA_UBICACION_DOCUMENTAL"] + status["FUERA_DE_PROVINCIA"] + status["REVISION_PENDIENTE"]
                         + missing, declared)
        for t in D["tables"]:
            pts = [p for p in D["points"] if p["cuadro"] == t["cuadro"]]
            self.assertEqual(len(pts), t["rows"])
            self.assertEqual(t["admitted"], sum(p["status"] == "ADMITIDA_UBICACION_DOCUMENTAL" for p in pts))
            self.assertEqual(t["outside_province"], sum(p["status"] == "FUERA_DE_PROVINCIA" for p in pts))


class Isolation(unittest.TestCase):
    def test_not_used_by_rain_or_priority(self):
        for script in ("v09_zone_rain_engine.py", "v09_build_dashboard_data.py", "v09_build_territory_bundle.py",
                       "v09_imerg_north_archive.py", "v09_aviso_zone_crossing.py"):
            text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            self.assertNotIn("ana2017", text, script)
        bundle = json.loads((ROOT / "site/data/v09/territory_v0_1.json").read_text(encoding="utf-8"))
        self.assertFalse(any(str(f["properties"].get("id", "")).startswith("ANA2017-") for f in bundle["geometries"]["features"]))


if __name__ == "__main__":
    unittest.main()
