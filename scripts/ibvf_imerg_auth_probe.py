#!/usr/bin/env python3
"""Probe authenticated raw-byte transport for one IMERG Final V07 granule.

RESEARCH_ONLY / TEST_ONLY. The probe never treats missing credentials or a
transport/authentication failure as missing scientific data. It chooses the
first CMR-resolved granule on the requested event date, downloads it only when
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

import ibvf_imerg_inventory as inv


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
        "schema_version": "irfen-ibvf-imerg-auth-probe-v0.1",
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
        report["cmr_data_link_count"] = len(links)
        if not links:
            report["probe_status"] = "NO_DATA_LINK_IN_CMR_METADATA"
            report["scientific_data_status"] = "PRESENT_METADATA_RAW_LINK_UNRESOLVED"
        else:
            url = links[0]
            report["selected_url"] = url
            token = os.environ.get("EARTHDATA_TOKEN")
            args.work_dir.mkdir(parents=True, exist_ok=True)
            raw = args.work_dir / Path(url.split("?", 1)[0]).name
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
        "raw_byte_probe": report.get("raw_byte_probe"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
