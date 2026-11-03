#!/usr/bin/env python3
"""Independent, fail-closed scientific QA of IRFEN v0.9.1 coast checkpoints.

Only archived evidence; never infers flood hazard, alters colours, downloads data or publishes.
Run after checking out code branch with current main's catchment archive and geometry available.
python scripts/v091_independent_science_audit.py --inventory ... [--archive ...] [--config ...] [--geometry ...] [--output ...] [--strict]
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYDRO = ROOT / "data/v09/research/semaforo/checkpoint_hydrology_v0_1.json"
RAIN = ROOT / "data/v09/rain/imerg_early_catchments_v0_1.json"
TARGETS = ROOT / "config/v091_catchment_rain_targets_v0_1.json"
IMPORTANT = ("TUM-R-ZARUMILLA-MEDIO", "LIM-R-RIMAC-ALTO",
             "ARE-R-TAMBO-BAJO", "ICA-R-SAN_JUAN-BAJO")


def dt(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("time without UTC offset")
    return t.astimezone(timezone.utc)


def audit(inventory, archive=None, config=None, geometry_raw=None):
    issues = []
    def flag(level, code, point=None, details=None):
        issues.append(dict(level=level, code=code, checkpoint=point, detail=details))
    records = inventory.get("checkpoints", [])
    ids = [r.get("id") for r in records]
    if len(ids) != len(set(ids)) or not records:
        flag("ERROR", "INVENTORY_DUPLICATE_OR_EMPTY")
    by_id = {r.get("id"): r for r in records}
    classified = Counter()
    for r in records:
        cid, typ = r.get("id"), r.get("type")
        q3 = r.get("q3_contributing_area") or {}
        st = q3.get("status")
        classified[typ] += 1
        if not r.get("q1_coordinate", {}).get("source") or not r.get("q2_water_body"):
            flag("ERROR", "MISSING_PROVENANCE", cid)
        if not r.get("q5_missing"):
            flag("ERROR", "NO_EXPLICIT_LIMITATIONS", cid)
        if typ != "rio":
            if st == "APORTACION_DELIMITADA_EXPERIMENTAL" or q3.get("area_km2"):
                flag("ERROR", "ANA_POPULATION_ASSIGNED_UNVERIFIED_CATCHMENT", cid)
            continue
        if st == "APORTACION_DELIMITADA_EXPERIMENTAL":
            sn = q3.get("snap") or {}
            a = q3.get("area_km2")
            if not isinstance(a, (float, int)) or not math.isfinite(a) or a <= 0:
                flag("ERROR", "CATCHMENT_AREA_INVALID", cid)
            if not isinstance(sn.get("snap_km"), (int, float)) or sn["snap_km"] > 1.0:
                flag("ERROR", "CHANNEL_SNAP_GT_1_KM", cid, sn.get("snap_km"))
            if q3.get("touches_crop_edge"):
                flag("ERROR", "TRUNCATED_WATERSHED_PROMOTED", cid)
            ratio = q3.get("hydrorivers_ratio")
            if ratio is not None and (not isinstance(ratio, (int, float)) or not 0.99 <= ratio <= 1.01):
                flag("REVIEW", "HYDRORIVERS_RATIO_OUTSIDE_1_PCT", cid, ratio)
        elif r.get("evaluation_status") == "EVALUABLE_LLUVIA_DE_CUENCA":
            flag("ERROR", "UNVERIFIED_CATCHMENT_PROMOTED", cid)
    for cid in IMPORTANT:
        r = by_id.get(cid)
        if not r:
            flag("REVIEW", "PRIORITY_POINT_NOT_FOUND", cid)
        elif (r.get("q3_contributing_area") or {}).get("status") == "APORTACION_DELIMITADA_EXPERIMENTAL":
            flag("ERROR", "KNOWN_PROBLEMATIC_REACH_PROMOTED", cid)

    represented = set()
    archive_stats = dict(available=bool(archive), n_targets=0, n_granules=0, newest_utc=None)
    if config is not None:
        requested = config.get("targets", [])
        if len(set(requested)) != len(requested):
            flag("ERROR", "TARGET_CONFIG_DUPLICATES")
        if config.get("geometry_sha256") and geometry_raw is not None:
            actual = hashlib.sha256(geometry_raw).hexdigest()
            if actual != config["geometry_sha256"]:
                flag("ERROR", "GEOMETRY_HASH_MISMATCH", details=actual)
        if any(config.get(k) != v for k, v in dict(deployment_status="RESEARCH_ONLY",
               test_mode="TEST_ONLY", production_use=False, public_alerting=False,
               notifications_enabled=False, activation_gate="BLOCKED", map_publishable=False).items()):
            flag("ERROR", "CONFIG_RESEARCH_GUARDS_MISSING")
        for cid in requested:
            r = by_id.get(cid)
            if not r or r.get("type") != "rio" or r.get("q3_contributing_area", {}).get("status") != "APORTACION_DELIMITADA_EXPERIMENTAL":
                flag("ERROR", "TARGET_WITHOUT_VERIFIED_EXPERIMENTAL_GEOMETRY", cid)
            else:
                represented.add(cid)
    if archive is not None:
        if any(archive.get(k) != v for k,v in dict(deployment_status="RESEARCH_ONLY",
            test_mode="TEST_ONLY", production_use=False, public_alerting=False,
            notifications_enabled=False, activation_gate="BLOCKED", map_publishable=False).items()):
            flag("ERROR", "ARCHIVE_RESEARCH_GUARDS_MISSING")
        ar_targets = archive.get("targets", [])
        tids = [t.get("checkpoint_id") for t in ar_targets]
        archive_stats["n_targets"] = len(tids)
        if len(tids) != len(set(tids)):
            flag("ERROR", "ARCHIVE_TARGET_DUPLICATES")
        if config is not None and tids != config.get("targets", []):
            flag("ERROR", "ARCHIVE_TARGET_ORDER_OR_CONTENT_MISMATCH")
        if config is not None and archive.get("geometry_sha256") != config.get("geometry_sha256"):
            flag("ERROR", "ARCHIVE_GEOMETRY_HASH_MISMATCH")
        for cid in tids:
            r = by_id.get(cid)
            if not r or r.get("type") != "rio" or r.get("q3_contributing_area", {}).get("status") != "APORTACION_DELIMITADA_EXPERIMENTAL":
                flag("ERROR", "ARCHIVE_ID_WITHOUT_DELIMITED_CATCHMENT", cid)
        seen = set()
        for g in archive.get("granules", []):
            stamp = g.get("time_utc")
            try:
                t = dt(stamp)
            except (ValueError, TypeError, AttributeError):
                flag("ERROR", "INVALID_UTC_GRANULE_TIME", details=stamp)
                continue
            if t in seen:
                flag("ERROR", "DUPLICATE_GRANULE_TIME", details=stamp)
            seen.add(t)
            vals, cov = g.get("rate_mm_hr"), g.get("covered_pct")
            if not isinstance(vals, list) or not isinstance(cov, list) or len(vals)!=len(tids) or len(cov)!=len(tids):
                flag("ERROR", "MISALIGNED_GRANULE_VECTORS", details=stamp)
                continue
            for i, (v, c) in enumerate(zip(vals,cov)):
                if not isinstance(c,(int,float)) or not math.isfinite(c) or c < 0 or c > 100:
                    flag("ERROR", "INVALID_SPATIAL_COVERAGE", tids[i], stamp)
                if v is not None and (not isinstance(v,(int,float)) or not math.isfinite(v) or v < 0):
                    flag("ERROR", "INVALID_RAIN_RATE", tids[i], stamp)
                if v is not None and c == 0:
                    flag("ERROR", "ZERO_COVERAGE_WITH_VALUE", tids[i], stamp)
        archive_stats["n_granules"] = len(archive.get("granules", []))
        archive_stats["newest_utc"] = max(seen).isoformat() if seen else None
    return dict(schema_version="irfen_v091_independent_science_audit_v0_1",
        deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
        production_use=False, public_alerting=False, notifications_enabled=False,
        activation_gate="BLOCKED",
        inventory_count=len(records), types=dict(classified),
        delimited_rivers=sum(r.get("type")=="rio" and r.get("q3_contributing_area", {}).get("status")=="APORTACION_DELIMITADA_EXPERIMENTAL" for r in records),
        archive=archive_stats, issues=issues,
        errors=sum(i["level"]=="ERROR" for i in issues), review_items=sum(i["level"]=="REVIEW" for i in issues),
        caveats=["HydroSHEDS 15 arcsecond is experimental, not official flood mapping.",
          "A ±1% HydroRIVERS area comparison does not independently establish hydraulic connectivity.",
          "IMERG satellite rain is not measured streamflow; rainfall and flood impacts must not be conflated.",
          "Two 80% geometric overlap thresholds are heuristic coverage checks, not scientifically calibrated hazard thresholds.",
          "Historical rainfall-response skill, temporal lag and independent negative controls are not validated here."])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, default=HYDRO)
    p.add_argument("--archive", type=Path, default=RAIN)
    p.add_argument("--config", type=Path, default=TARGETS)
    p.add_argument("--output", type=Path)
    p.add_argument("--strict", action="store_true")
    a = p.parse_args()
    def load_optional(x):
        return json.loads(x.read_text(encoding="utf-8")) if x.is_file() else None
    inv = json.loads(a.inventory.read_text(encoding="utf-8"))
    cfg = load_optional(a.config)
    arch = load_optional(a.archive)
    geom = None
    if cfg and cfg.get("geometry_path"):
        path = ROOT / cfg["geometry_path"]
        if path.is_file():
            geom = path.read_bytes()
    out = audit(inv, arch, cfg, geom)
    msg = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(msg, encoding="utf-8")
    print(msg)
    return int(a.strict and out["errors"] > 0)

if __name__ == "__main__":
    raise SystemExit(main())
