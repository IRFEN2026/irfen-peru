#!/usr/bin/env python3
"""IRFEN v0.9 — archivo TEST_ONLY y continuo de IMERG Early (GPM_3IMERGHHE, 30 min) para las zonas del norte.

Reutiliza las funciones del probe v0.8 (scripts/probe_imerg_early_live.py: lectura del HDF5, media ponderada por
área de celda dentro del polígono, nombres y tiempos de gránulo, preflight de Earthdata). La diferencia es la
política: aquí se descarga cada media hora que falte en las últimas `WINDOW_HOURS` horas (acotado por ejecución),
para que las ventanas de 1/3/6/24 h se puedan reconstruir sin huecos. Objetivos:

* las cuencas con geometría verificada de config/v09_north_surveillance_zones_v0_1.json;
* las provincias de los departamentos sin cuenca validada fuera de Bocapán (Piura, Tumbes; polígonos INEI
  referenciales archivados), como contexto administrativo: la media sobre la provincia no es la lluvia de ninguna quebrada.

IMERG Early tiene horas de latencia: nunca se presenta como observación en tiempo real. Un fallo de Earthdata se
registra y nunca se interpreta como lluvia cero. El archivo solo se reescribe cuando entra un gránulo nuevo o cambia
el estado de la fuente.

Interrupción de NASA (28-30 oct. 2026, migración del ingest de GES DISC): el catálogo dejó de publicar gránulos y el
estado seguía diciendo AVAILABLE sin huecos, porque los huecos se medían solo hasta el gránulo más nuevo del catálogo.
Ahora:
* el estado distingue la latencia normal (unas 4-6 h) de un retraso en la fuente (CATALOG_DELAYED, más de
  CATALOG_DELAY_H h sin gránulo nuevo en el catálogo) y lista las medias horas que ya deberían existir;
* la búsqueda cubre BACKFILL_HOURS (dentro de RETAIN_HOURS): si NASA publica más tarde los gránulos atrasados, se
  recuperan del mismo producto en ejecuciones sucesivas (más recientes primero, acotado). Nunca se sustituye la fuente
  ni se rellena nada: lo que falta sigue siendo dato ausente.

  python scripts/v09_imerg_north_archive.py      # runner con EARTHDATA_TOKEN
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
BOUNDARIES_LATEST = ROOT / "data/v09/admin_boundaries/latest.json"
OUT = ROOT / "data/v09/rain/imerg_early_north_v0_1.json"
# v0.9.1 (research): contributing areas of the coastal river checkpoints (HydroSHEDS, experimental). Sampled from the
# same downloaded granules (no extra Earthdata traffic) into a separate compact archive that nothing published reads.
CATCHMENT_TARGETS = ROOT / "config/v091_catchment_rain_targets_v0_1.json"
CATCHMENT_OUT = ROOT / "data/v09/rain/imerg_early_catchments_v0_1.json"
WINDOW_HOURS = 30
# The whole window fits in one run (60 half-hours; 16 granules took 26 s on the runner). With 16, runs more than 8 h
# apart left the oldest granules behind for good (newest-first starvation): 24 h windows stayed NO_DISPONIBLE.
MAX_DOWNLOADS_PER_RUN = 60
CONTACT_ATTEMPTS = 3          # bounded retries of the Earthdata contact (preflight, login, search)
CONTACT_BACKOFF_S = (20, 60)  # waits between attempts
RETAIN_HOURS = 96
# Search span: late-published granules (an outage at the source, then backlog ingestion) are still recovered while
# they are inside the retained archive. Downloads stay bounded per run and newest first; older ones follow next runs.
BACKFILL_HOURS = 90
SEARCH_COUNT = 2 * BACKFILL_HOURS + 20
# IMERG Early is normally in the catalog some 4-6 h after its half-hour ends. A half-hour that ended more than
# NORMAL_LATENCY_H ago and is not in the catalog is reported as missing; no new granule for more than CATALOG_DELAY_H
# (the engine's IMERG freshness limit) is a delay at the source, never zero rain.
NORMAL_LATENCY_H = 6
CATALOG_DELAY_H = 12
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
    context = {z["registered_department"]: z["zone_id"] for z in cfg["zones"] if z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN"}
    if BOUNDARIES_LATEST.is_file():
        latest = json.loads(BOUNDARIES_LATEST.read_text(encoding="utf-8"))
        fc = json.loads((ROOT / latest["path"]).read_text(encoding="utf-8"))
        for f in fc["features"]:
            p = f["properties"]
            if p["NOMBDEP"] in context:
                targets.append(dict(id=f"{context[p['NOMBDEP']]}:{p['NOMBPROV']}", name=f"Provincia {p['NOMBPROV'].title()} ({p['NOMBDEP'].title()})",
                                    kind="ADMIN_PROVINCE_POLYGON_INEI_REFERENTIAL", geometry=shape(f["geometry"]).buffer(0),
                                    geometry_sha256=latest["sha256"]))
    return targets


def load_catchment_targets() -> list[dict]:
    """Contributing-area polygons of the river checkpoints (config/v091_catchment_rain_targets_v0_1.json). The geometry
    file must match its recorded SHA-256; otherwise nothing is sampled (never a silently different area)."""
    import hashlib

    from shapely.geometry import shape

    if not CATCHMENT_TARGETS.is_file():
        return []
    cfg = json.loads(CATCHMENT_TARGETS.read_text(encoding="utf-8"))
    raw = (ROOT / cfg["geometry_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != cfg["geometry_sha256"]:
        print("::warning::catchment geometry does not match its SHA-256: catchment rain not sampled")
        return []
    feats = {f["properties"]["checkpoint_id"]: f for f in json.loads(raw)["features"]}
    return [dict(id=cfg["id_prefix"] + cid, checkpoint_id=cid, area_km2=feats[cid]["properties"]["area_km2"],
                 geometry=shape(feats[cid]["geometry"]).buffer(0), geometry_sha256=cfg["geometry_sha256"])
            for cid in cfg["targets"] if cid in feats]


def cell_weights(geom, lat, lon) -> dict:
    """Area of the intersection of `geom` with each 0.1° IMERG cell: the weights of probe_imerg_early_live.polygon_mean,
    computed once per run (the IMERG grid is fixed) instead of once per granule."""
    import numpy as np
    from shapely.geometry import box

    dx = float(np.median(np.abs(np.diff(lon))))
    dy = float(np.median(np.abs(np.diff(lat))))
    minx, miny, maxx, maxy = geom.bounds
    xs = np.where((lon >= minx - dx / 2) & (lon <= maxx + dx / 2))[0]
    ys = np.where((lat >= miny - dy / 2) & (lat <= maxy + dy / 2))[0]
    rows, cols, areas = [], [], []
    for r in ys:
        for c in xs:
            inter = geom.intersection(box(float(lon[c]) - dx / 2, float(lat[r]) - dy / 2, float(lon[c]) + dx / 2, float(lat[r]) + dy / 2))
            if not inter.is_empty and inter.area > 0:
                rows.append(int(r))
                cols.append(int(c))
                areas.append(inter.area)
    return dict(rows=np.array(rows, dtype=int), cols=np.array(cols, dtype=int), areas=np.array(areas), geom_area=geom.area)


def weighted_mean(w: dict, values):
    """Same result as polygon_mean: area-weighted mean over the finite cells; None when no cell is valid (unknown,
    never 0 mm). Returns (mean, covered_pct)."""
    import numpy as np

    if not len(w["areas"]):
        return None, 0.0
    v = values[w["rows"], w["cols"]]
    ok = np.isfinite(v)
    sw = float(w["areas"][ok].sum())
    if not sw:
        return None, 0.0
    return float((w["areas"][ok] * v[ok]).sum() / sw), round(min(100.0, 100.0 * sw / max(w["geom_area"], 1e-15)), 1)


def empty_catchment_archive(targets: list[dict]) -> dict:
    import hashlib

    tid = [t["id"] for t in targets]
    return dict(schema_version="0.1", archive_id="irfen-v091-imerg-early-catchments:v0.1", **GUARDS, map_publishable=False,
                public_alerting=False, notifications_enabled=False,
                source=dict(product="GPM_3IMERGHHE", version="07", provider="NASA GES DISC via earthaccess",
                            nature="satellite estimate, half-hourly, Early run (hours of latency); not a real-time observation"),
                sample=("area-weighted mean of the 0.1° cells intersecting each HydroSHEDS contributing area (weights identical "
                        "to probe_imerg_early_live.polygon_mean); rate_mm_hr null = no valid cell (unknown, never 0 mm)"),
                geometry_sha256=targets[0]["geometry_sha256"] if targets else None,
                targets=[dict(id=t["id"], checkpoint_id=t["checkpoint_id"], area_km2=t["area_km2"]) for t in targets],
                targets_sha256=hashlib.sha256(json.dumps(tid).encode()).hexdigest(), retain_hours=RETAIN_HOURS,
                granules=[], status=dict(state="NEVER_CHECKED"))


def empty_archive() -> dict:
    return dict(schema_version="0.1", archive_id="irfen-v09-imerg-early-north:v0.1", **GUARDS, map_publishable=False,
                source=dict(product="GPM_3IMERGHHE", version="07", provider="NASA GES DISC via earthaccess",
                            nature="satellite estimate, half-hourly, Early run (hours of latency); not a real-time observation"),
                policy=dict(window_hours=WINDOW_HOURS, max_downloads_per_run=MAX_DOWNLOADS_PER_RUN, retain_hours=RETAIN_HOURS,
                            backfill_hours=BACKFILL_HOURS, normal_latency_hours=NORMAL_LATENCY_H, catalog_delay_hours=CATALOG_DELAY_H,
                            sample="area-weighted mean of 0.1° cells intersecting the target polygon (probe_imerg_early_live.polygon_mean)"),
                targets={}, granules=[], status=dict(state="NEVER_CHECKED"))


def contact_with_retries(probe, earthaccess, now: datetime, sleep=time.sleep):
    """Earthdata preflight + login + search with bounded retries. Returns (granules, attempts); raises the last
    error after CONTACT_ATTEMPTS failures. Every attempt is recorded for traceability."""
    attempts, last = [], None
    for i in range(CONTACT_ATTEMPTS):
        try:
            probe.earthdata_preflight()
            earthaccess.login(strategy="environment")
            found = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07",
                                            temporal=((now - timedelta(hours=BACKFILL_HOURS)).isoformat(), now.isoformat()),
                                            count=SEARCH_COUNT)
            attempts.append(dict(attempt=i + 1, ok=True))
            return found, attempts
        except Exception as exc:  # noqa: BLE001 - retried, then recorded as a source failure
            last = exc
            attempts.append(dict(attempt=i + 1, ok=False, error=f"{type(exc).__name__}: {str(exc)[:160]}"))
            if i + 1 < CONTACT_ATTEMPTS:
                sleep(CONTACT_BACKOFF_S[min(i, len(CONTACT_BACKOFF_S) - 1)])
    exc = RuntimeError(attempts[-1]["error"])
    exc.attempts = attempts
    raise exc from last


def newest_expected_half_hour(now: datetime) -> datetime:
    """Start of the newest half-hour that ended at least NORMAL_LATENCY_H ago (it should be in the catalog by now)."""
    t = now - timedelta(hours=NORMAL_LATENCY_H, minutes=30)
    return t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)


def missing_half_hours(catalog_times: list[datetime], archived: set[datetime], now: datetime) -> list[dict]:
    """Half-hours of the last 24 h that are not archived, with the reason. The span ends at the newest catalog granule
    or at the newest half-hour that should already be published (whichever is later), so a catalog that stops
    publishing is visible as missing data instead of an empty list:
    NOT_IN_CATALOG (a hole before the newest published granule), NOT_IN_CATALOG_PAST_NORMAL_LATENCY (after the newest
    published granule and older than the normal latency: delay at the source) or IN_CATALOG_NOT_ARCHIVED (download
    pending or failed). A missing half-hour is never zero rain."""
    expected = newest_expected_half_hour(now)
    newest = max(catalog_times) if catalog_times else None
    end = max(newest, expected) if newest else expected
    in_catalog = set(catalog_times)
    out, t = [], end - timedelta(minutes=30 * 47)
    while t <= end:
        if t not in archived:
            reason = ("IN_CATALOG_NOT_ARCHIVED" if t in in_catalog else
                      "NOT_IN_CATALOG" if newest and t < newest else "NOT_IN_CATALOG_PAST_NORMAL_LATENCY")
            out.append(dict(time_utc=t.isoformat(), reason=reason))
        t += timedelta(minutes=30)
    return out


def catalog_freshness(catalog_times: list[datetime], now: datetime) -> dict:
    """How far the source catalog is behind now. WITHIN_NORMAL_LATENCY / DELAYED_AT_SOURCE / EMPTY_IN_SEARCH_SPAN."""
    if not catalog_times:
        return dict(state="EMPTY_IN_SEARCH_SPAN", newest_catalog_granule_start_utc=None, lag_hours=None,
                    normal_latency_hours=NORMAL_LATENCY_H, delayed_after_hours=CATALOG_DELAY_H, search_span_hours=BACKFILL_HOURS)
    newest = max(catalog_times)
    lag = (now - (newest + timedelta(minutes=30))).total_seconds() / 3600
    return dict(state="DELAYED_AT_SOURCE" if lag > CATALOG_DELAY_H else "WITHIN_NORMAL_LATENCY",
                newest_catalog_granule_start_utc=newest.isoformat(), lag_hours=round(lag, 1),
                normal_latency_hours=NORMAL_LATENCY_H, delayed_after_hours=CATALOG_DELAY_H, search_span_hours=BACKFILL_HOURS)


def run_state(latest: str | None, freshness: dict) -> str:
    if freshness["state"] != "WITHIN_NORMAL_LATENCY":
        return "CATALOG_DELAYED"  # the source publishes nothing new: archived data are kept with their dates, never as current
    return "AVAILABLE" if latest else "NO_GRANULES"


def select_downloads(indexed: list[tuple], have: set[str], budget: int = MAX_DOWNLOADS_PER_RUN) -> list[tuple]:
    """Catalog rows (time, name, granule) not yet archived, newest first, at most `budget` per run."""
    return sorted((r for r in indexed if r[1] not in have), key=lambda r: r[0], reverse=True)[:budget]


def download_granules(earthaccess, selected: list[tuple], local_path: str) -> tuple[list[str], list[dict]]:
    """Download the selected granules. A failed download (e.g. HTTP 400 from GES DISC on 02-11-2026 10:04 UTC) is a
    source failure of that granule, never an aborted run: the remaining granules and the GOES-19 step still run."""
    if not selected:
        return [], []
    try:
        return list(earthaccess.download([r[2] for r in selected], local_path=local_path, threads=4, show_progress=False)), []
    except Exception:  # noqa: BLE001 - one bad granule must not lose the others: retry one by one, record each failure
        paths, failures = [], []
        for ts, name, granule in selected:
            try:
                paths += list(earthaccess.download([granule], local_path=local_path, threads=1, show_progress=False))
            except Exception as exc:  # noqa: BLE001
                failures.append(dict(granule=name, time_utc=ts.isoformat(), error=f"{type(exc).__name__}: {str(exc)[:200]}"))
        return paths, failures


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
    ctargets = load_catchment_targets()
    carchive = None
    if ctargets:
        fresh = empty_catchment_archive(ctargets)
        carchive = json.loads(CATCHMENT_OUT.read_text(encoding="utf-8")) if CATCHMENT_OUT.is_file() else fresh
        if carchive.get("targets_sha256") != fresh["targets_sha256"] or carchive.get("geometry_sha256") != fresh["geometry_sha256"]:
            carchive = fresh  # other areas: earlier means are not comparable; the window is re-sampled from the granules
        cbefore = json.dumps(carchive, sort_keys=True)
        have &= {g["granule"] for g in carchive["granules"]}  # a granule missing in either archive is downloaded again
    try:
        found, attempts = contact_with_retries(probe, earthaccess, now)
    except Exception as exc:  # noqa: BLE001 - recorded as a source failure, never as zero rain
        state = dict(state="SOURCE_UNREACHABLE", error=f"{type(exc).__name__}: {str(exc)[:200]}",
                     contact_attempts=getattr(exc, "attempts", []))
        if archive.get("status", {}).get("state") != state["state"]:
            archive["status"] = dict(state, since_utc=now.isoformat())
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"::warning::IMERG Early unreachable: {state['error']}")
        return 0
    indexed = [row for row in probe.index_granules(found) if row[1]]
    missing = [row for row in indexed if row[1] not in have]
    selected = select_downloads(indexed, have)  # newest first, bounded; older backlog follows in the next runs
    new_rows = []
    with tempfile.TemporaryDirectory(prefix="irfen_v09_imerg_") as td:
        paths, failures = download_granules(earthaccess, selected, td)
        if selected and failures and not paths:  # nothing could be downloaded: a source failure, never zero rain
            state = dict(state="DOWNLOAD_FAILED", error=failures[0]["error"], download_failures=failures[:10])
            if archive.get("status", {}).get("state") != state["state"]:
                archive["status"] = dict(state, since_utc=now.isoformat())
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"::warning::IMERG Early download failed for all {len(selected)} granules: {state['error']}")
            return 0
        by_name = {Path(p).name: p for p in paths}
        for ts, name, _ in selected:
            path = by_name.get(name)
            if path is None:
                continue
            lat, lon, values, units = probe.read_grid(path)
            if not any(u in units.lower() for u in ("mm/hr", "mm h-1", "mm/hour")):
                print(f"::warning::{name}: unexpected units {units!r}; not archived")
                continue
            if carchive is not None:
                if "_w" not in carchive:
                    carchive["_w"] = [cell_weights(t["geometry"], lat, lon) for t in ctargets]
                means = [weighted_mean(w, values) for w in carchive["_w"]]
                carchive.setdefault("_new", []).append(dict(granule=name, time_utc=ts.isoformat(), retrieved_at_utc=now.isoformat(),
                                                            rate_mm_hr=[None if m is None else round(m, 4) for m, _ in means],
                                                            covered_pct=[c for _, c in means]))
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
    archived = {datetime.fromisoformat(g["time_utc"]) for g in archive["granules"]}
    gaps = missing_half_hours([r[0] for r in indexed], archived, now)
    freshness = catalog_freshness([r[0] for r in indexed], now)
    archive["policy"] = empty_archive()["policy"]  # the policy actually applied in this run
    archive["status"] = dict(state=run_state(latest, freshness), latest_granule_start_utc=latest,
                             catalog_granules_in_window=len(indexed), missing_in_window_after_run=max(0, len(missing) - len(new_rows)),
                             contact_attempts=attempts, catalog_freshness=freshness, missing_half_hours_24h=gaps,
                             download_failures=failures[:10])
    if failures:
        print(f"::warning::IMERG Early: {len(failures)} granule download(s) failed (retried next run): {failures[0]['error']}")
    if freshness["state"] != "WITHIN_NORMAL_LATENCY":
        print(f"::warning title=V09_IMERG_NORTH_SOURCE_DELAY::NASA catalog has no IMERG Early granule after "
              f"{freshness['newest_catalog_granule_start_utc']} (lag {freshness['lag_hours']} h > {CATALOG_DELAY_H} h). "
              "Delay at the source, not a download failure; missing half-hours are unknown, never 0 mm.")
    if carchive is not None:
        carchive.pop("_w", None)
        cby = {g["granule"]: g for g in carchive["granules"]}
        for row in carchive.pop("_new", []):
            cby[row["granule"]] = row
        carchive["granules"] = sorted((g for g in cby.values() if g["time_utc"] >= horizon), key=lambda g: g["time_utc"])
        carchive["status"] = dict(state=archive["status"]["state"],
                                  latest_granule_start_utc=carchive["granules"][-1]["time_utc"] if carchive["granules"] else None,
                                  source_status_in="data/v09/rain/imerg_early_north_v0_1.json")
        if json.dumps(carchive, sort_keys=True) != cbefore:
            carchive["status"]["written_at_utc"] = now.isoformat()
            CATCHMENT_OUT.parent.mkdir(parents=True, exist_ok=True)
            CATCHMENT_OUT.write_text(json.dumps(carchive, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if json.dumps(archive, sort_keys=True) != before:
        archive["status"]["written_at_utc"] = now.isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=V09_IMERG_NORTH::new={len(new_rows)} missing_after={archive['status']['missing_in_window_after_run']} "
          f"latest={latest} catalog={freshness['state']} lag_h={freshness['lag_hours']} targets={len(targets)} attempts={len(attempts)} "
          f"gaps_24h={len(gaps)} first={[g['time_utc'][5:16] + ':' + g['reason'] for g in gaps[:3]]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
