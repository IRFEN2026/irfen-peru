"""IRFEN v0.9 modelo estadístico propio: pruebas sin red con insumos sintéticos de solución conocida."""
import importlib.util
import math
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load_module("v09_own_model", "scripts/v09_own_model.py")
V = load_module("v09_fc_evaluate_for_model", "scripts/v09_fc_evaluate.py")


def synthetic_inputs(days=400, seed=0):
    rng = np.random.default_rng(seed)
    start = date(1995, 9, 1)
    ocean, atmos, indices, rain = {}, {}, {}, {}
    topo = {"2001": dict(elev_mean="50", elev_max="300", frac_sierra="0.0", coast_km="20"),
            "2003": dict(elev_mean="2200", elev_max="3500", frac_sierra="1.0", coast_km="120")}
    for k in range(days):
        d = start + timedelta(days=k)
        sst = 24.0 + 3.0 * math.sin(2 * math.pi * k / 365) + rng.normal(0, 0.5)
        ocean[d.isoformat()] = dict(sst_paita=f"{sst:.2f}", sst_trop="27.0")
        atmos[d.isoformat()] = dict(pw=f"{30 + rng.normal(0, 3):.2f}", u200=f"{rng.normal(0, 5):.2f}",
                                    u850=f"{rng.normal(-3, 2):.2f}", w500=f"{rng.normal(0, 0.02):.3f}")
        indices[d.strftime("%Y-%m")] = dict(nino12="1.0", nino4="0.5", nino34="0.8", E="", C="")
        for pid in topo:
            # en la costa llueve cuando el mar supera 26 °C; en la sierra con probabilidad fija
            p = 0.85 if (pid == "2001" and sst > 26.0) else (0.3 if pid == "2003" else 0.03)
            wet = rng.random() < p
            rain[(d.isoformat(), pid)] = ((20.0 if wet else 1.0), (12.0 if wet else 0.5))
    return M.Inputs(ocean, indices, atmos, topo, rain)


class Logistic(unittest.TestCase):
    def test_irls_recovers_known_coefficients(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(20000, 3))
        beta = np.array([-1.0, 2.0, -0.5, 0.0])
        y = (rng.random(20000) < M.predict_logistic(beta, X)).astype(float)
        est = M.fit_logistic(X, y, l2=0.0)
        np.testing.assert_allclose(est, beta, atol=0.08)

    def test_l2_shrinks_but_keeps_intercept(self):
        rng = np.random.default_rng(2)
        X = rng.normal(size=(500, 2))
        y = (X[:, 0] > 0).astype(float)
        b0 = M.fit_logistic(X, y, l2=0.1)
        b1 = M.fit_logistic(X, y, l2=100.0)
        self.assertLess(abs(b1[1]), abs(b0[1]))

    def test_season_split(self):
        self.assertEqual(M.season_of(date(2026, 9, 1)), 2026)
        self.assertEqual(M.season_of(date(2027, 3, 1)), 2026)


class Features(unittest.TestCase):
    def test_feature_row_complete_and_fail_closed(self):
        inp = synthetic_inputs(400)
        issue = date(1995, 10, 20)
        row = M.feature_row(inp, issue, 2, "2001")
        self.assertEqual(set(row), set(M.FEATURES))
        self.assertEqual(row["coast_x_excess"], row["sst_excess"])  # provincia costera: frac_sierra = 0
        self.assertEqual(M.feature_row(inp, issue, 2, "9999"), None)  # sin topografía: nada se rellena
        del inp.ocean[(issue - timedelta(days=1)).isoformat()]
        self.assertIsNone(M.feature_row(inp, issue, 2, "2001"))
        self.assertIsNotNone(M.feature_row(inp, issue, 2, "2001", ocean_max_age=2))  # tolerancia explícita

    def test_without_rain_history_only_no_rain_variant_applies(self):
        inp = synthetic_inputs(400)
        issue = date(1995, 10, 20)
        del inp.rain[((issue - timedelta(days=1)).isoformat(), "2001")]
        row = M.feature_row(inp, issue, 1, "2001")
        self.assertTrue(set(M.NO_RAIN) <= set(row))
        self.assertFalse(any(f.startswith("rain_") for f in row))


