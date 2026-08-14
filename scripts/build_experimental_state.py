#!/usr/bin/env python3
"""Construye el estado experimental de decisión para IRFEN v0.8.

Este archivo implementa el contrato de PRUEBAS del núcleo v0.8. No genera
alertas operativas, no modifica umbrales y no altera la lógica v0.7.1.
Mantiene observación, forecast, estado fluvial y puertas hidráulicas como
señales trazables separadas y emite únicamente recomendaciones TEST_*.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = SITE / "data" / "experimental_state.json"


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def ratio(value, threshold):
    if value is None or threshold in (None, 0):
        return None
    return round(float(value) / float(threshold), 4)


def available_numbers(values):
    return [float(v) for v in values if v is not None]


def zone_observation(zone):
    exp = zone.get("experimental_polygon")
    if exp and exp.get("production_use") is False and zone.get("id") in {"san_ildefonso", "chosica"}:
        return {
            "method": "validated_dem_polygon_parallel",
            "rain24": exp.get("rain24"),
            "rain72": exp.get("rain72"),
            "rain7d": exp.get("rain7d"),
            "source_status": exp.get("status"),
            "production_use": False,
        }
    return {
        "method": "operational_sampling_geometry_reference",
        "rain24": zone.get("rain24"),
        "rain72": zone.get("rain72"),
        "rain7d": zone.get("rain7d"),
        "source_status": "operational_reference_only",
        "production_use": False,
    }


def test_recommendation(zid, observed_ratios, forecast_ratios, river_state):
    obs_values = available_numbers(observed_ratios.values())
    fc_values = available_numbers(forecast_ratios.values())
    max_obs = max(obs_values) if obs_values else None
    max_fc = max(fc_values) if fc_values else None

    river_class = (river_state or {}).get("proxy_class")
    river_fc = (river_state or {}).get("forecast_signal") or {}
    river_forecast = any(bool(v) for v in river_fc.values())

    reasons = []
    if max_obs is not None:
        reasons.append(f"máximo observado = {max_obs:.2f}× umbral provisional")
    if max_fc is not None:
        reasons.append(f"máximo forecast = {max_fc:.2f}× umbral provisional")
    if river_class:
        reasons.append(f"proxy fluvial = {river_class}")

    # El orden prioriza evidencia observada y señal fluvial actual; forecast es
    # anticipatorio. Todo sigue siendo TEST_ONLY.
    if zid == "catacaos" and river_class in {"MODELLED_20Y_EXCEEDANCE", "MODELLED_5Y_EXCEEDANCE"}:
        code = "TEST_RIVER_MODEL_SIGNAL"
        action = "Revisar de inmediato el estado del río Piura, los tramos críticos ANA y la lluvia observada/pronosticada; escalar solo la revisión simulada."
    elif max_obs is not None and max_obs >= 1.35:
        code = "TEST_STRONG_OBSERVED_SIGNAL"
        action = "Verificar consistencia de datos, exposición e infraestructura y preparar escalamiento simulado; no emitir alerta operativa."
    elif max_obs is not None and max_obs >= 1.0:
        code = "TEST_OBSERVED_THRESHOLD_CROSSING"
        action = "Revisar la zona y las fuentes independientes; mantener seguimiento reforzado en modo de prueba."
    elif (max_fc is not None and max_fc >= 1.0) or river_forecast:
        code = "TEST_FORECAST_REVIEW"
        action = "Aumentar la frecuencia de revisión de observaciones y contexto durante el horizonte pronosticado; simulación únicamente."
    elif max([v for v in [max_obs, max_fc] if v is not None], default=0.0) >= 0.70:
        code = "TEST_WATCH"
        action = "Mantener vigilancia de prueba y comprobar tendencia de acumulados y forecast; sin escalamiento operativo."
    else:
        code = "TEST_NO_TRIGGER"
        action = "Continuar monitoreo normal y registrar el caso para validación; no hay señal de prueba que justifique escalamiento."

    return {
        "code": code,
        "mode": "TEST_ONLY",
        "operational_alert": False,
        "action": action,
        "reason": "; ".join(reasons) if reasons else "sin señales numéricas suficientes",
        "thresholds_modified": False,
        "hydraulic_modifier_applied": False,
    }


def main():
    latest = load(SITE / "data" / "latest.json", {"zones": []}) or {"zones": []}
    forecast = load(SITE / "data" / "forecast" / "latest.json", {"zones": []}) or {"zones": []}
    hydraulics = load(SITE / "data" / "hydraulics" / "current_infrastructure.json", {"zones": []}) or {"zones": []}
    piura = load(SITE / "data" / "hydrology" / "piura_source_status.json", {}) or {}
    glofas = load(SITE / "data" / "hydrology" / "glofas_catacaos_current.json", {}) or {}
    pedregal_validation = load(SITE / "data" / "calibration" / "pedregal_ana_validation.json", {}) or {}
    pedregal_halfhour = load(SITE / "data" / "calibration" / "pedregal_2015_imerg_halfhour.json", {}) or {}
    pedregal_ground = load(SITE / "data" / "calibration" / "pedregal_ground_evidence_2015.json", {}) or {}
    isaac = load(SITE / "data" / "stations" / "isaac_access_probe.json", {}) or {}
    lima_decomp = load(SITE / "data" / "hazard_models" / "lima_east_decomposition.json", {}) or {}

    forecast_by = {z.get("zone_id"): z for z in forecast.get("zones", [])}
    hydraulic_by = {z.get("zone_id"): z for z in hydraulics.get("zones", [])}

    output = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "production_ready": False,
        "objective_reference": "config/v08_objective.json",
        "purpose": "Contrato integrado para pruebas end-to-end; nunca equivale a una alerta operativa.",
        "rules": {
            "no_composite_risk_score": True,
            "no_hydraulic_attenuation_without_calibration": True,
            "no_automatic_threshold_promotion": True,
            "test_recommendations_must_start_with_TEST": True,
            "catacaos_requires_river_state": True,
            "catacaos_primary_river_authority": "SENAMHI/PHISIS",
            "catacaos_secondary_proxy_allowed_only_for_tests": True,
            "threshold_crossings_are_test_signals_only": True,
            "manual_external_verification_never_becomes_automatic_alert": True,
        },
        "zones": [],
    }

    for zone in latest.get("zones", []):
        zid = zone.get("id")
        thresholds = zone.get("thresholds_provisional") or {}
        obs = zone_observation(zone)
        fc = forecast_by.get(zid, {})
        hyd = hydraulic_by.get(zid, {})

        observed_ratios = {k: ratio(obs.get(k), thresholds.get(k)) for k in ("rain24", "rain72", "rain7d")}
        forecast_ratios = {
            "forecast24": ratio(fc.get("forecast24_mm"), thresholds.get("rain24")),
            "forecast72": ratio(fc.get("forecast72_mm"), thresholds.get("rain72")),
        }
        observed_crossings = [k for k, v in observed_ratios.items() if v is not None and v >= 1]
        forecast_crossings = [k for k, v in forecast_ratios.items() if v is not None and v >= 1]
        gate = (hyd.get("scientific_gate") or {}).get("status")
        modifier = hyd.get("production_modifier")

        obs_available = all(obs.get(k) is not None for k in ("rain24", "rain72", "rain7d"))
        forecast_available = (
            forecast.get("status") == "experimental_forecast_available"
            and fc.get("forecast24_mm") is not None
        )
        river_state = None

        if zid == "catacaos":
            sen = piura.get("senamhi") or {}
            numeric = bool(sen.get("numeric_river_state_available"))
            proxy_ok = bool(glofas.get("usable_for_experimental_decision")) and glofas.get("status") == "available"
            if numeric:
                river_state = {
                    "available": True,
                    "role": "primary_official_numeric",
                    "source": "SENAMHI/PHISIS",
                    "value": sen.get("current_value"),
                    "unit": sen.get("unit"),
                    "proxy_class": None,
                    "production_use": False,
                }
                readiness = "END_TO_END_TESTABLE_PRIMARY_RIVER_STATE"
                blockers = []
            elif proxy_ok:
                river_state = {
                    "available": True,
                    "role": "secondary_modelled_categorical_proxy",
                    "source": glofas.get("source"),
                    "value": None,
                    "unit": None,
                    "proxy_class": glofas.get("river_proxy_class"),
                    "forecast_signal": glofas.get("forecast_signal"),
                    "generated_at": glofas.get("generated_at"),
                    "interpretation": glofas.get("interpretation"),
                    "production_use": False,
                }
                readiness = "END_TO_END_TESTABLE_SECONDARY_RIVER_PROXY"
                blockers = ["senamhi_numeric_river_state_preferred_when_available"]
            else:
                river_state = {
                    "available": False,
                    "role": "none",
                    "source": None,
                    "value": None,
                    "unit": None,
                    "proxy_class": None,
                    "production_use": False,
                }
                readiness = "METEO_TESTABLE_RIVER_GATE_BLOCKED"
                blockers = ["official_river_state_or_validated_secondary_proxy_required"]
            blockers.append("floodplain_and_current_channel_capacity_validation_required")
            river_available = river_state["available"]
            test_ready = bool(obs_available and forecast_available and river_available)
            if not obs_available:
                blockers.append("observed_rainfall_unavailable")
            if not forecast_available:
                blockers.append("forecast_unavailable")
        else:
            river_available = None
            polygon_ready = obs.get("method") == "validated_dem_polygon_parallel"
            test_ready = bool(obs_available and forecast_available and polygon_ready)
            readiness = "END_TO_END_METEO_TESTABLE_HYDRAULIC_GATE_OPEN_FOR_TESTS" if test_ready else "METEO_TEST_INPUTS_INCOMPLETE"
            blockers = ["hydraulic_calibration_required"] if gate else []
            if not polygon_ready:
                blockers.append("validated_polygon_observation_required")
            if not obs_available:
                blockers.append("observed_rainfall_unavailable")
            if not forecast_available:
                blockers.append("forecast_unavailable")

        recommendation = test_recommendation(zid, observed_ratios, forecast_ratios, river_state)
        output["zones"].append({
            "zone_id": zid,
            "name": zone.get("name"),
            "production_use": False,
            "test_ready": test_ready,
            "observation": obs,
            "thresholds_provisional": thresholds,
            "observed_threshold_ratios": observed_ratios,
            "observed_threshold_crossings": observed_crossings,
            "forecast": {
                "status": forecast.get("status"),
                "sampling_method": fc.get("sampling_method"),
                "forecast24_mm": fc.get("forecast24_mm"),
                "forecast72_mm": fc.get("forecast72_mm"),
                "available_future_hours": fc.get("available_future_hours"),
                "threshold_ratios": forecast_ratios,
                "threshold_crossings": forecast_crossings,
                "production_use": False,
            },
            "hydraulic_gate": {
                "status": gate,
                "production_modifier": modifier,
                "system_status": hyd.get("system_status"),
            },
            "river_state_available": river_available,
            "river_state": river_state,
            "readiness": readiness,
            "blockers": list(dict.fromkeys(blockers)),
            "test_recommendation": recommendation,
            "interpretation": "Recomendación TEST_ONLY: orienta una prueba funcional y nunca sustituye una alerta oficial u operativa.",
        })

    # Lima Este se conserva como dos mecanismos. Pedregal es el representante
    # local que ya tiene control ANA de boca. ISAAC aporta una estación oficial
    # local para verificación humana en sombra, pero no expone una interfaz de
    # datos documentada que IRFEN pueda consumir con garantías.
    pedregal_geometry_ok = (
        pedregal_validation.get("status") == "ANA_CONTROLLED_CANDIDATE"
        and (pedregal_validation.get("gates") or {}).get("ana_outlet_spatial_control") == "PASS"
        and (pedregal_validation.get("gates") or {}).get("dem_internal_area_consistency") == "PASS"
    )
    pedregal_history_ok = (
        pedregal_halfhour.get("production_use") is False
        and (pedregal_halfhour.get("metrics") or {}).get("max_24h") is not None
    )
    pedregal_ground_ok = (
        pedregal_ground.get("status") == "GROUND_EVENT_DAY_CONTROL_AVAILABLE_DIAGNOSTIC_ONLY"
        and (pedregal_ground.get("decision_gate") or {}).get("automatic_bias_correction_allowed") is False
    )
    isaac_manual_available = (
        isaac.get("production_use") is False
        and (isaac.get("official_context") or {}).get("target_station_named_by_senamhi") == "Pedregal Koica"
        and isaac.get("status") in {
            "PUBLIC_PLATFORM_REACHED_NO_OBVIOUS_STRUCTURED_CHANNEL",
            "STRUCTURED_CHANNEL_CANDIDATE_FOUND",
        }
    )
    huay_zone = next((z for z in output["zones"] if z.get("zone_id") == "chosica"), {})
    output["lima_east_submodels"] = {
        "production_use": False,
        "legacy_zone_id": "chosica",
        "decomposition_status": lima_decomp.get("status", "HAZARD_DECOMPOSITION_REQUIRED"),
        "huaycoloro_main_channel": {
            "status": "END_TO_END_METEO_TESTABLE" if huay_zone.get("test_ready") else "TEST_INPUTS_INCOMPLETE",
            "test_ready": bool(huay_zone.get("test_ready")),
            "hydraulic_gate": "HYDRAULIC_CALIBRATION_REQUIRED",
            "production_use": False,
        },
        "chosica_local_debris_flows": {
            "representative_catchment": "Pedregal",
            "status": "SHADOW_TEST_WITH_MANUAL_OFFICIAL_VERIFICATION" if pedregal_geometry_ok and pedregal_history_ok and pedregal_ground_ok and isaac_manual_available else ("HISTORICAL_TEST_ONLY" if pedregal_geometry_ok and pedregal_history_ok else "GEOMETRY_OR_HISTORY_INCOMPLETE"),
            "geometry_control": pedregal_validation.get("status"),
            "geometry_area_km2": (pedregal_validation.get("dem_candidate") or {}).get("delineated_area_km2"),
            "outlet_distance_to_ana_m": (pedregal_validation.get("dem_candidate") or {}).get("distance_to_ana_mouth_cross_section_m"),
            "historical_halfhour_imerg_available": pedregal_history_ok,
            "ground_event_control_available": pedregal_ground_ok,
            "live_test_ready": False,
            "shadow_test_ready_with_manual_official_verification": bool(isaac_manual_available and pedregal_geometry_ok and pedregal_history_ok and pedregal_ground_ok),
            "blocking_requirement": "LIVE_LOCAL_OR_GROUND_RAINFALL_SIGNAL_REQUIRED",
            "official_manual_verification": {
                "available": isaac_manual_available,
                "source": "SENAMHI ISAAC",
                "station": (isaac.get("official_context") or {}).get("target_station_named_by_senamhi"),
                "platform_url": ((isaac.get("attempts") or [{}])[0]).get("final_url") if isaac.get("attempts") else None,
                "regular_update_times_local": (isaac.get("official_context") or {}).get("regular_update_times_local"),
                "event_update_frequency": (isaac.get("official_context") or {}).get("event_update_frequency"),
                "machine_readable_channel": bool(isaac.get("usable_structured_candidates")),
                "role": "external_manual_shadow_verification_only",
                "production_use": False,
            },
            "reason": "IMERG 0.1°/30 min subcaptó el evento local severo de 23/03/2015 frente al control terrestre de Chosica. ISAAC dispone de estación Pedregal Koica, pero sin interfaz de datos documentada; se usará como verificación oficial manual durante pruebas en sombra. No se bajarán umbrales ni se aplicará un factor de corrección automático.",
            "production_use": False,
        },
        "other_local_catchments": {
            "status": "DEFER_UNTIL_PEDREGAL_LOCAL_SIGNAL_RESOLVED",
            "names": ["Quirio", "Rayos de Sol"],
            "production_use": False,
        },
    }

    testable = [z.get("zone_id") for z in output["zones"] if z.get("test_ready")]
    missing = [z.get("zone_id") for z in output["zones"] if not z.get("test_ready")]
    all_three = set(testable) == {"san_ildefonso", "chosica", "catacaos"}
    local_shadow = output["lima_east_submodels"]["chosica_local_debris_flows"].get("shadow_test_ready_with_manual_official_verification") is True
    output["core_test_status"] = {
        "code": "END_TO_END_TEST_MODE_AVAILABLE_WITH_KNOWN_LIMITATIONS" if all_three else "END_TO_END_TEST_MODE_PARTIAL",
        "production_ready": False,
        "testable_pilot_lanes": testable,
        "incomplete_pilot_lanes": missing,
        "local_chosica_status": output["lima_east_submodels"]["chosica_local_debris_flows"]["status"],
        "local_chosica_shadow_manual_verification_available": local_shadow,
        "statement": (
            "Los tres carriles principales pueden ejecutarse en modo de prueba con señales reales/experimentales y trazabilidad. Pedregal puede añadirse a pruebas en sombra mediante verificación manual oficial ISAAC; sigue bloqueado para decisión automática."
            if all_three and local_shadow else
            "El motor de pruebas funciona, pero al menos un piloto o submodelo local aún carece de una señal necesaria para una prueba end-to-end."
        ),
        "stop_rule": "No ampliar a nuevas cuencas hasta cerrar calibración, controles sin impacto y puertas de los tres pilotos.",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "core_test_status": output["core_test_status"],
        "zone_recommendations": [
            {"zone_id": z["zone_id"], "test_ready": z["test_ready"], "recommendation": z["test_recommendation"]["code"]}
            for z in output["zones"]
        ],
        "pedregal": output["lima_east_submodels"]["chosica_local_debris_flows"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
