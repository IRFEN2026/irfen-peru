"""IRFEN v0.9 ECMWF ENS por provincia, recolector IMERG Late y evaluación en sombra: pruebas sin red.

Las geometrías son las provincias INEI ya archivadas en el repositorio; el ensamble es sintético y conocido, de modo
que cada probabilidad esperada se calcula a mano. La descarga y la lectura GRIB solo corren en el runner.
"""
import csv
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = load_module("v09_ecmwf_ens_north", "scripts/v09_ecmwf_ens_north.py")
V = load_module("v09_fc_evaluate", "scripts/v09_fc_evaluate.py")
I = load_module("v09_imerg_late_province_daily", "scripts/v09_imerg_late_province_daily.py")

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
                                             [[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]}


def grid():
    lats = np.arange(-3.0, -9.6 - 1e-9, -0.25)
    lons = np.arange(-81.75, -76.5 + 1e-9, 0.25)
    _, _, la, lo = E.subset_bbox(lats, lons)
    return la, lo


def provinces():
    path, _ = E.boundaries_paths()
    return E.load_provinces(path)


class Geometry(unittest.TestCase):
    def test_hole_is_excluded_and_edges_are_consistent(self):
        poly = E._rings_of(SQUARE)[0]
        px = np.array([0.5, 2.0, 3.5, 5.0])
        py = np.array([0.5, 2.0, 3.5, 2.0])
        self.assertEqual(E.points_in_polygon(px, py, poly).tolist(), [True, False, True, False])

    def test_multipolygon_and_centroid(self):
        geom = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
                                                        [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]]]}
        polys = E._rings_of(geom)
        self.assertEqual(len(polys), 2)
        area, cx, cy = E.ring_area_centroid(polys[0][0])
        self.assertAlmostEqual(area, 4.0)
        self.assertAlmostEqual(cx, 1.0)
        self.assertAlmostEqual(cy, 1.0)

    def test_real_inei_north_provinces_all_get_land_cells(self):
        provs = provinces()
        self.assertEqual(len(provs), 26)  # Tumbes 3 + Piura 8 + Lambayeque 3 + La Libertad 12
        self.assertEqual({p["department"] for p in provs}, set(E.DEPARTMENTS))
        la, lo = grid()
        assignment = E.assign_cells(provs, la, lo)
        land = np.zeros(la.size * lo.size, dtype=bool)
        glon, glat = np.meshgrid(lo, la)
        for p in provs:
            for poly in p["polygons"]:
                land |= E.points_in_polygon(glon.ravel(), glat.ravel(), poly)
        for p in provs:
            a = assignment[p["id"]]
            self.assertGreaterEqual(a["idx"].size, E.MIN_CELLS, p["name"])
            if a["method"].startswith("NEAREST"):
                self.assertTrue(land[a["idx"]].all(), f"{p['name']}: el respaldo no debe usar celdas de mar")
        self.assertTrue(assignment["2001"]["method"] == "CELL_CENTRE_IN_POLYGON")  # Piura


class Windows(unittest.TestCase):
    def test_windows_close_at_07_peru_for_every_run_hour(self):
        self.assertEqual(E.day_windows(12), [(0, 24), (24, 48), (48, 72)])
        self.assertEqual(E.day_windows(0), [(12, 36), (36, 60), (60, 84)])
        self.assertEqual(E.day_windows(6), [(6, 30), (30, 54), (54, 78)])
        self.assertEqual(E.day_windows(18), [(18, 42), (42, 66), (66, 90)])
        for hour in (0, 6, 12, 18):
            for start, end in E.day_windows(hour):
                self.assertEqual((hour + end) % 24, E.CLOSE_HOUR_UTC)
                self.assertEqual(end - start, 24)

    def test_daily_totals_from_cumulative_metres(self):
        tp = np.zeros((2, 3, 1, 1))
        tp[:, 0] = 0.010  # 10 mm al paso 24
        tp[:, 1] = 0.035  # +25 mm
        tp[:, 2] = 0.0349  # ruido numérico negativo → 0
        d1, d2, d3 = E.daily_totals_mm(tp, [24, 48, 72], [(0, 24), (24, 48), (48, 72)])
        np.testing.assert_allclose(d1, 10.0)
        np.testing.assert_allclose(d2, 25.0)
        np.testing.assert_allclose(d3, 0.0)
        with self.assertRaises(ValueError):
            E.daily_totals_mm(tp, [24, 48], [(48, 72)])


