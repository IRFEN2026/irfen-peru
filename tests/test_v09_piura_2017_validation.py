"""IRFEN v0.9 · validación histórica del río Piura (2017, control 2018): extracción PECHP con dos lectores, integridad
IMERG Final diario, reglas estadísticas y aislamiento. Sin red; sin umbrales ni capacidad predictiva."""
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


X = _load("pechp_x", "scripts/v09_pechp_extract.py")
V = _load("piura_v", "scripts/v09_piura_2017_validation.py")
PX = json.loads(X.OUT.read_text(encoding="utf-8"))
D = json.loads(V.OUT.read_text(encoding="utf-8"))
IM = json.loads(V.IMERG.read_text(encoding="utf-8"))


class PechpExtraction(unittest.TestCase):
    def test_rebuilds_byte_for_byte_from_the_archived_pdfs(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(X.main(["--check"]), 0)
        for m in PX["months"]:
            self.assertEqual(hashlib.sha256((X.SRC / m["pdf"]).read_bytes()).hexdigest(), m["pdf_sha256"])

    def test_march_2017_daily_means_reproduce_the_declared_monthly_volume(self):
        m = next(x for x in PX["months"] if x["month"] == "2017-03")
        self.assertEqual(m["tables"]["rivers"]["column_identity_from_report_notes"],
                         {"R_PIURA_1": "PUENTE_SANCHEZ_CERRO", "R_PIURA_2": "EL_PAPAYO"})
        self.assertEqual(m["checks"]["sanchez_cerro_volume_from_daily_means_mmc"], 3530.7)
        self.assertIn(3530.7, m["checks"]["declared"])
        self.assertEqual(m["tables"]["rivers"]["days"]["27"]["values"]["R_PIURA_1"], 2754.5)  # checked on the page image
        self.assertEqual(m["tables"]["nacara_tambogrande"]["days"]["26"]["values"]["TAMBOGRANDE"], 2676.0)

    def test_every_accepted_row_is_read_by_two_readers_and_gaps_stay_null(self):
        for m in PX["months"]:
            for name, t in m["tables"].items():
                if t.get("status") != "OK":
                    continue
                for day, row in t["days"].items():
                    self.assertIn(row["readers"], ("DOS_LECTORES", "UN_LECTOR"))
                    self.assertTrue(1 <= int(day) <= 31)
        m = next(x for x in PX["months"] if x["month"] == "2017-03")
        self.assertIsNone(m["tables"]["rivers"]["days"]["21"]["values"]["CURUMUY"])  # blank cell in the report, not 0

    def test_instantaneous_extremes_are_kept_apart_from_daily_means(self):
        m = next(x for x in PX["months"] if x["month"] == "2017-03")
        inst = {(x["river"], x["station"]): x for x in m["instantaneous"]}
        self.assertEqual(inst[("Chira", "El Ciruelo")]["max_m3s"], 2286.2)
        self.assertEqual(inst[("Chira", "El Ciruelo")]["max_day"], 31)
        self.assertEqual(m["tables"]["rivers"]["statistic"], "CAUDAL_MEDIO_DIARIO")
        self.assertNotIn("PUENTE_SANCHEZ_CERRO", {x["station"] for x in m["instantaneous"]})  # not published for Piura

    def test_source_inconsistencies_are_recorded_not_corrected(self):
        m = next(x for x in PX["months"] if x["month"] == "2017-04")
        period = [n for n in m["notes"] if n["kind"] == "VOLUMEN_DE_PERIODO_SANCHEZ_CERRO_DECLARADO"]
        self.assertEqual(period[0]["mmc"], 5489.3)
        self.assertIn("2016", period[0]["source_inconsistency"])  # the April 2017 report labels the period «2016»
        self.assertGreater(m["checks"]["el_papayo_two_tables"]["days_different"], 0)

    def test_visual_check_image_is_archived(self):
        self.assertTrue((X.SRC / "visual_check_2017-03_p6_days23-31.png").is_file())

    def test_image_only_tables_are_declared_not_guessed(self):
        m = next(x for x in PX["months"] if x["month"] == "2017-02")
        self.assertIn("TABLA_EN_IMAGEN", m["tables"]["rivers"]["status"])
        self.assertNotIn("days", m["tables"]["rivers"])


class ImergFinalIntegrity(unittest.TestCase):
    def test_units_versions_time_and_counts(self):
        i = D["rain"]["integrity"]
        self.assertEqual(i["units"], ["mm/day"])
        self.assertEqual(i["versions"], ["V07B"])
        self.assertEqual(i["internal_day_matches"], i["days"])
        self.assertEqual(i["name_day_matches"], i["days"])
        self.assertEqual(i["sha256_recorded"], i["days"])
        self.assertEqual(i["cnt_range"], [48, 48])

    def test_absent_days_are_recorded_never_zero(self):
        for day, reason in IM["absent"].items():
            self.assertNotIn(day, IM["days"])
            self.assertTrue(reason)
            self.assertIsNone(D["rain"]["series"].get(day, {}).get("p_mm"))
        for k, acc in D["rain"]["accumulations"].items():
            for day in IM["absent"]:
                self.assertIsNone(acc.get(day), (k, day))


class StatisticsAndRules(unittest.TestCase):
    def test_spearman_and_pearson(self):
        self.assertEqual(V.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0)
        self.assertEqual(V.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1.0)
        self.assertIsNone(V.spearman([1, 2, 3], [1, 2, 3]))  # too short
        self.assertIsNone(V.pearson([1, 1, 1, 1, 1], [1, 2, 3, 4, 5]))  # constant series

    def test_accumulation_requires_every_day(self):
        s = {"2017-03-01": {"p_mm": 1.0}, "2017-03-02": {"p_mm": None}, "2017-03-03": {"p_mm": 2.0}}
        a = V.accumulations(s, 2)
        self.assertIsNone(a["2017-03-02"])
        self.assertIsNone(a["2017-03-03"])

    def test_full_lag_curves_are_reported_not_only_the_maximum(self):
        for y, s in D["seasons"].items():
            for st, r in s.get("stations", {}).items():
                if r.get("p_vs_q"):
                    self.assertEqual([c["lag_days"] for c in r["p_vs_q"]], list(range(0, 11)))
                    for k, curve in r["acc_vs_q"].items():
                        self.assertEqual(len(curve), 11, (y, st, k))

    def test_canals_are_context_only(self):
        for s in D["seasons"].values():
            for st in s.get("stations", {}):
                self.assertNotIn(st, V.CANALS)

    def test_guards_polygon_flag_and_no_thresholds(self):
        for k, v in V.GUARDS.items():
            self.assertEqual(D[k], v, k)
        self.assertEqual(D["polygon"]["flag"], "POLIGONO_NO_EQUIVALENTE_A_LA_CUENCA_DE_LA_ESTACION")
        text = V.OUT.read_text(encoding="utf-8")
        self.assertNotRegex(text, r'"(threshold|umbral)[a-z_]*":\s*[0-9]')

    def test_rebuilds_byte_for_byte_and_view_is_self_contained(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(V.main(["--check"]), 0)
        html = V.HTML.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(src|href)=\"https?://", html))
        self.assertFalse(str(V.HTML.relative_to(ROOT)).startswith("site/"))


class Isolation(unittest.TestCase):
    def test_engine_and_priority_do_not_read_historical_research(self):
        for script in ("v09_zone_rain_engine.py", "v09_build_dashboard_data.py", "v09_build_territory_bundle.py",
                       "v09_imerg_north_archive.py", "v09_aviso_zone_crossing.py"):
            text = (ROOT / "scripts" / script).read_text(encoding="utf-8")
            for token in ("research/historical", "pechp", "imerg_final_daily"):
                self.assertNotIn(token, text, (script, token))


if __name__ == "__main__":
    unittest.main()
