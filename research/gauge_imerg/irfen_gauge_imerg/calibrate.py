"""Calibración experimental de IMERG con pluviómetros: línea base y correcciones simples, con compuertas estrictas.

Métodos (solo se ajustan con el periodo de entrenamiento):
* ``raw``             — IMERG sin corrección (línea base obligatoria).
* ``multiplicative``  — factor k = Σ pluviómetro / Σ IMERG en pares de entrenamiento con IMERG ≥ umbral de detección,
                        limitado a [0,25; 4].
* ``quantile_map``    — mapeo cuantil empírico IMERG → pluviómetro (exige ≥ ``MIN_TRAIN_PAIRS_QM`` pares).

Validación sin fuga:
* división **cronológica** por días con **embargo** (días descartados entre entrenamiento y prueba) y comprobación de
  que ninguna ventana de prueba se solape con una de entrenamiento;
* «dejando una estación fuera» solo si hay ≥ 3 estaciones con ≥ 5 pares lluviosos: ajuste con las demás estaciones
  del periodo de entrenamiento y prueba en la estación excluida del periodo de prueba;
* la generalización a temporadas futuras solo se declara evaluada si la prueba cae en otra temporada (sep–ago).

Si cualquier compuerta falla, el resultado es ``BLOCKED`` con sus motivos: nunca se ajusta con lo que haya.
"""
from __future__ import annotations

import bisect
from datetime import date, timedelta

from .evaluate import _quantile, block, bootstrap_ci, thresholds_for

MIN_TRAIN_WET = 20
MIN_TEST_WET = 10
MIN_TRAIN_DAYS = 15
MIN_TEST_DAYS = 7
MIN_TRAIN_PAIRS_QM = 50
MIN_LOSO_STATIONS = 3
MIN_LOSO_WET_PER_STATION = 5
K_CAP = (0.25, 4.0)
TOL_POD_DROP = 0.05
TOL_FAR_RISE = 0.05


def _day(p) -> date:
    return date.fromisoformat(p["window_start_utc"][:10])


def season(d: date) -> int:
    """Temporada lluviosa sep–ago, identificada por el año en que termina."""
    return d.year + 1 if d.month >= 9 else d.year


def chrono_split(pairs: list[dict], frac: float = 0.7, embargo_days: int = 1):
    days = sorted({_day(p) for p in pairs})
    if len(days) < 2:
        return [], [], {"reason": "MENOS_DE_DOS_DIAS"}
    cut = days[max(1, int(len(days) * frac)) - 1]
    train = [p for p in pairs if _day(p) <= cut]
    test = [p for p in pairs if _day(p) > cut + timedelta(days=embargo_days)]
    t_end = max((p["window_end_utc"] for p in train), default=None)
    s_start = min((p["window_start_utc"] for p in test), default=None)
    leak = bool(t_end and s_start and s_start < t_end)
    info = {"train_last_day": cut.isoformat(), "embargo_days": embargo_days,
            "test_first_day": min((_day(p) for p in test), default=None),
            "train_window_end_max": t_end, "test_window_start_min": s_start, "temporal_overlap": leak}
    if info["test_first_day"]:
        info["test_first_day"] = info["test_first_day"].isoformat()
    if leak:
        raise AssertionError("fuga temporal: una ventana de prueba empieza antes de que termine una de entrenamiento")
    return train, test, info


def fit_multiplicative(train: list[dict], det: float) -> dict:
    sel = [p for p in train if p["imerg_cell_mm"] >= det]
    si = sum(p["imerg_cell_mm"] for p in sel)
    if not sel or si <= 0:
        return {"status": "BLOCKED", "reason": "SIN_PARES_CON_IMERG_HUMEDO_EN_ENTRENAMIENTO"}
    k = sum(p["gauge_mm"] for p in sel) / si
    return {"status": "FITTED", "k_raw": round(k, 4), "k": round(min(max(k, K_CAP[0]), K_CAP[1]), 4),
            "capped": not (K_CAP[0] <= k <= K_CAP[1]), "n_fit": len(sel)}


