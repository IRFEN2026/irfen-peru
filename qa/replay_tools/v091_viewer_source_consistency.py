#!/usr/bin/env python3
"""IRFEN v0.9.1 · ¿los valores de lluvia del paquete del visor coinciden con los archivos de origen de main?

RESEARCH_ONLY. Lectura pura. Recalcula de forma independiente, desde los archivos IMERG de main con los que se construyó
el paquete (su `main_sha`), las ventanas que muestra el visor:

* puntos de río con `catchment:<id>`: media de cuenca, ventanas 1/3/6/24/72 h (archivo por cuenca);
* puntos con `zone:<id>`: media de zona, mismas ventanas (archivo del norte) y su copia en `rain.north_zones`;
* cada `rain_ref` usado por un checkpoint existe en el paquete; las poblaciones ANA no usan `catchment:`.

Una ventana con alguna media hora ausente o con cobertura < 80 % debe ser nula en ambos lados (nunca 0 mm).

    python3 qa/replay_tools/v091_viewer_source_consistency.py --bundle current/surveillance_view_v0_1.json \
        --catchments <main_sha:data/v09/rain/imerg_early_catchments_v0_1.json> --north <main_sha:data/v09/rain/imerg_early_north_v0_1.json>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

WINDOWS = (1, 3, 6, 24, 72)
TOL_MM = 0.011  # values are rounded to 0.01 / 0.001 mm in the bundle
MIN_COV = 80.0


def iso(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def catchment_windows(arch: dict, cid: str) -> tuple[str | None, dict]:
    ids = [t["checkpoint_id"] for t in arch["targets"]]
    if cid not in ids:
        return None, {}
    k = ids.index(cid)
    by = {}
    for g in arch["granules"]:
        t = iso(g["time_utc"])
        by[t] = None if t in by else (g["rate_mm_hr"][k], g["covered_pct"][k])  # duplicate time: ambiguous
    last = max(by)
    out = {}
    for h in WINDOWS:
        sel = [by.get(last - timedelta(minutes=30 * j)) for j in range(2 * h)]
        ok = all(x is not None and x[0] is not None and x[1] is not None and x[1] >= MIN_COV for x in sel)
        out[f"{h}h"] = round(sum(x[0] * 0.5 for x in sel), 3) if ok else None
    return (last + timedelta(minutes=30)).isoformat(), out


def zone_windows(arch: dict, zid: str, end: datetime) -> dict:
    by = {iso(g["time_utc"]): (g.get("targets") or {}).get(zid, {}).get("rate_mm_hr") for g in arch["granules"]}
    out = {}
    for h in WINDOWS:
        sel = [by.get(end - timedelta(minutes=30 * j)) for j in range(1, 2 * h + 1)]
        out[f"{h}h"] = None if any(v is None for v in sel) else round(sum(v * 0.5 for v in sel), 3)
    return out


def close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOL_MM


def check(bundle: dict, catchments: dict | None, north: dict | None) -> dict:
    sm = bundle.get("semaforo") or {}
    refs = sm.get("rain_refs") or {}
    mism, checked = [], dict(catchment=0, zone=0, zone_copy=0, refs=0)
    for cp in sm.get("checkpoints", []):
        ref = cp.get("rain_ref")
        if ref:
            checked["refs"] += 1
            if ref not in refs:
                mism.append(dict(kind="ref_missing", checkpoint=cp["id"], ref=ref))
            if cp["type"] != "rio" and ref.startswith("catchment:"):
                mism.append(dict(kind="ana_with_catchment", checkpoint=cp["id"], ref=ref))
    for ref, rr in refs.items():
        win = ((rr.get("imerg") or {}).get("windows")) or {}
        if ref.startswith("catchment:") and catchments is not None:
            end, exp = catchment_windows(catchments, ref.split(":", 1)[1])
            checked["catchment"] += 1
            if end is None:
                mism.append(dict(kind="catchment_not_in_archive", ref=ref))
                continue
            if (rr.get("imerg") or {}).get("end_utc") and iso(rr["imerg"]["end_utc"]) != iso(end):
                mism.append(dict(kind="end_mismatch", ref=ref, bundle=rr["imerg"]["end_utc"], source=end))
            for k, v in exp.items():
                if k in win and not close(win[k], v):
                    mism.append(dict(kind="window_mismatch", ref=ref, window=k, bundle=win[k], source=v))
        elif ref.startswith("zone:") and north is not None and (rr.get("imerg") or {}).get("end_utc"):
            zid = ref.split(":", 1)[1]
            exp = zone_windows(north, zid, iso(rr["imerg"]["end_utc"]))
            checked["zone"] += 1
            for k, v in exp.items():
                if k in win and not close(win[k], v):
                    mism.append(dict(kind="window_mismatch", ref=ref, window=k, bundle=win[k], source=v))
    for f in ((bundle.get("rain") or {}).get("north_zones") or {}).get("zones", {}).get("features", []):
        p = f["properties"]
        rr = refs.get("zone:" + p["zone_id"])
        if not rr:
            continue
        checked["zone_copy"] += 1
        for k, w in (p.get("windows") or {}).items():
            v = w.get("mm") if w.get("status") == "COMPLETA" else None
            if k in rr["imerg"]["windows"] and not close(v, rr["imerg"]["windows"][k]):
                mism.append(dict(kind="zone_copy_mismatch", zone=p["zone_id"], window=k, layer=v, semaforo=rr["imerg"]["windows"][k]))
    # department summary: recent rain per contributing area (rain.catchments), never a departmental mean
    cr = (bundle.get("rain") or {}).get("catchments") or {}
    if cr.get("status") == "OK" and catchments is not None:
        checked["summary_catchments"] = 0
        rivers = {c["id"]: c["department"] for c in sm.get("checkpoints", []) if c["type"] == "rio"}
        for dep, rows in cr["departments"].items():
            for r in rows:
                checked["summary_catchments"] += 1
                if rivers.get(r["id"]) != dep:
                    mism.append(dict(kind="summary_wrong_department", checkpoint=r["id"], department=dep))
                end, exp = catchment_windows(catchments, r["id"])
                if end is None:
                    mism.append(dict(kind="summary_not_in_archive", checkpoint=r["id"]))
                    continue
                if cr.get("observation_end_utc") and iso(cr["observation_end_utc"]) != iso(end):
                    mism.append(dict(kind="summary_end_mismatch", checkpoint=r["id"], bundle=cr["observation_end_utc"], source=end))
                for k, v in exp.items():
                    if k in r["windows"] and not close(r["windows"][k], v):
                        mism.append(dict(kind="summary_window_mismatch", checkpoint=r["id"], window=k, bundle=r["windows"][k], source=v))
        ids = {t["checkpoint_id"] for t in catchments["targets"]}
        listed = {r["id"] for rows in cr["departments"].values() for r in rows}
        if listed != ids & set(rivers):
            mism.append(dict(kind="summary_target_set_mismatch", missing=sorted((ids & set(rivers)) - listed)[:10], extra=sorted(listed - ids)[:10]))
        named = {x["id"] for rows in (cr.get("without_catchment") or {}).values() for x in rows}
        checked["summary_without_catchment"] = len(named)
        if named != set(rivers) - ids:  # every river point without a verified area is named, and only those
            mism.append(dict(kind="summary_without_catchment_mismatch", expected=sorted(set(rivers) - ids), named=sorted(named)))
    return dict(schema_version="irfen_v091_viewer_source_consistency_v0_1", deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                checked=checked, mismatches=mism, ok=not mism and checked["refs"] > 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--catchments", type=Path)
    ap.add_argument("--north", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else None
    rep = check(load(a.bundle), load(a.catchments), load(a.north))
    if a.out:
        a.out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(dict(ok=rep["ok"], checked=rep["checked"], mismatches=rep["mismatches"][:10]), ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
