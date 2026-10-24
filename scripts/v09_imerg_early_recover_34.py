#!/usr/bin/env python3
"""One-off research recovery for 34 confirmed missing NASA IMERG Early v07 slots.
Only on an isolated GitHub branch, manual scope, bounded download, artifact-only.
NEVER updates live archives, map, engine, Pages or production.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SNAPSHOT = ROOT / "data/v09/capture_ledger/snapshots/20261013T0000Z_20261020T0000Z/ledger_v0_1.json"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
              production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED",
              missing_data_rule="UNKNOWN_NOT_LOW_RISK", decision_thresholds=None,
              hydraulic_factors=None)
MAX_PER_SHARD = 16
MAX_BYTES_SHARD = 150_000_000
MAX_BYTES_OBJECT = 12_000_000
SLOT_COUNT = 34

def iso(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def expected_rows(snapshot):
    assert snapshot.get("deployment_status") == "RESEARCH_ONLY"
    assert snapshot.get("missing_data_rule") == "UNKNOWN_NOT_LOW_RISK"
    rows = [r for r in snapshot["intervals"] if r.get("product") == "IMERG_EARLY_HH"
            and r.get("state") == "MISSING_RETRYING"
            and r.get("catalog", {}).get("response_complete") is True
            and r.get("catalog", {}).get("listed")]
    rows.sort(key=lambda r: r["interval_start_utc"])
    slots = [r["interval_start_utc"] for r in rows]
    if len(rows) != SLOT_COUNT or len(set(slots)) != SLOT_COUNT:
        raise RuntimeError("SCOPE_MISMATCH: expected exactly 34 unique NASA-listed slots")
    if any(not s.startswith(("2026-10-15T", "2026-10-16T")) for s in slots):
        raise RuntimeError("SCOPE_MISMATCH: outside 15/16 October 2026")
    return rows

def select_shard(rows, shard):
    if shard not in (0, 1, 2):
        raise ValueError("INVALID_SHARD")
    chosen = rows[shard * MAX_PER_SHARD:(shard + 1) * MAX_PER_SHARD]
    if len(chosen) != (16 if shard < 2 else 2):
        raise RuntimeError("UNEXPECTED_SHARD_LENGTH")
    return chosen

def checked_catalog_match(row, by_time):
    import probe_imerg_early_live as probe
    start = datetime.fromisoformat(row["interval_start_utc"].replace("Z", "+00:00"))
    matches = by_time.get(start, [])
    if len(matches) != 1:
        raise RuntimeError("NASA_CATALOG_MISSING_OR_AMBIGUOUS")
    t, filename, granule = matches[0]
    if not filename.endswith(".HDF5") or not filename.endswith(".V07B.HDF5") and ".V07" not in filename:
        raise RuntimeError("PRODUCT_VERSION_MISMATCH")
    listed = row["catalog"]["listed"]
    if len(listed) != 1:
        raise RuntimeError("FROZEN_CATALOG_AMBIGUOUS")
    historical_title = listed[0].get("title", "")
    if filename != historical_title and filename not in historical_title:
        raise RuntimeError("NASA_CATALOG_CHANGED_GRANULE")
    if t != start or not probe.timestamp_from_filename(filename) == start:
        raise RuntimeError("TIME_MISMATCH")
    return filename, granule

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True, choices=[0, 1, 2])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if os.getenv("GITHUB_REF_NAME") != "research/imerg-early-recovery-34-20261020":
        raise SystemExit("BRANCH_GATE_BLOCKED")
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("EARTHDATA_TOKEN_MISSING")
    out = args.out.resolve()
    if ROOT == out or ROOT in out.parents:
        raise SystemExit("REPO_OUTPUT_FORBIDDEN")
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    selected = select_shard(expected_rows(snapshot), args.shard)
    import earthaccess
    import probe_imerg_early_live as probe
    import v09_imerg_north_archive as live
    probe.earthdata_preflight()
    earthaccess.login(strategy="environment")
    found = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07",
                                    temporal=("2026-10-15T00:00:00Z", "2026-10-17T00:00:00Z"),
                                    count=140)
    by_time = {}
    for indexed in probe.index_granules(found):
        by_time.setdefault(indexed[0], []).append(indexed)
    # Fail closed before the first download if any object is absent or ambiguous.
    checked = [(r, *checked_catalog_match(r, by_time)) for r in selected]
    targets = live.load_targets()
    if not targets:
        raise SystemExit("NO_TARGETS")
    result = dict(schema_version="0.1", **GUARDS, archive_id="irfen-v09-imerg-early-manual-recovery:v0.1",
                  recovered=True, recovery_scope="34_missing_20261015_20261016",
                  source=dict(product="GPM_3IMERGHHE", version="07", provider="NASA GES DISC"),
                  shard=args.shard, target_ids=sorted(x["id"] for x in targets),
                  requested_slots=[r["interval_start_utc"] for r in selected], granules=[], errors=[],
                  map_publishable=False, engine_consumable=False,
                  downloaded_file_content_stored=False)
    used_bytes = 0
    with tempfile.TemporaryDirectory(prefix="irfen_imerg_recovery_") as td:
        for row, filename, granule in checked:
            slot = row["interval_start_utc"]
            try:
                # Each object is downloaded once, the temporary HDF5 is never committed.
                paths = earthaccess.download([granule], local_path=td, threads=1, show_progress=False)
                path = next((Path(p) for p in paths if Path(p).name == filename), None)
                if not path or not path.is_file():
                    raise RuntimeError("DOWNLOAD_MISSING")
                size = path.stat().st_size
                if size > MAX_BYTES_OBJECT or used_bytes + size > MAX_BYTES_SHARD:
                    raise RuntimeError("BYTE_BUDGET_EXCEEDED")
                used_bytes += size
                digest = sha_file(path)
                lat, lon, values, units = probe.read_grid(path)
                if not any(v in units.lower() for v in ("mm/hr", "mm h-1", "mm/hour")):
                    raise RuntimeError("UNEXPECTED_UNITS")
                stats = {}
                for target in targets:
                    value, meta = probe.polygon_mean(target["geometry"], lat, lon, values)
                    stats[target["id"]] = dict(rate_mm_hr=None if value is None else round(value, 4),
                        accum_30min_mm=None if value is None else round(value * 0.5, 4),
                        valid_cells=meta["valid_cells"], cells_intersected=meta["cells_intersected"],
                        covered_pct=meta["covered_geometry_pct"])
                result["granules"].append(dict(time_utc=slot, granule=filename,
                    source_catalog_id=row["catalog"]["listed"][0]["id"],
                    recovered=True, recovered_at_utc=iso(datetime.now(timezone.utc)),
                    sha256=digest, size_bytes=size, retrieved_from="NASA_GES_DISC",
                    units=units, targets=stats))
            except Exception as exc:
                result["errors"].append(dict(time_utc=slot, error=type(exc).__name__ + ": " + str(exc)[:160]))
                # Error is explicitly NOT zero rainfall. Stop on network or budget failure.
                if "BUDGET" in str(exc) or "HTTP" in str(exc) or "DOWNLOAD" in str(exc):
                    break
            finally:
                for p in Path(td).glob("*.HDF5"):
                    p.unlink(missing_ok=True)
            time.sleep(1)
    result["downloaded_bytes_total"] = used_bytes
    result["finished_at_utc"] = iso(datetime.now(timezone.utc))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise SystemExit("WILL_NOT_OVERWRITE_EXISTING")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"shard={args.shard} recovered={len(result['granules'])}/{len(selected)} errors={len(result['errors'])} bytes={used_bytes}")
    if result["errors"] or len(result["granules"]) != len(selected):
        raise SystemExit("PARTIAL_RECOVERY_REVIEW_REQUIRED")

if __name__ == "__main__":
    main()