def fit_quantile_map(train: list[dict]) -> dict:
    if len(train) < MIN_TRAIN_PAIRS_QM:
        return {"status": "BLOCKED", "reason": f"MENOS_DE_{MIN_TRAIN_PAIRS_QM}_PARES_DE_ENTRENAMIENTO"}
    return {"status": "FITTED", "imerg_sorted": sorted(p["imerg_cell_mm"] for p in train),
            "gauge_sorted": sorted(p["gauge_mm"] for p in train), "n_fit": len(train)}


def apply_quantile_map(model: dict, x: float) -> float:
    xs, ys = model["imerg_sorted"], model["gauge_sorted"]
    if x > xs[-1]:
        return ys[-1] + (x - xs[-1])  # extrapolación aditiva, documentada
    lo, hi = bisect.bisect_left(xs, x), bisect.bisect_right(xs, x)
    q = ((lo + hi) / 2) / len(xs) if hi > lo else lo / len(xs)  # rango medio para empates (p. ej. muchos ceros)
    return max(0.0, _quantile(ys, min(max(q, 0.0), 1.0)))


def _with_estimate(pairs, fn, key):
    return [{**p, key: round(fn(p["imerg_cell_mm"]), 4)} for p in pairs]


def compare(test: list[dict], key: str, det: float) -> dict:
    raw, cand = block(test, "imerg_cell_mm"), block(test, key)

    def dmae(ps):
        return (sum(abs(p[key] - p["gauge_mm"]) for p in ps) - sum(abs(p["imerg_cell_mm"] - p["gauge_mm"])
                                                                  for p in ps)) / len(ps) if ps else None
    ci = bootstrap_ci(test, dmae)
    rc, cc = raw["continuous"], cand["continuous"]
    d = {"delta_MAE_mm": round(cc["MAE_mm"] - rc["MAE_mm"], 4),
         "delta_abs_bias_mm": round(abs(cc["bias_mm"]) - abs(rc["bias_mm"]), 4),
         "delta_POD": _diff(cand["detection"]["POD"], raw["detection"]["POD"]),
         "delta_FAR": _diff(cand["detection"]["FAR"], raw["detection"]["FAR"]), "delta_MAE_CI": ci}
    if ci.get("status") != "OK":
        verdict = "NO_DEMONSTRATED_IMPROVEMENT_CI_NOT_DEFENSIBLE"
    elif ci["low"] > 0:
        verdict = "DEGRADES"
    elif ci["high"] < 0 and d["delta_abs_bias_mm"] <= 0 and (d["delta_POD"] or 0) >= -TOL_POD_DROP \
            and (d["delta_FAR"] or 0) <= TOL_FAR_RISE:
        verdict = "IMPROVES_ON_THIS_TEST_PERIOD"
    else:
        verdict = "NO_DEMONSTRATED_IMPROVEMENT"
    return {"raw": raw, "candidate": cand, "deltas": d, "verdict": verdict}


def _diff(a, b):
    return None if a is None or b is None else round(a - b, 4)


def _gates(train, test, det) -> list[str]:
    r = []
    tw = sum(p["gauge_mm"] >= det for p in train)
    sw = sum(p["gauge_mm"] >= det for p in test)
    td, sd = len({_day(p) for p in train}), len({_day(p) for p in test})
    if tw < MIN_TRAIN_WET:
        r.append(f"TRAIN_WET_PAIRS {tw} < {MIN_TRAIN_WET}")
    if sw < MIN_TEST_WET:
        r.append(f"TEST_WET_PAIRS {sw} < {MIN_TEST_WET}")
    if td < MIN_TRAIN_DAYS:
        r.append(f"TRAIN_DAYS {td} < {MIN_TRAIN_DAYS}")
    if sd < MIN_TEST_DAYS:
        r.append(f"TEST_DAYS {sd} < {MIN_TEST_DAYS}")
    return r


