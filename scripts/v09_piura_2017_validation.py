#!/usr/bin/env python3
"""IRFEN v0.9 · primera validación histórica de crecidas fluviales: río Piura, Niño Costero 2017 (con control 2018).
RESEARCH_ONLY / TEST_ONLY. Sin red. Sin umbrales, sin modelos predictivos. Sigue el protocolo
qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md (fijado antes de mirar los resultados).

Entradas:
* data/v09/research/historical/pechp_daily_v0_1.json — caudales medios diarios PECHP (scripts/v09_pechp_extract.py);
* data/v09/research/historical/imerg_final_daily_piura_chira_v0_1.json — celdas IMERG Final V07 diarias;
* data/v09/research/uh_units_v0_1.json — fracción de cada celda de 0,1° dentro de la UH ANA 1378 (Cuenca Piura).

Salida: data/v09/research/historical/piura_2017_validation_v0_1.json y research/v09/piura_2017_validation.html.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HIST = ROOT / "data/v09/research/historical"
PECHP = HIST / "pechp_daily_v0_1.json"
IMERG = HIST / "imerg_final_daily_piura_chira_v0_1.json"
UNITS = ROOT / "data/v09/research/uh_units_v0_1.json"
OUT = HIST / "piura_2017_validation_v0_1.json"
HTML = ROOT / "research/v09/piura_2017_validation.html"
UNIT = "1378"
K_DAYS = (1, 3, 5, 7, 10, 15, 30)
LAGS_P_Q = range(0, 11)
LAGS_Q_Q = range(0, 6)
PIURA_STATIONS = ("PUENTE_NACARA", "TAMBOGRANDE", "PUENTE_SANCHEZ_CERRO", "EL_PAPAYO")  # upstream -> downstream
CANALS = ("CURUMUY", "CANAL_EJIDOS")  # operated canals: context only (transfer in / diversion out), never correlated
GAUGES = ("CHULUCANAS", "TAMBOGRANDE", "CPTO_PIURA")
MIN_COVER = 0.95
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None, map_publishable=False, predictive_skill_claimed=False,
              used_by_rain_engine_or_priority=False)
POLYGON_FLAG = "POLIGONO_NO_EQUIVALENTE_A_LA_CUENCA_DE_LA_ESTACION"


# ------------------------------------------------------------------ rain
def clean_attr(v: str) -> str:
    """netCDF4 string attributes arrive as "['mm/day']": keep the text."""
    v = str(v or "").strip()
    return v[2:-2] if v.startswith("['") and v.endswith("']") else v


def internal_day(units: str, value) -> str | None:
    import re
    m = re.match(r"(days|seconds) since (\d{4}-\d{2}-\d{2})", clean_attr(units))
    if not m or value is None:
        return None
    base = date.fromisoformat(m.group(2))
    return (base + timedelta(days=float(value) if m.group(1) == "days" else float(value) / 86400)).isoformat()


def integrity(imerg: dict) -> dict:
    rows = []
    for day, d in imerg["days"].items():
        cnts = [c for row in (d.get("cnt_lon_by_lat") or []) for c in row if c is not None]
        rows.append(dict(day=day, version=d["version"], units=clean_attr(d["units"]), internal_day=internal_day(d["time_units"], d["time_value"]),
                         name_day_matches=d["granule"].split(".")[4][:8] == day.replace("-", ""),
                         cnt_min=min(cnts) if cnts else None, cnt_max=max(cnts) if cnts else None))
    return dict(days=len(rows), versions=sorted({r["version"] for r in rows}), units=sorted({r["units"] for r in rows}),
                internal_day_matches=sum(1 for r in rows if r["internal_day"] == r["day"]),
                name_day_matches=sum(1 for r in rows if r["name_day_matches"]),
                cells_with_fewer_than_48_half_hours=sum(1 for r in rows if r["cnt_min"] is not None and r["cnt_min"] < 48),
                cnt_range=[min((r["cnt_min"] for r in rows if r["cnt_min"] is not None), default=None),
                           max((r["cnt_max"] for r in rows if r["cnt_max"] is not None), default=None)],
                sha256_recorded=sum(1 for d in imerg["days"].values() if len(d.get("file_sha256", "")) == 64),
                mismatches=[r for r in rows if r["internal_day"] != r["day"] or not r["name_day_matches"]][:10])


def basin_series(imerg: dict, fractions: dict) -> dict[str, dict]:
    out = {}
    for day, d in imerg["days"].items():
        sw = sv = tot = 0.0
        cnt_min = None
        for i, lo in enumerate(d["lon"]):
            for j, la in enumerate(d["lat"]):
                f = fractions.get((round(lo, 2), round(la, 2)))
                if not f:
                    continue
                tot += f
                v = d["values_lon_by_lat"][i][j]
                c = d["cnt_lon_by_lat"][i][j] if d.get("cnt_lon_by_lat") else None
                if c is not None:
                    cnt_min = c if cnt_min is None else min(cnt_min, c)
                if v is not None:
                    sw += f
                    sv += f * v
        cover = sw / tot if tot else 0.0
        out[day] = dict(p_mm=round(sv / sw, 3) if sw and cover >= MIN_COVER else None, coverage=round(cover, 4),
                        min_valid_half_hours_in_cell=cnt_min, units=clean_attr(d["units"]), version=d["version"])
    return dict(sorted(out.items()))


def accumulations(series: dict, k: int) -> dict[str, float | None]:
    days = sorted(series)
    out = {}
    for d in days:
        dd = date.fromisoformat(d)
        win = [(dd - timedelta(days=i)).isoformat() for i in range(k)]
        vals = [series.get(x, {}).get("p_mm") for x in win]
        out[d] = round(sum(vals), 2) if all(v is not None for v in vals) else None
    return out


# ------------------------------------------------------------------ flow
def flow_series(pechp: dict) -> dict[str, dict[str, float | None]]:
    """station -> {YYYY-MM-DD: daily mean m3/s}. Only DOS_LECTORES rows."""
    out: dict[str, dict] = {}
    for m in pechp["months"]:
        y, mo = map(int, m["month"].split("-"))
        rv = m["tables"].get("rivers", {})
        ident = rv.get("column_identity_from_report_notes", {})
        for day, row in (rv.get("days") or {}).items():
            if row["readers"] != "DOS_LECTORES":
                continue
            ds = date(y, mo, int(day)).isoformat()
            for col, st in (("R_PIURA_1", ident.get("R_PIURA_1")), ("R_PIURA_2", ident.get("R_PIURA_2")), ("CURUMUY", "CURUMUY"),
                            ("CANAL_EJIDOS", "CANAL_EJIDOS"), ("EL_CIRUELO", "EL_CIRUELO")):
                if st:
                    out.setdefault(st, {})[ds] = row["values"][col]
        nt = m["tables"].get("nacara_tambogrande", {})
        for day, row in (nt.get("days") or {}).items():
            if row["readers"] != "DOS_LECTORES":
                continue
            ds = date(y, mo, int(day)).isoformat()
            out.setdefault("PUENTE_NACARA", {})[ds] = row["values"]["PUENTE_NACARA"]
            out.setdefault("TAMBOGRANDE", {})[ds] = row["values"]["TAMBOGRANDE"]
    return {k: dict(sorted(v.items())) for k, v in out.items()}


# ------------------------------------------------------------------ statistics (no scipy needed)
def _rank(x: list[float]) -> list[float]:
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 5:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return None
    return round(sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy), 3)


def spearman(x, y):
    return pearson(_rank(x), _rank(y)) if len(x) >= 5 else None


def lagged(x: dict, y: dict, lags, days: list[str], exclude: set[str] = frozenset()) -> list[dict]:
    """corr(x(d), y(d+L)) over d in `days` with both present; y is the response."""
    out = []
    for L in lags:
        xs, ys = [], []
        for d in days:
            d2 = (date.fromisoformat(d) + timedelta(days=L)).isoformat()
            if d in exclude or d2 in exclude:
                continue
            a, b = x.get(d), y.get(d2)
            if a is not None and b is not None:
                xs.append(a)
                ys.append(b)
        out.append(dict(lag_days=L, n=len(xs), spearman=spearman(xs, ys),
                        pearson_log=(pearson([math.log1p(v) for v in xs], [math.log1p(v) for v in ys])
                                     if xs and min(xs + ys) >= 0 else None)))  # a negative source value: no log, never clipped
    return out


def differences(series: dict) -> dict:
    """Day-to-day change (removes the shared seasonal trend that inflates correlations of autocorrelated series)."""
    out = {}
    for d, v in series.items():
        prev = series.get((date.fromisoformat(d) - timedelta(days=1)).isoformat())
        if v is not None and prev is not None:
            out[d] = v - prev
    return out


def lagged_plain(x: dict, y: dict, lags, days: list[str]) -> list[dict]:
    out = []
    for L in lags:
        pairs = [(x[d], y[(date.fromisoformat(d) + timedelta(days=L)).isoformat()]) for d in days
                 if x.get(d) is not None and y.get((date.fromisoformat(d) + timedelta(days=L)).isoformat()) is not None]
        out.append(dict(lag_days=L, n=len(pairs), spearman=spearman([a for a, _ in pairs], [b for _, b in pairs])))
    return out


def best(curve: list[dict], key="spearman") -> dict | None:
    c = [r for r in curve if r[key] is not None]
    return max(c, key=lambda r: r[key]) if c else None


def gauges_vs_imerg(pechp: dict, p: dict, year: int) -> dict:
    """Point gauges (PECHP) vs the IMERG basin mean: descriptive only (point vs area, unknown day convention)."""
    m = next((x for x in pechp["months"] if x["month"] == f"{year}-03"), None)
    rg = (m or {}).get("tables", {}).get("rain_gauges", {})
    if rg.get("status") != "OK":
        return dict(status="SIN_TABLA_DE_PLUVIOMETROS_EN_TEXTO")
    out = dict(status="OK", note="Comparación punto–área y convención de día desconocida: descriptiva, no mide la precisión de IMERG. "
                                 "Celda vacía del informe = desconocido (no se distingue de 0) y se excluye.",
               imerg_basin_total_mm=round(sum(v for d, v in p.items() if d.startswith(f"{year}-03") and v is not None), 1), gauges={})
    for g in GAUGES:
        series = {date(year, 3, int(dd)).isoformat(): r["values"][g] for dd, r in rg["days"].items()
                  if r["readers"] == "DOS_LECTORES" and r["values"].get(g) is not None}
        out["gauges"][g] = dict(days_with_value=len(series), total_mm_of_days_with_value=round(sum(series.values()), 1),
                                spearman_by_day_shift={str(sh): spearman([series[d] for d in sorted(series) if p.get(
                                    (date.fromisoformat(d) + timedelta(days=sh)).isoformat()) is not None],
                                    [p[(date.fromisoformat(d) + timedelta(days=sh)).isoformat()] for d in sorted(series) if p.get(
                                        (date.fromisoformat(d) + timedelta(days=sh)).isoformat()) is not None])
                                    for sh in (-1, 0, 1)})
    return out


# ------------------------------------------------------------------ build
def build() -> dict:
    pechp = json.loads(PECHP.read_text(encoding="utf-8"))
    imerg = json.loads(IMERG.read_text(encoding="utf-8"))
    units = json.loads(UNITS.read_text(encoding="utf-8"))
    u = next(x for x in units["units"] if x["code"] == UNIT)
    fractions = {(round(c["lon_center"], 2), round(c["lat_center"], 2)): c["fraction_inside"] for c in u["imerg"]["cells"]}
    rain = basin_series(imerg, fractions)
    p = {d: r["p_mm"] for d, r in rain.items()}
    acc = {k: accumulations(rain, k) for k in K_DAYS}
    flow = flow_series(pechp)
    seasons = {}
    for year, role in ((2017, "EPISODIO"), (2018, "CONTROL"), (2016, "CONTROL")):
        days = [d for d in rain if f"{year}-01-01" <= d <= f"{year}-04-30"]
        stations = {s: {d: v for d, v in flow.get(s, {}).items() if d.startswith(f"{year}-")} for s in PIURA_STATIONS}
        stations = {s: q for s, q in stations.items() if q}
        if not stations:
            seasons[str(year)] = dict(role=role, status="SIN_CAUDALES_DIARIOS_EXTRAIDOS",
                                      rain_days=len(days), note="El informe del mes no trae la tabla diaria como texto, o no se ha archivado")
            continue
        res = dict(role=role, status="OK", window=f"{year}-01-01..{year}-04-30 (solo los días con caudal y lluvia)", stations={})
        for st, q in stations.items():
            qd = [d for d in sorted(q) if q[d] is not None]
            peak = max(qd, key=lambda d: q[d]) if qd else None
            st_res = dict(n_days=len(qd), max_daily_mean_m3s=q[peak] if peak else None, max_day=peak,
                          all_zero=all(q[d] == 0 for d in qd) if qd else None)
            if qd and not st_res["all_zero"]:
                st_res["p_vs_q"] = lagged(p, q, LAGS_P_Q, days)
                st_res["acc_vs_q"] = {f"A{k}": lagged(acc[k], q, LAGS_P_Q, days) for k in K_DAYS}
                st_res["acc_vs_q_best_for_reading_only"] = {k: best(v) for k, v in st_res["acc_vs_q"].items()}
                excl = {(date.fromisoformat(peak) + timedelta(days=i)).isoformat() for i in range(-3, 4)}
                st_res["p_vs_q_excluding_peak_pm3d"] = lagged(p, q, LAGS_P_Q, days, exclude=excl)
                st_res["dp_vs_dq_first_differences"] = lagged_plain(differences(p), differences(q), LAGS_P_Q, days)
                st_res["peak_chronology"] = {f"A{k}": dict(max_day=max((d for d in days if acc[k].get(d) is not None),
                                                                          key=lambda d: acc[k][d], default=None))
                                             for k in K_DAYS}
                for k, v in st_res["peak_chronology"].items():
                    if v["max_day"] and peak:
                        v["days_before_flow_peak"] = (date.fromisoformat(peak) - date.fromisoformat(v["max_day"])).days
            else:
                st_res["note"] = "Serie nula o constante: sin correlación definida (p. ej., Los Ejidos deriva todo el caudal)"
            res["stations"][st] = st_res
        chain = {}
        for up, down in (("PUENTE_NACARA", "TAMBOGRANDE"), ("TAMBOGRANDE", "PUENTE_SANCHEZ_CERRO"), ("PUENTE_NACARA", "PUENTE_SANCHEZ_CERRO")):
            if up in stations and down in stations:
                curve = lagged(stations[up], stations[down], LAGS_Q_Q, sorted(stations[up]))
                chain[f"{up}->{down}"] = dict(curve=curve, best=best(curve))
        res["flow_to_flow"] = chain
        canal = {}
        for c in CANALS:
            q = {d: v for d, v in flow.get(c, {}).items() if d.startswith(f"{year}-03") and v is not None}
            if q:
                canal[c] = dict(days=len(q), mean_m3s=round(sum(q.values()) / len(q), 1),
                                volume_mmc=round(sum(q.values()) * 86400 / 1e6, 1))
        sc = {d: v for d, v in flow.get("PUENTE_SANCHEZ_CERRO", {}).items() if d.startswith(f"{year}-03") and v is not None}
        res["operated_canals_context"] = dict(canals=canal, sanchez_cerro_volume_mmc=round(sum(sc.values()) * 86400 / 1e6, 1) if sc else None,
                                             note="Curumuy = trasvase Chira→Piura que entra al río; canal Ejidos = derivación en Los Ejidos. "
                                                  "Contexto de regulación: no se correlacionan con la lluvia.")
        res["gauges_vs_imerg"] = gauges_vs_imerg(pechp, p, year)
        seasons[str(year)] = res
    absent = imerg.get("absent", {})
    return dict(
        schema_version="irfen_v09_piura_2017_validation_v0_1", **GUARDS,
        question_es=("¿Contienen los acumulados de precipitación IMERG señales temporalmente útiles para explicar las crecidas "
                     "observadas del río Piura? (sin afirmar capacidad predictiva)"),
        protocol="qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md v0.1",
        polygon=dict(unit=f"ANA UH {UNIT} {u['name']}", area_km2=u["area_km2_ana"], flag=POLYGON_FLAG,
                     reasons=["La UH incluye el Bajo Piura aguas abajo de Sánchez Cerro (hasta Sechura).",
                              "No hay coordenadas oficiales de estación ni cuenca delimitada hasta cada estación.",
                              "Sánchez Cerro está regulado por la presa derivadora Los Ejidos y recibe el trasvase Chira→Piura "
                              "(canal Daniel Escobar, aforo Curumuy).",
                              "Puente Ñácara y Tambogrande están aguas arriba, pero su área de drenaje tampoco está delimitada."],
                     consequence="Asociación temporal, no relación causal ni balance hídrico."),
        rain=dict(product="IMERG Final V07 diario (GPM_3IMERGDF)", day="UTC 00–24 (19–19 h de Perú)",
                  station_day_convention="no declarada por el PECHP: desfases de ±1 día son ambiguos",
                  min_coverage=MIN_COVER, days=len(rain), days_without_basin_value=sum(1 for v in p.values() if v is None),
                  absent_days=absent, units=sorted({r["units"] for r in rain.values()}),
                  versions=sorted({r["version"] for r in rain.values()}),
                  min_valid_half_hours_in_any_cell=min((r["min_valid_half_hours_in_cell"] for r in rain.values()
                                                        if r["min_valid_half_hours_in_cell"] is not None), default=None),
                  integrity=integrity(imerg), series=rain, accumulations={f"A{k}": v for k, v in acc.items()}),
        flow=dict(source="PECHP, caudal medio diario (m³/s), filas con dos lectores coincidentes", stations=flow,
                  source_anomalies=[dict(station=st, day=d, value=v, note="valor negativo impreso en el informe; se conserva tal cual")
                                    for st, q in flow.items() for d, v in q.items() if v is not None and v < 0]),
        seasons=seasons)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc = build()
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    import importlib.util
    spec = importlib.util.spec_from_file_location("view", ROOT / "scripts/v09_render_piura_2017_view.py")
    V = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V)
    html = V.render(doc)
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text and HTML.is_file() and HTML.read_text(encoding="utf-8") == html
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    HTML.parent.mkdir(parents=True, exist_ok=True)
    HTML.write_text(html, encoding="utf-8")
    for y, s in doc["seasons"].items():
        print(y, s["role"], s["status"])
        for st, r in s.get("stations", {}).items():
            b = best(r["p_vs_q"]) if r.get("p_vs_q") else None
            print("  ", st, r["n_days"], r["max_daily_mean_m3s"], r["max_day"], "best P→Q", b,
                  {k: (v["lag_days"], v["spearman"]) for k, v in (r.get("acc_vs_q_best_for_reading_only") or {}).items() if v})
            if r.get("dp_vs_dq_first_differences"):
                print("      diffs:", [(c["lag_days"], c["spearman"]) for c in r["dp_vs_dq_first_differences"][:4]])
            if r.get("p_vs_q_excluding_peak_pm3d"):
                print("      excl. peak:", [(c["lag_days"], c["spearman"]) for c in r["p_vs_q_excluding_peak_pm3d"][:4]])
        print("  canals", s.get("operated_canals_context"))
        print("  gauges", json.dumps(s.get("gauges_vs_imerg"))[:500])
        for k, v in s.get("flow_to_flow", {}).items():
            print("  ", k, v["best"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
