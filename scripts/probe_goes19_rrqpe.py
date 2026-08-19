#!/usr/bin/env python3
"""Probe NOAA GOES-19 RRQPE as an isolated IRFEN shadow input.

The probe checks public catalog freshness and samples only representative
locations for the three fixed v0.8 pilots.  It never changes rainfall
thresholds, hydraulic factors, risk, recommendations, or release score.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import hashlib
import json
import math
import re


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/calibration/goes19_rrqpe_probe.json"
ARCHIVE = ROOT / "site/data/calibration/goes19_rrqpe_archive.json"
BUCKET = "noaa-goes19"
PRODUCT = "ABI-L2-RRQPEF"
BASE = f"https://{BUCKET}.s3.amazonaws.com"
LOOKBACK_HOURS = 4
MAX_FILE_BYTES = 12_000_000
MAX_ARCHIVE_RECORDS = 1000
USER_AGENT = "IRFEN-v0.8-GOES-TEST-ONLY/1.0 (+https://github.com/IRFEN2026/irfen-peru)"
FILENAME_TIME = re.compile(r"_(?P<kind>[sec])(\d{14})(?=_)")


def utc(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def product_time(key, kind="s"):
    """Parse GOES YYYY+day-of-year+HHMMSS+tenth timestamps from a key."""
    for match in FILENAME_TIME.finditer(key):
        if match.group("kind") != kind:
            continue
        value = match.group(2)
        base = datetime.strptime(value[:13], "%Y%j%H%M%S").replace(tzinfo=timezone.utc)
        return base + timedelta(seconds=int(value[13]) / 10)
    return None


def parse_listing(xml_bytes):
    root = ElementTree.fromstring(xml_bytes)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    rows = []
    for item in root.findall("s3:Contents", namespace):
        key = item.findtext("s3:Key", namespaces=namespace)
        modified = item.findtext("s3:LastModified", namespaces=namespace)
        size = item.findtext("s3:Size", namespaces=namespace)
        if not key or not key.endswith(".nc"):
            continue
        rows.append({
            "key": key,
            "last_modified": modified,
            "size_bytes": int(size or 0),
            "scan_start": product_time(key, "s").isoformat() if product_time(key, "s") else None,
            "scan_end": product_time(key, "e").isoformat() if product_time(key, "e") else None,
        })
    return rows


def open_bytes(url, opener=urlopen, timeout=35):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with opener(request, timeout=timeout) as response:
        return response.read(), {
            "status": getattr(response, "status", None),
            "content_type": response.headers.get("content-type"),
            "content_length": response.headers.get("content-length"),
        }


def catalog(now, opener=urlopen):
    objects = {}
    requests = []
    hour = now.replace(minute=0, second=0, microsecond=0)
    for offset in range(LOOKBACK_HOURS):
        target = hour - timedelta(hours=offset)
        prefix = f"{PRODUCT}/{target:%Y/%j/%H}/"
        url = f"{BASE}/?list-type=2&prefix={quote(prefix, safe='/')}&max-keys=1000"
        body, meta = open_bytes(url, opener=opener)
        rows = parse_listing(body)
        requests.append({"prefix": prefix, "http_status": meta["status"], "object_count": len(rows)})
        for row in rows:
            objects[row["key"]] = row
    ordered = sorted(
        objects.values(),
        key=lambda row: utc(row["scan_start"]) if row.get("scan_start") else datetime.min.replace(tzinfo=timezone.utc),
    )
    return ordered, requests


def _scalar(value):
    import numpy as np

    item = np.asarray(value).reshape(-1)[0]
    if isinstance(item, bytes):
        return item.decode("utf-8", errors="replace")
    return item.item() if hasattr(item, "item") else item


def _unpack(dataset):
    import numpy as np

    raw = np.asarray(dataset[:], dtype=float)
    scale = float(_scalar(dataset.attrs.get("scale_factor", 1.0)))
    offset = float(_scalar(dataset.attrs.get("add_offset", 0.0)))
    return raw * scale + offset


def load_targets():
    validations = {
        "san_ildefonso": ROOT / "site/data/watersheds/san_ildefonso_validation.json",
        "huaycoloro_main_channel": ROOT / "site/data/watersheds/huaycoloro_validation.json",
    }
    targets = []
    for target_id, path in validations.items():
        validation = json.loads(path.read_text(encoding="utf-8"))
        value = validation["external_spatial_check"]["basin_centroid"]
        targets.append({"target_id": target_id, "lon": float(value["lon"]), "lat": float(value["lat"]), "weight": 1.0})

    zones = json.loads((ROOT / "config/zones.json").read_text(encoding="utf-8"))
    catacaos = next(item for item in zones["zones"] if item["id"] == "catacaos")
    for area in catacaos["sampling_areas"]:
        west, south, east, north = area["bbox"]
        targets.append({
            "target_id": "catacaos",
            "sampling_area": area["name"],
            "lon": (west + east) / 2,
            "lat": (south + north) / 2,
            "weight": float(area.get("weight", 1.0)),
        })
    return targets


def sample_product(path, targets):
    import h5py
    import numpy as np
    from pyproj import Proj

    with h5py.File(path, "r") as handle:
        projection = handle["goes_imager_projection"]
        height = float(_scalar(projection.attrs["perspective_point_height"]))
        project = Proj(
            proj="geos",
            h=height,
            lon_0=float(_scalar(projection.attrs["longitude_of_projection_origin"])),
            sweep=str(_scalar(projection.attrs["sweep_angle_axis"])),
            a=float(_scalar(projection.attrs["semi_major_axis"])),
            b=float(_scalar(projection.attrs["semi_minor_axis"])),
        )
        x_axis = _unpack(handle["x"])
        y_axis = _unpack(handle["y"])
        rainfall = handle["RRQPE"]
        quality = handle["DQF"]
        fill = int(_scalar(rainfall.attrs["_FillValue"]))
        scale = float(_scalar(rainfall.attrs["scale_factor"]))
        offset = float(_scalar(rainfall.attrs["add_offset"]))

        samples = []
        for target in targets:
            x_m, y_m = project(target["lon"], target["lat"])
            if not (math.isfinite(x_m) and math.isfinite(y_m)):
                samples.append({**target, "coverage_valid": False, "reason": "OUTSIDE_SATELLITE_VIEW"})
                continue
            x_rad, y_rad = x_m / height, y_m / height
            ix = int(np.argmin(np.abs(x_axis - x_rad)))
            iy = int(np.argmin(np.abs(y_axis - y_rad)))
            y0, y1 = max(0, iy - 2), min(rainfall.shape[0], iy + 3)
            x0, x1 = max(0, ix - 2), min(rainfall.shape[1], ix + 3)
            raw = np.asarray(rainfall[y0:y1, x0:x1])
            dqf = np.asarray(quality[y0:y1, x0:x1])
            # DQF=0 is the only good-quality category; all other flags stay excluded.
            valid = (raw != fill) & (dqf == 0)
            values = raw[valid].astype(float) * scale + offset
            samples.append({
                **target,
                "grid_index": {"x": ix, "y": iy},
                "window_pixel_count": int(raw.size),
                "good_quality_pixel_count": int(valid.sum()),
                "coverage_valid": bool(valid.any()),
                "rain_rate_summary_mm_h": ({
                    "min": round(float(values.min()), 4),
                    "mean": round(float(values.mean()), 4),
                    "max": round(float(values.max()), 4),
                } if valid.any() else None),
                "rain_rate_interpretation": "MEASUREMENT_ONLY_NOT_EVENT_OR_LOW_RISK_CLASSIFICATION",
            })

        attrs = handle.attrs
        metadata = {
            "platform_id": str(_scalar(attrs.get("platform_ID"))),
            "orbital_slot": str(_scalar(attrs.get("orbital_slot"))),
            "scene_id": str(_scalar(attrs.get("scene_id"))),
            "title": str(_scalar(attrs.get("title"))),
            "spatial_resolution": str(_scalar(attrs.get("spatial_resolution"))),
            "time_coverage_start": str(_scalar(attrs.get("time_coverage_start"))),
            "time_coverage_end": str(_scalar(attrs.get("time_coverage_end"))),
            "production_data_source": str(_scalar(attrs.get("production_data_source"))),
            "rrqpe_units": str(_scalar(rainfall.attrs.get("units"))),
            "rrqpe_shape": list(rainfall.shape),
        }
    return metadata, samples


def archive_result(previous, probe, generated_at):
    records = list((previous or {}).get("records") or [])
    row = {
        "generated_at": probe["generated_at"],
        "status": probe["status"],
        "source_available": probe["source_available"],
        "source_object_key": (probe.get("latest_object") or {}).get("key"),
        "source_scan_end": (probe.get("latest_object") or {}).get("scan_end"),
        "capture_delay_minutes": (probe.get("freshness") or {}).get("capture_delay_minutes"),
        "all_v08_pilots_covered": (probe.get("coverage") or {}).get("all_v08_pilots_covered"),
        "missing_data_interpretation": None if probe["source_available"] else "UNKNOWN_NOT_ZERO_OR_LOW_RISK",
    }
    records.append(row)
    unique = {item["generated_at"]: item for item in records if item.get("generated_at")}
    records = sorted(unique.values(), key=lambda item: utc(item["generated_at"]))[-MAX_ARCHIVE_RECORDS:]
    successes = sum(item.get("source_available") is True for item in records)
    covered = sum(item.get("all_v08_pilots_covered") is True for item in records)
    delays = sorted(
        float(item["capture_delay_minutes"])
        for item in records
        if isinstance(item.get("capture_delay_minutes"), (int, float))
        and float(item["capture_delay_minutes"]) >= 0
    )
    p90_index = math.ceil(0.9 * len(delays)) - 1 if delays else None
    p90_delay = round(delays[p90_index], 2) if p90_index is not None else None
    availability = round(successes * 100 / len(records), 1) if records else 0.0
    review_ready = len(records) >= 72
    technical_pass = bool(
        review_ready
        and availability >= 80
        and p90_delay is not None
        and p90_delay <= 30
        and covered > 0
    )
    return {
        "version": "0.8-experimental",
        "generated_at": generated_at.isoformat(),
        "production_use": False,
        "production_ready": False,
        "integration_mode": "GOES_TEST_ONLY",
        "counts_toward_v08_closeout": False,
        "status": "ACCUMULATING_GOES_TEST_ONLY_EVIDENCE",
        "summary": {
            "probe_record_count": len(records),
            "successful_source_count": successes,
            "source_availability_pct": availability,
            "capture_delay_p90_minutes": p90_delay,
            "all_pilots_covered_count": covered,
            "latest_probe_generated_at": records[-1]["generated_at"] if records else None,
            "distinct_source_object_count": len({item.get("source_object_key") for item in records if item.get("source_object_key")}),
        },
        "records": records,
        "retention_decision": {
            "status": (
                "TECHNICAL_ACCESS_GATE_PASS_SCIENTIFIC_REVIEW_PENDING"
                if technical_pass else
                "TECHNICAL_DISCARD_REVIEW_REQUIRED"
                if review_ready else
                "KEEP_FOR_SHADOW_EVALUATION_NOT_VALIDATED"
            ),
            "technical_access_verified": bool(successes and covered),
            "technical_review_sample_complete": review_ready,
            "technical_access_gate_pass": technical_pass,
            "scientific_incremental_value_verified": False,
        },
        "discard_contract": {
            "minimum_probe_records_before_availability_review": 72,
            "discard_if_source_availability_below_pct": 80,
            "discard_if_p90_capture_delay_exceeds_minutes": 30,
            "scientific_review_requires": [
                "collocated GOES-IMERG comparisons",
                "officially verified rainfall or activation cases",
                "no-event controls reviewed by a human",
            ],
            "discard_if": "GOES adds no reproducible timeliness or spatial signal after the required scientific review.",
        },
        "scientific_gate": {
            "automatic_alerting_enabled": False,
            "automatic_event_or_none_classification": False,
            "threshold_promotion_allowed": False,
            "hydraulic_factor_promotion_allowed": False,
            "missing_data_is_low_risk": False,
            "replaces_imerg": False,
            "human_review_required": True,
        },
    }


def base_probe(generated_at):
    return {
        "version": "0.8-experimental",
        "generated_at": generated_at.isoformat(),
        "production_use": False,
        "production_ready": False,
        "integration_mode": "GOES_TEST_ONLY",
        "counts_toward_v08_closeout": False,
        "automatic_alerting_enabled": False,
        "source": {
            "operator": "NOAA/NESDIS (United States)",
            "satellite": "GOES-19 / GOES-East",
            "product": PRODUCT,
            "public_bucket": f"s3://{BUCKET}",
            "official_product_page": "https://www.ospo.noaa.gov/products/atmosphere/err/",
            "format": "NetCDF4",
            "nominal_frequency_minutes": 10,
            "nominal_resolution_km_at_nadir": 2,
        },
        "status": "SOURCE_UNAVAILABLE",
        "source_available": False,
        "latest_object": None,
        "freshness": None,
        "catalog": {},
        "product_metadata": None,
        "samples": [],
        "coverage": {"all_v08_pilots_covered": False, "covered_target_ids": []},
        "scientific_gate": {
            "status": "UNVALIDATED_AGAINST_IMERG_GROUND_AND_OUTCOMES",
            "technical_access_is_not_scientific_validation": True,
            "automatic_event_or_none_classification": False,
            "threshold_promotion_allowed": False,
            "hydraulic_factor_promotion_allowed": False,
            "missing_or_zero_rain_rate_is_low_risk": False,
            "replaces_imerg": False,
            "counts_toward_v08_closeout": False,
            "human_review_required": True,
        },
    }


def run(now=None, opener=urlopen):
    generated_at = utc(now or datetime.now(timezone.utc))
    probe = base_probe(generated_at)
    temp_path = None
    try:
        objects, requests = catalog(generated_at, opener=opener)
        probe["catalog"] = {
            "lookback_hours": LOOKBACK_HOURS,
            "object_count": len(objects),
            "requests": requests,
        }
        if not objects:
            raise RuntimeError("NO_RECENT_RRQPE_OBJECTS")
        latest = objects[-1]
        if latest["size_bytes"] <= 0 or latest["size_bytes"] > MAX_FILE_BYTES:
            raise RuntimeError("LATEST_OBJECT_SIZE_OUT_OF_BOUNDS")
        body, http = open_bytes(f"{BASE}/{quote(latest['key'], safe='/')}", opener=opener, timeout=60)
        if len(body) != latest["size_bytes"]:
            raise RuntimeError("DOWNLOADED_SIZE_MISMATCH")
        with NamedTemporaryFile(prefix="irfen-goes19-", suffix=".nc", delete=False) as temp:
            temp.write(body)
            temp_path = Path(temp.name)
        metadata, samples = sample_product(temp_path, load_targets())
        expected = (
            metadata["platform_id"] == "G19"
            and metadata["orbital_slot"] == "GOES-East"
            and metadata["scene_id"] == "Full Disk"
            and metadata["rrqpe_units"] == "mm h-1"
        )
        if not expected:
            raise RuntimeError("UNEXPECTED_PRODUCT_METADATA")
        target_ids = {"san_ildefonso", "huaycoloro_main_channel", "catacaos"}
        covered = {sample["target_id"] for sample in samples if sample.get("coverage_valid")}
        all_covered = target_ids.issubset(covered)
        scan_end = utc(latest["scan_end"])
        delay = round((generated_at - scan_end).total_seconds() / 60, 2)
        recent_scans = [utc(row["scan_start"]) for row in objects if row.get("scan_start")]
        gaps = [round((b - a).total_seconds() / 60, 2) for a, b in zip(recent_scans, recent_scans[1:])]
        probe.update({
            "status": "KEEP_FOR_SHADOW_EVALUATION" if all_covered and delay <= 30 else "TECHNICAL_REVIEW_REQUIRED",
            "source_available": True,
            "latest_object": {**latest, "url": f"{BASE}/{latest['key']}", "sha256": hashlib.sha256(body).hexdigest()},
            "freshness": {
                "capture_delay_minutes": delay,
                "candidate_under_30_minutes": delay <= 30,
                "negative_delay_clock_warning": delay < 0,
            },
            "catalog": {
                **probe["catalog"],
                "observed_scan_gap_minutes": {
                    "min": min(gaps) if gaps else None,
                    "max": max(gaps) if gaps else None,
                },
            },
            "download": {"http_status": http["status"], "bytes": len(body)},
            "product_metadata": metadata,
            "samples": samples,
            "coverage": {
                "all_v08_pilots_covered": all_covered,
                "covered_target_ids": sorted(covered),
                "required_target_ids": sorted(target_ids),
                "sampling_role": "REPRESENTATIVE_5X5_PIXEL_TECHNICAL_PROBE_NOT_BASIN_ACCUMULATION",
            },
        })
    except Exception as exc:
        probe["error"] = {"type": type(exc).__name__, "message": str(exc)[:800]}
        probe["scientific_gate"]["missing_data_interpretation"] = "UNKNOWN_NOT_ZERO_OR_LOW_RISK"
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
    return probe


def main():
    generated_at = datetime.now(timezone.utc)
    probe = run(generated_at)
    previous = None
    if ARCHIVE.exists():
        try:
            previous = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
    archive = archive_result(previous, probe, generated_at)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    ARCHIVE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": probe["status"],
        "source_available": probe["source_available"],
        "latest_scan_end": (probe.get("latest_object") or {}).get("scan_end"),
        "capture_delay_minutes": (probe.get("freshness") or {}).get("capture_delay_minutes"),
        "all_v08_pilots_covered": (probe.get("coverage") or {}).get("all_v08_pilots_covered"),
        "archive_records": archive["summary"]["probe_record_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
