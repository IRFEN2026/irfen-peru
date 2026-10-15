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
* Frescura (parámetros de calidad de dato, no umbrales de decisión): una ventana IMERG que termina más de
  FRESHNESS["imerg_stale_after_h"] horas antes del instante evaluado, o un escaneo GOES-19 de más de
  FRESHNESS["goes_stale_after_min"] minutos, se sigue mostrando con su fecha pero NO cuenta para la prioridad:
  un dato antiguo equivale a un dato ausente (nunca a «sin lluvia»). Un ciclo GEOS-CF de más de
  FRESHNESS["geos_max_cycle_age_h"] horas no da sumas de 6/24 h, y una suma solo existe si todas sus horas
  consecutivas están en el ciclo.
* La prioridad se evalúa en un instante explícito (``at``): el estado de cada aviso se recalcula con su vigencia
  documentada y se publica ``next_change_utc``, el siguiente instante en que la evaluación puede cambiar sin datos
  nuevos. El panel aplica la misma regla (site/v09/index.html, bloque SHARED-RULES) con la hora del lector; una
  prueba comprueba que ambas implementaciones coinciden.

  python scripts/v09_zone_rain_engine.py           # escribe si el contenido cambió
  python scripts/v09_zone_rain_engine.py --check   # reproduce la salida desde sus entradas en su evaluated_at_utc
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
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
GOES_NORTH = ROOT / "data/v09/rain/goes19_rrqpe_north_v0_1.json"
GEOS_NORTH = ROOT / "data/v09/rain/geos_cf_north_v0_1.json"
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
# Data-freshness parameters (quality of the evidence, not decision thresholds). IMERG Early: nominal latency ~4 h,
# observed 5-6 h on the north archive, so 12 h tolerates one or two missed runs. GOES-19 full disk: a scan every
# 10 min, so 90 min means several missed runs. GEOS-CF: one cycle a day (first hour 09:30 UTC) that the public store
# publishes 21.6-28.5 h later (measured 12-13 Oct 2026), so the newest cycle reaches 45.6-52.5 h before the next one
# arrives: 54 h = 24 h cadence + 28.5 h maximum observed lag, rounded up. Revisit with more cycles.
FRESHNESS = dict(imerg_stale_after_h=12, goes_stale_after_min=90, geos_max_cycle_age_h=54)
NEGATIVE_RELATION = "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES"


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
    coverage = dict(required_half_hours=48, available_half_hours=sum(v is not None for _, v in tail),
                    missing_half_hours_utc=[t for t, v in tail if v is None]) if tail else dict(required_half_hours=48, available_half_hours=0,
                                                                                               missing_half_hours_utc=[])
    return dict(source=name, series_24h_half_hourly_mm=tail, coverage_24h=coverage, status="CALCULADO" if any(v["status"] == "CALCULADO" for v in best["windows"].values()) else "NO_DISPONIBLE",
                nature_es="Estimación satelital IMERG Early (30 min), con horas de latencia; no es una observación en tiempo real.",
                **best, alternatives=[c[0] for c in candidates if c[0] != name])


def goes_for_zone(target: str | None, probe: dict | None, zone_id: str | None = None, north: dict | None = None) -> dict:
    """Latest GOES-19 RRQPE rate. Prefers the v0.9 polygon sampling (all DQF=0 pixels inside the zone); falls back to
    the v0.8 probe's 5×5-pixel point windows."""
    scans = [s for s in (north or {}).get("scans", []) if zone_id and zone_id in s.get("targets", {})]
    if scans:
        last = scans[-1]
        row = last["targets"][zone_id]
        recent = [[s["scan_end"], s["targets"][zone_id].get("rate_mean_mm_h")] for s in scans[-24:]]
        if row.get("valid_pixels"):
            return dict(status="CALCULADO", source="GOES19_RRQPE_V09_POLYGON", rate_mean_mm_h=row["rate_mean_mm_h"],
                        rate_max_mm_h=row["rate_max_mm_h"], scan_end_utc=last["scan_end"], good_quality_pixels=row["valid_pixels"],
                        window_pixels=row["pixels"], valid_fraction=row.get("valid_fraction"), recent_scans_mm_h=recent,
                        sampling_es=f"Tasa instantánea media de {row['valid_pixels']} píxeles DQF=0 (de {row['pixels']}) dentro del polígono; no es acumulado.",
                        uncertainty_es="RRQPE no validado localmente contra IMERG ni pluviómetros: uso exploratorio.")
        return dict(status="NO_DISPONIBLE", source="GOES19_RRQPE_V09_POLYGON", scan_end_utc=last["scan_end"], recent_scans_mm_h=recent,
                    reason=f"no pixel passed quality control (DQF=0) in the last scan ({row.get('pixels', 0)} pixels in the polygon)")
    if not target:
        return dict(status="NO_DISPONIBLE", reason="zone not sampled by any GOES-19 RRQPE archive")
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
    return dict(status="CALCULADO", source=f"GOES19_RRQPE_V08_PROBE:{target}", rate_mean_mm_h=round(mean, 2), rate_max_mm_h=round(mx, 2),
                scan_end_utc=lo.get("scan_end"), good_quality_pixels=sum(s["good_quality_pixel_count"] for s in good),
                window_pixels=sum(s["window_pixel_count"] for s in rows),
                sampling_es="Tasa instantánea en ventanas de 5×5 píxeles (≈2 km) en puntos representativos; no es acumulado de cuenca.",
                uncertainty_es="RRQPE no validado localmente contra IMERG ni pluviómetros: uso exploratorio.")


