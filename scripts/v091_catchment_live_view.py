#!/usr/bin/env python3
"""Experimental, read-only aggregation of archived IMERG Early rainfall over checkpoint catchments.

No published hazard state is changed. All half-hourly periods and spatial coverage must be complete;
partial windows are NULL (not zero). The archive's geometry and target list are hash-locked upstream.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data/v09/rain/imerg_early_catchments_v0_1.json"
WINDOW_HOURS = (1, 3, 6, 24, 72)
MIN_SPATIAL_COVERAGE_PCT = 80.0
MAX_AGE_HOURS = 12.0


def _dt(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Timestamp without UTC timezone")
    return d.astimezone(timezone.utc)


def summarize(archive, checkpoint_id, evaluated_at_utc, windows_h=WINDOW_HOURS):
    """Return a strictly evidence-scoped satellite rain context for one checkpoint."""
    result = dict(status="NO_DISPONIBLE", source="NASA GPM IMERG Early V07 (experimental, 30 min)",
                  point_id=checkpoint_id, observation_end_utc=None, evaluated_at_utc=evaluated_at_utc,
                  age_hours=None, windows={}, spatial_min_pct=MIN_SPATIAL_COVERAGE_PCT,
                  note_es="Media espacial de la cuenca HydroSHEDS; no mide el caudal ni predice desbordes.")
    if not archive or archive.get("production_use") is not False or archive.get("public_alerting") is not False or archive.get("activation_gate") != "BLOCKED":
        result["reason_es"] = "Archivo inexistente o sin garantías RESEARCH_ONLY/TEST_ONLY"
        return result
    ids = [t.get("checkpoint_id") for t in archive.get("targets", [])]
    if checkpoint_id not in ids:
        result["reason_es"] = "Checkpoint sin cuenca de lluvia vinculada al archivo"
        return result
    idx = ids.index(checkpoint_id)
    rows = []
    for g in archive.get("granules", []):
        try:
            t = _dt(g["time_utc"])
            v = g["rate_mm_hr"][idx]
            cov = g["covered_pct"][idx]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        rows.append((t, v, cov))
    if not rows:
        result["reason_es"] = "No hay gránulos en el archivo"
        return result
    # IMERG half-hour granule time is the START. The observation end is +30 min.
    rows.sort(key=lambda x: x[0])
    latest_start = rows[-1][0]
    end = latest_start + timedelta(minutes=30)
    now = _dt(evaluated_at_utc)
    age = (now - end).total_seconds() / 3600
    result["observation_end_utc"] = end.isoformat()
    result["age_hours"] = round(age, 3)
    result["status"] = "RECIENTE" if 0 <= age <= MAX_AGE_HOURS else "CADUCADA"
    if age < 0:
        result["status"] = "FECHA_INCONSISTENTE"
    by_time = {}
    for t, v, cov in rows:
        if t in by_time:
            # Duplicate timestamp makes that interval ambiguous: do not count either value.
            by_time[t] = None
        else:
            by_time[t] = (v, cov)
    for hours in windows_h:
        n = hours * 2
        required = [latest_start - timedelta(minutes=30 * j) for j in range(n)]
        selected = [by_time.get(t) for t in required]
        complete = len(selected) == n and all(x is not None and x[0] is not None and
                isinstance(x[1], (float, int)) and x[1] >= MIN_SPATIAL_COVERAGE_PCT
                and isinstance(x[0], (float, int)) and 0 <= x[0] < 1e5 for x in selected)
        result["windows"][f"{hours}h"] = dict(status="COMPLETA" if complete else "INCOMPLETA",
                                               mm=round(sum(x[0] * 0.5 for x in selected), 3) if complete else None,
                                               intervals_valid=sum(x is not None and x[0] is not None and
                                                                   x[1] is not None and x[1] >= MIN_SPATIAL_COVERAGE_PCT for x in selected),
                                               intervals_required=n)
    if result["status"] == "RECIENTE" and not any(w["status"] == "COMPLETA" for w in result["windows"].values()):
        result["status"] = "DATOS_INCOMPLETOS"
    return result


def build(archive, checkpoint_ids, evaluated_at_utc):
    return dict(schema_version="irfen_v091_catchment_live_view_v0_1",
                deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY",
                production_use=False, public_alerting=False, notifications_enabled=False,
                activation_gate="BLOCKED", hazard_colors_enabled=False,
                evaluated_at_utc=evaluated_at_utc,
                points={cid: summarize(archive, cid, evaluated_at_utc) for cid in checkpoint_ids})


def load(path=ARCHIVE):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else None
