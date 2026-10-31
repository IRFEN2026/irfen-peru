#!/usr/bin/env python3
"""IRFEN v0.9 · robustez de la relación lluvia–caudal en el río Piura. RESEARCH_ONLY / TEST_ONLY. Sin red.
Sin umbrales; nada se ajusta al episodio de 2017. Complementa el protocolo qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md
(v0.2: añade autocorrelación, selección de desfase, convención de día y la distinción correlación / explicación
retrospectiva / anticipación).

Reglas:
* La comparación lluvia–caudal solo se recalcula con una cuenca VALIDADA_EXPERIMENTAL hasta la estación
  (scripts/v09_piura_catchments.py). Con la UH ANA 1378 no se recalcula: queda la de #458, marcada.
* Régimen de cada mes en Sánchez Cerro: aportación natural aproximada Qn = Q_SC + Q_canal_Ejidos − Q_Curumuy (balance
  diario sin tiempos de viaje ni otras extracciones) y peso de la regulación R = (Q_Curumuy + Q_Ejidos)/(Q_SC + Q_Ejidos).
  Mes DOMINADO_POR_REGULACION si la mediana de R > 0,5 o la mediana de Q_SC < 5 m³/s; APORTACION_NATURAL_DOMINANTE si
  la mediana de R < 0,1; MIXTO en otro caso. Solo los meses no dominados por la regulación son controles comparables.
* Autocorrelación: (a) diferencias diarias; (b) preblanqueo AR(1) estimado sobre la lluvia y aplicado a ambas series.
* Selección del desfase: el estadístico es el máximo de ρ en L = 0…10; su distribución nula se obtiene desplazando
  circularmente la lluvia dentro de la temporada (todos los desplazamientos ≥ 7 días; determinista), lo que conserva la
  autocorrelación. p = fracción de desplazamientos con máximo ≥ observado.
* Convención de día: lluvia desplazada −1, 0, +1 días y mezcla 0,5·(P(d)+P(d+1)) como aproximación al día 12–12 UTC
  (≈ 07–07 h de Perú). Es una aproximación declarada; la exacta exige IMERG por media hora.
* Tres preguntas distintas:
  - correlación: ρ(A_k(d), Q(d+L));
  - explicación retrospectiva: ρ parcial(Q(d), A_k(d) | Q(d−1)) — ¿la lluvia explica el cambio del caudal más allá de la
    persistencia?;
  - anticipación: ρ parcial(Q(d+L), A_k(d) | Q(d)), L = 1…3 — ¿la lluvia conocida en d añade información sobre el caudal
    futuro más allá del caudal ya observado? Solo esto se acerca a «capacidad de anticipación», y aun así es retrospectivo.

    python scripts/v09_piura_robustness.py [--check]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data/v09/research/historical"
CATCH = HIST / "piura_catchments_v0_1.json"
OUT = HIST / "piura_robustness_v0_1.json"
_spec = importlib.util.spec_from_file_location("v", ROOT / "scripts/v09_piura_2017_validation.py")
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)
LAGS = list(range(0, 11))
K = (1, 3, 7, 15)
MIN_SHIFT = 7
GUARDS = dict(V.GUARDS)


def d2s(d: date) -> str:
    return d.isoformat()


def rank(x):
    return np.asarray(V._rank(list(x)), float)


def spear(x, y):
    if len(x) < 8:
        return None
    rx, ry = rank(x), rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def partial_spear(x, y, z):
    """Spearman partial correlation of x and y given z (ranks, linear residualisation)."""
    if len(x) < 10:
        return None
    rx, ry, rz = rank(x), rank(y), rank(z)
    A = np.vstack([rz, np.ones_like(rz)]).T
    ex = rx - A @ np.linalg.lstsq(A, rx, rcond=None)[0]
    ey = ry - A @ np.linalg.lstsq(A, ry, rcond=None)[0]
    if ex.std() == 0 or ey.std() == 0:
        return None
    return float(np.corrcoef(ex, ey)[0, 1])


def r3(v):
    return None if v is None else round(v, 3)


def season_arrays(p: dict, q: dict, start: str, end: str):
    days = [date.fromisoformat(start) + timedelta(days=i) for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
    P = np.array([np.nan if p.get(d2s(d)) is None else p[d2s(d)] for d in days], float)
    Q = np.array([np.nan if q.get(d2s(d)) is None else q[d2s(d)] for d in days], float)
    return days, P, Q


def lag_curve(P, Q, lags=LAGS):
    out = []
    for L in lags:
        x, y = P[:len(P) - L] if L else P, Q[L:]
        m = ~np.isnan(x) & ~np.isnan(y)
        out.append(dict(lag_days=L, n=int(m.sum()), spearman=r3(spear(x[m], y[m]))))
    return out


def max_rho(curve):
    vals = [c["spearman"] for c in curve if c["spearman"] is not None]
    return max(vals) if vals else None


def ar1_prewhiten(P, Q):
    m = ~np.isnan(P[1:]) & ~np.isnan(P[:-1])
    if m.sum() < 10:
        return None, None, None
    x0, x1 = P[:-1][m], P[1:][m]
    phi = float(np.dot(x0 - x0.mean(), x1 - x1.mean()) / np.dot(x0 - x0.mean(), x0 - x0.mean()))
    return P[1:] - phi * P[:-1], Q[1:] - phi * Q[:-1], phi


def shift_null(P, Q, observed):
    """All circular shifts of P (≥ MIN_SHIFT days, ≤ n − MIN_SHIFT): distribution of max_L ρ."""
    n = len(P)
    vals = []
    for s in range(MIN_SHIFT, n - MIN_SHIFT + 1):
        m = max_rho(lag_curve(np.roll(P, s), Q))
        if m is not None:
            vals.append(m)
    if observed is None or not vals:
        return dict(shifts=len(vals), p_value=None)
    return dict(shifts=len(vals), p_value=round(sum(v >= observed for v in vals) / len(vals), 3),
                null_p95=round(float(np.percentile(vals, 95)), 3))


def acc_series(P, k):
    out = np.full_like(P, np.nan)
    for i in range(k - 1, len(P)):
        w = P[i - k + 1:i + 1]
        if not np.isnan(w).any():
            out[i] = w.sum()
    return out


def three_questions(P, Q):
    res = {}
    for k in K:
        A = acc_series(P, k)
        corr = lag_curve(A, Q)
        m = ~np.isnan(A[1:]) & ~np.isnan(Q[1:]) & ~np.isnan(Q[:-1])
        retro = partial_spear(Q[1:][m], A[1:][m], Q[:-1][m])
        ant = []
        for L in (1, 2, 3):
            mm = ~np.isnan(A[:-L]) & ~np.isnan(Q[L:]) & ~np.isnan(Q[:-L])
            ant.append(dict(lead_days=L, n=int(mm.sum()), partial_spearman=r3(partial_spear(Q[L:][mm], A[:-L][mm], Q[:-L][mm]))))
        res[f"A{k}"] = dict(correlation=dict(best=max(corr, key=lambda c: c["spearman"] or -9), curve=corr),
                            retrospective_explanation=dict(partial_spearman_Q_d_with_A_d_given_Q_dminus1=r3(retro), n=int(m.sum())),
                            anticipation=ant)
    return res


def regime(pechp: dict) -> dict:
    flow = V.flow_series(pechp)
    sc, cur, eji = flow.get("PUENTE_SANCHEZ_CERRO", {}), flow.get("CURUMUY", {}), flow.get("CANAL_EJIDOS", {})
    months = sorted({d[:7] for d in sc})
    out, qnat = {}, {}
    for m in months:
        R, Qs = [], []
        for d in sorted(x for x in sc if x.startswith(m)):
            q, c, e = sc.get(d), cur.get(d), eji.get(d)
            if q is None:
                continue
            Qs.append(q)
            if c is not None and e is not None:
                qnat[d] = round(q + e - c, 2)
                R.append((c + e) / max(q + e, 1e-6))
        med_r = float(np.median(R)) if R else None
        med_q = float(np.median(Qs)) if Qs else None
        cls = ("SIN_DATOS" if med_q is None else "DOMINADO_POR_REGULACION" if (med_r is not None and med_r > 0.5) or med_q < 5
               else "APORTACION_NATURAL_DOMINANTE" if med_r is not None and med_r < 0.1 else "MIXTO")
        out[m] = dict(days=len(Qs), median_q_sanchez_cerro=r3(med_q), median_regulation_share=r3(med_r), regime=cls)
    return dict(months=out, natural_component_approx=qnat,
                formula="Qn ≈ Q_SC + Q_canal_Ejidos − Q_Curumuy (sin tiempos de viaje ni otras extracciones)")


def build() -> dict:
    pechp = json.loads(V.PECHP.read_text(encoding="utf-8"))
    imerg = json.loads(V.IMERG.read_text(encoding="utf-8"))
    catch = json.loads(CATCH.read_text(encoding="utf-8")) if CATCH.is_file() else {"catchments": []}
    reg = regime(pechp)
    flow = V.flow_series(pechp)
    analyses = {}
    for c in catch["catchments"]:
        if c.get("status") != "VALIDADA_EXPERIMENTAL":
            analyses[c["station"]] = dict(status="NO_RECALCULADO", reason=f"cuenca {c.get('status')}: {c.get('reasons') or c.get('note')}")
            continue
        fr = {(round(x["lon_center"], 2), round(x["lat_center"], 2)): x["fraction_inside"] for x in c["imerg_cells"]}
        rain = V.basin_series(imerg, fr)
        p = {d: r["p_mm"] for d, r in rain.items()}
        station_flow = {"PUENTE_SANCHEZ_CERRO": flow.get("PUENTE_SANCHEZ_CERRO", {}),
                        "APORTACION_NATURAL_APROX": reg["natural_component_approx"]}.get(c["station"]) or flow.get(c["station"], {})
        targets = {"Q_observado": station_flow}
        if c["station"] == "PUENTE_SANCHEZ_CERRO":
            targets["Q_natural_aprox"] = reg["natural_component_approx"]
        seasons = {}
        for y in sorted({d[:4] for d in station_flow}):
            months = sorted({d[:7] for d in station_flow if d.startswith(y)})
            start, end = f"{months[0]}-01", max(d for d in station_flow if d.startswith(y))
            comparable = [m for m in months if reg["months"].get(m, {}).get("regime") not in ("DOMINADO_POR_REGULACION", "SIN_DATOS")]
            res = dict(window=f"{start}..{end}", months=months, regimes={m: reg["months"].get(m, {}).get("regime") for m in months},
                       hydrologically_comparable_months=comparable, targets={})
            for tname, q in targets.items():
                days, P, Q = season_arrays(p, q, start, end)
                if np.isnan(Q).all() or np.nanstd(Q) == 0:
                    res["targets"][tname] = dict(status="SERIE_NULA_O_CONSTANTE")
                    continue
                lev = lag_curve(P, Q)
                dP, dQ = np.diff(P), np.diff(Q)
                diff = lag_curve(dP, dQ)
                pwP, pwQ, phi = ar1_prewhiten(P, Q)
                pw = lag_curve(pwP, pwQ) if pwP is not None else None
                conv = {}
                for name, PP in (("dia_utc_menos_1", np.r_[P[1:], np.nan]), ("dia_utc", P), ("dia_utc_mas_1", np.r_[np.nan, P[:-1]]),
                                 ("aprox_12_12_utc", 0.5 * (P + np.r_[P[1:], np.nan]))):
                    cv = lag_curve(PP, Q)
                    b = max(cv, key=lambda c: c["spearman"] if c["spearman"] is not None else -9)
                    conv[name] = dict(best_lag=b["lag_days"], best_spearman=b["spearman"])
                res["targets"][tname] = dict(
                    n_days=int((~np.isnan(Q)).sum()), levels=lev, first_differences=diff,
                    prewhitened_ar1=dict(phi_rain=r3(phi), curve=pw),
                    lag_selection_null_levels=shift_null(P, Q, max_rho(lev)),
                    lag_selection_null_differences=shift_null(dP, dQ, max_rho(diff)),
                    day_convention_sensitivity=conv, three_questions=three_questions(P, Q))
            seasons[y] = res
        analyses[c["station"]] = dict(status="RECALCULADO", catchment_area_km2=c["area_km2_pixels"], polygon="HydroSHEDS v1 15″ (no oficial)",
                                      seasons=seasons)
    return dict(schema_version="irfen_v09_piura_robustness_v0_1", **GUARDS,
                rules=dict(lags=LAGS, accumulations_days=list(K), min_circular_shift_days=MIN_SHIFT,
                           regime_rule="DOMINADO_POR_REGULACION si mediana R > 0,5 o mediana Q_SC < 5 m³/s; "
                                       "APORTACION_NATURAL_DOMINANTE si mediana R < 0,1; MIXTO en otro caso",
                           thresholds_fitted_to_2017=False),
                regime=reg, analyses=analyses)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    d = json.loads(text)
    print({m: (v["regime"], v["median_q_sanchez_cerro"], v["median_regulation_share"]) for m, v in d["regime"]["months"].items()})
    for st, an in d["analyses"].items():
        print(st, an["status"], an.get("reason", ""))
        for y, s in an.get("seasons", {}).items():
            for t, r in s["targets"].items():
                if "levels" not in r:
                    print("  ", y, t, r)
                    continue
                print("  ", y, t, "n", r["n_days"], "lev max", max_rho(r["levels"]), r["lag_selection_null_levels"],
                      "diff max", max_rho(r["first_differences"]), r["lag_selection_null_differences"])
                print("     conv", r["day_convention_sensitivity"])
                q3 = r["three_questions"]["A3"]
                print("     A3 retro", q3["retrospective_explanation"], "antic", q3["anticipation"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
