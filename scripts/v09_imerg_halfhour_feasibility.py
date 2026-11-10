#!/usr/bin/env python3
"""IRFEN v0.9 · viabilidad de IMERG V07 cada 30 min para el estudio de anticipación. RESEARCH_ONLY / TEST_ONLY.

Usa solo lo capturado por `v09_anticipation_capture.py` (recuento CMR y piloto de un día, 2017-03-26) y el diario
Final ya archivado. Produce:
* cobertura (gránulos encontrados frente a medias horas esperadas) por producto y ventana;
* coste de reproducibilidad extrapolado a partir de bytes y segundos MEDIDOS en el piloto;
* coherencia interna: Σ(HH Final × 0,5 h) frente al diario Final del mismo día UTC, celda a celda;
* Early frente a Final ese día, en las cuencas VALIDADA_EXPERIMENTAL (media areal ponderada por fracción de celda).
No compara con caudales (no hay caudal subdiario). Ningún valor es umbral.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CMR = ROOT / "data/v09/research/anticipation/capture_imerg_cmr_v0_1.json"
PILOT = ROOT / "data/v09/research/anticipation/capture_imerg_pilot_v0_1.json"
DAILY = ROOT / "data/v09/research/historical/imerg_final_daily_piura_chira_v0_1.json"
CATCH = ROOT / "data/v09/research/anticipation/north_catchments_v0_1.json"
OUT = ROOT / "data/v09/research/anticipation/imerg_halfhour_feasibility_v0_1.json"


def grid(slot) -> dict:
    return {(round(lo, 2), round(la, 2)): v for i, lo in enumerate(slot["lon"]) for j, la in enumerate(slot["lat"])
            for v in [slot["values_lon_by_lat"][i][j]]}


def areal(cells: list, g: dict):
    num = den = 0.0
    for c in cells:
        v = g.get((round(c["lon_center"], 2), round(c["lat_center"], 2)))
        if v is None:
            return None  # a missing cell makes the areal value unknown (never 0)
        num += c["fraction_inside"] * v
        den += c["fraction_inside"]
    return num / den if den else None


def build() -> dict:
    cmr = json.loads(CMR.read_text(encoding="utf-8"))["result"]
    pil = json.loads(PILOT.read_text(encoding="utf-8"))["result"]
    daily = json.loads(DAILY.read_text(encoding="utf-8"))
    catch = json.loads(CATCH.read_text(encoding="utf-8"))
    day = pil["day"]
    cover = {p: {w: dict(granules=v.get("granules"), expected=v.get("expected_half_hours"),
                         complete=v.get("granules") == v.get("expected_half_hours"), first=v.get("first"), last=v.get("last"))
                 for w, v in d.items()} for p, d in cmr["products"].items()}
    cost, sums, hourly = {}, {}, {}
    for prod, rec in pil["products"].items():
        slots = rec["slots"]
        nbytes = [s["file_bytes"] for s in slots.values()]
        per_gran_mb = float(np.mean(nbytes)) / 1e6
        per_gran_s = rec["download_seconds"] / max(1, rec["granules_found"])
        windows = {w: dict(granules=v["granules"], transfer_gb=round(v["granules"] * per_gran_mb / 1000, 1),
                           download_minutes_at_pilot_rate=round(v["granules"] * per_gran_s / 60, 1),
                           stored_box_values=v["granules"] * len(next(iter(slots.values()))["lon"]) * len(next(iter(slots.values()))["lat"]))
                   for w, v in cmr["products"].get(prod, {}).items() if v.get("granules")}
        cost[prod] = dict(pilot_granules=rec["granules_found"], pilot_slots_read=rec["slots_read"],
                          mean_granule_mb=round(per_gran_mb, 2), pilot_download_s=rec["download_seconds"],
                          seconds_per_granule=round(per_gran_s, 3), windows=windows,
                          note="Gránulo global completo (HDF5); se descarga entero y se conserva solo el recuadro. Tasa medida en un runner de GitHub")
        g_sum: dict = {}
        for s in slots.values():
            for k, v in grid(s).items():
                if v is None:
                    g_sum[k] = None
                elif k not in g_sum or g_sum[k] is not None:
                    g_sum[k] = (g_sum.get(k) or 0.0) + v * 0.5
        sums[prod] = g_sum
        series = {}
        for c in catch["catchments"]:
            if not str(c.get("status", "")).startswith("VALIDADA_EXPERIMENTAL"):
                continue
            vals = [areal(c["imerg_cells"], grid(slots[k])) for k in sorted(slots)]
            series[c["id"]] = dict(mm_per_half_hour=[None if v is None else round(v * 0.5, 3) for v in vals],
                                   total_mm=None if any(v is None for v in vals) else round(sum(v * 0.5 for v in vals), 2),
                                   max_half_hour_mm=None if any(v is None for v in vals) else round(max(vals) * 0.5, 2),
                                   slot_of_max_utc=None if any(v is None for v in vals) else sorted(slots)[int(np.argmax(vals))])
        hourly[prod] = series
    d = daily["days"].get(day)
    consistency = None
    if d:
        gd = grid(d)
        pairs = [(gd[k], sums["GPM_3IMERGHH"].get(k)) for k in gd if gd[k] is not None and sums["GPM_3IMERGHH"].get(k) is not None]
        diffs = np.array([a - b for a, b in pairs])
        consistency = dict(cells_compared=len(pairs), max_abs_diff_mm=round(float(np.abs(diffs).max()), 3),
                           mean_abs_diff_mm=round(float(np.abs(diffs).mean()), 3), daily_mean_mm=round(float(np.mean([a for a, _ in pairs])), 2),
                           daily_granule=d["granule"],
                           verdict="COHERENTE" if float(np.abs(diffs).max()) <= 0.5 else "DIFERENCIAS_A_REVISAR",
                           rule="El diario Final V07 es la suma de las 48 medias horas Final del mismo día UTC; tolerancia 0,5 mm por redondeo.")
    ef = {}
    for cid, s in hourly.get("GPM_3IMERGHHE", {}).items():
        f = hourly["GPM_3IMERGHH"].get(cid, {})
        ef[cid] = dict(early_total_mm=s["total_mm"], final_total_mm=f.get("total_mm"),
                       early_peak_slot=s["slot_of_max_utc"], final_peak_slot=f.get("slot_of_max_utc"))
    return dict(schema_version="irfen_v09_imerg_halfhour_feasibility_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, decision_thresholds=None, missing_data_rule="UNKNOWN_NOT_LOW_RISK",
                pilot_day_utc=day, coverage=cover, reproducibility_cost=cost, daily_consistency=consistency,
                early_vs_final_pilot_day=ef, catchment_half_hourly=hourly,
                role_in_protocol=dict(GPM_3IMERGHHE="Predictor admisible (latencia 4 h; V07 reprocesado, no idéntico al publicado en 2017)",
                                      GPM_3IMERGHHL="Predictor admisible con latencia 14 h",
                                      GPM_3IMERGHH="ORACULO_NO_OPERATIVO: solo cota superior; prohibido como predictor"),
                comparison_with_flow="NO_REALIZADA: no hay caudal ni nivel subdiario archivado (protocolo v0.3 §3)")


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
    print(json.dumps(dict(cost=d["reproducibility_cost"], consistency=d["daily_consistency"], ef=d["early_vs_final_pilot_day"]),
                     ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
