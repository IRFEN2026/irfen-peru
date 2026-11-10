#!/usr/bin/env python3
"""IRFEN v0.9.1 · módulo experimental de anticipación (NARANJA) — RESEARCH_ONLY / TEST_ONLY.

Aplica el protocolo fijado de antemano (config/v091_anticipation_protocol_v0_1.json) sin cambiarlo:
  1. medias areales diarias de IMERG Final por cuenca de aportación HydroSHEDS (ríos) y por celda (quebradas);
  2. acumulados A1, A3, A10 y su climatología dic–abr dejando fuera la temporada evaluada (sin fuga de información);
  3. alarmas de cada regla candidata, eventos documentados, aciertos, plazos, episodios sin evento, línea base de azar;
  4. veredicto por regla contra los criterios de aceptación: mientras no se cumplan TODOS, la regla queda
     CANDIDATA_NO_VALIDADA y NARANJA es solo simulación (sin color operativo y sin correos);
  5. simulación en vivo por checkpoint: señal candidata solo donde exista una unidad con climatología completa;
     si no, NO_EVALUABLE con el motivo. No inventa umbrales: todo umbral es un percentil de la propia unidad.

    python3 scripts/v091_anticipation.py              # escribe validación + simulación
    python3 scripts/v091_anticipation.py --check      # reproduce y compara con lo archivado (CI)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "config/v091_anticipation_protocol_v0_1.json"
IMERG = ROOT / "data/v09/research/historical/imerg_final_daily_piura_chira_v0_1.json"
CATCH = ROOT / "data/v09/research/anticipation/north_catchments_v0_1.json"
PECHP = ROOT / "data/v09/research/historical/pechp_daily_v0_1.json"
BUNDLE = ROOT / "site/data/v09/surveillance_view_v0_1.json"
OUT = ROOT / "data/v09/research/anticipation/v091_anticipation_validation_v0_1.json"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, activation_gate="BLOCKED",
              public_alerting=False, notifications_enabled=False, predictive_skill_claimed=False, decision_thresholds=None)
FLOW_COLUMN = {"PUENTE_SANCHEZ_CERRO": "R_PIURA_1", "EL_CIRUELO": "EL_CIRUELO"}
N_SHIFTS = 999


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def season_of(d: date) -> str | None:
    if d.month == 12:
        return f"{d.year}-{str(d.year + 1)[2:]}"
    if 1 <= d.month <= 4:
        return f"{d.year - 1}-{str(d.year)[2:]}"
    return None


# ------------------------------------------------------------------ rain series
def load_grid():
    d = json.loads(IMERG.read_text(encoding="utf-8"))
    days = sorted(d["days"])
    first = d["days"][days[0]]
    lats, lons = first["lat"], first["lon"]
    vals = np.full((len(days), len(lons), len(lats)), np.nan)
    for i, k in enumerate(days):
        g = d["days"][k]
        assert g["lat"] == lats and g["lon"] == lons, k
        v = np.array(g["values_lon_by_lat"], dtype=float)
        c = np.array(g["cnt_lon_by_lat"], dtype=float)
        v[(c < 48) | (v < 0)] = np.nan  # incomplete or fill: unknown, never 0
        vals[i] = v
    return [date.fromisoformat(k) for k in days], np.array(lats), np.array(lons), vals, d


def cell_index(lats, lons, lat, lon):
    i = int(np.argmin(np.abs(lons - lon)))
    j = int(np.argmin(np.abs(lats - lat)))
    if abs(lons[i] - lon) > 0.051 or abs(lats[j] - lat) > 0.051:
        return None
    return i, j


def unit_series(cells, lats, lons, vals):
    """Area-weighted daily mean; a day is known only if every cell of the unit is complete."""
    idx, w = [], []
    for c in cells:
        ij = cell_index(lats, lons, c["lat_center"], c["lon_center"])
        if ij is None:
            return None
        idx.append(ij)
        w.append(c["fraction_inside"])
    w = np.array(w)
    sub = np.stack([vals[:, i, j] for i, j in idx], axis=1)
    out = (sub * w).sum(axis=1) / w.sum()
    out[np.isnan(sub).any(axis=1)] = np.nan
    return out


def accum(days, series, k):
    """A_k(d): sum of the k UTC days ending at d; unknown if any day is missing or not contiguous."""
    out = np.full(len(series), np.nan)
    pos = {d: i for i, d in enumerate(days)}
    for i, d in enumerate(days):
        idx = [pos.get(d - timedelta(days=j)) for j in range(k)]
        if None in idx:
            continue
        v = series[idx]
        if not np.isnan(v).any():
            out[i] = v.sum()
    return out


# ------------------------------------------------------------------ rules
def percentile_excluding(values, seasons, season, q):
    m = np.array([s is not None and s != season for s in seasons]) & ~np.isnan(values)
    return float(np.percentile(values[m], q)) if m.sum() >= 100 else None


def alarms_for(rule_id, days, A, seasons):
    """Boolean alarm per day (None = not evaluable that day), with leave-one-season-out percentiles."""
    alarm = [None] * len(days)
    thr_cache = {}
    for i, d in enumerate(days):
        s = seasons[i]
        if s is None:
            continue
        if s not in thr_cache:
            if rule_id == "RIO_A3_P99":
                thr_cache[s] = dict(A3=percentile_excluding(A[3], seasons, s, 99))
            elif rule_id == "RIO_A1P99_A10P90":
                thr_cache[s] = dict(A1=percentile_excluding(A[1], seasons, s, 99), A10=percentile_excluding(A[10], seasons, s, 90))
            elif rule_id == "QDA_A1_P995":
                thr_cache[s] = dict(A1=percentile_excluding(A[1], seasons, s, 99.5))
        t = thr_cache[s]
        if any(v is None for v in t.values()):
            continue
        need = {k: A[int(k[1:])][i] for k in t}
        if any(np.isnan(v) for v in need.values()):
            continue
        alarm[i] = all(need[k] >= t[k] for k in t)
    return alarm, thr_cache


def episodes(days, alarm):
    eps, cur = [], None
    for d, a in zip(days, alarm):
        if a:
            if cur and (d - cur[1]).days <= 2:
                cur[1] = d
            else:
                cur = [d, d]
                eps.append(cur)
    return [(a, b) for a, b in eps]


def wilson(k, n, z=1.645):
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def hits(days, alarm, events):
    pos = {d: i for i, d in enumerate(days)}
    out = []
    for e in events:
        E = date.fromisoformat(e["date"])
        window = [E - timedelta(days=k) for k in range(3, -1, -1)]
        known = [alarm[pos[d]] for d in window if d in pos]
        al = [d for d in window if d in pos and alarm[pos[d]]]
        out.append(dict(event=e["id"], date=e["date"], hit=bool(al), lead_days=(E - al[0]).days if al else None,
                        window_evaluable=sum(x is not None for x in known), alarm_days_in_window=[d.isoformat() for d in al]))
    return out


def chance_baseline(days, alarm, seasons, events, rng):
    """Circular shifts of the alarm series within each season keep number and clustering of alarms."""
    by_season = {}
    for i, s in enumerate(seasons):
        if s is not None:
            by_season.setdefault(s, []).append(i)
    observed = sum(h["hit"] for h in hits(days, alarm, events))
    ge = 0
    for _ in range(N_SHIFTS):
        sh = list(alarm)
        for s, idx in by_season.items():
            k = int(rng.integers(1, len(idx)))
            seg = [alarm[i] for i in idx]
            seg = seg[k:] + seg[:k]
            for i, v in zip(idx, seg):
                sh[i] = v
        ge += sum(h["hit"] for h in hits(days, sh, events)) >= observed
    return dict(observed_hits=observed, shifts=N_SHIFTS, p=round((ge + 1) / (N_SHIFTS + 1), 4))


def flow_lookup():
    p = json.loads(PECHP.read_text(encoding="utf-8"))
    q = {}
    for m in p["months"]:
        t = (m.get("tables") or {}).get("rivers") or {}
        for dd, row in (t.get("days") or {}).items():
            try:
                d = date.fromisoformat(f"{m['month']}-{int(dd):02d}")
            except ValueError:
                continue
            for col, v in (row.get("values") or {}).items():
                if v is not None:
                    q.setdefault(col, {})[d] = v
    return q


# ------------------------------------------------------------------ validation
def validate() -> dict:
    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    days, lats, lons, vals, meta = load_grid()
    seasons = [season_of(d) for d in days]
    catchments = {c["id"]: c for c in json.loads(CATCH.read_text(encoding="utf-8"))["catchments"] if c.get("imerg_cells")}
    flows = flow_lookup()
    rng = np.random.default_rng(20261102)
    crit = proto["acceptance_criteria_for_validated_orange"]
    results = []
    for rule in proto["candidate_rules"]:
        rid = rule["id"]
        if rule["unit"] != "RIO":
            ev = proto["quebrada_events_in_box"]
            results.append(dict(rule=rid, phenomenon=rule["phenomenon"], status=("NO_EVALUABLE_SIN_CLIMATOLOGIA_SUBDIARIA" if rid == "QDA_I3H"
                                                                               else "NO_EVALUABLE_SIN_EVENTOS_FECHADOS"),
                                events=len(ev), verdict="CANDIDATA_NO_VALIDADA",
                                missing_es=["Catálogo de activaciones de quebrada con fecha y lugar dentro del recuadro (INDECI/SINPAD, INGEMMET, ANA, municipalidades).",
                                            "Climatología subdiaria (IMERG 30 min o pluviómetros) para intensidades de 1–3 h."
                                            if rid == "QDA_I3H" else "Microcuencas delimitadas de las quebradas expuestas."]))
            continue
        per_unit, all_hits = [], []
        for uid in sorted({e["unit_id"] for e in proto["documented_events"]} | {"PUENTE_NACARA", "TAMBOGRANDE", "CHIRA_DESEMBOCADURA"}):
            c = catchments.get(uid)
            if c is None:
                continue
            s = unit_series(c["imerg_cells"], lats, lons, vals)
            A = {k: accum(days, s, k) for k in (1, 3, 10)}
            alarm, thr = alarms_for(rid, days, A, seasons)
            evs = [e for e in proto["documented_events"] if e["unit_id"] == uid]
            h = hits(days, alarm, evs)
            all_hits += h
            eps = episodes(days, alarm)
            ev_dates = [date.fromisoformat(e["date"]) for e in evs]
            fa = []
            for a, b in eps:
                matched = any(a <= E <= b + timedelta(days=3) for E in ev_dates)
                row = dict(start=a.isoformat(), end=b.isoformat(), matched_event=matched)
                col = FLOW_COLUMN.get(uid)
                if col and col in flows:
                    qs = [flows[col][a + timedelta(days=k)] for k in range((b - a).days + 4) if (a + timedelta(days=k)) in flows[col]]
                    month = [v for d, v in flows[col].items() if (d.year, d.month) == (a.year, a.month)]
                    if qs and month:
                        row["flow_max_m3s_start_to_end+3"] = max(qs)
                        row["flow_month_median_m3s"] = float(np.median(month))
                if not matched:
                    fa.append(row)
            per_unit.append(dict(
                unit=uid, unit_status=c["status"], area_km2=c.get("area_km2_pixels"),
                evaluable_days=int(sum(a is not None for a in alarm)), alarm_days=int(sum(bool(a) for a in alarm)),
                episodes=len(eps), episodes_without_documented_event=len(fa), false_alarm_ratio_upper_bound=(round(len(fa) / len(eps), 3) if eps else None),
                episodes_detail=[dict(start=a.isoformat(), end=b.isoformat(),
                                      matched_event=any(a <= E <= b + timedelta(days=3) for E in ev_dates)) for a, b in eps],
                unmatched_with_flow=[r for r in fa if "flow_max_m3s_start_to_end+3" in r],
                events=h,
                thresholds_mm_by_left_out_season={k: {kk: (round(vv, 1) if vv is not None else None) for kk, vv in v.items()} for k, v in sorted(thr.items())},
                chance=chance_baseline(days, alarm, seasons, evs, rng) if evs else None))
        n = len(all_hits)
        k = sum(x["hit"] for x in all_hits)
        leads = [x["lead_days"] for x in all_hits if x["hit"]]
        eps_tot = sum(u["episodes"] for u in per_unit if any(e["unit_id"] == u["unit"] for e in proto["documented_events"]))
        fa_tot = sum(u["episodes_without_documented_event"] for u in per_unit if any(e["unit_id"] == u["unit"] for e in proto["documented_events"]))
        pod = round(k / n, 3) if n else None
        far = round(fa_tot / eps_tot, 3) if eps_tot else None
        checks = dict(
            events_enough=n >= crit["min_independent_events_per_phenomenon_and_region"],
            pod_ok=pod is not None and pod >= crit["pod_min"],
            pod_lower_ok=(wilson(k, n)[0] or 0) >= crit["pod_wilson90_lower_min"],
            far_ok=far is not None and far <= crit["false_alarm_ratio_max"],
            lead_ok=bool(leads) and float(np.median(leads)) >= crit["median_lead_days_min_with_realtime_product"],
            realtime_product=False,  # evaluated with IMERG Final (not available in real time)
            chance_ok=False,  # requires the pooled baseline over enough events (n too small: not computed as a pass)
            independent_review=False, owner_authorization=False)
        verdict = "VALIDADA" if all(checks.values()) else "CANDIDATA_NO_VALIDADA"
        results.append(dict(rule=rid, phenomenon=rule["phenomenon"], status="EVALUADA_HISTORICAMENTE", events=n, hits=k,
                            pod=pod, pod_wilson90=wilson(k, n), median_lead_days=(float(np.median(leads)) if leads else None), leads=leads,
                            episodes_units_with_events=eps_tot, episodes_without_documented_event=fa_tot, false_alarm_ratio_upper_bound=far,
                            criteria=checks, verdict=verdict, units=per_unit))
    return dict(schema_version="irfen_v091_anticipation_validation_v0_1", **GUARDS,
                protocol=dict(path=str(PROTOCOL.relative_to(ROOT)), sha256=sha(PROTOCOL)),
                inputs={str(p.relative_to(ROOT)): sha(p) for p in (IMERG, CATCH, PECHP)},
                rain_product="IMERG Final V07B diario (cota superior: no disponible en tiempo real)",
                days=dict(first=days[0].isoformat(), last=days[-1].isoformat(), n=len(days), missing=sorted(meta["absent"])),
                results=results,
                summary_es=summary(results, crit))


def summary(results, crit):
    out = []
    for r in results:
        if r["status"] == "EVALUADA_HISTORICAMENTE":
            failed = [k for k, v in r["criteria"].items() if not v]
            out.append(f"{r['rule']}: {r['hits']}/{r['events']} eventos detectados (plazo mediano {r['median_lead_days']} días); "
                       f"episodios sin evento documentado {r['episodes_without_documented_event']}/{r['episodes_units_with_events']} (cota superior). "
                       f"{r['verdict']}: no cumple {', '.join(failed)}.")
        else:
            out.append(f"{r['rule']}: {r['status']} · {r['verdict']}.")
    return out


# ------------------------------------------------------------------ live simulation (research layer only)
def polygon_cell_fraction(poly, lon_c, lat_c, half=0.05):
    """Area of polygon ∩ cell / cell area (planar degrees), Sutherland–Hodgman against the cell box."""
    def clip(pts, inside, inter):
        out = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if inside(b):
                if not inside(a):
                    out.append(inter(a, b))
                out.append(b)
            elif inside(a):
                out.append(inter(a, b))
        return out
    x0, x1, y0, y1 = lon_c - half, lon_c + half, lat_c - half, lat_c + half
    pts = [tuple(p[:2]) for p in poly]
    for inside, inter in (
            (lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
            (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
            (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
            (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))):
        if not pts:
            return 0.0
        pts = clip(pts, inside, inter)
    if len(pts) < 3:
        return 0.0
    area = 0.5 * abs(sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts))))
    return area / (4 * half * half)


def zone_cells(geom, lats, lons):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    cells, outside = [], 0.0
    for lo in np.arange(math.floor(min(xs) * 10) / 10 + 0.05, max(xs) + 0.05, 0.1):
        for la in np.arange(math.floor(min(ys) * 10) / 10 + 0.05, max(ys) + 0.05, 0.1):
            f = sum(polygon_cell_fraction(poly[0], lo, la) for poly in polys) - sum(
                polygon_cell_fraction(h, lo, la) for poly in polys for h in poly[1:])
            if f <= 1e-6:
                continue
            if cell_index(lats, lons, la, lo) is None:
                outside += f
            else:
                cells.append(dict(lat_center=round(float(la), 2), lon_center=round(float(lo), 2), fraction_inside=round(f, 4)))
    inside = sum(c["fraction_inside"] for c in cells)
    return cells, (inside / (inside + outside) if inside + outside else 0.0)


def climatology(cells, days, lats, lons, vals):
    s = unit_series(cells, lats, lons, vals)
    if s is None:
        return None
    seasons = [season_of(d) for d in days]
    A = {k: accum(days, s, k) for k in (1, 3, 10)}
    m = np.array([x is not None for x in seasons])
    q = lambda k, p: round(float(np.percentile(A[k][m & ~np.isnan(A[k])], p)), 2)
    return dict(A1_P99=q(1, 99), A1_P995=q(1, 99.5), A3_P99=q(3, 99), A10_P90=q(10, 90), n_days=int((m & ~np.isnan(A[1])).sum()))


def live_simulation(bundle: dict, now: datetime | None = None) -> dict:
    """Candidate signal per checkpoint with the CURRENT live rain, where a unit with complete climatology exists.
    Research layer only: operational=false, no colour, no e-mail."""
    days, lats, lons, vals, _ = load_grid()
    sm = bundle.get("semaforo") or {}
    zones = {(f["properties"].get("zone_id") or f["properties"].get("id")): f for f in
             (((bundle.get("rain") or {}).get("north_zones") or {}).get("zones") or {}).get("features", [])}
    fr = (sm.get("rules") or {}).get("freshness") or {"imerg_max_age_hours": 12}
    now = now or datetime.now(timezone.utc)
    items, clim_cache = [], {}
    for cp in sm.get("checkpoints", []):
        ref = cp.get("rain_ref") or ""
        rr = (sm.get("rain_refs") or {}).get(ref) or {}
        phen = "CRECIDA_DESBORDE_RIO" if cp["type"] == "rio" else "ACTIVACION_QUEBRADA"
        it = dict(checkpoint_id=cp["id"], phenomenon=phen, rule=("RIO_A3_P99" if cp["type"] == "rio" else "QDA_A1_P995"), signal=None)
        if cp["type"] == "rio":
            if not ref.startswith("zone:") or ref[5:] not in zones:
                items.append(dict(it, status="NO_EVALUABLE", reason_es="Sin cuenca de aportación con geometría para este punto."))
                continue
            if ref not in clim_cache:
                cells, cov = zone_cells(zones[ref[5:]]["geometry"], lats, lons)
                clim_cache[ref] = (cov, climatology(cells, days, lats, lons, vals) if cov >= 0.95 else None)
            cov, clim = clim_cache[ref]
            if clim is None:
                items.append(dict(it, status="NO_EVALUABLE", unit=ref, climatology_coverage=round(cov, 3),
                                  reason_es=f"La climatología IMERG Final archivada cubre solo el {cov:.0%} de la zona (recuadro hasta 6,5° S). "
                                            "Ampliar el archivo diario al sur para Lambayeque."))
                continue
            a72 = (rr.get("imerg") or {}).get("windows", {}).get("72h")
            items.append(dict(it, status="NO_EVALUABLE", unit=ref, climatology=clim,
                              reason_es="La ventana en vivo es de 72 h (IMERG Early); la regla usa A3 diario UTC de IMERG Final: "
                                        "no son comparables sin una climatología de IMERG Early." if a72 is not None else "Sin lluvia en vivo."))
        else:
            if rr.get("connection") != "CONTINUA":
                items.append(dict(it, status="NO_EVALUABLE", reason_es="La lluvia de este punto es la instantánea costera del 01-11 (no conectada)."))
                continue
            items.append(dict(it, status="NO_EVALUABLE", reason_es="Sin climatología de celda comparable con IMERG Early."))
    return dict(evaluated_at_utc=now.isoformat(), operational=False, validated_rules=[], items=items,
                note_es="Simulación de investigación: ninguna regla de anticipación está validada. No colorea el mapa operativo ni envía correos.")


def historical_replay(day: str, unit_id: str) -> dict:
    """What the candidate river rule shows for one documented unit on one historical UTC day (real IMERG Final values)."""
    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    days, lats, lons, vals, _ = load_grid()
    seasons = [season_of(d) for d in days]
    c = {x["id"]: x for x in json.loads(CATCH.read_text(encoding="utf-8"))["catchments"]}[unit_id]
    s = unit_series(c["imerg_cells"], lats, lons, vals)
    A = {k: accum(days, s, k) for k in (1, 3, 10)}
    i = days.index(date.fromisoformat(day))
    out = dict(unit=unit_id, unit_name=c["name"], day_utc=day, area_km2=c.get("area_km2_pixels"), unit_status=c["status"],
               documented_point=c.get("documented_point"), outlet=c.get("outlet"), cells=c["imerg_cells"],
               A1_mm=round(float(A[1][i]), 1), A3_mm=round(float(A[3][i]), 1), A10_mm=round(float(A[10][i]), 1),
               daily_last_7=[dict(day=days[i - k].isoformat(), mm=(None if np.isnan(s[i - k]) else round(float(s[i - k]), 1))) for k in range(6, -1, -1)],
               rules={})
    for rid in ("RIO_A3_P99", "RIO_A1P99_A10P90"):
        alarm, thr = alarms_for(rid, days, A, seasons)
        out["rules"][rid] = dict(signal=alarm[i], thresholds_left_out_season={k: round(v, 1) for k, v in thr[seasons[i]].items()},
                                 status=next(r["status"] for r in proto["candidate_rules"] if r["id"] == rid))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    res = validate()
    text = json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.check:
        old = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if old != text:
            print("anticipation validation differs from the archived result", file=sys.stderr)
            return 1
        print("anticipation validation reproduced")
        return 0
    OUT.write_text(text, encoding="utf-8")
    for line in res["summary_es"]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
