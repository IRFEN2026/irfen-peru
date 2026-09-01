#!/usr/bin/env python3
"""Science-independent Sentinel-1 AUX_POEORB resolver for IBVF R2.

RESEARCH_ONLY / TEST_ONLY. Resolves valid overlapping precise-orbit files using
only frozen acquisition UTC and orbit-file metadata. No SAR response, rainfall,
known event dates, territorial outcomes, or case/control roles are read.
"""
from __future__ import annotations

import hashlib
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
DIRECTORY_SCOPE_OFFSETS = (-1, 0, 1)


def parse_creation(name: str) -> datetime | None:
    m = CREATION_RE.search(name)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def month_url(root: str, t: datetime, offset: int) -> str:
    serial = t.year * 12 + (t.month - 1) + offset
    year, month0 = divmod(serial, 12)
    return f"{root.rstrip('/')}/{year:04d}/{month0 + 1:02d}/"


def freeze_orbit(root: str, acquisition: str, side: str, tmp: Path) -> dict:
    t = parse_utc(acquisition)
    acquisition_month_url = month_url(root, t, 0)
    directory_urls = [month_url(root, t, x) for x in DIRECTORY_SCOPE_OFFSETS]
    inventories = []
    candidate_by_name = {}
    for directory_url in directory_urls:
        try:
            html = get(directory_url).text
        except Exception as exc:
            return {
                "side": side,
                "acquisition_utc": acquisition,
                "directory_url": acquisition_month_url,
                "directory_urls_inventory_scope": directory_urls,
                "directory_inventory_success": False,
                "directory_inventory_results": inventories,
                "status": "TRANSPORT_BLOCKED",
                "scientific_data_status": "UNKNOWN_NOT_MISSING",
                "selection_rule": RULE,
                "selection_uses_science_values": False,
                "selection_uses_outcomes": False,
                "selection_uses_known_event_dates": False,
                "error": repr(exc),
            }
        hrefs = sorted(set(HREF_RE.findall(html)))
        inventories.append({
            "directory_url": directory_url,
            "directory_inventory_success": True,
            "aux_poeorb_zip_count": len(hrefs),
        })
        for href in hrefs:
            name = Path(href).name
            prior = candidate_by_name.get(name)
            candidate = {"href": href, "name": name, "source_directory_url": directory_url}
            if prior is None or (directory_url, href) < (prior["source_directory_url"], prior["href"]):
                candidate_by_name[name] = candidate

    candidates = [candidate_by_name[x] for x in sorted(candidate_by_name)]
    covering = []
    for candidate in candidates:
        iv = filename_interval(candidate["name"])
        if iv and iv[0] <= t <= iv[1]:
            covering.append({
                **candidate,
                "interval": iv,
                "creation": parse_creation(candidate["name"]),
            })

    inventory = {
        "directory_url": acquisition_month_url,
        "directory_urls_inventory_scope": directory_urls,
        "directory_month_offsets": list(DIRECTORY_SCOPE_OFFSETS),
        "directory_inventory_success": True,
        "directory_inventory_results": inventories,
        "aux_poeorb_zip_count": len(candidates),
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
            "scientific_data_status": "MISSING_PRECISE_ORBIT_RESOURCE_AFTER_SUCCESSFUL_ADJACENT_MONTH_DIRECTORY_INVENTORY",
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
    source_directory_url = chosen["source_directory_url"]
    url = urljoin(source_directory_url, href)
    zpath = tmp / f"{side}.EOF.zip"
    dl = download(url, zpath)
    if dl["status"] != "SUCCESS":
        return {
            "side": side,
            "acquisition_utc": acquisition,
            "selected_filename": chosen["name"],
            "selected_creation_utc": latest.isoformat(),
            "selected_source_directory_url": source_directory_url,
            **inventory,
            **dl,
        }

    try:
        with zipfile.ZipFile(zpath) as z:
            members = sorted(n for n in z.namelist() if n.upper().endswith(".EOF"))
            if not members:
                raise ValueError("expected at least one EOF member, got none")
            payloads = [(n, z.read(n)) for n in members]
            payload_hashes = {hashlib.sha256(b).hexdigest() for _, b in payloads}
            if len(payload_hashes) != 1:
                raise ValueError(f"multiple EOF members differ by payload hash: {members}")
            # STEP may duplicate the same EOF bytes at ZIP root and under a web-root path.
            # Treat that strictly as archive layout only: identical bytes are accepted;
            # differing bytes remain an integrity block. A deterministic member is recorded.
            root_members = [n for n, _ in payloads if "/" not in n]
            chosen_member = sorted(root_members or members)[0]
            chosen_payload = next(b for n, b in payloads if n == chosen_member)
            eof_path = tmp / f"{side}.EOF"
            eof_path.write_bytes(chosen_payload)
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
            "selected_source_directory_url": source_directory_url,
            "url": url,
            "validity_start": iv[0].isoformat(),
            "validity_stop": iv[1].isoformat(),
            "zip_sha256": dl["sha256"],
            "zip_bytes": dl["bytes"],
            "inner_eof_member": chosen_member,
            "inner_eof_member_count": len(members),
            "inner_eof_duplicate_payloads_identical": len(members) > 1,
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
            "selected_source_directory_url": source_directory_url,
            "url": url,
            "zip_sha256": dl.get("sha256"),
            "error": repr(exc),
        }