def geos_for_zone(target: str | None, forecast: dict | None, zone_id: str | None = None, north: dict | None = None) -> dict:
    zn = (north or {}).get("zones", {}).get(zone_id) if zone_id else None
    if zn and zn.get("hourly"):
        return dict(status="CALCULADO", source="GEOS_CF_V09_POLYGON", generated_at_utc=north.get("generated_at_utc"),
                    dataset_time_start=north.get("dataset_time_start"), cells=zn["cells"], resolution_note=zn["resolution_note"],
                    hourly=[dict(valid_time_utc=h["valid_time"], precip_mm=h["precip_mm"]) for h in zn["hourly"]],
                    nature_es="Pronóstico experimental NASA GEOS-CF v2 (celdas de 0,25°). Las sumas se calculan al mostrar, desde la hora actual.")
    if not target:
        return dict(status="NO_DISPONIBLE", reason="zone not in any GEOS-CF experimental forecast run")
    zone = next((z for z in (forecast or {}).get("zones", []) if z.get("zone_id") == target), None)
    if not zone or not zone.get("hourly"):
        return dict(status="NO_DISPONIBLE", reason="GEOS-CF forecast has no hourly series for this zone")
    return dict(status="CALCULADO", source=f"GEOS_CF_V08:{target}", generated_at_utc=forecast.get("generated_at"),
                dataset_time_start=forecast.get("dataset_time_start"),
                hourly=[dict(valid_time_utc=h["valid_time"], precip_mm=h["precip_mm"]) for h in zone["hourly"][:120]],
                nature_es="Pronóstico experimental NASA GEOS-CF v2 (0.25°). Las sumas se calculan al mostrar, desde la hora actual.")


# --------------------------------------------------------------------------- shared rules (pure; mirrored in site/v09/index.html)
def _t(ts: str | None) -> datetime | None:
    if not ts:
        return None
    t = re.sub(r"(\.\d{6})\d+", r"\1", str(ts).replace("Z", "+00:00"))  # numpy datetime64: nanoseconds, no zone (UTC)
    d = datetime.fromisoformat(t)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def aviso_status_at(a: dict, at: datetime) -> str:
    """Same rule as the capturer and the viewer: documented validity only."""
    if a.get("cancellation_text") or a.get("status") == "CANCELADO":
        return "CANCELADO"
    if a.get("superseded_by") or a.get("status") == "REEMPLAZADO":
        return "REEMPLAZADO"
    s, e = _t(a.get("validity_start")), _t(a.get("validity_end"))
    if not s or not e or e < s:
        return "DESCONOCIDO"
    return "FUTURO" if at < s else "VIGENTE" if at <= e else "VENCIDO"


def imerg_usable_at(imerg: dict, at: datetime) -> bool:
    end = _t(imerg.get("window_end_utc"))
    return bool(end) and at - end <= timedelta(hours=FRESHNESS["imerg_stale_after_h"])


def goes_usable_at(goes: dict, at: datetime) -> bool:
    end = _t(goes.get("scan_end_utc"))
    return goes.get("status") == "CALCULADO" and bool(end) and at - end <= timedelta(minutes=FRESHNESS["goes_stale_after_min"])