class Probabilities(unittest.TestCase):
    def test_mean_and_max_definitions(self):
        # 4 miembros, provincia de 2 celdas: [0,0], [12,0], [12,12], [30,40]
        day = np.array([[[0.0, 0.0]], [[12.0, 0.0]], [[12.0, 12.0]], [[30.0, 40.0]]])
        stats = E.province_stats(day, {"X": dict(idx=np.array([0, 1]))}, thresholds=(10.0, 25.0))["X"]
        self.assertEqual(stats["p_max"], {"10": 0.75, "25": 0.25})
        self.assertEqual(stats["p_mean"], {"10": 0.5, "25": 0.25})

    def test_run_record_dates_and_guards(self):
        provs = provinces()
        la, lo = grid()
        tp = np.zeros((51, 3, la.size, lo.size))
        tp[:26, 1:, :, :] = 0.030  # la mitad de los miembros llueve 30 mm en el día 2 en toda la región
        run = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
        rec = E.build_run_record(run, tp, [24, 48, 72], la, lo, provs)
        self.assertEqual([d["valid_date_peru"] for d in rec["days"]], ["2026-10-15", "2026-10-16", "2026-10-17"])
        piura = rec["provinces"]["2001"]["days"]
        self.assertEqual(piura[0]["p_max"]["10"], 0.0)
        self.assertEqual(piura[1]["p_max"]["25"], round(26 / 51, 3))
        self.assertEqual(piura[2]["p_mean"]["10"], 0.0)
        self.assertEqual((rec["test_mode"], rec["deployment_status"], rec["operational_alerting_enabled"]),
                         ("TEST_ONLY", "RESEARCH_ONLY", False))  # cada línea del registro lleva sus guardas
        doc = E.latest_document(dict(state="AVAILABLE"), rec, {})
        self.assertEqual(doc["test_mode"], "TEST_ONLY")
        self.assertIs(doc["operational_alerting_enabled"], False)
        self.assertIn("CC BY 4.0", doc["source"]["attribution"])

    def test_assemble_members_orders_and_requires_full_grid(self):
        fields = {(m, s): np.full((2, 2), 100 * m + s) for m in (2, 0, 1) for s in (48, 24)}
        tp, members, steps = E.assemble_members(fields)
        self.assertEqual((members, steps), ([0, 1, 2], [24, 48]))
        self.assertEqual(tp.shape, (3, 2, 2, 2))
        self.assertEqual(tp[2, 1, 0, 0], 248)
        del fields[(1, 48)]
        with self.assertRaises(ValueError):
            E.assemble_members(fields)

    def test_ledger_is_append_only_and_idempotent(self):
        rec = dict(run_utc="2026-10-14T12:00:00+00:00", provinces={})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            self.assertTrue(E.append_ledger(rec, path))
            self.assertFalse(E.append_ledger(rec, path))
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)


