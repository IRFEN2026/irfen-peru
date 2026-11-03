#!/usr/bin/env python3
"""IRFEN v0.9.1 — offline daily rainfall/river-response exploratory lag analysis.

Research-only; not a prediction model. Pre-register fixed rain accumulation and lag
candidates, select by positive train Spearman, report untouched later seasons.
No reanalysis products or borrowed river flows are promoted to real-time alerts.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
PECHP = ROOT / "data/v09/research/historical/pechp_daily_v0_1.json"
IMERG = ROOT / "data/v09/research/historical/imerg_final_daily_piura_chira_v0_1.json"
CATCH = ROOT / "data/v09/research/anticipation/north_catchments_v0_1.json"
OUT = ROOT / "data/v09/research/anticipation/v091_fluvial_response_lag_v0_1.json"
PERIODS = {"train": (2016, 2020), "holdout": (2021, 2023)}
LAGS = (0, 1, 2, 3, 4, 5, 6, 7)
ACC_DAYS = (1, 3, 5, 7)
MIN_PAIRS = 30
# Only physically mapped gauge-to-catchment comparisons. No synthetic gauge in Tumbes.
PAIRS = (
    dict(river="Chira", catchment_id="EL_CIRUELO", flow_column="EL_CIRUELO",
         station="El Ciruelo", note="Caudal PECHP y cuenca HydroSHEDS del mismo aforo; comprobar influencias de regulación."),
    dict(river="Piura", catchment_id="PUENTE_SANCHEZ_CERRO", flow_column="R_PIURA_1",
         station="Puente Sánchez Cerro", note="Se usan únicamente meses donde PECHP identifica R_PIURA_1 como Sánchez Cerro; trasvase Curumuy y derivaciones no cuantificados."),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank(values):
    idx = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(idx):
        j = i + 1
        while j < len(idx) and values[idx[j]] == values[idx[i]]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            result[idx[k]] = avg_rank
        i = j
    return result


def pearson(a, b):
    if len(a) < 2 or len(a) != len(b):
        return None
    ma, mb = mean(a), mean(b)
    ax, bx = [v - ma for v in a], [v - mb for v in b]
    den = math.sqrt(sum(v*v for v in ax) * sum(v*v for v in bx))
    return sum(x*y for x,y in zip(ax,bx)) / den if den > 0 else None


def spearman(a, b):
    return pearson(rank(a), rank(b)) if len(a) >= 2 else None


def flow_series(doc, col, expected_station=None):
    """Strict paired-reader and documentary station identity: absences stay absent."""
    out, excluded = {}, 0
    for month in doc.get("months", []):
        table = (month.get("tables") or {}).get("rivers") or {}
        identity = table.get("column_identity_from_report_notes") or {}
        if expected_station and identity.get(col) != expected_station:
            continue
        for dd, row in (table.get("days") or {}).items():
            try:
                d = date.fromisoformat(month["month"] + "-" + str(int(dd)).zfill(2))
            except (ValueError, TypeError):
                excluded += 1
                continue
            v = (row.get("values") or {}).get(col)
            if row.get("readers") != "DOS_LECTORES" or not isinstance(v, (int,float)) or not math.isfinite(v) or v < 0:
                excluded += 1
                continue
            if d in out and out[d] != v:
                excluded += 1
                out.pop(d, None)
                continue
            out[d] = float(v)
    return out, excluded


def accum_at(rain, day, k):
    """UTC calendar-day rainfall; never fill an unobserved day with zero."""
    days = [day - timedelta(days=n) for n in range(k)]
    vals = [rain.get(d) for d in days]
    return sum(vals) if all(isinstance(v,(int,float)) and math.isfinite(v) and v >= 0 for v in vals) else None


def paired(rain, flows, acc_days, lag, period):
    """P(d-lag-k+1..d-lag) vs Q(d); preserve exact dates and skip missing dates."""
    lo, hi = period
    r, q, dates = [], [], []
    for d, qv in sorted(flows.items()):
        if not lo <= d.year <= hi:
            continue
        mm = accum_at(rain, d - timedelta(days=lag), acc_days)
        if mm is not None:
            dates.append(d.isoformat())
            r.append(float(mm))
            q.append(float(qv))
    return r, q, dates


def monthly_anomaly_spearman(x, y, dates, minimum=MIN_PAIRS):
    """Remove within-calendar-month means, reducing wet-season confounding.
    Diagnostic only; the sample is not independent in time and this is not predictive skill.
    """
    groups = {}
    for i, d in enumerate(dates):
        groups.setdefault(d[:7], []).append(i)
    xa, ya = [], []
    for indices in groups.values():
        if len(indices) < 4:
            continue
        mx=mean(x[i] for i in indices)
        my=mean(y[i] for i in indices)
        xa += [x[i]-mx for i in indices]
        ya += [y[i]-my for i in indices]
    score = spearman(xa, ya) if len(xa)>=minimum else None
    return dict(n=len(xa), spearman=round(score,5) if score is not None else None,
                status="DESCRIPTIVE_WITHIN_MONTH" if score is not None else "INSUFFICIENT_WITHIN_MONTH")


def future_rain_falsification(rain, flows, k, holdout, minimum=MIN_PAIRS):
    """Non-causal control: precipitation *after* discharge cannot forecast past flow.
    If future rain also tracks flow, shared seasonality/persistence can drive correlations.
    """
    lo, hi=holdout
    x, y = [], []
    for d, q in sorted(flows.items()):
        if not lo <= d.year <= hi:
            continue
        vals=[rain.get(d+timedelta(days=i)) for i in range(1,k+1)]
        if all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in vals):
            x.append(sum(vals))
            y.append(q)
    cor=spearman(x,y) if len(x)>=minimum else None
    return dict(n=len(x),spearman=round(cor,5) if cor is not None else None,
                interpretation="FUTURE_RAIN_NEGATIVE_CONTROL_NOT_PREDICTIVE",
                no_tuning=True)


def persistence_control(rain, flows, k, lag, holdout, minimum=MIN_PAIRS):
    """Compare rain association with yesterday's observed flow on exactly same held-out dates.
    It is not a simulation of real-time data availability and cannot establish a forecast.
    """
    lo, hi = holdout
    rain_x, yesterday, today = [], [], []
    for d, q in sorted(flows.items()):
        if not lo <= d.year <= hi or d-timedelta(days=1) not in flows:
            continue
        mm=accum_at(rain,d-timedelta(days=lag),k)
        if mm is None:
            continue
        rain_x.append(float(mm))
        yesterday.append(float(flows[d-timedelta(days=1)]))
        today.append(float(q))
    rrain=spearman(rain_x,today) if len(today)>=minimum else None
    rflow=spearman(yesterday,today) if len(today)>=minimum else None
    return dict(n=len(today),
                rain_vs_current_flow_spearman=round(rrain,5) if rrain is not None else None,
                previous_day_flow_vs_current_flow_spearman=round(rflow,5) if rflow is not None else None,
                same_matched_days=True,
                interpretation="BENCHMARK_DESCRIPTIVE_ONLY_NO_INCREMENTAL_FORECAST_CLAIM")


def evaluate_pair(rain, flows, min_pairs=MIN_PAIRS):
    candidates = []
    for k in ACC_DAYS:
        for lag in LAGS:
            x, y, _ = paired(rain, flows, k, lag, PERIODS["train"])
            corr = spearman(x, y) if len(x) >= min_pairs else None
            candidates.append(dict(acc_days=k, lag_days=lag, n_train=len(x),
                                   train_spearman=round(corr, 5) if corr is not None else None))
    valid = [c for c in candidates if c["train_spearman"] is not None]
    # One-dimensional preselected candidate; holdout never participates in selection.
    selected = max(valid, key=lambda c:(c["train_spearman"], -c["lag_days"], -c["acc_days"])) if valid else None
    result = dict(status="EXPLORATORIO_SIN_HABILIDAD_PREDICTIVA_VALIDADA",
                  candidates=candidates, selected_on_train=selected, holdout=None)
    if selected:
        x,y,dates = paired(rain, flows, selected["acc_days"], selected["lag_days"], PERIODS["holdout"])
        s = spearman(x,y) if len(x)>=min_pairs else None
        result["holdout"] = dict(n=len(x), spearman=round(s,5) if s is not None else None,
                                 first=dates[0] if dates else None, last=dates[-1] if dates else None,
                                 status="DESCRIPTIVE_ONLY" if s is not None else "INSUFFICIENT_HOLDOUT_PAIRS",
                                 monthly_anomaly=monthly_anomaly_spearman(x,y,dates,min_pairs),
                                 future_rain_control=future_rain_falsification(rain,flows,selected["acc_days"],PERIODS["holdout"],min_pairs),
                                 river_persistence_control=persistence_control(rain,flows,selected["acc_days"],selected["lag_days"],PERIODS["holdout"],min_pairs))
        # Negative control: circular shifts of the held-out paired rain vector. No claim of significance
        # when the available dates are sparse; shifts are illustrative only.
        if s is not None and len(x)>=60:
            negatives = []
            for shift in (7, 14, 30):
                if shift < len(x):
                    z = spearman(x[shift:]+x[:shift], y)
                    negatives.append(dict(shift_observed_pairs=shift,
                                          spearman=round(z,5) if z is not None else None,
                                          limitation="Shift in observed pairs, not uniformly spaced calendar days."))
            result["negative_control_exploratory"] = negatives
    return result


def source_rain():
    """Reuse IRFEN's strict IMERG Final area-weighting and complete-48-halfhours checks."""
    import numpy as np
    spec=importlib.util.spec_from_file_location("irfen_anticipation_for_lag", ROOT / "scripts/v091_anticipation.py")
    A=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(A)
    days, lats, lons, values, meta = A.load_grid()
    catch = {r["id"]:r for r in json.loads(CATCH.read_text(encoding="utf-8"))["catchments"]}
    output = {}
    for c in PAIRS:
        unit = catch.get(c["catchment_id"])
        if not unit or not unit.get("imerg_cells"):
            output[c["catchment_id"]] = None
            continue
        vals = A.unit_series(unit["imerg_cells"],lats,lons,values)
        output[c["catchment_id"]] = {d: float(v) for d,v in zip(days,vals) if np.isfinite(v) and v >= 0}
    return output


