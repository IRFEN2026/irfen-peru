#!/usr/bin/env python3
"""IRFEN v0.9 — archivo TEST_ONLY y continuo de IMERG Early (GPM_3IMERGHHE, 30 min) para las zonas del norte.

Reutiliza las funciones del probe v0.8 (scripts/probe_imerg_early_live.py: lectura del HDF5, media ponderada por
área de celda dentro del polígono, nombres y tiempos de gránulo, preflight de Earthdata). La diferencia es la
política: aquí se descarga cada media hora que falte en las últimas `WINDOW_HOURS` horas (acotado por ejecución),
para que las ventanas de 1/3/6/24 h se puedan reconstruir sin huecos. Objetivos:

* las cuencas con geometría verificada de config/v09_north_surveillance_zones_v0_1.json;
* las provincias de Piura (polígonos INEI referenciales archivados), como contexto administrativo: la media sobre
  la provincia no es la lluvia de ninguna quebrada.

IMERG Early tiene horas de latencia: nunca se presenta como observación en tiempo real. Un fallo de Earthdata se
registra y nunca se interpreta como lluvia cero. El archivo solo se reescribe cuando entra un gránulo nuevo o cambia
el estado de la fuente.

  python scripts/v09_imerg_north_archive.py      # runner con EARTHDATA_TOKEN
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
BOUNDARIES_LATEST = ROOT / "data/v09/admin_boundaries/latest.json"
OUT = ROOT / "data/v09/rain/imerg_early_north_v0_1.json"
WINDOW_HOURS = 30
MAX_DOWNLOADS_PER_RUN = 16
RETAIN_HOURS = 96
DAILY_HISTORY_MAX = 400
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)


def load_targets() -> list[dict]:
    from shapely.geometry import shape
    from shapely.ops import unary_union

    cfg = json.loads(ZONES.read_text(encoding="utf-8"))
    targets = []
    for z in cfg["zones"]:
        if z["zone_type"] == "BASIN_GEOMETRY":
            feats = json.loads((ROOT / z["geometry_path"]).read_text(encoding="utf-8"))
            feats = feats.get("features") or [feats]
            geom = unary_union([shape(f["geometry"]) for f in feats]).buffer(0)
            targets.append(dict(id=z["zone_id"], name=z["display_name"], kind="BASIN_POLYGON", geometry=geom,
                                geometry_sha256=z["geometry_sha256"]))
    if BOUNDARIES_LATEST.is_file():
        latest = json.loads(BOUNDARIES_LATEST.read_text(encoding="utf-8"))
        fc = json.loads((ROOT / latest["path"]).read_text(encoding="utf-8"))
        for f in fc["features"]:
            p = f["properties"]
            if p["NOMBDEP"] == "PIURA":
                targets.append(dict(id=f"piura_province_context:{p['NOMBPROV']}", name=f"Provincia {p['NOMBPROV'].title()} (Piura)",
                                    kind="ADMIN_PROVINCE_POLYGON_INEI_REFERENTIAL", geometry=shape(f["geometry"]).buffer(0),
                                    geometry_sha256=latest["sha256"]))
    return targets


def empty_archive() -> dict:
    return dict(schema_version="0.1", archive_id="irfen-v09-imerg-early-north:v0.1", **GUARDS, map_publishable=False,
                source=dict(product="GPM_3IMERGHHE", version="07", provider="NASA GES DISC via earthaccess",
                            nature="satellite estimate, half-hourly, Early run (hours of latency); not a real-time observation"),
                policy=dict(window_hours=WINDOW_HOURS, max_downloads_per_run=MAX_DOWNLOADS_PER_RUN, retain_hours=RETAIN_HOURS,
                            sample="area-weighted mean of 0.1° cells intersecting the target polygon (probe_imerg_early_live.polygon_mean)"),
                targets={}, granules=[], status=dict(state="NEVER_CHECKED"))


def main() -> int:
    if not os.getenv("EARTHDATA_TOKEN"):
        print("::warning::EARTHDATA_TOKEN missing: nothing captured (not a zero-rain result)")
        return 0
    import earthaccess
    import probe_imerg_early_live as probe

    now = datetime.now(timezone.utc)
    archive = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else empty_archive()
    before = json.dumps(archive, sort_keys=True)
    targets = load_targets()
    archive["targets"] = {t["id"]: dict(name=t["name"], kind=t["kind"], geometry_sha256=t["geometry_sha256"]) for t in targets}
    have = {g["granule"] for g in archive["granules"] if set(archive["targets"]) <= set(g["targets"])}
    try:
        probe.earthdata_preflight()
        earthaccess.login(strategy="environment")
        found = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07",
                                        temporal=((now - timedelta(hours=WINDOW_HOURS)).isoformat(), now.isoformat()), count=80)
    except Exception as exc:  # noqa: BLE001 - recorded as a source failure, never as zero rain
        state = dict(state="SOURCE_UNREACHABLE", error=f"{type(exc).__name__}: {str(exc)[:200]}")
        if archive.get("status", {}).get("state") != state["state"]:
            archive["status"] = dict(state, since_utc=now.isoformat())
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"::warning::IMERG Early unreachable: {state['error']}")
        return 0
    indexed = [row for row in probe.index_granules(found) if row[1]]
    missing = [row for row in indexed if row[1] not in have]
    selected = sorted(missing, key=lambda r: r[0], reverse=True)[:MAX_DOWNLOADS_PER_RUN]  # newest first, bounded
    new_rows = []
    with tempfile.TemporaryDirectory(prefix="irfen_v09_imerg_") as td:
        paths = earthaccess.download([r[2] for r in selected], local_path=td, threads=2, show_progress=False) if selected else []
        by_name = {Path(p).name: p for p in paths}
        for ts, name, _ in selected:
            path = by_name.get(name)
            if path is None:
                continue
            lat, lon, values, units = probe.read_grid(path)
            if not any(u in units.lower() for u in ("mm/hr", "mm h-1", "mm/hour")):
                print(f"::warning::{name}: unexpected units {units!r}; not archived")
                continue
            rows = {}
            for t in targets:
                value, meta = probe.polygon_mean(t["geometry"], lat, lon, values)
                rows[t["id"]] = dict(rate_mm_hr=None if value is None else round(value, 4),
                                     accum_30min_mm=None if value is None else round(value * 0.5, 4),
                                     valid_cells=meta["valid_cells"], cells_intersected=meta["cells_intersected"],
                                     covered_pct=meta["covered_geometry_pct"])
            new_rows.append(dict(granule=name, time_utc=ts.isoformat(), retrieved_at_utc=now.isoformat(), units=units, targets=rows))
    by_name = {g["granule"]: g for g in archive["granules"]}
    for row in new_rows:
        by_name[row["granule"]] = row
    horizon = (now - timedelta(hours=RETAIN_HOURS)).isoformat()
    archive["granules"] = sorted((g for g in by_name.values() if g["time_utc"] >= horizon), key=lambda g: g["time_utc"])
    latest = archive["granules"][-1]["time_utc"] if archive["granules"] else None
    archive["status"] = dict(state="AVAILABLE" if latest else "NO_GRANULES", latest_granule_start_utc=latest,
                             catalog_granules_in_window=len(indexed), missing_in_window_after_run=max(0, len(missing) - len(new_rows)))
    if json.dumps(archive, sort_keys=True) != before:
        archive["status"]["written_at_utc"] = now.isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=V09_IMERG_NORTH::new={len(new_rows)} missing_after={archive['status']['missing_in_window_after_run']} "
          f"latest={latest} targets={len(targets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
