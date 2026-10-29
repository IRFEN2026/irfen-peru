"""Evaluación de estimaciones IMERG frente a pluviómetros en pares válidos (detección, cuantificación y extremos).

Todo el cálculo es determinista y sin dependencias externas. Las muestras pequeñas se informan como
``DESCRIPTIVE_ONLY_SMALL_SAMPLE`` y sin intervalos de confianza: un IC solo se estima por bootstrap de **días**
completos (los pares del mismo día no son independientes) cuando hay ≥ ``MIN_PAIRS_CI`` pares y ≥ ``MIN_DAYS_CI`` días.
"""
from __future__ import annotations

import math
import random

MIN_PAIRS_EVAL = 30
MIN_DAYS_EVAL = 10
MIN_PAIRS_CI = 30
MIN_DAYS_CI = 10
MIN_EVENTS_CATEGORICAL = 10
INTENSITY_BINS = ((0.0, 0.0, "seco (0 mm)"), (0.0, 1.0, "traza (0–1 mm)"), (1.0, 10.0, "ligera (1–10 mm)"),
                  (10.0, 25.0, "moderada (10–25 mm)"), (25.0, 50.0, "fuerte (25–50 mm)"),
                  (50.0, math.inf, "muy fuerte (≥50 mm)"))


def thresholds_for(duration_h: float) -> tuple[float, ...]:
    if duration_h <= 1:
        return (0.5, 2.0, 5.0, 10.0)
    if duration_h <= 6:
        return (1.0, 5.0, 10.0, 25.0)
    return (1.0, 10.0, 25.0, 50.0)


def duration_class(h: float) -> str:
    return "≤1 h" if h <= 1 else "1–6 h" if h <= 6 else "6–24 h" if h <= 24 else ">24 h"


def intensity_class(mm: float) -> str:
    if mm == 0:
        return INTENSITY_BINS[0][2]
    for lo, hi, name in INTENSITY_BINS[1:]:
        if mm < hi:
            return name
    return INTENSITY_BINS[-1][2]


def _r(x, k=4):
    return None if x is None else round(x, k)


def continuous(obs: list[float], est: list[float]) -> dict:
    n = len(obs)
    if n == 0:
        return {"n": 0}
    err = [e - o for o, e in zip(obs, est)]
    so, se = sum(obs), sum(est)
    out = {"n": n, "mean_gauge_mm": _r(so / n), "mean_imerg_mm": _r(se / n), "bias_mm": _r(sum(err) / n),
           "MAE_mm": _r(sum(abs(x) for x in err) / n), "RMSE_mm": _r(math.sqrt(sum(x * x for x in err) / n)),
           "ratio_of_sums": _r(se / so) if so > 0 else None}
    if n >= 10:
        mo, me = so / n, se / n
        vo = sum((o - mo) ** 2 for o in obs)
        ve = sum((e - me) ** 2 for e in est)
        out["pearson_r"] = _r(sum((o - mo) * (e - me) for o, e in zip(obs, est)) / math.sqrt(vo * ve)) \
            if vo > 0 and ve > 0 else None
    else:
        out["pearson_r"] = None
        out["pearson_r_note"] = "no calculado con n < 10"
    return out


def categorical(obs: list[float], est: list[float], thr: float) -> dict:
    h = sum(o >= thr and e >= thr for o, e in zip(obs, est))
    m = sum(o >= thr and e < thr for o, e in zip(obs, est))
    f = sum(o < thr and e >= thr for o, e in zip(obs, est))
    c = len(obs) - h - m - f
    out = {"threshold_mm": thr, "hits": h, "misses": m, "false_alarms": f, "correct_negatives": c,
           "events_observed": h + m,
           "POD": _r(h / (h + m)) if h + m else None, "FAR": _r(f / (h + f)) if h + f else None,
           "CSI": _r(h / (h + m + f)) if h + m + f else None, "FBI": _r((h + f) / (h + m)) if h + m else None}
    if h + m < MIN_EVENTS_CATEGORICAL:
        out["note"] = f"menos de {MIN_EVENTS_CATEGORICAL} eventos observados: solo descriptivo"
    return out