class TrainPredict(unittest.TestCase):
    def test_model_learns_coastal_sst_threshold_and_record_is_evaluable(self):
        inp = synthetic_inputs(400)
        issues = sorted({date.fromisoformat(d) for d, _ in inp.rain})[3:-4]
        X, meta = M.design(inp, issues, ["2001", "2003"], 1, M.NO_RAIN)
        mu, sd = X.mean(0), X.std(0)
        sd[sd == 0] = 1
        y = np.array([m[2] >= 10 for m in meta], float)
        beta = M.fit_logistic((X - mu) / sd, y)
        coef = dict(zip(M.NO_RAIN, beta[1:]))
        self.assertGreater(coef["coast_x_excess"], 0.3)  # el umbral costero de TSM aparece en el ajuste

        models = {f"{k}|{u:g}|{lead}": dict(beta=beta.tolist(), mean=mu.tolist(), sd=sd.tolist())
                  for k in M.KINDS for u in M.THRESHOLDS_MM for lead in M.LEADS}
        model = dict(model_id="test", variants=dict(full=dict(features=list(M.FEATURES), models={}),
                                                    no_rain=dict(features=list(M.NO_RAIN), models=models)))
        provinces = [dict(id="2001", name="PIURA", department="PIURA"), dict(id="2003", name="X", department="PIURA")]
        issue_time = datetime(1996, 3, 1, 0, tzinfo=timezone.utc)
        for pid in ("2001", "2003"):  # sin lluvia previa: debe usar la variante sin persistencia
            inp.rain.pop(("1996-02-29", pid), None)
        rec = M.forecast_record(model, inp, provinces, issue_time)
        self.assertEqual([d["valid_date_peru"] for d in rec["days"]], ["1996-03-02", "1996-03-03", "1996-03-04"])
        self.assertEqual(rec["variants_used"], {"no_rain": 6})
        self.assertEqual((rec["test_mode"], rec["operational_alerting_enabled"]), ("TEST_ONLY", False))
        p = rec["provinces"]["2001"]["days"][0]["p_max"]["10"]
        self.assertTrue(0.0 <= p <= 1.0)
        obs = {(d["valid_date_peru"], "2001"): dict(max=30.0, mean=5.0) for d in rec["days"]}
        rec["archived_at_utc"] = "1996-03-01T08:00:00+00:00"
        probs, events = V.pairs([rec], obs, 1, 10.0, "max")
        self.assertEqual(probs.size, 1)
        self.assertTrue(events[0])

    def test_missing_inputs_give_missing_probability_not_zero(self):
        inp = synthetic_inputs(60)
        model = dict(model_id="test", variants=dict(full=dict(features=list(M.FEATURES), models={}),
                                                    no_rain=dict(features=list(M.NO_RAIN), models={})))
        rec = M.forecast_record(model, inp, [dict(id="9999", name="X", department="Y")],
                                datetime(1995, 10, 20, 12, tzinfo=timezone.utc))
        self.assertIsNone(rec["provinces"]["9999"]["days"][0]["p_max"]["10"])
        self.assertEqual(rec["variants_used"], {"SIN_INSUMOS": 3})


class Topography(unittest.TestCase):
    def test_topography_rows_on_real_provinces(self):
        E = load_module("v09_ecmwf_ens_north_topo", "scripts/v09_ecmwf_ens_north.py")
        provinces = E.load_provinces(E.boundaries_paths()[0])
        la = np.arange(-9.6, -2.95, 0.05)
        lo = np.arange(-81.7, -76.55, 0.05)
        glo, gla = np.meshgrid(lo, la)
        alt = np.where(glo < -81.0, -100.0, (glo + 81.0) * 1500.0)  # mar al oeste, sube hacia el este
        pts = np.column_stack([gla.ravel(), glo.ravel(), alt.ravel()])
        rows = {r["idprov"]: r for r in M.topography_rows(provinces, pts)}
        self.assertLess(float(rows["2005"]["elev_mean"]), float(rows["2003"]["elev_mean"]))  # Paita < Huancabamba
        self.assertEqual(float(rows["2005"]["frac_sierra"]), 0.0)
        self.assertGreater(float(rows["2003"]["coast_km"]), float(rows["2005"]["coast_km"]))