def calibrate_group(pairs: list[dict], embargo_days: int = 1) -> dict:
    det = thresholds_for(max(p["duration_h"] for p in pairs))[0]
    try:
        train, test, split = chrono_split(pairs, embargo_days=embargo_days)
    except AssertionError as exc:
        return {"status": "BLOCKED", "reasons": [f"TEMPORAL_LEAKAGE: {exc}"]}
    out = {"n_pairs": len(pairs), "detection_threshold_mm": det, "split": split,
           "n_train": len(train), "n_test": len(test)}
    gates = _gates(train, test, det) if train and test else ["SPLIT_EMPTY"]
    if gates:
        return {**out, "status": "BLOCKED", "reasons": gates}
    res = {}
    mm = fit_multiplicative(train, det)
    if mm["status"] == "FITTED":
        res["multiplicative"] = {"model": mm, **compare(_with_estimate(test, lambda x: mm["k"] * x, "est"), "est", det)}
    else:
        res["multiplicative"] = mm
    qm = fit_quantile_map(train)
    if qm["status"] == "FITTED":
        res["quantile_map"] = {"model": {"status": "FITTED", "n_fit": qm["n_fit"]},
                               **compare(_with_estimate(test, lambda x: apply_quantile_map(qm, x), "est"), "est", det)}
    else:
        res["quantile_map"] = qm
    out["methods"] = res
    out["local_calibration"] = "EVALUATED_ON_LATER_PERIOD_SAME_STATIONS"
    train_seasons = {season(_day(p)) for p in train}
    test_seasons = {season(_day(p)) for p in test}
    out["future_generalization"] = ("EVALUATED_ON_DIFFERENT_SEASON" if test_seasons - train_seasons
                                    else "NOT_EVALUATED_SAME_SEASON")
    out["territorial_extrapolation"] = loso(train, test, det)
    out["status"] = "EXPLORATORY_RESULTS_NOT_OPERATIONAL"
    return out


def loso(train: list[dict], test: list[dict], det: float) -> dict:
    wet = {}
    for p in train + test:
        if p["gauge_mm"] >= det:
            wet[p["station_id"]] = wet.get(p["station_id"], 0) + 1
    ok = [s for s, n in wet.items() if n >= MIN_LOSO_WET_PER_STATION]
    if len(ok) < MIN_LOSO_STATIONS:
        return {"status": "BLOCKED", "reason": f"{len(ok)} estaciones con ≥{MIN_LOSO_WET_PER_STATION} pares "
                                               f"lluviosos (mínimo {MIN_LOSO_STATIONS})"}
    per = {}
    for s in ok:
        tr = [p for p in train if p["station_id"] != s]
        te = [p for p in test if p["station_id"] == s]
        mm = fit_multiplicative(tr, det)
        if mm["status"] != "FITTED" or not te:
            per[s] = {"status": "BLOCKED", "reason": mm.get("reason", "SIN_PARES_DE_PRUEBA")}
            continue
        te2 = _with_estimate(te, lambda x: mm["k"] * x, "est")
        per[s] = {"k": mm["k"], "raw": block(te2)["continuous"], "candidate": block(te2, "est")["continuous"]}
    return {"status": "EVALUATED", "method": "multiplicative", "per_station": per}


def calibrate(pairs_doc: dict, embargo_days: int = 1) -> dict:
    base = {"schema": "irfen.gauge_imerg.calibration", "schema_version": "1.0.0",
            "deployment_status": "RESEARCH_ONLY", "test_mode": "TEST_ONLY", "operational_use": False}
    if (pairs_doc.get("policy") or {}).get("use") != "calibration":
        return {**base, "status": "BLOCKED", "reasons": ["PAIRS_NOT_BUILT_WITH_CALIBRATION_ELIGIBILITY"]}
    pairs = pairs_doc.get("pairs", [])
    if not pairs:
        return {**base, "status": "BLOCKED", "reasons": ["NO_VALID_PAIRS"]}
    groups: dict[str, list] = {}
    for p in pairs:  # nunca se mezclan duraciones distintas (p. ej. 12 h y 24 h) en un mismo ajuste
        groups.setdefault(f"{p['duration_h']:g} h", []).append(p)
    res = {k: calibrate_group(v, embargo_days) for k, v in sorted(groups.items())}
    status = "BLOCKED" if all(r["status"] == "BLOCKED" for r in res.values()) else "EXPLORATORY_RESULTS_NOT_OPERATIONAL"
    return {**base, "status": status, "by_duration": res,
            "decision_rule": "Mejora solo si el IC 90 % por días de ΔMAE está por debajo de 0, |sesgo| no aumenta, "
                             f"POD no cae más de {TOL_POD_DROP} y FAR no sube más de {TOL_FAR_RISE}."}
