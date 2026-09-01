#!/usr/bin/env python3
"""Science-independent Sentinel-1 AUX_POEORB resolver for IBVF R2.

RESEARCH_ONLY / TEST_ONLY. Resolves valid overlapping precise-orbit files using
only frozen acquisition UTC and orbit-file metadata. No SAR response, rainfall,
known event dates, territorial outcomes, or case/control roles are read.
"""
from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from ibvf_sentinel1_r2_freeze_prerequisites import (
    HREF_RE,
    download,
    filename_interval,
    get,
    parse_utc,
    sha_file,
)

CREATION_RE = re.compile(r"_OPOD_(\d{8}T\d{6})_V", re.I)
RULE = "LATEST_CREATION_TIMESTAMP_AMONG_AUX_POEORB_FILES_WHOSE_VALIDITY_COVERS_FROZEN_ACQUISITION_UTC"


def parse_creation(name: str) -> datetime | None:
    m = CREATION_RE.search(name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def freeze_orbit(root: str, acquisition: str, side: str, tmp: Path) -> dict:
    t = parse_utc(acquisition)
    month_url = f"{root.rstrip('/')}/{t.year:04d}/{t.month:02d}/"
    try:
        html = get(month_url).text
    except Exception as exc:
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "directory_url": month_url,
            "status": "TRANSPORT_BLOCKED",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            "selection_rule": RULE,
            "error": repr(exc),
        }

    names = sorted(set(HREF_RE.findall(html)))
    covering = []
    for href in names:
        name = Path(href).name
        iv = filename_interval(name)
        if iv and iv[0] <= t <= iv[1]:
            covering.append({"href": href, "name": name, "interval": iv, "creation": parse_creation(name)})

    inventory = {
        "directory_url": month_url,
        "directory_inventory_success": True,
        "aux_poeorb_zip_count": len(names),
        "covering_count": len(covering),
        "covering_files": [x["name"] for x in covering],
        "covering_creation_utc": [x["creation"].isoformat() if x["creation"] else None for x in covering],
        "selection_rule": RULE,
        "selection_uses_science_values": False,
        "selection_uses_outcomes": False,
        "selection_uses_known_event_dates": False,
    }
    if not covering:
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "status": "MISSING",
            "scientific_data_status": "MISSING_PRECISE_ORBIT_RESOURCE_AFTER_SUCCESSFUL_DIRECTORY_INVENTORY",
            **inventory,
        }
    if any(x["creation"] is None for x in covering):
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "status": "AMBIGUOUS_BLOCK_R2_UNPARSEABLE_CREATION_TIMESTAMP",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            **inventory,
        }

    latest = max(x["creation"] for x in covering)
    winners = [x for x in covering if x["creation"] == latest]
    if len(winners) != 1:
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "status": "AMBIGUOUS_BLOCK_R2_LATEST_CREATION_TIE",
            "scientific_data_status": "UNKNOWN_NOT_MISSING",
            **inventory,
        }

    chosen = winners[0]
    href = chosen["href"]
    iv = chosen["interval"]
    url = urljoin(month_url, href)
    zpath = tmp / f"{side}.EOF.zip"
    dl = download(url, zpath)
    if dl["status"] != "SUCCESS":
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "selected_filename": chosen["name"],
            "selected_creation_utc": latest.isoformat(),
            **inventory,
            **dl,
        }

    try:
        with zipfile.ZipFile(zpath) as z:
            members = [n for n in z.namelist() if n.upper().endswith(".EOF")]
            if len(members) != 1:
                raise ValueError(f"expected one EOF member, got {members}")
            eof_path = tmp / f"{side}.EOF"
            eof_path.write_bytes(z.read(members[0]))
        eof_sha, eof_bytes = sha_file(eof_path)
        text = eof_path.read_text(encoding="utf-8", errors="replace")
        product_ok = "AUX_POEORB" in text or "AUX_POEORB" in chosen["name"]
        validity_ok = iv[0] <= t <= iv[1]
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "status": "PASS" if product_ok and validity_ok else "INTEGRITY_BLOCK_R2",
            **inventory,
            "selected_filename": chosen["name"],
            "selected_creation_utc": latest.isoformat(),
            "url": url,
            "validity_start": iv[0].isoformat(),
            "validity_stop": iv[1].isoformat(),
            "zip_sha256": dl["sha256"],
            "zip_bytes": dl["bytes"],
            "inner_eof_member": members[0],
            "inner_eof_sha256": eof_sha,
            "inner_eof_bytes": eof_bytes,
            "product_class_aux_poeorb_confirmed": product_ok,
            "validity_covers_acquisition": validity_ok,
        }
    except Exception as exc:
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "status": "INTEGRITY_BLOCK_R2",
            **inventory,
            "selected_filename": chosen["name"],
            "selected_creation_utc": latest.isoformat(),
            "url": url,
            "zip_sha256": dl.get("sha256"),
            "error": repr(exc),
        }
