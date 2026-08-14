#!/usr/bin/env python3
"""Construye una regla candidata TEST_ONLY para San Ildefonso.

Usa exclusivamente los casos subdiarios ya documentados en
san_ildefonso_imerg_halfhour_events.json. El objetivo es medir separación
histórica, NO calibrar un umbral de producción. El control 2025 pertenece a una
fase de infraestructura distinta; por ello una separación perfecta sigue sin
ser evidencia suficiente para producción.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site/data/calibration/san_ildefonso_imerg_halfhour_events.json"
OUT = ROOT / "site/data/calibration/san_ildefonso_test_rule.json"
WINDOWS = ("max_3h", "max_6h", "max_24h")


def metric(case, key):
    block = case.get(key) or {}
    value = block.get("mm")
    return None if value is None else float(value)


def midpoint(control_value, impact_floor):
    return round((float(control_value) + float(impact_floor)) / 2.0, 3)


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    impacts = [c for c in cases if c.get("outcome") == "urban_debris_flow_impact"]
    controls = [c for c in cases if c.get("outcome") != "urban_debris_flow_impact"]

    if len(impacts) < 2 or not controls:
        raise RuntimeError("Se requieren al menos 2 impactos y 1 control para esta prueba")

    # Para esta primera evaluación usamos el control documentado más reciente.
    control = sorted(controls, key=lambda c: c.get("date") or "")[-1]
    thresholds = {}
    separation = {}
    for key in WINDOWS:
        impact_values = [metric(c, key) for c in impacts]
        impact_values = [v for v in impact_values if v is not None]
        control_value = metric(control, key)
        if len(impact_values) != len(impacts) or control_value is None:
            raise RuntimeError(f"Métrica incompleta: {key}")
        impact_floor = min(impact_values)
        candidate = midpoint(control_value, impact_floor)
        thresholds[key] = candidate
        separation[key] = {
            "control_mm": round(control_value, 3),
            "minimum_impact_mm": round(impact_floor, 3),
            "candidate_midpoint_mm": candidate,
            "absolute_gap_mm": round(impact_floor - control_value, 3),
            "control_to_impact_floor_ratio": round(control_value / impact_floor, 3) if impact_floor else None,
        }

    evaluations = []
    for case in cases:
        checks = {}
        for key in WINDOWS:
            value = metric(case, key)
            checks[key] = {
                "value_mm": value,
                "candidate_mm": thresholds[key],
                "crossed": bool(value is not None and value >= thresholds[key]),
            }
        crossed = sum(1 for x in checks.values() if x["crossed"])
        test_trigger = crossed >= 2
        evaluations.append({
            "case_id": case.get("id"),
            "date": case.get("date"),
            "outcome": case.get("outcome"),
            "infrastructure_phase": case.get("infrastructure_phase"),
            "checks": checks,
            "crossed_count": crossed,
            "test_rule_triggered": test_trigger,
            "expected_for_separation_test": case.get("outcome") == "urban_debris_flow_impact",
            "separation_match": test_trigger == (case.get("outcome") == "urban_debris_flow_impact"),
        })

    all_match = all(x["separation_match"] for x in evaluations)
    result = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "zone_id": "san_ildefonso",
        "production_use": False,
        "production_ready": False,
        "status": "HISTORICAL_SEPARATION_DEMONSTRATED_TEST_ONLY" if all_match else "INSUFFICIENT_HISTORICAL_SEPARATION",
        "source": "data/calibration/san_ildefonso_imerg_halfhour_events.json",
        "candidate_test_rule": {
            "mode": "TEST_ONLY",
            "logic": "trigger if at least 2 of 3 windows cross their candidate midpoint",
            "windows": {
                "3h_mm": thresholds["max_3h"],
                "6h_mm": thresholds["max_6h"],
                "24h_mm": thresholds["max_24h"],
            },
            "minimum_crossings": 2,
            "thresholds_modified_in_production": False,
            "operational_alert": False,
        },
        "separation_evidence": separation,
        "case_evaluations": evaluations,
        "confounders": [
            "The 2025 control occurred after substantial protective works, while the 2017 and 2023 impact cases are from earlier infrastructure phases.",
            "IMERG 0.1 degree averages only a small number of satellite grid cells over the 28.34 km2 catchment.",
            "Three cases are insufficient to estimate false-alarm rate, sensitivity or seasonal robustness.",
        ],
        "decision_gate": {
            "status": "MORE_CONTROLS_AND_CURRENT_INFRASTRUCTURE_EVENTS_REQUIRED",
            "can_use_for_historical_replay": True,
            "can_use_for_live_test_if_same_subdaily_signal_available": True,
            "can_use_for_production": False,
            "required_before_production": [
                "additional rainy non-impact controls",
                "events observed with the 2026 infrastructure configuration",
                "hydraulic state/capacity and overflow behaviour",
                "validation of live subdaily rainfall latency and continuity",
                "false-alarm and missed-event evaluation",
            ],
        },
        "interpretation": "The candidate rule is a discriminant test, not a calibrated hazard threshold. A successful historical split is useful evidence but does not authorize production promotion.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "candidate_test_rule": result["candidate_test_rule"],
        "evaluations": [
            {"case_id": x["case_id"], "triggered": x["test_rule_triggered"], "match": x["separation_match"]}
            for x in evaluations
        ],
        "production_ready": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
