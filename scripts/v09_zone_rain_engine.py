#!/usr/bin/env python3
"""IRFEN v0.9 — motor TEST_ONLY de lluvia y prioridad interna de revisión por zona de vigilancia.

Combina, sin recalcular las fuentes:
* avisos SENAMHI vía INDECI/COEN y su relación territorial (data/v09/surveillance/aviso_zone_links_v0_1.json);
* IMERG Early 30 min: archivo continuo del norte (data/v09/rain/imerg_early_north_v0_1.json) y, como respaldo,
  el archivo del probe v0.8 (site/data/calibration/imerg_early_live_archive.json);
* GOES-19 RRQPE: última muestra del probe v0.8 que pasa su control de calidad (DQF=0), tasa instantánea en una
  ventana de 5×5 píxeles, no validada localmente;
* GEOS-CF v2: pronóstico experimental horario del probe v0.8.

Reglas científicas:
* Una ventana de 1/3/6/24 h solo se calcula si están todas sus medias horas con valor; si no, NO_DISPONIBLE con
  el número de medias horas que faltan. Las ventanas terminan en el último gránulo disponible y su antigüedad
  (latencia de IMERG Early) se muestra siempre: nunca es «lluvia en tiempo real».
* Percentiles: solo con una serie histórica homogénea de la misma fuente, objetivo y ventana con al menos
  MIN_PERCENTILE_SAMPLES valores; hoy no existe, así que se declara NO_DISPONIBLE.
* Sin umbrales de activación, caudales, cotas ni probabilidades. La prioridad interna de revisión es un
  vocabulario propio de IRFEN, separado del nivel oficial de SENAMHI, y un dato ausente nunca baja la prioridad.

  python scripts/v09_zone_rain_engine.py           # escribe si el contenido cambió
  python scripts/v09_zone_rain_engine.py --check   # reproduce la salida desde sus entradas (sin reloj)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
LINKS = ROOT / "data/v09/surveillance/aviso_zone_links_v0_1.json"
IMERG_NORTH = ROOT / "data/v09/rain/imerg_early_north_v0_1.json"
IMERG_V08 = ROOT / "site/data/calibration/imerg_early_live_archive.json"
GOES = ROOT / "site/data/calibration/goes19_rrqpe_probe.json"
GEOS = ROOT / "site/data/forecast/latest.json"
BOUNDARIES_LATEST = ROOT / "data/v09/admin_boundaries/latest.json"
OUT = ROOT / "data/v09/surveillance/zone_rain_state_v0_1.json"
WINDOWS = {"1h": 2, "3h": 6, "6h": 12, "24h": 48}
MIN_PERCENTILE_SAMPLES = 60
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)
REVIEW_PRIORITIES = [  # IRFEN internal vocabulary (never a SENAMHI level, never a probability)
    dict(code="R1_REVISION_PRIORITARIA", label_es="Revisión prioritaria",
         rule_es="Aviso de lluvia VIGENTE y anomalía de lluvia observada interpretable (percentil exploratorio ≥ 95 de una serie homogénea)."),
    dict(code="R2_VIGILANCIA_ACTIVA", label_es="Vigilancia activa",
         rule_es="Aviso de lluvia VIGENTE relacionado con la zona."),
    dict(code="R3_PREPARAR_VIGILANCIA", label_es="Preparar vigilancia",
         rule_es="Aviso de lluvia FUTURO (o de vigencia desconocida) relacionado con la zona."),
    dict(code="R4_LLUVIA_OBSERVADA_SIN_AVISO", label_es="Seguimiento por lluvia observada",
         rule_es="Sin aviso de lluvia, pero la última ventana completa de IMERG o la última muestra GOES válida no es nula."),
    dict(code="R5_DATOS_INSUFICIENTES", label_es="Datos insuficientes",
         rule_es="Sin aviso de lluvia y sin observaciones completas: no se puede descartar nada (dato ausente ≠ riesgo bajo)."),
    dict(code="R6_SIN_SENAL_EN_DATOS_DISPONIBLES", label_es="Sin señal en los datos disponibles",
         rule_es="Sin aviso de lluvia; ventana IMERG de 24 h completa y nula, y GOES válido y nulo. No significa ausencia de peligro."),
]
RANK = {p["code"]: i for i, p in enumerate(REVIEW_PRIORITIES)}


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# --------------------------------------------------------------------------- observations (pure)
def series_from_north(archive: dict | None, target: str) -> dict[str, float | None]:
    out = {}
    for g in (archive or {}).get("granules", []):
        row = g["targets"].get(target)
        if row is not None:
            out[g["time_utc"]] = row["accum_30min_mm"] if row.get("valid_cells") else None
    return out


def series_from_v08(archive: dict | None, target: str) -> dict[str, float | None]:
    out = {}
    for g in (archive or {}).get("granules", []):
        for t in g.get("targets", []):
            if t.get("target_id") == target:
                out[g["time_utc"]] = t.get("accum_30min_mm") if (t.get("valid_cells") or 0) > 0 else None
    return out


def windows(series: dict[str, float | None]) -> dict:
    """Accumulations ending at the latest half-hour with a value. A window with any missing half-hour is
    NO_DISPONIBLE; nothing is interpolated."""
    valid = sorted(t for t, v in series.items() if v is not None)
    if not valid:
        return dict(latest_granule_start_utc=None, windows={k: dict(status="NO_DISPONIBLE", reason="no IMERG Early samples for this zone")
                                                             for k in WINDOWS})
    last = parse(valid[-1])
    out = {}
    for name, n in WINDOWS.items():
        slots = [(last - timedelta(minutes=30 * k)).isoformat() for k in range(n)]
        missing = [s for s in slots if series.get(s) is None]
        start, end = (last - timedelta(minutes=30 * (n - 1))).isoformat(), (last + timedelta(minutes=30)).isoformat()
        if missing:
            out[name] = dict(status="NO_DISPONIBLE", start_utc=start, end_utc=end, required_half_hours=n,
                             missing_half_hours=len(missing), reason=f"{len(missing)} of {n} half-hours missing: not reconstructed")
        else:
            out[name] = dict(status="CALCULADO", start_utc=start, end_utc=end, required_half_hours=n,
                             accum_mm=round(sum(series[s] for s in slots), 2),
                             max_half_hour_mm=round(max(series[s] for s in slots), 2))
    return dict(latest_granule_start_utc=valid[-1], window_end_utc=(last + timedelta(minutes=30)).isoformat(), windows=out)


def imerg_for_zone(zone_id: str, v08_target: str | None, north: dict | None, v08: dict | None) -> dict:
    candidates = []
    if north and any(zone_id in g["targets"] for g in north.get("granules", [])):
        candidates.append(("IMERG_EARLY_V09_NORTH_CONTINUOUS", windows(series_from_north(north, zone_id))))
    if v08_target:
        candidates.append((f"IMERG_EARLY_V08_PROBE:{v08_target}", windows(series_from_v08(v08, v08_target))))
    if not candidates:
        return dict(source=None, status="NO_DISPONIBLE", reason="zone not sampled by any IMERG Early archive yet",
                    windows={k: dict(status="NO_DISPONIBLE") for k in WINDOWS})

    def score(c):
        w = c[1]["windows"]
        return (sum(v["status"] == "CALCULADO" for v in w.values()), c[1].get("latest_granule_start_utc") or "")

    name, best = max(candidates, key=score)
    series = (series_from_north(north, zone_id) if name.startswith("IMERG_EARLY_V09") else series_from_v08(v08, v08_target))
    last = best.get("latest_granule_start_utc")
    tail = []
    if last:
        for k in range(47, -1, -1):
            t = (parse(last) - timedelta(minutes=30 * k)).isoformat()
            tail.append([t, series.get(t)])
    return dict(source=name, series_24h_half_hourly_mm=tail, status="CALCULADO" if any(v["status"] == "CALCULADO" for v in best["windows"].values()) else "NO_DISPONIBLE",
                nature_es="Estimación satelital IMERG Early (30 min), con horas de latencia; no es una observación en tiempo real.",
                **best, alternatives=[c[0] for c in candidates if c[0] != name])


def goes_for_zone(target: str | None, probe: dict | None) -> dict:
    if not target:
        return dict(status="NO_DISPONIBLE", reason="zone not sampled by the GOES-19 RRQPE probe")
    if not probe or not probe.get("source_available"):
        return dict(status="NO_DISPONIBLE", reason="GOES-19 probe has no available source in its last run")
    rows = [s for s in probe.get("samples", []) if s.get("target_id") == target]
    good = [s for s in rows if s.get("coverage_valid") and (s.get("good_quality_pixel_count") or 0) > 0]
    if not good:
        return dict(status="NO_DISPONIBLE", reason="no sample passed the probe quality control (DQF=0)")
    wsum = sum(float(s.get("weight", 1.0)) for s in good)
    mean = sum(float(s.get("weight", 1.0)) * s["rain_rate_summary_mm_h"]["mean"] for s in good) / wsum
    mx = max(s["rain_rate_summary_mm_h"]["max"] for s in good)
    lo = probe.get("latest_object") or {}
    return dict(status="CALCULADO", rate_mean_mm_h=round(mean, 2), rate_max_mm_h=round(mx, 2), scan_end_utc=lo.get("scan_end"),
                good_quality_pixels=sum(s["good_quality_pixel_count"] for s in good), window_pixels=sum(s["window_pixel_count"] for s in rows),
                sampling_es="Tasa instantánea en ventanas de 5×5 píxeles (≈2 km) en puntos representativos; no es acumulado de cuenca.",
                uncertainty_es="RRQPE no validado localmente contra IMERG ni pluviómetros: uso exploratorio.")


def geos_for_zone(target: str | None, forecast: dict | None) -> dict:
    if not target:
        return dict(status="NO_DISPONIBLE", reason="zone not in the GEOS-CF experimental forecast run")
    zone = next((z for z in (forecast or {}).get("zones", []) if z.get("zone_id") == target), None)
    if not zone or not zone.get("hourly"):
        return dict(status="NO_DISPONIBLE", reason="GEOS-CF forecast has no hourly series for this zone")
    return dict(status="CALCULADO", generated_at_utc=forecast.get("generated_at"), dataset_time_start=forecast.get("dataset_time_start"),
                hourly=[dict(valid_time_utc=h["valid_time"], precip_mm=h["precip_mm"]) for h in zone["hourly"][:120]],
                nature_es="Pronóstico experimental NASA GEOS-CF v2 (0.25°). Las sumas se calculan al mostrar, desde la hora actual.")


# --------------------------------------------------------------------------- review priority (pure)
def review_priority(avisos: list[dict], imerg: dict, goes: dict, percentile: dict) -> dict:
    """Transparent internal review priority. Inputs are evidence; no thresholds on rain amounts."""
    rain_vig = [a for a in avisos if a["status"] == "VIGENTE" and a["relation_method"] != "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES"]
    rain_fut = [a for a in avisos if a["status"] in ("FUTURO", "DESCONOCIDO") and a["relation_method"] != "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES"]
    w24 = imerg["windows"].get("24h", {})
    observed_nonzero = any(v.get("status") == "CALCULADO" and v.get("accum_mm", 0) > 0 for v in imerg["windows"].values()) or \
        (goes.get("status") == "CALCULADO" and goes.get("rate_max_mm_h", 0) > 0)
    complete_zero = w24.get("status") == "CALCULADO" and w24.get("accum_mm") == 0 and goes.get("status") == "CALCULADO" and goes.get("rate_max_mm_h") == 0
    reasons, missing = [], []
    if imerg["windows"].get("24h", {}).get("status") != "CALCULADO":
        missing.append("IMERG 24 h incompleta")
    if goes.get("status") != "CALCULADO":
        missing.append("GOES-19 no disponible para esta zona")
    if percentile.get("status") != "CALCULADO":
        missing.append("percentil histórico no disponible: anomalía no evaluable")
    if rain_vig and percentile.get("status") == "CALCULADO" and (percentile.get("percentile_24h") or 0) >= 95:
        code = "R1_REVISION_PRIORITARIA"
    elif rain_vig:
        code = "R2_VIGILANCIA_ACTIVA"
    elif rain_fut:
        code = "R3_PREPARAR_VIGILANCIA"
    elif observed_nonzero:
        code = "R4_LLUVIA_OBSERVADA_SIN_AVISO"
    elif complete_zero:
        code = "R6_SIN_SENAL_EN_DATOS_DISPONIBLES"
    else:
        code = "R5_DATOS_INSUFICIENTES"
    for a in rain_vig + rain_fut:
        reasons.append(f"Aviso {a['aviso_key']} ({a['status']}; nivel oficial: {a.get('official_level') or 'no consta'}) — {a['relation_method']}")
    if observed_nonzero:
        reasons.append("Lluvia observada no nula en la última ventana completa de IMERG o en la última muestra GOES válida")
    if rain_vig and percentile.get("status") != "CALCULADO":
        reasons.append("Situación C (aviso vigente + anomalía) no evaluable: no hay percentiles interpretables")
    p = REVIEW_PRIORITIES[RANK[code]]
    return dict(code=code, label_es=p["label_es"], rule_es=p["rule_es"], reasons_es=reasons, missing_es=missing,
                data_complete=not missing[:2])


def sort_key(row: dict):
    acc = row["imerg"]["windows"].get("24h", {}).get("accum_mm")
    six = row["imerg"]["windows"].get("6h", {}).get("accum_mm")
    obs = acc if acc is not None else six
    # Missing observations sort before observed values inside a tier: a missing signal is never 'low'.
    return (RANK[row["review_priority"]["code"]], 0 if obs is None else 1, -(obs or 0), row["zone_id"])


# --------------------------------------------------------------------------- build
def zone_universe(zones_cfg: dict, boundaries: dict | None) -> list[dict]:
    out = []
    for z in zones_cfg["zones"]:
        v08 = z.get("v08_source_targets") or {}
        if z["zone_type"] == "BASIN_GEOMETRY":
            out.append(dict(zone_id=z["zone_id"], display_name=z["display_name"], department=z["registered_department"],
                            zone_type=z["zone_type"], geometry_path=z["geometry_path"], v08=v08))
        else:
            for prov in (boundaries or {}).get("piura_provinces", []):
                out.append(dict(zone_id=f"{z['zone_id']}:{prov}", display_name=f"Piura · {prov.title()}", department="PIURA",
                                zone_type="ADMINISTRATIVE_CONTEXT_NO_BASIN", province=prov,
                                v08=v08 if v08.get("province") == prov else {}))
    return out


def build(now: datetime | None = None) -> dict:
    zones_cfg, links = load(ZONES), load(LINKS) or {}
    latest = load(BOUNDARIES_LATEST)
    boundaries = None
    if latest:
        fc = load(ROOT / latest["path"])
        boundaries = dict(piura_provinces=sorted(f["properties"]["NOMBPROV"] for f in fc["features"] if f["properties"]["NOMBDEP"] == "PIURA"))
    north, v08, goes, geos = load(IMERG_NORTH), load(IMERG_V08), load(GOES), load(GEOS)
    by_zone = {r["zone_id"]: r for r in links.get("surveillance_zones", [])}
    rows = []
    for z in zone_universe(zones_cfg, boundaries):
        avisos = list(by_zone.get(z["zone_id"], {}).get("avisos", []))
        if z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN":  # department-only links of the Piura context zone
            avisos += [dict(a, relation_method=a["relation_method"]) for a in by_zone.get("piura_province_context", {}).get("avisos", [])]
        imerg = imerg_for_zone(z["zone_id"], z["v08"].get("imerg_early"), north, v08)
        goes_row = goes_for_zone(z["v08"].get("goes19_rrqpe"), goes)
        geos_row = geos_for_zone(z["v08"].get("geos_cf"), geos)
        percentile = dict(status="NO_DISPONIBLE", min_samples=MIN_PERCENTILE_SAMPLES,
                          reason="no homogeneous historical series of IMERG Early 24 h windows for this target yet (archive keeps 96 h)")
        rows.append(dict(zone_id=z["zone_id"], display_name=z["display_name"], department=z["department"], zone_type=z["zone_type"],
                         province=z.get("province"), avisos=avisos, imerg=imerg, goes19=goes_row, geos_cf=geos_row,
                         percentile=percentile,
                         river_level=dict(status="NO_DISPONIBLE", reason="no verified river level or discharge readings integrated for this zone "
                                                                              "(Piura Ñácara probe queries a SENAMHI host: owner decision pending)"),
                         documentary_antecedents=dict(status="NO_INTEGRADO", reason="documentary identity/event leads not yet linked to this zone"),
                         v08_source_caveat=z["v08"].get("caveat"),
                         review_priority=review_priority(avisos, imerg, goes_row, percentile)))
    rows.sort(key=sort_key)
    return dict(schema_version="0.1", output_id="irfen-v09-zone-rain-state:v0.1", **GUARDS, map_publishable=False,
                inputs={k: sha(p) for k, p in (("zones", ZONES), ("links", LINKS), ("imerg_north", IMERG_NORTH),
                                                ("imerg_v08", IMERG_V08), ("goes19", GOES), ("geos_cf", GEOS))},
                links_evaluated_at_utc=links.get("evaluated_at_utc"), links_statuses_valid_until_utc=links.get("statuses_valid_until_utc"),
                aviso_source_state=links.get("source_state"),
                review_priorities=REVIEW_PRIORITIES,
                rules_es=["Ventanas solo con todas sus medias horas; si falta alguna, NO_DISPONIBLE.",
                          "IMERG Early tiene horas de latencia; la antigüedad de cada ventana se muestra siempre.",
                          "GOES-19 RRQPE solo con píxeles que pasan el control de calidad; uso exploratorio sin validación local.",
                          "Sin umbrales de lluvia, caudales, cotas ni probabilidades de huaico.",
                          "La prioridad interna de revisión no es un nivel SENAMHI, ni un riesgo, ni una alerta.",
                          "Un dato ausente nunca rebaja la prioridad: 'Datos insuficientes' se ordena antes que 'Sin señal'."],
                zones=rows)


def content_equal(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k != "evaluated_at_utc"} == {k: v for k, v in b.items() if k != "evaluated_at_utc"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = build()
    committed = load(OUT)
    if args.check:
        if committed is None or not content_equal(committed, out):
            print("FAIL: zone_rain_state does not match its inputs: run scripts/v09_zone_rain_engine.py")
            return 1
        print(f"OK: {len(out['zones'])} zones")
        return 0
    if committed is None or not content_equal(committed, out):
        out["evaluated_at_utc"] = datetime.now(timezone.utc).isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("written")
    for r in out["zones"]:
        w = r["imerg"]["windows"]
        print(f"{r['review_priority']['code']:36s} {r['display_name'][:40]:40s} imerg={r['imerg']['source']} "
              + " ".join(f"{k}={w[k].get('accum_mm', w[k]['status'])}" for k in WINDOWS) + f" goes={r['goes19'].get('rate_mean_mm_h', r['goes19']['status'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
