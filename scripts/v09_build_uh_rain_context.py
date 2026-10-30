#!/usr/bin/env python3
"""IRFEN v0.9 · producto científico independiente `uh_rain_context`: lluvia IMERG Early por unidad hidrográfica
oficial ANA, con cobertura, contexto territorial y avisos oficiales en bloques separados. RESEARCH_ONLY / TEST_ONLY.
Sin red. No lo lee el motor de lluvia ni la priorización; no contiene umbrales ni alertas.

Entradas (todas en el repositorio):
* data/v09/research/uh_units_v0_1.json — unidades (scripts/v09_build_research_uh_units.py);
* data/v09/research/uh_rain/imerg_early_uh_halfhours_v0_1.json — medias por media hora (scripts/v09_uh_rain_capture.py);
* data/v09/research/uh_rain/imerg_validation_sample_v0_1.json — lectura directa de 3 gránulos;
* data/v09/research/uh_rain/avisos_registry_main_snapshot.json — registro de avisos SENAMHI vía INDECI/COEN (copia de main);
* data/v09/research/uh_rain/imerg_north_archive_main_snapshot.json — archivo IMERG operativo (copia de main), solo
  para comprobar la consistencia en Bocapán (mismo polígono);
* data/v09/sources/inei_coastal_provinces/provinces.geojson — provincias INEI referenciales.

Reglas:
* Ventanas de 1, 3, 6, 24 y 72 h que terminan en `as_of` (fin de la media hora más reciente disponible). Una media
  hora vale si existe y su cobertura espacial es ≥ MIN_COVER_PCT. Acumulado solo con TODAS las medias horas
  válidas; si falta alguna, la ventana es INCOMPLETA: acumulado = null y se da, aparte, el mínimo conocido (suma de lo
  disponible; la lluvia no es negativa, así que es una cota inferior, nunca el acumulado). Sin datos → SIN_DATOS.
* Además se busca la ventana completa más reciente de cada duración dentro del periodo capturado.
* Ninguna media hora ausente se convierte en 0 mm ni se usa para inferir ausencia de lluvia.

    python scripts/v09_build_uh_rain_context.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data/v09/research"
UNITS = RES / "uh_units_v0_1.json"
UNITS_GEO = RES / "uh_units_v0_1.geojson"
HALF = RES / "uh_rain/imerg_early_uh_halfhours_v0_1.json"
VALID = RES / "uh_rain/imerg_validation_sample_v0_1.json"
AVISOS = RES / "uh_rain/avisos_registry_main_snapshot.json"
NORTH = RES / "uh_rain/imerg_north_archive_main_snapshot.json"
PROVINCES = ROOT / "data/v09/sources/inei_coastal_provinces/provinces.geojson"
OUT = RES / "uh_rain_context_v0_1.json"
HTML = ROOT / "research/v09/uh_rain_context.html"
WINDOWS_H = (1, 3, 6, 24, 72)
MIN_COVER_PCT = 95.0
HALF_H = timedelta(minutes=30)
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, public_alerting=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None, hydraulic_factors=None,
              map_publishable=False, used_by_rain_engine_or_priority=False, predictive_skill_claimed=False)
_spec = importlib.util.spec_from_file_location("units", ROOT / "scripts/v09_build_research_uh_units.py")
U = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(U)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


def sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", s).strip()


# ---------------------------------------------------------------- half-hour series per unit
def series(half: dict, code: str) -> dict[datetime, dict]:
    """start -> slot record. Missing slots are absent from the dict (never zero)."""
    out = {}
    for g in half["granules"]:
        v = g["units_values"].get(code)
        if v is None:
            continue
        start = ts(g["start_utc"])
        if ts(g["end_utc"]) - start != HALF_H:
            continue  # not a half-hour interval: never mixed into the windows
        usable = v["rate_mm_hr"] is not None and v["covered_pct"] >= MIN_COVER_PCT
        out[start] = dict(depth_mm=v["depth_30min_mm"] if usable else None, covered_pct=v["covered_pct"],
                          reason=None if usable else ("SIN_VALOR" if v["rate_mm_hr"] is None else "COBERTURA_ESPACIAL_BAJA"))
    return out


def window(slots: dict, absent: dict, catalog_known: set, end: datetime, hours: int) -> dict:
    n = hours * 2
    starts = [end - HALF_H * (k + 1) for k in range(n)]
    have = [slots[s] for s in starts if s in slots and slots[s]["depth_mm"] is not None]
    missing = []
    for s in sorted(starts):
        if s in slots and slots[s]["depth_mm"] is not None:
            continue
        reason = (slots[s]["reason"] if s in slots else absent.get(s) or
                  ("NO_PUBLICADO_EN_EL_CATALOGO" if s not in catalog_known else "NO_PROCESADO"))
        missing.append(dict(start_utc=iso(s), reason=reason))
    known = round(sum(x["depth_mm"] for x in have), 2)
    complete = len(have) == n
    covers = [x["covered_pct"] for x in have]
    return dict(hours=hours, start_utc=iso(end - HALF_H * n), end_utc=iso(end), half_hours_expected=n,
                half_hours_valid=len(have), availability_pct=round(100 * len(have) / n, 1),
                status="COMPLETA" if complete else ("SIN_DATOS" if not have else "INCOMPLETA"),
                accumulation_mm=known if complete else None,
                mean_rate_mm_hr=round(known / hours, 3) if complete else None,
                minimum_known_mm=None if complete or not have else known,
                minimum_known_note=None if complete or not have else
                "Suma de las medias horas disponibles: cota inferior, NO es el acumulado de la ventana",
                spatial_coverage_pct=dict(min=min(covers), mean=round(sum(covers) / len(covers), 2)) if covers else None,
                missing=missing[:12], missing_count=len(missing))


def latest_complete(slots: dict, end: datetime, first: datetime, hours: int) -> dict | None:
    t = end
    while t - HALF_H * hours * 2 >= first:
        starts = [t - HALF_H * (k + 1) for k in range(hours * 2)]
        if all(s in slots and slots[s]["depth_mm"] is not None for s in starts):
            acc = round(sum(slots[s]["depth_mm"] for s in starts), 2)
            return dict(hours=hours, start_utc=iso(t - HALF_H * hours * 2), end_utc=iso(t), accumulation_mm=acc,
                        mean_rate_mm_hr=round(acc / hours, 3), age_hours_before_as_of=round((end - t).total_seconds() / 3600, 1))
        t -= HALF_H
    return None


# ---------------------------------------------------------------- territory: provinces and avisos
def province_shares(geom: dict, provinces: list, step: float = 0.02) -> dict[str, float]:
    b = U.bbox(geom)
    counts, total = {}, 0
    cand = [(f, U.bbox(f["geometry"])) for f in provinces]
    y = math.floor(b[1] / step) * step + step / 2
    while y <= b[3]:
        x = math.floor(b[0] / step) * step + step / 2
        while x <= b[2]:
            if U.contains(geom, x, y):
                total += 1
                hit = next((f for f, bb in cand if bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] and U.contains(f["geometry"], x, y)), None)
                k = f"{hit['properties']['NOMBDEP']}/{hit['properties']['NOMBPROV']}" if hit else "FUERA_DE_PROVINCIAS_INEI"
                counts[k] = counts.get(k, 0) + 1
            x += step
        y += step
    return {k: round(v / total, 3) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])} if total else {}


def aviso_status(cur: dict, at: datetime) -> str:
    try:
        s, e = ts(cur["validity_start"]), ts(cur["validity_end"])
    except Exception:  # noqa: BLE001
        return "DESCONOCIDO"
    return "VIGENTE" if s <= at < e else ("FUTURO" if at < s else "VENCIDO")


def avisos_for(shares: dict, registry: dict, as_of: datetime, span_start: datetime) -> list[dict]:
    provs = {}
    for k, v in shares.items():
        if "/" in k:
            dep, prov = k.split("/", 1)
            provs.setdefault(fold(dep), {})[fold(prov)] = v
    out = []
    for key, a in sorted(registry.get("avisos", {}).items()):
        cur = a.get("current") or {}
        try:
            s, e = ts(cur["validity_start"]), ts(cur["validity_end"])
            overlaps = s < as_of and e > span_start
        except Exception:  # noqa: BLE001
            s = e = None
            overlaps = True  # unknown validity is never treated as inactive
        if not overlaps:
            continue
        rel, share = None, 0.0
        listed = {fold(d): [fold(p) for p in ps] for d, ps in (cur.get("provinces_by_department") or {}).items()}
        for dep in [fold(d) for d in cur.get("departments") or []]:
            if dep not in provs:
                continue
            if listed.get(dep):
                sh = sum(provs[dep].get(p, 0.0) for p in listed[dep])
                if sh > 0:
                    rel, share = "PROVINCIA_LISTADA_INTERSECA_LA_UH", share + sh
            else:
                rel, share = rel or "DEPARTAMENTO_LISTADO_SIN_PROVINCIAS", share + sum(provs[dep].values())
        if not rel:
            continue
        out.append(dict(aviso_key=key, product=a.get("product"), phenomenon=cur.get("phenomenon"),
                        validity_start=cur.get("validity_start"), validity_end=cur.get("validity_end"),
                        status_at_as_of=aviso_status(cur, as_of) if s else "DESCONOCIDO", relation=rel,
                        share_of_uh_in_listed_area=round(min(share, 1.0), 3),
                        official_level=cur.get("official_level"), official_level_note=cur.get("official_level_note"),
                        source_url=a.get("official_url"),
                        caveat="Relación administrativa (provincias listadas en el aviso), no huella del aviso ni efecto hidrológico"))
    return out


# ---------------------------------------------------------------- validation
def validate(half: dict, sample: dict, units: dict) -> dict:
    # fraction of each 0.1° cell inside each unit (10×10 sub-sampling, pure Python; uh_units_v0_1.json)
    fractions = {u["code"]: {(round(c["lon_center"], 2), round(c["lat_center"], 2)): c["fraction_inside"] for c in u["imerg"]["cells"]}
                 for u in units["units"]}
    by_name = {g["granule"]: g for g in half["granules"]}
    checks = []
    for s in sample.get("samples", []):
        d = s.get("direct")
        g = by_name.get(s["granule"])
        if not d or not g:
            checks.append(dict(granule=s["granule"], ok=False, error=s.get("error", "sin lectura directa")))
            continue
        c = dict(granule=s["granule"],
                 time_matches_filename=d["time_utc"] == g["start_utc"],
                 units=d["units"], units_ok=str(d["units"]).lower() in ("mm/hr", "mm h-1", "mm/hour"),
                 grid_ok=(abs(d["lat_first"] + 89.95) < 1e-4 and abs(d["lon_first"] + 179.95) < 1e-4
                          and abs(d["lat_step"] - 0.1) < 1e-6 and abs(d["lon_step"] - 0.1) < 1e-6),
                 dims=d.get("dims_attr"), fill_value=d.get("fill_value"), units_means={})
        for code, cells in d["units_cells"].items():
            sw = sv = 0.0
            for i, lo in enumerate(cells["lon"]):
                for j, la in enumerate(cells["lat"]):
                    v = cells["values_lon_by_lat"][i][j]
                    frac = fractions[code].get((round(lo, 2), round(la, 2)), 0.0)
                    if frac and v is not None:
                        sw += frac
                        sv += frac * v
            mine = sv / sw if sw else None
            got = g["units_values"][code]["rate_mm_hr"]
            diff = None if mine is None or got is None else abs(mine - got)
            c["units_means"][code] = dict(recomputed_from_raw_cells=None if mine is None else round(mine, 5), captured=got,
                                          abs_diff_mm_hr=None if diff is None else round(diff, 5),
                                          agrees=diff is not None and diff <= max(0.01, 0.02 * abs(got)))
        c["ok"] = c["time_matches_filename"] and c["units_ok"] and c["grid_ok"] and all(
            u["agrees"] or (u["captured"] is None and u["recomputed_from_raw_cells"] is None) for u in c["units_means"].values())
        checks.append(c)
    starts = [g["start_utc"] for g in half["granules"]]
    control = [abs(v["rate_mm_hr"] - v["control_rate_mm_hr"]) for g in half["granules"] for v in g["units_values"].values()
               if v["rate_mm_hr"] is not None and v["control_rate_mm_hr"] is not None]
    lengths = {(ts(g["end_utc"]) - ts(g["start_utc"])).total_seconds() for g in half["granules"]}
    return dict(direct_granule_checks=checks,
                duplicate_starts_in_series=len(starts) - len(set(starts)),
                duplicates_dropped_from_catalog=half["catalog"]["duplicates"],
                interval_lengths_s=sorted(lengths),
                units_seen=sorted({g["units"] for g in half["granules"]}),
                primary_vs_control=dict(n=len(control), max_abs_diff_mm_hr=round(max(control), 5) if control else None,
                                        note="Muestreador existente (área celda∩polígono en grados²) frente a control "
                                             "(10×10 sub-puntos, cos(lat)); mide el efecto de celdas parciales y de la ponderación"))


def bocapan_crosscheck(half: dict, north: dict | None) -> dict:
    if not north:
        return dict(status="SIN_ARCHIVO_OPERATIVO")
    ours = {g["start_utc"]: g["units_values"].get("13936", {}).get("rate_mm_hr") for g in half["granules"]}
    pairs = []
    for g in north.get("granules", []):
        t = (g.get("targets") or {}).get("tumbes_bocapan") or {}
        k = iso(ts(g["time_utc"]))
        if k in ours and ours[k] is not None and t.get("rate_mm_hr") is not None:
            pairs.append(abs(ours[k] - t["rate_mm_hr"]))
    return dict(status="COMPARADO" if pairs else "SIN_SOLAPE", half_hours_compared=len(pairs),
                max_abs_diff_mm_hr=round(max(pairs), 5) if pairs else None,
                note="Mismo polígono ANA 13936 y mismo muestreador que la zona operativa tumbes_bocapan: debe coincidir "
                     "(redondeo a 4 decimales en el archivo operativo)")


# ---------------------------------------------------------------- build
def build() -> dict:
    units = json.loads(UNITS.read_text(encoding="utf-8"))
    geo = json.loads(UNITS_GEO.read_text(encoding="utf-8"))
    half = json.loads(HALF.read_text(encoding="utf-8"))
    sample = json.loads(VALID.read_text(encoding="utf-8")) if VALID.is_file() else {"samples": []}
    registry = json.loads(AVISOS.read_text(encoding="utf-8")) if AVISOS.is_file() else {}
    north = json.loads(NORTH.read_text(encoding="utf-8")) if NORTH.is_file() else None
    provinces = json.loads(PROVINCES.read_text(encoding="utf-8"))["features"]
    feats = {f["properties"]["code"]: f for f in geo["features"]}
    granule_ends = [ts(g["end_utc"]) for g in half["granules"]]
    span_start = ts(half["requested_span"]["start_utc"])
    as_of = max(granule_ends) if granule_ends else None
    catalog_known = {ts(g["start_utc"]) for g in half["granules"]} | {ts(x["start_utc"]) for x in half["absent"]}
    absent = {ts(x["start_utc"]): x["reason"] for x in half["absent"]}
    # temporal coverage of the captured span (independent of the units)
    expected, t = [], span_start
    while as_of and t < as_of:
        expected.append(t)
        t += HALF_H
    have = {ts(g["start_utc"]) for g in half["granules"]}
    gaps, run = [], None
    for s in expected:
        if s not in have:
            run = run or [s, s]
            run[1] = s
        elif run:
            gaps.append(run)
            run = None
    if run:
        gaps.append(run)
    temporal = dict(span_start_utc=iso(span_start), as_of_utc=iso(as_of) if as_of else None,
                    half_hours_expected=len(expected), half_hours_processed=len(have & set(expected)),
                    availability_pct=round(100 * len(have & set(expected)) / len(expected), 1) if expected else None,
                    gaps=[dict(start_utc=iso(a), end_utc=iso(b + HALF_H), half_hours=int((b - a) / HALF_H) + 1,
                               reason=absent.get(a) or ("NO_PUBLICADO_EN_EL_CATALOGO" if a not in catalog_known else "NO_PROCESADO"))
                          for a, b in gaps])
    rows = []
    for u in units["units"]:
        code = u["code"]
        slots = series(half, code)
        wins = [window(slots, absent, catalog_known, as_of, h) for h in WINDOWS_H] if as_of else []
        latest = [latest_complete(slots, as_of, span_start, h) for h in WINDOWS_H] if as_of else []
        shares = province_shares(feats[code]["geometry"], provinces)
        unknowns = list(u["territorial_uncertainty"]["reasons"])
        unknowns += ["CAUCE_OFICIAL_NO_IDENTIFICADO (SNIRH bloqueado, IGN parado: #456)",
                     "HUELLA_REAL_DE_LOS_AVISOS_NO_PUBLICADA (solo provincias listadas)",
                     "SIN_COMPARACION_CON_ESTACIONES_EN_ESTA_VENTANA"]
        if any(w["status"] != "COMPLETA" for w in wins):
            unknowns.append("VENTANAS_INCOMPLETAS: " + ", ".join(f"{w['hours']} h" for w in wins if w["status"] != "COMPLETA"))
        rows.append(dict(
            code=code, name=u["name"], study_class=u["study_class"], area_km2_ana=u["area_km2_ana"],
            imerg_resolution=u["imerg"]["resolution"], imerg_cells_touching=u["imerg"]["cells_touching"],
            imerg_cells_fully_inside=u["imerg"]["cells_fully_inside"],
            headwaters_outside_peru=u["international_boundary"]["headwaters_outside_peru"],
            international_note=u["international_boundary"]["note"],
            observation=dict(windows=wins, latest_complete_windows=[x for x in latest if x],
                             note="IMERG Early (estimación satelital casi en tiempo real); no es medición de pluviómetro"),
            territorial_inference=dict(relation=u["settlements"]["relation"], settlements=u["settlements"]["count"],
                                       near_uh_boundary=u["settlements"]["near_uh_boundary"],
                                       points=u["settlements"]["points"], province_shares=shares),
            official_context=dict(avisos=avisos_for(shares, registry, as_of, as_of - timedelta(hours=72)) if as_of else [],
                                  registry_snapshot_sha256=sha(AVISOS)),
            unknowns=dict(territorial_uncertainty_grade=u["territorial_uncertainty"]["grade"], items=unknowns)))
    return dict(schema_version="irfen_v09_uh_rain_context_v0_1", **GUARDS,
                purpose_es=("Lluvia IMERG Early por unidad hidrográfica oficial ANA (Piura y Tumbes), con cobertura, "
                            "pertenencia espacial de centros poblados y avisos oficiales en bloques separados. Producto de "
                            "investigación: sin umbrales, sin alertas, sin efecto en la prioridad."),
                rules=dict(windows_h=list(WINDOWS_H), min_spatial_cover_pct=MIN_COVER_PCT,
                           incomplete_window="accumulation_mm = null; minimum_known_mm = cota inferior (suma de lo disponible)",
                           missing="nunca 0 mm; nunca ausencia de lluvia"),
                inputs={p.name: sha(p) for p in (UNITS, UNITS_GEO, HALF, VALID, AVISOS, NORTH, PROVINCES)},
                temporal_coverage=temporal, validation=validate(half, sample, units),
                bocapan_consistency=bocapan_crosscheck(half, north), units=rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    doc = build()
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    spec = importlib.util.spec_from_file_location("view", ROOT / "scripts/v09_render_uh_rain_view.py")
    V = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(V)
    html = V.render(doc, json.loads(UNITS_GEO.read_text(encoding="utf-8")))
    if a.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text and HTML.is_file() and HTML.read_text(encoding="utf-8") == html
        print("OK" if same else "FAIL")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8")
    HTML.parent.mkdir(parents=True, exist_ok=True)
    HTML.write_text(html, encoding="utf-8")
    print(json.dumps(doc["temporal_coverage"], ensure_ascii=False)[:600])
    for r in doc["units"]:
        print(r["code"], r["name"], [(w["hours"], w["status"], w["accumulation_mm"], w["availability_pct"]) for w in r["observation"]["windows"]],
              len(r["official_context"]["avisos"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
