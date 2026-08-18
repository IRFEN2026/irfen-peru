#!/usr/bin/env python3
"""Valida eventos de oportunidad RESEARCH_ONLY y genera un catálogo público."""
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTAKE_DIR = ROOT / "site/data/validation/phase2_event_intake"
OUT_PATH = ROOT / "site/data/phase2/research_events.json"
PILOT_ZONE_IDS = {"san_ildefonso", "chosica_huaycoloro", "catacaos_bajo_piura"}
REQUIRED_IDENTITY_FIELDS = {
    "feature_name": ("reported_location", "feature_name"),
    "coordinates": ("reported_location", "coordinates"),
    "occurrence_time_local": ("reported_event", "occurrence_time_local"),
    "official_event_source": ("verification", "official_event_source"),
}
REQUIRED_CONFIRMATION_FIELDS = {
    name: path for name, path in REQUIRED_IDENTITY_FIELDS.items() if name != "coordinates"
}


class EventIntakeError(ValueError):
    pass


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _get(row, path):
    value = row
    for key in path:
        value = (value or {}).get(key)
    return value


def validate_event(row, path=None):
    event_id = row.get("event_id")

    def require(ok, message):
        if not ok:
            raise EventIntakeError(f"{event_id or '<sin-id>'}: {message}")

    require(row.get("version") == "phase2-event-intake-v1", "versión inválida")
    require(isinstance(event_id, str) and event_id, "event_id requerido")
    require(not path or path.stem == event_id, "nombre de archivo no coincide")
    require(bool(_get(row, ("reported_event", "reported_date_local"))), "fecha reportada requerida")
    require(bool(_get(row, ("reported_location", "department"))), "departamento requerido")
    require(bool(_get(row, ("reported_location", "province"))), "provincia requerida")
    require(row.get("status") in {
        "CANDIDATE_EVENT_PENDING_OFFICIAL_VERIFICATION",
        "VERIFIED_OUTCOME_PENDING_ANALYSIS_GEOMETRY",
        "VERIFIED_EVENT_RESEARCH_ONLY",
    }, "status inválido")
    require(row.get("deployment_status") == "RESEARCH_ONLY", "debe ser RESEARCH_ONLY")
    require(row.get("production_use") is False, "production_use debe ser false")
    require(row.get("alerting_enabled") is False, "alertas deben permanecer desactivadas")
    require(row.get("counts_toward_v08_closeout") is False, "no puede contar para v0.8")
    require(row.get("operational_zone_activation") is False, "no puede activar una zona")
    require(row.get("decision_thresholds") is None, "umbrales no permitidos")
    require(row.get("hydraulic_factors") is None, "factores hidráulicos no permitidos")
    require(row.get("missing_data_rule") == "UNKNOWN_NOT_LOW_RISK", "dato ausente no es bajo riesgo")
    require(row.get("target_zone_id") not in PILOT_ZONE_IDS, "evento Phase 2 no se asigna a un piloto v0.8")

    verification = row.get("verification") or {}
    confirmed = verification.get("event_confirmed") is True
    missing_confirmation = sorted(
        name for name, field_path in REQUIRED_CONFIRMATION_FIELDS.items()
        if not _get(row, field_path)
    )
    missing = sorted(
        name for name, field_path in REQUIRED_IDENTITY_FIELDS.items()
        if not _get(row, field_path)
    )
    require(sorted(row.get("missing_required_fields") or []) == missing,
            "missing_required_fields no coincide con la identidad disponible")

    analysis = row.get("analysis") or {}
    require(analysis.get("imerg_windows_hours") == [3, 6, 24], "ventanas IMERG deben ser 3/6/24 h")
    require(analysis.get("threshold_inference_allowed") is False, "no puede inferir umbrales")
    require(analysis.get("hydraulic_transfer_allowed") is False, "no puede transferir hidráulica")
    require(analysis.get("results") is None, "resultados requieren un artefacto de reanálisis separado")

    if confirmed:
        require(not missing_confirmation,
                "evento confirmado requiere lugar nombrado, tiempo y fuente oficial")
        require(str(verification.get("official_event_source") or "").startswith("https://"),
                "fuente oficial del evento inválida")
        require(bool(verification.get("verified_by")), "evento confirmado requiere revisor identificado")
        require(bool(verification.get("verified_at")), "evento confirmado requiere fecha de revisión")
        require(verification.get("spatial_identity_confirmed") is True,
                "evento confirmado requiere identidad espacial revisada")
        require(verification.get("temporal_identity_confirmed") is True,
                "evento confirmado requiere identidad temporal revisada")
        if "coordinates" in missing:
            require(row.get("status") == "VERIFIED_OUTCOME_PENDING_ANALYSIS_GEOMETRY",
                    "evento confirmado sin coordenadas debe declarar geometría pendiente")
            require(analysis.get("status") == "BLOCKED_MISSING_ANALYSIS_GEOMETRY",
                    "reanálisis debe bloquearse sin geometría")
        else:
            coordinates = _get(row, ("reported_location", "coordinates")) or {}
            try:
                lat = float(coordinates["lat"])
                lon = float(coordinates["lon"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EventIntakeError(f"{event_id}: coordenadas inválidas") from exc
            require(-90 <= lat <= 90 and -180 <= lon <= 180, "coordenadas fuera de rango")
            if coordinates.get("official_event_geometry") is not True:
                require(coordinates.get("role") == "research_sampling_reference",
                        "geometría no oficial solo puede seleccionar muestreo de investigación")
                require(bool(coordinates.get("precision")),
                        "geometría no oficial requiere precisión declarada")
                require(str(coordinates.get("source_url") or "").startswith("https://"),
                        "geometría no oficial requiere fuente reproducible")
            require(row.get("status") == "VERIFIED_EVENT_RESEARCH_ONLY",
                    "estado no refleja verificación completa")
            require(analysis.get("status") == "READY_FOR_REANALYSIS",
                    "evento con geometría revisada debe quedar listo")
    else:
        require(row.get("status") == "CANDIDATE_EVENT_PENDING_OFFICIAL_VERIFICATION",
                "evento no confirmado debe quedar pendiente")
        expected = "BLOCKED_MISSING_EVENT_IDENTITY" if missing else "BLOCKED_PENDING_OFFICIAL_REVIEW"
        require(analysis.get("status") == expected, "reanálisis debe permanecer bloqueado hasta verificación")

    for source in row.get("context_sources") or []:
        require(source.get("supports_event_confirmation") is False,
                "una fuente de contexto no puede confirmar el evento")
        require(str(source.get("url") or "").startswith("https://"), "fuente de contexto inválida")
    return row


def build_catalog(rows):
    items = []
    for row in rows:
        location = row.get("reported_location") or {}
        event = row.get("reported_event") or {}
        verification = row.get("verification") or {}
        analysis = row.get("analysis") or {}
        items.append({
            "event_id": row["event_id"],
            "status": row["status"],
            "deployment_status": "RESEARCH_ONLY",
            "reported_date_local": event.get("reported_date_local"),
            "department": location.get("department"),
            "province": location.get("province"),
            "feature_name": location.get("feature_name"),
            "event_confirmed": verification.get("event_confirmed") is True,
            "analysis_status": analysis.get("status"),
            "missing_required_fields": row.get("missing_required_fields") or [],
            "counts_toward_v08_closeout": False,
            "operational_zone_activation": False,
        })
    return {
        "version": "phase2-research-event-catalog-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "deployment_status": "RESEARCH_ONLY",
        "relationship_to_v08": {
            "v08_scope_unchanged": True,
            "events_count_toward_closeout": False,
            "events_can_activate_zones": False,
        },
        "guardrails": {
            "unverified_events_block_reanalysis": True,
            "threshold_inference_disabled": True,
            "hydraulic_transfer_disabled": True,
            "missing_data_is_not_low_risk": True,
        },
        "summary": {
            "registered_events": len(items),
            "verified_events": sum(item["event_confirmed"] for item in items),
            "verified_pending_geometry": sum(
                item["status"] == "VERIFIED_OUTCOME_PENDING_ANALYSIS_GEOMETRY" for item in items
            ),
            "ready_for_reanalysis": sum(item["analysis_status"] == "READY_FOR_REANALYSIS" for item in items),
            "operational_activations": 0,
        },
        "items": items,
    }


def generate_public_catalog(write=True):
    paths = sorted(INTAKE_DIR.glob("*.json"))
    rows = [validate_event(load_json(path), path) for path in paths]
    event_ids = [row["event_id"] for row in rows]
    if len(event_ids) != len(set(event_ids)):
        raise EventIntakeError("event_id duplicado")
    catalog = build_catalog(rows)
    if write:
        write_json(OUT_PATH, catalog)
    return catalog


if __name__ == "__main__":
    catalog = generate_public_catalog()
    print(json.dumps(catalog["summary"], ensure_ascii=False, sort_keys=True))
