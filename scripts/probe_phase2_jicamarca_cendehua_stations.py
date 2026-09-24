#!/usr/bin/env python3
"""Bounded CENDEHUA station-metadata capture for Jicamarca local children.

This script reuses the already-vetted official-client endpoint discovery from
``probe_igp_cendehua.py``. It does not enumerate endpoints, infer EVENT/NONE,
create geometry/outlets, infer discharge, import provider thresholds, or enable
routing. Missing/stale/provider-false data remain UNKNOWN_NOT_LOW_RISK.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import unicodedata
from urllib.parse import urlparse

from probe_igp_cendehua import (
    MAX_HTML_BYTES,
    MAX_PROBES,
    MAX_SCRIPT_BYTES,
    MAX_SCRIPT_PROBES,
    RECENT_SIGNAL_SECONDS,
    START_URLS,
    extract_candidates,
    extract_script_candidates,
    iso_from_epoch,
    safe_get,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "site/data/phase2/sources/jicamarca_cendehua_live"
LATEST = OUT_DIR / "station_metadata_latest_v0_1.json"
ARCHIVE = OUT_DIR / "station_metadata_archive_v0_1.json"
MAX_ARCHIVE_CAPTURES = 1000

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}

# Controlled provider-label mapping only. This is not a geometric crosswalk.
ALLOWED_COMPONENTS = {
    "huaycoloro": "huaycoloro",
    "rio seco": "rio_seco",
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def normalized_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().casefold()


def component_from_provider_ravine(value):
    return ALLOWED_COMPONENTS.get(normalized_text(value))


def summarize_monitored_rows(payload, captured_at: datetime):
    """Keep only bounded station metadata for Huaycoloro and Río Seco.

    Provider names bind records to a research component label only; they never
    define a catchment polygon, channel geometry, outlet, confluence or routing
    relation.
    """
    if not isinstance(payload, list):
        return []
    captured_epoch = captured_at.timestamp()
    observations = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        group = str(row.get("grupo") or "")
        provider_ravine = str(row.get("nombre_quebrada") or "")
        component_id = component_from_provider_ravine(provider_ravine)
        if group != "lima/huaycos" or component_id is None:
            continue

        alert = row.get("ultima_alerta") if isinstance(row.get("ultima_alerta"), dict) else {}
        image = row.get("ultima_imagen") if isinstance(row.get("ultima_imagen"), dict) else {}
        alert_epoch = alert.get("actualizado_a")
        image_epoch = image.get("actualizado_a")
        try:
            age_seconds = round(captured_epoch - float(alert_epoch), 3)
        except (TypeError, ValueError):
            age_seconds = None

        observations.append(
            {
                "component_id": component_id,
                "component_binding_basis": "PROVIDER_NOMBRE_QUEBRADA_ONLY_PENDING_SPATIAL_CROSSWALK",
                "station_id": row.get("id_estacion"),
                "station_name": row.get("nombre_estacion"),
                "group": group,
                "provider_ravine_label": provider_ravine,
                "last_alert_update": iso_from_epoch(alert_epoch),
                "last_image_update": iso_from_epoch(image_epoch),
                "alert_age_seconds_at_capture": age_seconds,
                "recent_signal": age_seconds is not None
                and -300 <= age_seconds <= RECENT_SIGNAL_SECONDS,
                "provider_activity_flag_raw": alert.get("actividad_lahar")
                if isinstance(alert.get("actividad_lahar"), bool)
                else None,
                "irfen_outcome_label": None,
                "outlet": None,
                "confluence": None,
                "Q_i_t": None,
                "travel_time": None,
                "attenuation": None,
                "human_review_required": True,
            }
        )
    return sorted(
        observations,
        key=lambda item: (item["component_id"], str(item.get("station_id") or "")),
    )


def capture_key(capture):
    return (
        capture.get("source_url"),
        tuple(
            (
                row.get("component_id"),
                row.get("station_id"),
                row.get("last_alert_update"),
                row.get("last_image_update"),
            )
            for row in capture.get("observations", [])
            if isinstance(row, dict)
        ),
    )


def build_archive(existing, capture):
    archive = existing if isinstance(existing, dict) else {}
    captures = archive.get("captures") if isinstance(archive.get("captures"), list) else []
    known = {capture_key(item) for item in captures if isinstance(item, dict)}
    if capture_key(capture) not in known:
        captures.append(capture)
    captures = captures[-MAX_ARCHIVE_CAPTURES:]
    station_ids = sorted(
        {
            str(row.get("station_id"))
            for item in captures
            for row in item.get("observations", [])
            if isinstance(row, dict) and row.get("station_id")
        }
    )
    component_ids = sorted(
        {
            row.get("component_id")
            for item in captures
            for row in item.get("observations", [])
            if isinstance(row, dict) and row.get("component_id")
        }
    )
    return {
        "schema_version": "0.1",
        **SAFE,
        "status": "BOUNDED_CENDEHUA_STATION_METADATA_ARCHIVE",
        "purpose": "Archive exact provider station/timestamp metadata for Jicamarca child research without outcome or hydraulic inference.",
        "capture_count": len(captures),
        "distinct_station_ids": station_ids,
        "distinct_component_ids": component_ids,
        "captures": captures,
        "scientific_gate": {
            "automatic_event_or_none_classification": False,
            "absence_of_provider_activity_is_none": False,
            "provider_activity_flag_is_irfen_threshold": False,
            "provider_ravine_label_is_outlet_or_geometry": False,
            "station_id_is_outlet": False,
            "station_name_is_outlet": False,
            "discharge_inference_allowed": False,
            "routing_enabled": False,
            "human_review_required": True,
        },
    }


def discover_official_candidates():
    attempts = []
    final = None
    for start_url in START_URLS:
        row = {"start_url": start_url}
        try:
            response = safe_get(start_url)
            content_type = response.headers.get("content-type")
            row.update(
                {
                    "status_code": response.status_code,
                    "final_url": response.url,
                    "content_type": content_type,
                    "redirect_chain": [item.url for item in response.history] + [response.url],
                }
            )
            attempts.append(row)
            if response.ok and "text/html" in (content_type or "").lower():
                final = response
                break
        except Exception as exc:
            row["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
            attempts.append(row)

    if final is None:
        return attempts, None, []

    raw = final.content[:MAX_HTML_BYTES]
    text = raw.decode(final.encoding or "utf-8", errors="ignore")
    references, candidates = extract_candidates(text, final.url)
    script_urls = [
        url
        for url in references
        if urlparse(url).hostname == "grd.igp.gob.pe"
        and urlparse(url).path.lower().endswith(".js")
    ][:MAX_SCRIPT_PROBES]
    for script_url in script_urls:
        try:
            response = safe_get(script_url)
            if not response.ok:
                continue
            script = response.content[:MAX_SCRIPT_BYTES].decode(
                response.encoding or "utf-8", errors="ignore"
            )
            for item in extract_script_candidates(script, script_url):
                if not any(existing["url"] == item["url"] for existing in candidates):
                    candidates.append(item)
        except Exception:
            continue
    return attempts, final.url, candidates[:MAX_PROBES]


def main():
    captured_at = datetime.now(timezone.utc)
    attempts, page_url, candidates = discover_official_candidates()
    probes = []
    selected_source_url = None
    observations = []

    for candidate in candidates:
        try:
            response = safe_get(candidate["url"])
            content_type = (response.headers.get("content-type") or "").lower()
            row = {
                **candidate,
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "final_url": response.url,
                "structured_response": "json" in content_type,
                "bytes": len(response.content),
            }
            if response.ok and "json" in content_type:
                try:
                    candidate_observations = summarize_monitored_rows(response.json(), captured_at)
                except (ValueError, TypeError):
                    candidate_observations = []
                if candidate_observations:
                    selected_source_url = response.url
                    observations = candidate_observations
                    row["jicamarca_station_count"] = len(candidate_observations)
                    row["component_ids"] = sorted({item["component_id"] for item in candidate_observations})
                    probes.append(row)
                    break
            probes.append(row)
        except Exception as exc:
            probes.append({**candidate, "error": {"type": type(exc).__name__, "message": str(exc)[:300]}})

    if observations:
        status = "JICAMARCA_BOUNDED_STRUCTURED_STATION_METADATA_FOUND"
    elif any(row.get("structured_response") for row in probes):
        status = "STRUCTURED_CHANNEL_REACHED_NO_ALLOWED_JICAMARCA_ROWS"
    elif page_url:
        status = "OFFICIAL_MONITOR_REACHED_NO_STRUCTURED_JICAMARCA_METADATA"
    else:
        status = "OFFICIAL_MONITOR_NOT_REACHABLE"

    latest = {
        "schema_version": "0.1",
        **SAFE,
        "status": status,
        "generated_at": captured_at.isoformat(),
        "purpose": "Bounded official CENDEHUA metadata capture for Huaycoloro and Río Seco as separate Jicamarca research children.",
        "official_page_url": page_url,
        "attempts": attempts,
        "candidate_probes": probes,
        "source_url": selected_source_url,
        "observations": observations,
        "automatic_outcome_label": None,
        "routing_enabled": False,
        "receiver_overflow_inferred": False,
        "map_geometry_created": False,
        "scientific_interpretation": (
            "Provider station/timestamp metadata are direct monitoring context only. Provider activity flags, names and timestamps do not define IRFEN outcomes, thresholds, geometry, outlets, discharge, travel time, attenuation or Rímac overflow."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(canonical(latest), encoding="utf-8")

    if observations and selected_source_url:
        existing = json.loads(ARCHIVE.read_text(encoding="utf-8")) if ARCHIVE.is_file() else None
        capture = {
            "captured_at": captured_at.isoformat(),
            "source_url": selected_source_url,
            "observations": observations,
        }
        ARCHIVE.write_text(canonical(build_archive(existing, capture)), encoding="utf-8")

    print(canonical({"status": status, "observation_count": len(observations), "source_url": selected_source_url}).strip())


if __name__ == "__main__":
    main()