def sum_tenths(values) -> float:
    """Sum left to right and round half up to 0.1 mm with the same IEEE-754 operations the dashboard uses
    (``Math.floor(acc * 10 + 0.5) / 10`` after a plain ``reduce``). Python's ``sum()`` (compensated since 3.12) and
    ``round()`` (half-even on the binary value) could land on the other side of a .x5 boundary than the browser."""
    acc = 0.0
    for v in values:
        acc += v
    return math.floor(acc * 10 + 0.5) / 10


def geos_windows_at(geos: dict, at: datetime) -> dict:
    """Forecast sums for the next 6/24 h from ``at``. Only for a cycle no older than geos_max_cycle_age_h and only
    when every consecutive hour is in the cycle; otherwise NO_DISPONIBLE with the reason."""
    if not geos or geos.get("status") != "CALCULADO":
        return dict(status="NO_DISPONIBLE", reason=(geos or {}).get("reason") or "sin pronóstico GEOS-CF para esta zona")
    start = _t(geos.get("dataset_time_start"))
    if not start:
        return dict(status="NO_DISPONIBLE", reason="ciclo GEOS-CF sin fecha: no se puede comprobar su antigüedad")
    if at - start > timedelta(hours=FRESHNESS["geos_max_cycle_age_h"]):
        return dict(status="DESACTUALIZADO", cycle_start_utc=start.isoformat(),
                    reason=f"ciclo GEOS-CF que empieza el {start.isoformat()}: más de {FRESHNESS['geos_max_cycle_age_h']} h antes de la evaluación")
    hours = sorted(((_t(h["valid_time_utc"]), h["precip_mm"]) for h in geos.get("hourly", [])), key=lambda x: x[0])
    fut = [(t, v) for t, v in hours if t >= at]
    out = dict(status="CALCULADO", cycle_start_utc=start.isoformat(), windows={})
    for name, n in (("6h", 6), ("24h", 24)):
        seq = fut[:n]
        ok = (len(seq) == n and seq[0][0] - at < timedelta(hours=1) and all(v is not None for _, v in seq)
              and all(seq[i + 1][0] - seq[i][0] == timedelta(hours=1) for i in range(n - 1)))
        out["windows"][name] = (dict(status="CALCULADO", accum_mm=sum_tenths(v for _, v in seq), start_utc=seq[0][0].isoformat(),
                                     end_utc=seq[-1][0].isoformat()) if ok else
                                dict(status="NO_DISPONIBLE", reason=f"el ciclo no cubre {n} horas consecutivas desde la evaluación"))
    return out


def review_priority(avisos: list[dict], imerg: dict, goes: dict, percentile: dict, at: datetime) -> dict:
    """Transparent internal review priority evaluated at ``at``. Inputs are evidence; no thresholds on rain amounts.
    Stale observations count as missing, never as zero."""
    live = [dict(a, status_at=aviso_status_at(a, at)) for a in avisos if a.get("relation_method") != NEGATIVE_RELATION]
    rain_vig = [a for a in live if a["status_at"] == "VIGENTE"]
    rain_fut = [a for a in live if a["status_at"] in ("FUTURO", "DESCONOCIDO")]
    im_ok, go_ok = imerg_usable_at(imerg, at), goes_usable_at(goes, at)
    w = imerg.get("windows", {})
    w24 = w.get("24h", {})
    observed_nonzero = (im_ok and any(v.get("status") == "CALCULADO" and v.get("accum_mm", 0) > 0 for v in w.values())) or \
        (go_ok and (goes.get("rate_max_mm_h") or 0) > 0)
    complete_zero = im_ok and go_ok and w24.get("status") == "CALCULADO" and w24.get("accum_mm") == 0 and goes.get("rate_max_mm_h") == 0
    reasons, missing = [], []
    if not imerg.get("window_end_utc"):
        missing.append("IMERG Early sin muestras para esta zona")
    elif not im_ok:
        missing.append(f"IMERG Early desactualizado: la última ventana termina el {imerg['window_end_utc']} "
                       f"(más de {FRESHNESS['imerg_stale_after_h']} h antes de la evaluación); no cuenta para la prioridad")
    elif w24.get("status") != "CALCULADO":
        missing.append("IMERG 24 h incompleta")
    if goes.get("status") != "CALCULADO":
        missing.append("GOES-19 no disponible para esta zona")
    elif not go_ok:
        missing.append(f"GOES-19 desactualizado: último escaneo {goes.get('scan_end_utc')} "
                       f"(más de {FRESHNESS['goes_stale_after_min']} min antes de la evaluación); no cuenta para la prioridad")
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
        reasons.append(f"Aviso {a['aviso_key']} ({a['status_at']}; nivel oficial: {a.get('official_level') or 'no consta'}) — {a['relation_method']}")
    if observed_nonzero:
        reasons.append("Lluvia observada no nula en la última ventana completa de IMERG o en la última muestra GOES válida")
    if rain_vig and percentile.get("status") != "CALCULADO":
        reasons.append("Situación C (aviso vigente + anomalía) no evaluable: no hay percentiles interpretables")
    edges = [t for a in live for t in (_t(a.get("validity_start")), _t(a.get("validity_end")) and _t(a.get("validity_end")) + timedelta(seconds=1)) if t]
    if imerg.get("window_end_utc"):
        edges.append(_t(imerg["window_end_utc"]) + timedelta(hours=FRESHNESS["imerg_stale_after_h"], seconds=1))
    if goes.get("status") == "CALCULADO" and goes.get("scan_end_utc"):
        edges.append(_t(goes["scan_end_utc"]) + timedelta(minutes=FRESHNESS["goes_stale_after_min"], seconds=1))
    nxt = min((t for t in edges if t > at), default=None)
    p = REVIEW_PRIORITIES[RANK[code]]
    return dict(code=code, label_es=p["label_es"], rule_es=p["rule_es"], reasons_es=reasons, missing_es=missing,
                imerg_usable=im_ok, goes_usable=go_ok, data_complete=im_ok and go_ok and w24.get("status") == "CALCULADO",
                next_change_utc=nxt.astimezone(timezone.utc).isoformat() if nxt else None)


