#!/usr/bin/env python3
"""Prueba el canal numérico oficial SENAMHI para Puente Ñácara.

Consulta el reporte hidrológico diario público con una sola petición. El
resultado permanece TEST_ONLY: descubrir un canal numérico no valida tiempos
de tránsito, capacidad del cauce ni umbrales para Catacaos/Bajo Piura.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/hydrology/senamhi_nacara_numeric_probe.json"
STATION_ID = "47E0415A"
ENDPOINT = "https://www.senamhi.gob.pe/include/ajax-informacion-diaria-piura.php"
PUBLIC_PAGE = "https://www.senamhi.gob.pe/?p=monitoreo-informacion-diaria"
LIMA = timezone(timedelta(hours=-5))
MISSING_SENTINELS = {-999.0, -9999.0}


def normalized(value):
    text = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").upper()


def rows_from_response(payload):
    content = payload.get("content") if isinstance(payload, dict) else None
    if isinstance(content, dict):
        return list(content.values())
    if isinstance(content, list):
        return content
    return []


def extract_station(payload, station_id=STATION_ID):
    """Devuelve una lectura solo si estación, unidad y valor son inequívocos."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None, "API_RESPONSE_NOT_SUCCESSFUL"
    matches = [row for row in rows_from_response(payload) if str(row.get("codEsta")) == station_id]
    if len(matches) != 1:
        return None, "STATION_NOT_UNIQUE"
    row = matches[0]
    if "PUENTE NACARA" not in normalized(row.get("nomEsta")):
        return None, "STATION_NAME_MISMATCH"
    unit = str(row.get("unidad") or "").replace("³", "3").replace(" ", "").lower()
    if unit != "m3/s":
        return None, "UNIT_NOT_FLOW"
    try:
        value = float(row.get("dato"))
    except (TypeError, ValueError):
        return None, "VALUE_NOT_NUMERIC"
    if not math.isfinite(value) or value < 0 or value in MISSING_SENTINELS:
        return None, "VALUE_MISSING_OR_INVALID"
    return {
        "station_id": station_id,
        "station_name": row.get("nomEsta"),
        "basin": row.get("nomCuenca"),
        "department": row.get("nomDepa"),
        "variable": "CAUDAL",
        "value": value,
        "unit": "m3/s",
        "trend_code": row.get("tendencia"),
        "official_reference_red": row.get("umbralRojo"),
        "official_reference_red_use": "SOURCE_METADATA_ONLY_NOT_IRFEN_THRESHOLD",
    }, None


def query_time(now=None):
    current = (now or datetime.now(timezone.utc)).astimezone(LIMA)
    # El tablero publica cortes horarios; nunca pedimos una hora futura.
    return current.replace(minute=0, second=0, microsecond=0)


def main():
    generated_at = datetime.now(timezone.utc)
    requested_at = query_time(generated_at)
    request_fields = {
        "fecha": requested_at.strftime("%Y-%m-%d"),
        "hora": requested_at.strftime("%H:00"),
    }
    headers = {
        "User-Agent": "IRFEN-v0.8-scientific-probe/1.0 (+https://github.com/IRFEN2026/irfen-peru)",
        "Accept": "application/json",
        "Referer": PUBLIC_PAGE,
    }

    http = {"endpoint": ENDPOINT, "method": "POST", "request_fields": request_fields}
    reading = None
    rejection_reason = None
    try:
        request = Request(
            ENDPOINT,
            data=urlencode(request_fields).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            body = response.read()
            http.update({
                "status": response.status,
                "content_type": response.headers.get("content-type"),
                "bytes": len(body),
            })
        payload = json.loads(body.decode("utf-8"))
        reading, rejection_reason = extract_station(payload)
        http["api_success"] = payload.get("success") is True
        http["returned_station_count"] = len(rows_from_response(payload))
    except Exception as exc:
        rejection_reason = type(exc).__name__
        http.update({"error_type": type(exc).__name__, "error": str(exc)[:800]})

    candidate_available = reading is not None
    result = {
        "version": "0.8-experimental",
        "generated_at": generated_at.isoformat(),
        "production_use": False,
        "production_ready": False,
        "integration_mode": "TEST_ONLY",
        "source": {
            "agency": "SENAMHI",
            "public_page": PUBLIC_PAGE,
            "endpoint": ENDPOINT,
        },
        "query": {
            "requested_observation_time": requested_at.isoformat(),
            "timezone": "America/Lima (UTC-05:00)",
            "time_is_request_selector": True,
            "response_echoes_observation_time": False,
        },
        "status": (
            "OFFICIAL_NUMERIC_RIVER_STATE_CANDIDATE_AVAILABLE"
            if candidate_available else "NO_VALID_NUMERIC_READING"
        ),
        "numeric_river_state_available": candidate_available,
        "reading": reading,
        "rejection_reason": rejection_reason,
        "http": http,
        "channel_validation": {
            "exact_station_code_required": STATION_ID,
            "station_name_required": "PUENTE ÑACARA",
            "flow_unit_required": "m3/s",
            "missing_sentinels_rejected": sorted(MISSING_SENTINELS),
            "request_time_stored": True,
            "response_time_echo_pending": True,
        },
        "scientific_gate": {
            "status": "TEST_ONLY_NUMERIC_CHANNEL_FOUND" if candidate_available else "AUTOMATIC_NUMERIC_ACCESS_UNRESOLVED",
            "remaining_gap": (
                "Acumular frescura y continuidad; validar tiempo de tránsito Ñácara-Bajo Piura y capacidad hidráulica. "
                "La hora es el selector de consulta pero no vuelve en la respuesta JSON."
            ),
            "prohibitions": [
                "No usar como alerta operativa.",
                "No trasladar el valor de Ñácara directamente a Catacaos.",
                "No adoptar umbralRojo como umbral IRFEN sin contrato hidráulico.",
                "No interpretar una lectura ausente como caudal cero o riesgo bajo.",
            ],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "requested_observation_time": result["query"]["requested_observation_time"],
        "reading": reading,
        "rejection_reason": rejection_reason,
        "http_status": http.get("status"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