class VariantsAndSources(unittest.TestCase):
    def test_missing_atmosphere_keeps_core_and_selects_no_atmos_variant(self):
        inp = synthetic_inputs(400)
        issue = date(1996, 3, 1)
        for k in range(5):
            inp.atmos.pop((issue - timedelta(days=1 + k)).isoformat(), None)
        row = M.feature_row(inp, issue, 1, "2001", atmos_max_age=3)
        self.assertIsNotNone(row)
        self.assertFalse(any(f in row for f in M.ATMOS_FEATURES))
        self.assertTrue(set(M.VARIANTS["no_atmos"]) <= set(row))
        dummy = dict(beta=[0.0] * (len(M.VARIANTS["no_atmos"]) + 1), mean=[0.0] * len(M.VARIANTS["no_atmos"]),
                     sd=[1.0] * len(M.VARIANTS["no_atmos"]))
        model = dict(model_id="t", enso_source="nino", variants={
            v: dict(features=list(f), models={f"{k}|{u:g}|{d}": dict(dummy, beta=[0.0] * (len(f) + 1),
                                                                      mean=[0.0] * len(f), sd=[1.0] * len(f))
                                              for k in M.KINDS for u in M.THRESHOLDS_MM for d in M.LEADS})
            for v, f in M.VARIANTS.items()})
        rec = M.forecast_record(model, inp, [dict(id="2001", name="P", department="PIURA")],
                                datetime(1996, 3, 1, 0, tzinfo=timezone.utc))
        self.assertEqual(rec["variants_used"], {"no_atmos": 3})
        self.assertEqual(rec["provinces"]["2001"]["days"][0]["p_max"]["10"], 0.5)  # beta 0 → 0,5

    def test_enso_source_requires_current_ec(self):
        idx = {"2020-02": dict(E="0.1", C="0.2"), "2026-09": dict(E="", C="")}
        self.assertEqual(M.enso_source(idx, date(2026, 10, 14)), "nino")
        idx["2026-08"] = dict(E="0.5", C="0.1")
        self.assertEqual(M.enso_source(idx, date(2026, 10, 14)), "ec")
        inp = synthetic_inputs(400)
        row_n = M.feature_row(inp, date(1996, 3, 1), 1, "2001", enso="nino")
        self.assertEqual(row_n["enso_e"], 1.0)  # nino12 sintético
        self.assertIsNone(M.feature_row(inp, date(1996, 3, 1), 1, "2001", enso="ec"))  # sin E/C: falla cerrada


class LandSupport(unittest.TestCase):
    def test_sea_fill_never_enters_land_means(self):
        I = load_module("v09_imerg_for_land", "scripts/v09_imerg_late_province_daily.py")
        lat = np.round(np.arange(-3.05, -3.6, -0.1), 2)
        lon = np.round(np.arange(-81.05, -80.4, 0.1), 2)
        field = np.full((lat.size, lon.size), 4.0)
        land = np.ones_like(field, dtype=bool)
        land[:, :2] = False                    # dos columnas de mar
        field[:, :2] = -9.9e33                  # relleno de PISCO sobre el mar
        field[field < 0] = np.nan
        out = I.regrid_area_mean(field, lat, lon, np.array([-3.25]), np.array([-80.75]), land=land)
        np.testing.assert_allclose(out, 4.0)
        sea = I.regrid_area_mean(field, lat, lon, np.array([-3.25]), np.array([-81.0]), land=land)
        self.assertTrue(np.isnan(sea).all() or np.allclose(sea, 4.0))
        holes = field.copy()
        holes[0:3, 3:6] = np.nan               # falta parte de la tierra: la celda queda faltante
        self.assertTrue(np.isnan(I.regrid_area_mean(holes, lat, lon, np.array([-3.25]), np.array([-80.75]),
                                                    land=land)).all())