def block(pairs: list[dict], est_key: str = "imerg_cell_mm") -> dict:
    if not pairs:
        return {"n_pairs": 0, "sample_status": "NO_PAIRS"}
    obs = [p["gauge_mm"] for p in pairs]
    est = [p[est_key] for p in pairs]
    days = {p["window_start_utc"][:10] for p in pairs}
    dur = max(p["duration_h"] for p in pairs)
    thr = thresholds_for(dur)
    det = thr[0]
    wet = [(o, e) for o, e in zip(obs, est) if o >= det and e >= det]
    ext_thr = max(thr[2], _quantile(obs, 0.9)) if obs else thr[2]
    status = "EVALUABLE" if len(pairs) >= MIN_PAIRS_EVAL and len(days) >= MIN_DAYS_EVAL \
        else "DESCRIPTIVE_ONLY_SMALL_SAMPLE"
    return {
        "n_pairs": len(pairs), "n_stations": len({p["station_id"] for p in pairs}), "n_days": len(days),
        "sample_status": status,
        "continuous": continuous(obs, est),
        "detection": categorical(obs, est, det),
        "quantification_wet_wet": continuous([w[0] for w in wet], [w[1] for w in wet]),
        "extremes": categorical(obs, est, round(ext_thr, 3)),
        "categorical": [categorical(obs, est, t) for t in thr],
    }


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return math.nan
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def bootstrap_ci(pairs: list[dict], stat, b: int = 2000, seed: int = 400, alpha: float = 0.1) -> dict:
    """IC (1−α) por bootstrap de días completos; ``stat(pairs) → float``. Bloqueado si la muestra no lo permite."""
    days = sorted({p["window_start_utc"][:10] for p in pairs})
    if len(pairs) < MIN_PAIRS_CI or len(days) < MIN_DAYS_CI:
        return {"status": "CI_NOT_DEFENSIBLE", "reason": f"n={len(pairs)} pares, {len(days)} días "
                f"(mínimo {MIN_PAIRS_CI} y {MIN_DAYS_CI})"}
    by_day = {d: [p for p in pairs if p["window_start_utc"][:10] == d] for d in days}
    rng = random.Random(seed)
    vals = []
    for _ in range(b):
        sample = [p for d in (rng.choice(days) for _ in days) for p in by_day[d]]
        v = stat(sample)
        if v is not None and math.isfinite(v):
            vals.append(v)
    vals.sort()
    if len(vals) < b * 0.9:
        return {"status": "CI_UNSTABLE", "valid_resamples": len(vals)}
    return {"status": "OK", "level": 1 - alpha, "low": _r(_quantile(vals, alpha / 2)),
            "high": _r(_quantile(vals, 1 - alpha / 2)), "resamples": len(vals), "block": "day"}


def evaluate(pairs_doc: dict, est_key: str = "imerg_cell_mm") -> dict:
    pairs = pairs_doc.get("pairs", [])
    strata = {}
    for name, key in (("station", lambda p: p["station_id"]), ("region", lambda p: p.get("region") or "?"),
                      ("intensity_gauge", lambda p: intensity_class(p["gauge_mm"])),
                      ("duration", lambda p: duration_class(p["duration_h"]))):
        groups: dict[str, list] = {}
        for p in pairs:
            groups.setdefault(key(p), []).append(p)
        strata[name] = {k: block(v, est_key) for k, v in sorted(groups.items())}
    overall = block(pairs, est_key)
    mae = lambda ps: sum(abs(p[est_key] - p["gauge_mm"]) for p in ps) / len(ps) if ps else None  # noqa: E731
    bias = lambda ps: sum(p[est_key] - p["gauge_mm"] for p in ps) / len(ps) if ps else None  # noqa: E731
    return {"schema": "irfen.gauge_imerg.evaluation", "schema_version": "1.0.0", "estimate": est_key,
            "use_class": (pairs_doc.get("policy") or {}).get("use"),
            "overall": overall, "strata": strata,
            "confidence_intervals": {"MAE_mm": bootstrap_ci(pairs, mae), "bias_mm": bootstrap_ci(pairs, bias)},
            "interpretation_rule": "Con sample_status distinto de EVALUABLE las cifras son descriptivas: no "
                                   "demuestran precisión, sesgo sistemático ni mejora."}