def build(rain_by_catch=None, flows_by_column=None):
    doc = json.loads(PECHP.read_text(encoding="utf-8")) if flows_by_column is None else None
    rains=source_rain() if rain_by_catch is None else rain_by_catch
    rows=[]
    for p in PAIRS:
        if flows_by_column is None:
            f, excluded=flow_series(doc,p["flow_column"],
                "PUENTE_SANCHEZ_CERRO" if p["flow_column"]=="R_PIURA_1" else None)
        else:
            f,excluded=flows_by_column.get(p["flow_column"],{}),0
        rain=rains.get(p["catchment_id"])
        result=evaluate_pair(rain,f) if rain else dict(status="NOT_EVALUABLE_NO_COMPLETE_RAIN",candidates=[],selected_on_train=None,holdout=None)
        rows.append(dict(**p, flow_days=len(f), rain_days=len(rain or {}), rejected_flow_rows=excluded, analysis=result))
    rows.append(dict(river="Tumbes", catchment_id="TUMBES_DESEMBOCADURA",station=None,
                     analysis=dict(status="NOT_EVALUABLE_NO_MATCHED_DAILY_OBSERVED_FLOW",
                     reason_es="La delimitación y la lluvia histórica no sustituyen una serie diaria de caudal local homologada. No se toma un caudal prestado de Piura ni de Chira.")))
    return dict(schema_version="irfen_v091_fluvial_response_lag_v0_1",
                deployment_status="RESEARCH_ONLY",test_mode="TEST_ONLY",production_use=False,
                public_alerting=False,notifications_enabled=False,activation_gate="BLOCKED",
                predictive_skill_claimed=False,decision_thresholds=None,map_publishable=False,
                inputs={str(p.relative_to(ROOT)):sha(p) for p in (PECHP,IMERG,CATCH)},
                protocol=dict(train="2016-2020",holdout="2021-2023",rain_product="IMERG Final V07B DAILY, NOT realtime",
                              lags_days=list(LAGS),accum_days=list(ACC_DAYS),minimum_pairs_per_split=MIN_PAIRS,
                              selection="maximum positive training Spearman across fixed grid; no holdout tuning",
                              leakage_rule="Do not use future rainfall, do not calibrate using holdout",
                              confounding="Regulation, canal transfers and unknown PECHP day convention remain unresolved",
                              reporting="Station-specific exploratory associations; no warning thresholds or model activation",
                              falsification="Within-month demeaning and observed future rain are diagnostic controls only; not calibration or causality."),
                stations=rows)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=OUT)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args(argv)
    result=build()
    payload=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.check:
        if not args.out.exists() or args.out.read_text(encoding="utf-8")!=payload:
            print("DIFF: reproduce via python scripts/v091_fl uvial_response.py".replace("fl uvial","fluvial"))
            return 1
        print("OK_REPRODUCIBLE")
        return 0
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(payload,encoding="utf-8")
    print(json.dumps({r["river"]:r["analysis"].get("holdout") for r in result["stations"]},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
