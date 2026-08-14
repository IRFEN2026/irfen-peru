#!/usr/bin/env python3
"""Construye la descomposición científica de Lima Este para IRFEN v0.8.

No cambia la zona operativa v0.7.1. Mantiene separados:
1) Huaycoloro como sistema de cuenca/cauce principal.
2) Las quebradas locales de Chosica como flujos de respuesta corta.

Pedregal se usa únicamente como microcuenca local representativa porque ya
cuenta con control espacial ANA de su boca y consistencia interna DEM. Su
señal IMERG subdiaria de 2015 sigue siendo insuficiente para calibrar una
regla de alerta y por eso no habilita producción ni justifica bajar umbrales.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "data" / "hazard_models" / "lima_east_decomposition.json"


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def replay_case(replay, event_id):
    return next((c for c in (replay or {}).get("cases", []) if c.get("event_id") == event_id), None)


def compact_replay(case):
    if not case:
        return None
    legacy = case.get("legacy_sampling_replay") or {}
    poly = case.get("polygon_sampling_replay") or {}
    return {
        "event_id": case.get("event_id"),
        "date": case.get("date"),
        "event": case.get("event"),
        "legacy_threat_score": legacy.get("threat_score"),
        "legacy_threat_class": legacy.get("threat_class"),
        "polygon_threat_score": poly.get("threat_score") if poly else None,
        "polygon_threat_class": poly.get("threat_class") if poly else None,
        "diagnostic": case.get("diagnostic"),
    }


def main():
    replay = load(SITE / "data" / "calibration" / "historical_replay.json", {}) or {}
    ped = load(SITE / "data" / "calibration" / "pedregal_ana_validation.json", {}) or {}
    ped_hh = load(SITE / "data" / "calibration" / "pedregal_2015_imerg_halfhour.json", {}) or {}

    huay = compact_replay(replay_case(replay, "HU-2017-03-15"))
    chos = compact_replay(replay_case(replay, "CH-2015-03-23"))

    ped_gates = ped.get("gates") or {}
    ped_dem = ped.get("dem_candidate") or {}
    ped_metrics = ped_hh.get("metrics") or {}
    ped_geometry_ok = (
        ped.get("status") == "ANA_CONTROLLED_CANDIDATE"
        and ped_gates.get("ana_outlet_spatial_control") == "PASS"
        and ped_gates.get("dem_internal_area_consistency") == "PASS"
    )
    ped_history_available = ped_hh.get("production_use") is False and ped_metrics.get("max_24h") is not None

    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "legacy_operational_zone_id": "chosica",
        "legacy_zone_name": "Chosica / Huaycoloro",
        "status": "SUBMODEL_SPLIT_ACTIVE_EXPERIMENTAL",
        "reason": "La zona heredada agrupa dos mecanismos espacial e hidrológicamente distintos: desborde/conducción del sistema Huaycoloro y flujos de detritos de quebradas locales de Chosica hacia el río Rímac.",
        "evidence": {
            "official_2015_event_source": {
                "source": "INGEMMET / SIGRID-CENEPRED",
                "url": "https://sigrid4.cenepred.gob.pe/sigridv4/documento/3642",
                "finding": "El evento 23/03/2015 se documenta en quebradas locales de Lurigancho-Chosica, por lo que no debe calibrarse únicamente con la cuenca completa de Huaycoloro.",
            },
            "historical_replay": {
                "huaycoloro_2017": huay,
                "chosica_local_2015": chos,
                "interpretation": "Huaycoloro 2017 y Chosica local 2015 muestran respuestas muy distintas con el agregado espacial heredado; la separación de mecanismos es necesaria antes de calibrar.",
            },
        },
        "submodels": [
            {
                "id": "huaycoloro_main_channel",
                "name": "Huaycoloro · sistema de cuenca y cauce principal",
                "hazard_type": "basin_runoff_channel_overflow_and_conveyance",
                "geometry_status": "validated_dem_candidate",
                "geometry": "data/watersheds/huaycoloro_watershed.geojson",
                "reference_event": "HU-2017-03-15",
                "reference_event_replay": huay,
                "core_signals": [
                    "basin_rain24",
                    "basin_rain72",
                    "basin_rain7d",
                    "forecast24",
                    "channel_hydraulic_state",
                ],
                "infrastructure_context": "Canalización de 10.5 km y obras asociadas operativas desde 2025.",
                "scientific_gate": "HYDRAULIC_CALIBRATION_REQUIRED",
                "production_use": False,
            },
            {
                "id": "chosica_local_debris_flows",
                "name": "Chosica · quebradas locales de flujo de detritos",
                "hazard_type": "short_response_local_debris_flow",
                "geometry_status": "REPRESENTATIVE_PEDREGAL_ANA_CONTROLLED_CANDIDATE" if ped_geometry_ok else "REPRESENTATIVE_CATCHMENT_GEOMETRY_INCOMPLETE",
                "representative_catchment": {
                    "name": "Pedregal / San Antonio de Pedregal",
                    "candidate_id": ped.get("candidate_id"),
                    "geometry": "data/watersheds/pedregal_candidate.geojson",
                    "validation_status": ped.get("status"),
                    "delineated_area_km2": ped_dem.get("delineated_area_km2"),
                    "distance_to_ana_mouth_cross_section_m": ped_dem.get("distance_to_ana_mouth_cross_section_m"),
                    "ana_outlet_spatial_control": ped_gates.get("ana_outlet_spatial_control"),
                    "dem_internal_area_consistency": ped_gates.get("dem_internal_area_consistency"),
                    "production_use": False,
                },
                "priority_quebradas_after_representative_model": ["Quirio", "Rayos de Sol"],
                "reference_event": "CH-2015-03-23",
                "reference_event_replay": chos,
                "historical_subdaily_signal": {
                    "available": ped_history_available,
                    "source": (ped_hh.get("source") or {}).get("product"),
                    "peak_rate_mm_hr": ped_metrics.get("peak_rate_mm_hr"),
                    "max_1h_mm": (ped_metrics.get("max_1h") or {}).get("mm"),
                    "max_3h_mm": (ped_metrics.get("max_3h") or {}).get("mm"),
                    "max_6h_mm": (ped_metrics.get("max_6h") or {}).get("mm"),
                    "max_24h_mm": (ped_metrics.get("max_24h") or {}).get("mm"),
                    "interpretation": "IMERG 0.1°/30 min aporta señal subdiaria, pero el evento severo de 2015 sigue sin quedar explicado con suficiente fuerza para derivar umbrales locales.",
                    "production_use": False,
                },
                "core_signals_candidate": [
                    "local_catchment_rainfall",
                    "short_duration_rainfall_intensity",
                    "antecedent_wetness",
                    "debris_sediment_condition",
                    "forecast_convective_rainfall",
                ],
                "known_model_mismatch": "El agregado Huaycoloro/zona heredada deja el evento local severo del 23/03/2015 demasiado bajo; no se deben bajar umbrales para forzar su detección.",
                "next_steps": [
                    "resolver una señal local terrestre o de mayor fidelidad para Pedregal",
                    "construir controles lluviosos sin impacto para evaluar falsas alarmas",
                    "calibrar primero el submodelo representativo de Pedregal",
                    "solo después extender la geometría local a Quirio y Rayos de Sol si sigue siendo necesario para el objetivo v0.8",
                ],
                "scientific_gate": "LOCAL_GROUND_OR_HIGHER_FIDELITY_RAINFALL_AND_NON_EVENT_CALIBRATION_REQUIRED",
                "production_use": False,
            },
        ],
        "operational_rule": "No change to v0.7.1 zone or alert calculation. Decomposition is scientific-only until validated and explicitly promoted.",
        "scope_rule": "No ampliar a Lurín, Cieneguilla ni nuevas quebradas hasta cerrar los tres pilotos del objetivo v0.8.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "huaycoloro_replay_available": huay is not None,
        "chosica_replay_available": chos is not None,
        "pedregal_geometry_ok": ped_geometry_ok,
        "pedregal_subdaily_history_available": ped_history_available,
        "scientific_gate": report["submodels"][1]["scientific_gate"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