def sort_key(row: dict):
    rp = row["review_priority"]
    w = row["imerg"].get("windows", {})
    acc = w.get("24h", {}).get("accum_mm")
    six = w.get("6h", {}).get("accum_mm")
    obs = (acc if acc is not None else six) if rp.get("imerg_usable", True) else None
    # Missing or stale observations sort before observed values inside a tier: a missing signal is never 'low'.
    return (RANK[rp["code"]], 0 if obs is None else 1, -(obs or 0), row["zone_id"])


# --------------------------------------------------------------------------- build
def zone_universe(zones_cfg: dict, boundaries: dict | None) -> list[dict]:
    out = []
    for z in zones_cfg["zones"]:
        v08 = z.get("v08_source_targets") or {}
        if z["zone_type"] == "BASIN_GEOMETRY":
            out.append(dict(zone_id=z["zone_id"], display_name=z["display_name"], department=z["registered_department"],
                            zone_type=z["zone_type"], geometry_path=z["geometry_path"], v08=v08))
        else:
            dep = z["registered_department"]
            for prov in (boundaries or {}).get("provinces_by_department", {}).get(dep, []):
                out.append(dict(zone_id=f"{z['zone_id']}:{prov}", base_zone_id=z["zone_id"], display_name=f"{dep.title()} · {prov.title()}",
                                department=dep, zone_type="ADMINISTRATIVE_CONTEXT_NO_BASIN", province=prov,
                                v08=v08 if v08.get("province") == prov else {}))
    return out


