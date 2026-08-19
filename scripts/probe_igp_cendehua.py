#!/usr/bin/env python3
"""Sondeo acotado del canal oficial IGP/CENDEHUA para Huaycoloro.

El sondeo parte exclusivamente de URLs oficiales conocidas y solo inspecciona
recursos enlazados por la pagina obtenida. No enumera endpoints, no infiere
eventos y no cambia el estado operativo TEST_ONLY de IRFEN v0.8.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
import json
import re

import requests


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/stations/igp_cendehua_access_probe.json"
ARCHIVE = ROOT / "site/data/stations/igp_cendehua_huaycoloro_archive.json"
START_URLS = [
    "https://www.igp.gob.pe/servicios/centro-monitoreo-deslizamientos-huaicos/inicio",
    "https://grd.igp.gob.pe/lahares-huaicos/",
]
TIMEOUT = (5, 15)
MAX_HTML_BYTES = 2_000_000
MAX_REFERENCES = 120
MAX_CANDIDATES = 25
MAX_PROBES = 10
MAX_SCRIPT_PROBES = 4
MAX_SCRIPT_BYTES = 2_000_000
MAX_ARCHIVE_CAPTURES = 1_000
RECENT_SIGNAL_SECONDS = 60 * 60


def safe_get(url: str):
    return requests.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={"User-Agent": "IRFEN-v0.8-scientific-probe/1.0"},
    )


def classify_candidate(url: str):
    """Clasifica unicamente referencias con senales estructuradas explicitas."""
    low = url.lower()
    if any(token in low for token in (".geojson", "geojson", "?f=geojson")):
        return "geojson_candidate"
    if any(token in low for token in (".json", "/api/", "?f=json", "format=json")):
        return "json_or_api_candidate"
    if any(token in low for token in (".csv", "format=csv")):
        return "csv_candidate"
    if any(token in low for token in ("featureserver", "mapserver", "geoserver", "/wfs")):
        return "gis_service_candidate"
    if urlparse(url).hostname == "grd.igp.gob.pe" and low.rstrip("/").endswith("/medias"):
        return "cendehua_station_media_api_candidate"
    return None


def extract_candidates(html: str, base_url: str):
    """Extrae candidatos solo de href/src literales y con limites verificables."""
    references = []
    candidates = []
    for match in re.finditer(r"(?:src|href)=[\"']([^\"']+)[\"']", html, re.I):
        url = urljoin(base_url, unescape(match.group(1)).strip())
        if not url.startswith(("http://", "https://")) or url in references:
            continue
        references.append(url)
        kind = classify_candidate(url)
        if kind:
            candidates.append({"url": url, "kind": kind})
            if len(candidates) >= MAX_CANDIDATES:
                break
        if len(references) >= MAX_REFERENCES:
            break
    return references, candidates


def extract_script_candidates(script: str, script_url: str):
    """Extrae endpoints literales del cliente oficial, sin adivinar rutas."""
    candidates = []
    seen = set()
    patterns = (
        r"https://grd\.igp\.gob\.pe/[A-Za-z0-9_-]+/medias",
        r"[\"'](/?[A-Za-z0-9_-]+/medias)[\"']",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, script):
            raw = match.group(0).strip("\"'") if match.lastindex is None else match.group(1)
            url = urljoin(script_url, raw)
            if urlparse(url).hostname != "grd.igp.gob.pe" or url in seen:
                continue
            kind = classify_candidate(url)
            if kind:
                candidates.append({"url": url, "kind": kind, "discovered_in": script_url})
                seen.add(url)
            if len(candidates) >= MAX_CANDIDATES:
                return candidates
    return candidates


def iso_from_epoch(value):
    try:
        timestamp = float(value)
        if timestamp <= 0:
            return None
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def summarize_huaycoloro(payload, captured_at: datetime):
    """Resume telemetria sin convertir un booleano del proveedor en EVENT/NONE."""
    if not isinstance(payload, list):
        return []
    captured_epoch = captured_at.timestamp()
    observations = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        group = str(row.get("grupo") or "")
        ravine = str(row.get("nombre_quebrada") or "")
        if group != "lima/huaycos" or ravine.casefold() != "huaycoloro":
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
                "station_id": row.get("id_estacion"),
                "station_name": row.get("nombre_estacion"),
                "group": group,
                "ravine": ravine,
                "last_alert_update": iso_from_epoch(alert_epoch),
                "last_image_update": iso_from_epoch(image_epoch),
                "alert_age_seconds_at_capture": age_seconds,
                "recent_signal": age_seconds is not None
                and -300 <= age_seconds <= RECENT_SIGNAL_SECONDS,
                "provider_activity_flag_raw": alert.get("actividad_lahar")
                if isinstance(alert.get("actividad_lahar"), bool)
                else None,
                "irfen_outcome_label": None,
                "human_review_required": True,
            }
        )
    return sorted(observations, key=lambda item: str(item.get("station_id") or ""))


def build_archive(existing, capture):
    archive = existing if isinstance(existing, dict) else {}
    captures = archive.get("captures") if isinstance(archive.get("captures"), list) else []
    key = (
        capture.get("source_url"),
        tuple(
            (item.get("station_id"), item.get("last_alert_update"), item.get("last_image_update"))
            for item in capture.get("observations", [])
        ),
    )
    known = {
        (
            item.get("source_url"),
            tuple(
                (row.get("station_id"), row.get("last_alert_update"), row.get("last_image_update"))
                for row in item.get("observations", [])
            ),
        )
        for item in captures
        if isinstance(item, dict)
    }
    if key not in known:
        captures.append(capture)
    captures = captures[-MAX_ARCHIVE_CAPTURES:]
    summary = summarize_archive(captures)
    return {
        "version": "0.8-experimental",
        "integration_mode": "TEST_ONLY",
        "production_use": False,
        "production_ready": False,
        "purpose": "Archive official IGP/CENDEHUA Huaycoloro station snapshots for human shadow review.",
        "capture_count": len(captures),
        "summary": summary,
        "captures": captures,
        "scientific_gate": {
            "automatic_event_or_none_classification": False,
            "absence_of_provider_activity_is_none": False,
            "continuity_metrics_are_outcome_labels": False,
            "human_review_required": True,
            "missing_or_stale_data_rule": "UNCERTAIN; never low risk or NONE",
        },
    }


def summarize_archive(captures):
    """Describe signal continuity without assigning a hydrometeorological outcome."""
    parsed = []
    station_ids = set()
    all_recent_count = 0
    any_activity_true_count = 0
    activity_unknown_count = 0
    for capture in captures:
        try:
            captured_at = datetime.fromisoformat(
                str(capture.get("captured_at")).replace("Z", "+00:00")
            )
            if captured_at.tzinfo is None:
                raise ValueError("timestamp without timezone")
            parsed.append(captured_at.astimezone(timezone.utc))
        except (TypeError, ValueError):
            pass

        observations = [
            row for row in capture.get("observations", []) if isinstance(row, dict)
        ]
        station_ids.update(
            str(row.get("station_id")) for row in observations if row.get("station_id")
        )
        if observations and all(row.get("recent_signal") is True for row in observations):
            all_recent_count += 1
        flags = [row.get("provider_activity_flag_raw") for row in observations]
        if any(flag is True for flag in flags):
            any_activity_true_count += 1
        if not flags or any(not isinstance(flag, bool) for flag in flags):
            activity_unknown_count += 1

    parsed.sort()
    intervals_minutes = [
        round((current - previous).total_seconds() / 60, 3)
        for previous, current in zip(parsed, parsed[1:])
        if current >= previous
    ]
    median_interval = None
    if intervals_minutes:
        ordered = sorted(intervals_minutes)
        middle = len(ordered) // 2
        median_interval = (
            ordered[middle]
            if len(ordered) % 2
            else round((ordered[middle - 1] + ordered[middle]) / 2, 3)
        )
    return {
        "capture_count": len(captures),
        "distinct_station_ids": sorted(station_ids),
        "first_capture_at": parsed[0].isoformat() if parsed else None,
        "latest_capture_at": parsed[-1].isoformat() if parsed else None,
        "observed_span_hours": round((parsed[-1] - parsed[0]).total_seconds() / 3600, 3)
        if len(parsed) >= 2
        else 0.0,
        "valid_interval_count": len(intervals_minutes),
        "median_interval_minutes": median_interval,
        "max_interval_minutes": max(intervals_minutes) if intervals_minutes else None,
        "captures_with_all_reported_stations_recent": all_recent_count,
        "captures_with_any_provider_activity_true": any_activity_true_count,
        "captures_with_provider_activity_unknown": activity_unknown_count,
        "interpretation": (
            "Metrics describe availability and cadence only. Raw provider activity flags require "
            "named human review and never classify EVENT/NONE automatically."
        ),
    }


def main():
    captured_at = datetime.now(timezone.utc)
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

    page = None
    references = []
    candidates = []
    if final is not None:
        raw = final.content[:MAX_HTML_BYTES]
        text = raw.decode(final.encoding or "utf-8", errors="ignore")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        page = {
            "url": final.url,
            "title": re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else None,
            "bytes_inspected": len(raw),
        }
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

    probed = []
    huaycoloro_observations = []
    for candidate in candidates[:MAX_PROBES]:
        try:
            response = safe_get(candidate["url"])
            content_type = (response.headers.get("content-type") or "").lower()
            probe_row = {
                    **candidate,
                    "http_status": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "final_url": response.url,
                    "structured_response": any(
                        token in content_type for token in ("json", "csv", "geo+json")
                    ),
                    "bytes": len(response.content),
                }
            if response.ok and "json" in content_type:
                try:
                    observations = summarize_huaycoloro(response.json(), captured_at)
                except (ValueError, TypeError):
                    observations = []
                if observations:
                    huaycoloro_observations = observations
                    probe_row["huaycoloro_station_count"] = len(observations)
            probed.append(probe_row)
        except Exception as exc:
            probed.append(
                {**candidate, "error": {"type": type(exc).__name__, "message": str(exc)[:300]}}
            )

    usable = [
        item
        for item in probed
        if item.get("http_status") == 200 and item.get("structured_response") is True
    ]
    recent_count = sum(item["recent_signal"] for item in huaycoloro_observations)
    if huaycoloro_observations:
        status = "HUAYCOLORO_STRUCTURED_CHANNEL_FOUND"
        next_action = (
            "Archive TEST_ONLY station snapshots and submit dated outcomes to human review; "
            "never infer NONE from the provider activity flag."
        )
    elif usable:
        status = "STRUCTURED_CHANNEL_CANDIDATE_FOUND"
        next_action = (
            "Review schema, station identity and event semantics before adding any observation pair."
        )
    elif final is not None:
        status = "OFFICIAL_MONITOR_REACHED_NO_OBVIOUS_STRUCTURED_CHANNEL"
        next_action = (
            "Keep CENDEHUA as an authoritative external/manual outcome channel; stop endpoint exploration."
        )
    else:
        status = "OFFICIAL_MONITOR_NOT_REACHABLE_FROM_GITHUB"
        next_action = (
            "Retain the official IGP publications as documentary evidence and retry only the same URLs later."
        )

    result = {
        "version": "0.8-experimental",
        "generated_at": captured_at.isoformat(),
        "production_use": False,
        "production_ready": False,
        "purpose": (
            "Bounded check for a documented machine-readable IGP/CENDEHUA Huaycoloro monitoring channel."
        ),
        "official_context": {
            "institution": "Instituto Geofisico del Peru (IGP)",
            "platform": "CENDEHUA - monitoreo de deslizamientos y huaicos",
            "target_pilot": "Huaycoloro/Chosica",
            "official_service_url": "https://www.gob.pe/41855-centro-de-monitoreo-de-deslizamientos-y-huaicos-cendehua",
            "official_alerts_url": "https://www.gob.pe/8084-revisar-alertas-de-huaicos-en-lima",
            "official_monitoring_news_url": "https://www.gob.pe/institucion/igp/noticias/1343594-igp-refuerza-vigilancia-del-sistema-de-monitoreo-de-huaicos-en-las-quebradas-huaycoloro-y-rio-seco",
            "claimed_scope": "official 24/7 monitoring and alerts; not an IRFEN event label",
        },
        "status": status,
        "attempts": attempts,
        "page": page,
        "references_inspected": len(references),
        "structured_candidates_found": candidates,
        "candidate_probes": probed,
        "usable_structured_candidates": usable,
        "huaycoloro_ground_signal": {
            "status": "LIVE_STRUCTURED_SIGNAL_OBSERVED"
            if recent_count
            else "NO_RECENT_STRUCTURED_SIGNAL_OBSERVED",
            "station_count": len(huaycoloro_observations),
            "recent_station_count": recent_count,
            "observations": huaycoloro_observations,
            "automatic_outcome_label": None,
            "human_review_required": True,
        },
        "next_action": next_action,
        "stop_rule": (
            "Inspect only official page references and endpoint literals present in the official client; "
            "do not enumerate or guess undocumented endpoints."
        ),
        "validation_guard": (
            "This probe cannot classify an EVENT/NONE outcome or satisfy the Chosica validation contract by itself."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if huaycoloro_observations:
        try:
            existing_archive = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            existing_archive = None
        archive = build_archive(
            existing_archive,
            {
                "captured_at": captured_at.isoformat(),
                "source_url": next(
                    (
                        item["url"]
                        for item in usable
                        if item.get("huaycoloro_station_count")
                    ),
                    None,
                ),
                "station_count": len(huaycoloro_observations),
                "recent_station_count": recent_count,
                "observations": huaycoloro_observations,
                "automatic_outcome_label": None,
                "human_review_required": True,
            },
        )
        ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status,
                "page": page,
                "candidates": len(candidates),
                "usable_count": len(usable),
                "next_action": next_action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
