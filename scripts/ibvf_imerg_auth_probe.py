#!/usr/bin/env python3
"""Probe authenticated raw-byte transport for one IMERG Final V07 granule.

RESEARCH_ONLY / TEST_ONLY. The probe never treats missing credentials or a
transport/authentication failure as missing scientific data. It chooses the
first CMR-resolved granule on the requested event date and then selects only an
actual HDF5 byte URL (prefer GES DISC HTTPS; never a CMR virtual-directory,
landing page, credentials endpoint, or search URL). It downloads only when
EARTHDATA_TOKEN is configured, records SHA-256/byte count, then removes the raw
file so CI artifacts remain small.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import ibvf_imerg_inventory as inv


def is_hdf5_object_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.lower().endswith((".hdf5", ".h5"))


def select_raw_hdf5_url(links: list[str]) -> tuple[str | None, str]:
    hdf = sorted({u for u in links if is_hdf5_object_url(u)})
    https_gesdisc = [u for u in hdf if u.startswith("https://data.gesdisc.earthdata.nasa.gov/")]
    if https_gesdisc:
        return https_gesdisc[0], "GES_DISC_HTTPS_HDF5"
    https = [u for u in hdf if u.startswith("https://")]
    if https:
        return https[0], "HTTPS_HDF5"
    s3 = [u for u in hdf if u.startswith("s3://")]
    if s3:
        return s3[0], "S3_HDF5_REQUIRES_SEPARATE_CREDENTIAL_FLOW"
    return None, "NO_HDF5_OBJECT_URL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--event-date", required=True, type=date.fromisoformat)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    args = ap.parse_args()

    source = json.loads(args.inventory.read_text(encoding="utf-8"))
    rows = [g for g in source.get("granules", []) if g.get("date") == args.event_date.isoformat()]
    rows.sort(key=lambda x: (x.get("start_hhmmss") or "", x.get("producer_granule_id") or ""))

    report: dict[str, Any] = {
        "schema_version": "irfen-ibvf-imerg-auth-probe-v0.2",
        "generated_at": inv.now(),
        "case_id": "cashahuacra_2015-03-23",
        "deployment_status": "RESEARCH_ONLY",
        "test_only": True,
        "production_use": False,
        "production_ready": False,
        "operational_alerting_enabled": False,
        "uses_operational_event_none_labels": False,
        "territorial_activation_evidence_blinded": True,
        "product": {"short_name": inv.SHORT_NAME, "version": inv.VERSION},
        "event_date": args.event_date.isoformat(),
        "probe_scope": "FIRST_CMR_RESOLVED_EVENT_DAY_GRANULE_ONLY",
        "scientific_data_presence_source": "CMR_METADATA",
        "missing_data_rule": "AUTH_OR_TRANSPORT_FAILURE_IS_UNKNOWN_NOT_MISSING",
        "link_selection_rule": "ACTUAL_HDF5_OBJECT_URL_ONLY_PREFER_GES_DISC_HTTPS",
        "serious_modeling_gate": "CLOSED_MINIMUM_DATASET_NOT_REACHED",
    }

    if not rows:
        report["probe_status"] = "NO_EVENT_DAY_GRANULE_IN_INVENTORY"
        report["scientific_data_status"] = "UNKNOWN_REVIEW_INVENTORY"
    else:
        row = rows[0]
        links = row.get("data_links") or []
        report["producer_granule_id"] = row.get("producer_granule_id")
        report["start_hhmmss"] = row.get("start_hhmmss")
        report["cmr_candidate_link_count"] = len(links)
        url, selection = select_raw_hdf5_url(links)
        report["raw_link_selection"] = selection
        if not url:
            report["probe_status"] = "NO_HDF5_OBJECT_URL_IN_CMR_METADATA"
            report["scientific_data_status"] = "PRESENT_METADATA_RAW_LINK_UNRESOLVED"
        elif url.startswith("s3://"):
            report["selected_url"] = url
            report["probe_status"] = "S3_CREDENTIAL_FLOW_NOT_IMPLEMENTED_IN_THIS_PROBE"
            report["scientific_data_status"] = "UNKNOWN_NOT_MISSING"
        else:
            report["selected_url"] = url
            token = os.environ.get("EARTHDATA_TOKEN")
            args.work_dir.mkdir(parents=True, exist_ok=True)
            raw = args.work_dir / Path(urlparse(url).path).name
            result = inv.acquire_one(url, raw, token)
            report["raw_byte_probe"] = result
            report["probe_status"] = result.get("status")
            report["scientific_data_status"] = (
                "PRESENT_RAW_BYTES_FROZEN_ONE_GRANULE"
                if result.get("status") == "SUCCESS"
                else result.get("scientific_data_status", "UNKNOWN_NOT_MISSING")
            )
            if raw.exists():
                raw.unlink()
            report["raw_file_retained"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "probe_status": report.get("probe_status"),
        "scientific_data_status": report.get("scientific_data_status"),
        "producer_granule_id": report.get("producer_granule_id"),
        "raw_link_selection": report.get("raw_link_selection"),
        "selected_url": report.get("selected_url"),
        "raw_byte_probe": report.get("raw_byte_probe"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