def build(at: datetime) -> dict:
    zones_cfg, links = load(ZONES), load(LINKS) or {}
    latest = load(BOUNDARIES_LATEST)
    boundaries = None
    if latest:
        fc = load(ROOT / latest["path"])
        by_dep: dict[str, list[str]] = {}
        for f in fc["features"]:
            by_dep.setdefault(f["properties"]["NOMBDEP"], []).append(f["properties"]["NOMBPROV"])
        boundaries = dict(provinces_by_department={d: sorted(v) for d, v in by_dep.items()})
    north, v08, goes, geos = load(IMERG_NORTH), load(IMERG_V08), load(GOES), load(GEOS)
    goes_north, geos_north = load(GOES_NORTH), load(GEOS_NORTH)
    by_zone = {r["zone_id"]: r for r in links.get("surveillance_zones", [])}
    rows = []
    for z in zone_universe(zones_cfg, boundaries):
        avisos = list(by_zone.get(z["zone_id"], {}).get("avisos", []))
        if z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN":  # department-only links of the Piura context zone
            avisos += [dict(a, relation_method=a["relation_method"]) for a in by_zone.get(z["base_zone_id"], {}).get("avisos", [])]
        imerg = imerg_for_zone(z["zone_id"], z["v08"].get("imerg_early"), north, v08)
        goes_row = goes_for_zone(z["v08"].get("goes19_rrqpe"), goes, z["zone_id"], goes_north)
        geos_row = geos_for_zone(z["v08"].get("geos_cf"), geos, z["zone_id"], geos_north)
        percentile = dict(status="NO_DISPONIBLE", min_samples=MIN_PERCENTILE_SAMPLES,
                          reason="no homogeneous historical series of IMERG Early 24 h windows for this target yet (archive keeps 96 h)")
        rows.append(dict(zone_id=z["zone_id"], display_name=z["display_name"], department=z["department"], zone_type=z["zone_type"],
                         province=z.get("province"), avisos=avisos, imerg=imerg, goes19=goes_row, geos_cf=geos_row,
                         percentile=percentile,
                         river_level=dict(status="NO_DISPONIBLE", reason="no verified river level or discharge readings integrated for this zone "
                                                                              "(Piura Ñácara probe queries a SENAMHI host: owner decision pending)"),
                         documentary_antecedents=dict(status="NO_INTEGRADO", reason="documentary identity/event leads not yet linked to this zone"),
                         v08_source_caveat=z["v08"].get("caveat"),
                         review_priority=review_priority(avisos, imerg, goes_row, percentile, at)))
    rows.sort(key=sort_key)
    return dict(schema_version="0.1", output_id="irfen-v09-zone-rain-state:v0.1", **GUARDS, map_publishable=False,
                inputs={k: sha(p) for k, p in (("zones", ZONES), ("links", LINKS), ("imerg_north", IMERG_NORTH),
                                                ("imerg_v08", IMERG_V08), ("goes19", GOES), ("geos_cf", GEOS),
                                                ("goes19_north", GOES_NORTH), ("geos_cf_north", GEOS_NORTH))},
                links_evaluated_at_utc=links.get("evaluated_at_utc"), links_statuses_valid_until_utc=links.get("statuses_valid_until_utc"),
                aviso_source_state=links.get("source_state"),
                review_priorities=REVIEW_PRIORITIES, freshness=FRESHNESS,
                next_change_utc=min((r["review_priority"]["next_change_utc"] for r in rows if r["review_priority"]["next_change_utc"]), default=None),
                rules_es=["Ventanas solo con todas sus medias horas; si falta alguna, NO_DISPONIBLE.",
                          "IMERG Early tiene horas de latencia; la antigüedad de cada ventana se muestra siempre.",
                          f"Un dato antiguo (IMERG > {FRESHNESS['imerg_stale_after_h']} h, GOES-19 > {FRESHNESS['goes_stale_after_min']} min) se muestra con su fecha pero cuenta como ausente, nunca como «sin lluvia».",
                          f"GEOS-CF: sin sumas de 6/24 h si el ciclo tiene más de {FRESHNESS['geos_max_cycle_age_h']} h o le faltan horas consecutivas.",
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
    parser.add_argument("--at", help="evaluate at this ISO instant instead of now (replays and demos)")
    args = parser.parse_args(argv)
    committed = load(OUT)
    if args.check:
        if committed is None or not committed.get("evaluated_at_utc"):
            print("FAIL: no committed zone_rain_state to replay")
            return 1
        out = build(_t(committed["evaluated_at_utc"]))
        if not content_equal(committed, out):
            print("FAIL: zone_rain_state does not match its inputs at its evaluated_at_utc: run scripts/v09_zone_rain_engine.py")
            return 1
        print(f"OK: {len(out['zones'])} zones at {committed['evaluated_at_utc']}")
        return 0
    at = _t(args.at) if args.at else datetime.now(timezone.utc)
    out = build(at)
    if committed is None or not content_equal(committed, out):
        out["evaluated_at_utc"] = at.isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("written")
    for r in out["zones"]:
        w = r["imerg"]["windows"]
        print(f"{r['review_priority']['code']:36s} {r['display_name'][:40]:40s} imerg={r['imerg']['source']} "
              + " ".join(f"{k}={w[k].get('accum_mm', w[k]['status'])}" for k in WINDOWS) + f" goes={r['goes19'].get('rate_mean_mm_h', r['goes19']['status'])}"
              + ("" if r["review_priority"]["imerg_usable"] else " [IMERG antiguo]") + ("" if r["review_priority"]["goes_usable"] else " [GOES no usable]"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