class Verification(unittest.TestCase):
    def ledger(self):
        days = [dict(day=1, valid_date_peru="2026-10-15")]
        probs = [0.9, 0.8, 0.2, 0.1]
        return [dict(thresholds_mm=[10.0], days=days, provinces={
            f"000{i}": dict(days=[dict(day=1, p_max={"10": p}, p_mean={"10": p / 2})]) for i, p in enumerate(probs)})]

    def write_obs(self, tmp, rows):
        path = Path(tmp) / "obs.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(V.OBS_COLUMNS)
            w.writerows(rows)
        return path

    def test_scores_by_hand(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = V.read_observations(self.write_obs(tmp, [
                ["2026-10-15", "0", "15", "8", "SENAMHI", "2"],      # evento, p=0.9 → acierto
                ["2026-10-15", "1", "3", "", "SENAMHI", "1"],        # sin evento, p=0.8 → falsa alarma
                ["2026-10-15", "2", "12", "6", "SENAMHI", "3"],      # evento, p=0.2 → omisión
                ["2026-10-15", "3", "-999", "-999", "SENAMHI", "0"],  # faltante: excluido, nunca cero
            ]))
        probs, events = V.pairs(self.ledger(), obs, 1, 10.0, "max")
        self.assertEqual(probs.tolist(), [0.9, 0.8, 0.2])
        self.assertEqual(events.tolist(), [True, False, True])
        c = V.contingency(probs, events, 0.5)
        self.assertEqual((c["hits"], c["false_alarms"], c["misses"]), (1, 1, 1))
        self.assertEqual((c["pod"], c["far"]), (0.5, 0.5))
        b = V.brier(probs, events)
        self.assertAlmostEqual(b["brier"], round(((0.1) ** 2 + 0.8 ** 2 + 0.8 ** 2) / 3, 4))
        self.assertAlmostEqual(b["base_rate"], round(2 / 3, 4))
        mean_probs, mean_events = V.pairs(self.ledger(), obs, 1, 10.0, "mean")
        self.assertEqual(mean_probs.tolist(), [0.45, 0.1])  # la media vacía de la provincia 1 es faltante

    def test_duplicate_or_incomplete_observations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                V.read_observations(self.write_obs(tmp, [["2026-10-15", "1", "1", "1", "x", "1"]] * 2))
            bad = Path(tmp) / "bad.csv"
            bad.write_text("fecha_peru,idprov\n2026-10-15,0001\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                V.read_observations(bad)

    def test_verify_document_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            obs = V.read_observations(self.write_obs(tmp, [["2026-10-15", "0", "15", "8", "S", "1"]]))
        results = V.verify(self.ledger(), obs)
        self.assertEqual({r["kind"] for r in results}, {"max", "mean"})
        self.assertFalse(any(r["enough_sample"] for r in results))
        self.assertEqual(len(results[0]["contingency"]), len(V.ALERT_PROBS))


class ImergCollector(unittest.TestCase):
    def test_rain_day_is_07_to_07_peru(self):
        slots = I.rain_day_slots(datetime(2026, 10, 15).date())
        self.assertEqual(len(slots), 48)
        self.assertEqual(slots[0].isoformat(), "2026-10-14T12:00:00+00:00")
        self.assertEqual(slots[-1].isoformat(), "2026-10-15T11:30:00+00:00")
        self.assertTrue(all(I.rain_day_of(s) == datetime(2026, 10, 15).date() for s in slots))
        self.assertEqual(I.rain_day_of(datetime(2026, 10, 15, 12, tzinfo=timezone.utc)).isoformat(), "2026-10-16")

    def test_candidate_days_only_closed_days(self):
        now = datetime(2026, 10, 15, 11, 59, tzinfo=timezone.utc)  # el día 15 aún no cierra
        self.assertEqual(I.candidate_days(now, 3)[-1].isoformat(), "2026-10-14")
        now = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(I.candidate_days(now, 3)[-1].isoformat(), "2026-10-15")

    def test_area_regrid_conserves_uniform_and_weights_partial_cells(self):
        src_lat = np.round(np.arange(-3.05, -4.0, -0.1), 2)
        src_lon = np.round(np.arange(-81.05, -80.0, 0.1), 2)
        dst_lat, dst_lon = np.array([-3.25, -3.5]), np.array([-80.75, -80.5])
        uniform = np.full((src_lat.size, src_lon.size), 7.0)
        np.testing.assert_allclose(I.regrid_area_mean(uniform, src_lat, src_lon, dst_lat, dst_lon), 7.0)
        w = I.overlap_matrix(np.array([-3.15, -3.25, -3.35]), 0.1, np.array([-3.25]), 0.25)
        np.testing.assert_allclose(w, [[0.3, 0.4, 0.3]])  # bordes: 0,075° de 0,25°; los pesos suman 1
        holes = uniform.copy()
        holes[:, :] = np.nan
        self.assertTrue(np.isnan(I.regrid_area_mean(holes, src_lat, src_lon, dst_lat, dst_lon)).all())

    def test_accumulator_counts_each_half_hour_once_and_marks_gaps(self):
        lat, lon = np.array([-3.05, -3.15]), np.array([-80.05])
        acc = I.DayAccumulator(lat, lon)
        rate = np.array([[2.0], [np.nan]])
        for k in range(48):
            self.assertTrue(acc.add(f"slot{k}", lat, lon, rate))
        self.assertFalse(acc.add("slot0", lat, lon, rate))  # misma media hora: no suma dos veces
        self.assertTrue(acc.complete)
        f = acc.field()
        self.assertAlmostEqual(f[0, 0], 48.0)  # 2 mm/h × 24 h
        self.assertTrue(np.isnan(f[1, 0]))     # celda sin datos: faltante, nunca cero
        with tempfile.TemporaryDirectory() as tmp:
            acc.save(Path(tmp) / "d.npz")
            back = I.DayAccumulator.load(Path(tmp) / "d.npz")
        self.assertEqual(len(back.granules), 48)
        np.testing.assert_allclose(back.field()[0, 0], 48.0, rtol=1e-6)

    def test_province_rows_use_forecast_support_and_native_max(self):
        provs = provinces()
        lat = np.round(np.arange(-3.05, -9.6, -0.1), 2)
        lon = np.round(np.arange(-81.65, -76.6, 0.1), 2)
        field = np.zeros((lat.size, lon.size))
        r = int(np.argmin(abs(lat - (-5.15))))
        c = int(np.argmin(abs(lon - (-80.65))))
        field[r, c] = 100.0  # un chubasco de 0,1° en la provincia de Piura
        rows = {x["idprov"]: x for x in I.province_rows(datetime(2026, 10, 15).date(), field, lat, lon, provs)}
        piura = rows["2001"]
        self.assertEqual(float(piura["lluvia_max_nativo_mm"]), 100.0)
        self.assertLess(float(piura["lluvia_max_mm"]), 100.0 * 0.25)  # en 0,25° el chubasco se diluye
        self.assertGreater(float(piura["lluvia_max_mm"]), 0.0)
        incomplete = field.copy()
        incomplete[r, c] = np.nan
        rows = {x["idprov"]: x for x in I.province_rows(datetime(2026, 10, 15).date(), incomplete, lat, lon, provs)}
        self.assertEqual(rows["2001"]["lluvia_max_mm"], "")


class EvaluationExtras(unittest.TestCase):
    def test_brier_decomposition_and_auc(self):
        probs = np.array([0.9, 0.9, 0.1, 0.1])
        events = np.array([True, True, False, False])
        d = V.brier_decomposition(probs, events)
        self.assertAlmostEqual(d["uncertainty"], 0.25)
        self.assertAlmostEqual(d["resolution"], 0.25)
        self.assertAlmostEqual(d["reliability"], 0.01)
        self.assertEqual(V.roc_auc(probs, events), 1.0)
        self.assertEqual(V.roc_auc(np.array([0.5, 0.5]), np.array([True, False])), 0.5)
        self.assertIsNone(V.roc_auc(probs, np.zeros(4, bool)))

    def test_three_events_are_not_a_sufficient_sample(self):
        probs = np.linspace(0, 1, 104)
        few = np.zeros(104, bool)
        few[-3:] = True  # el caso real del 14-10-2026: 104 pares, 3 eventos
        self.assertFalse(V.score_block(probs, few)["enough_sample"])
        enough = np.zeros(104, bool)
        enough[-12:] = True
        self.assertTrue(V.score_block(probs, enough)["enough_sample"])
        self.assertFalse(V.score_block(probs, ~np.zeros(104, bool))["enough_sample"])  # sin días secos tampoco

    def test_backfill_runs_are_scored_apart_from_realtime(self):
        base = dict(thresholds_mm=[10.0], days=[dict(day=1, valid_date_peru="2026-10-10",
                                                      end_utc="2026-10-10T12:00:00+00:00")],
                    provinces={"2001": dict(days=[dict(day=1, p_max={"10": 0.7}, p_mean={"10": 0.2})])})
        live = dict(base, run_utc="a", archived_at_utc="2026-10-09T09:00:00+00:00")
        late = dict(base, run_utc="b", archived_at_utc="2026-10-14T20:00:00+00:00")
        back = dict(late, run_utc="c", backfill=True)
        obs = {("2026-10-10", "2001"): dict(max=12.0, mean=3.0)}
        self.assertEqual(V.pairs([live, late, back], obs, 1, 10.0, "max", "realtime")[0].size, 1)
        self.assertEqual(V.pairs([live, late, back], obs, 1, 10.0, "max", "backfill")[0].size, 1)
        rows = V.verify([live, back], obs, ("max",), "backfill")
        self.assertTrue(all(r["mode"] == "backfill" for r in rows))

    def test_forecast_archived_after_window_is_excluded(self):
        run = dict(thresholds_mm=[10.0], archived_at_utc="2026-10-16T13:00:00+00:00",
                   days=[dict(day=1, valid_date_peru="2026-10-15", end_utc="2026-10-15T12:00:00+00:00"),
                         dict(day=2, valid_date_peru="2026-10-16", end_utc="2026-10-16T12:00:00+00:00"),
                         dict(day=3, valid_date_peru="2026-10-17", end_utc="2026-10-17T12:00:00+00:00")],
                   provinces={"2001": dict(days=[dict(day=k, p_max={"10": 0.5}, p_mean={"10": 0.1}) for k in (1, 2, 3)])})
        obs = {(f"2026-10-1{k}", "2001"): dict(max=20.0, mean=1.0) for k in (5, 6, 7)}
        self.assertEqual(V.pairs([run], obs, 1, 10.0, "max")[0].size, 0)
        self.assertEqual(V.pairs([run], obs, 2, 10.0, "max")[0].size, 0)
        self.assertEqual(V.pairs([run], obs, 3, 10.0, "max")[0].size, 1)


if __name__ == "__main__":
    unittest.main()