class NinoSelection(unittest.TestCase):
    def test_oof_never_uses_the_held_out_season(self):
        rng = np.random.default_rng(1)
        Z = rng.normal(size=(60, 2))
        groups = np.repeat([1982, 1997, 2015], 20)
        y = np.zeros(60)
        y[groups == 1982] = 1.0  # solo una temporada tiene eventos
        oof = M._oof(Z, y, groups)
        self.assertTrue(np.all(oof[groups == 1982] == 0.0))  # entrenando sin 1982 no hay eventos: 0, no fuga

    def test_forecast_uses_nino_model_only_where_selected(self):
        inp = synthetic_inputs(400)
        k = len(M.NO_RAIN)
        low = dict(beta=[-9.0] + [0.0] * k, mean=[0.0] * k, sd=[1.0] * k)
        high = dict(beta=[9.0] + [0.0] * k, mean=[0.0] * k, sd=[1.0] * k)
        keys = [f"{kd}|{u:g}|{lead}" for kd in M.KINDS for u in M.THRESHOLDS_MM for lead in M.LEADS]
        selected = {key: ("nino" if key.startswith("max|10|") else "todas") for key in keys}
        model = dict(model_id="test", variants=dict(no_rain=dict(
            features=list(M.NO_RAIN), models={key: low for key in keys}, models_nino={key: high for key in keys},
            selected=selected)))
        for pid in ("2001", "2003"):
            inp.rain.pop(("1996-02-29", pid), None)
        rec = M.forecast_record(model, inp, [dict(id="2001", name="PIURA", department="PIURA")],
                                datetime(1996, 3, 1, 0, tzinfo=timezone.utc))
        day1 = rec["provinces"]["2001"]["days"][0]
        self.assertEqual(day1["p_max"]["10"], 1.0)   # clave elegida «solo Niño»
        self.assertEqual(day1["p_max"]["25"], 0.0)   # el resto sigue con el modelo entrenado con todas
        self.assertEqual(day1["p_mean"]["10"], 0.0)


class InputRobustness(unittest.TestCase):
    def test_float32_pisco_grid_is_square_but_a_real_mismatch_is_not(self):
        lat = (np.arange(-18.35, 0.05, 0.1)).astype(np.float32)  # coordenadas PISCO en float32
        lon = (np.arange(-81.35, -68.65, 0.1)).astype(np.float32)
        self.assertAlmostEqual(M._step(lat, lon), 0.1, places=5)
        with self.assertRaises(ValueError):
            M._step(lat, np.arange(-81.0, -68.0, 0.25))

    def test_partial_source_is_never_reported_ok(self):
        calls = []

        def fake_ocean(status, years=None):
            calls.append("ocean")
            status.setdefault("ocean_errors", []).append("1999: RuntimeError: NetCDF: DAP failure")

        orig = (M.build_indices, M.build_ocean, M.PROBE_JSON, M.ens.load_provinces, M.ens.boundaries_paths)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            try:
                M.build_indices = lambda status: None
                M.build_ocean = fake_ocean
                M.PROBE_JSON = Path(tmp) / "estado.json"
                M.ens.load_provinces = lambda path: []
                M.ens.boundaries_paths = lambda: (Path(tmp), {})
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):  # aviso sintético fuera de las anotaciones de CI
                    M.build_inputs(live_only=True)
                import json as _json
                status = _json.loads(M.PROBE_JSON.read_text(encoding="utf-8"))["status"]
            finally:
                (M.build_indices, M.build_ocean, M.PROBE_JSON, M.ens.load_provinces, M.ens.boundaries_paths) = orig
        self.assertEqual(calls, ["ocean"])
        self.assertEqual(status["indices_state"], "OK")
        self.assertEqual(status["ocean_state"], "PARTIAL (1 errores)")


if __name__ == "__main__":
    unittest.main()
