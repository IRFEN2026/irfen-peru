#!/usr/bin/env python3
"""Enriquece history.json con IMERG Final sobre polígonos v0.8 elegibles.

No reemplaza los valores históricos de las cajas v0.7.1. Guarda el cálculo por
polígono dentro de `experimental_polygon` para permitir comparaciones directas.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile

import earthaccess

from update_polygon_imerg import (
    ROOT,
    eligible_targets,
    read_grid,
    polygon_mean,
    date_from_name,
)

HISTORY = ROOT / "site" / "data" / "history.json"


def delta(a, b):
    return None if a is None or b is None else round(a - b, 2)


def main():
    if not os.getenv("EARTHDATA_TOKEN"):
        raise SystemExit("Falta EARTHDATA_TOKEN")

    targets = {x["zone_id"]: x for x in eligible_targets()}
    if not targets:
        print("No hay polígonos elegibles para histórico.")
        return 0

    payload = json.loads(HISTORY.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    candidates = [
        e for e in events
        if e.get("imerg") and e.get("date") and e.get("zone_id") in targets
    ]
    if not candidates:
        print("No hay eventos históricos elegibles.")
        return 0

    earthaccess.login(strategy="environment")

    for event in candidates:
        zid = event["zone_id"]
        target = targets[zid]
        event_date = datetime.fromisoformat(event["date"]).date()
        start = event_date - timedelta(days=7)
        end = event_date + timedelta(days=1)
        print("Procesando", event.get("id"), zid, event_date)

        granules = earthaccess.search_data(
            short_name="GPM_3IMERGDF",
            version="07",
            temporal=(start.isoformat(), end.isoformat()),
            count=20,
        )
        if not granules:
            print(" Sin gránulos IMERG Final")
            continue

        series = []
        with tempfile.TemporaryDirectory(prefix=f"irfen_hist_poly_{zid}_") as td:
            paths = earthaccess.download(granules, local_path=td, threads=4, show_progress=False)
            for path in sorted(paths):
                date = date_from_name(path)
                if not date:
                    continue
                try:
                    lat, lon, p = read_grid(path)
                    value, sampling = polygon_mean(target["geom"], lat, lon, p)
                except Exception as exc:
                    print("  gránulo omitido", path, exc)
                    continue
                series.append({
                    "date": date,
                    "rain_mm": None if value is None else round(value, 2),
                    "sampling": sampling,
                })

        dedup = {x["date"]: x for x in series}
        ordered = [dedup[k] for k in sorted(dedup)]
        by_date = {x["date"]: x["rain_mm"] for x in ordered}

        def total(days):
            vals = [
                by_date.get((event_date - timedelta(days=i)).isoformat())
                for i in range(days)
            ]
            return round(sum(vals), 2) if all(v is not None for v in vals) else None

        p24, p72, p7d = total(1), total(3), total(7)
        event["experimental_polygon"] = {
            "status": "historical_parallel_validation_only",
            "production_use": False,
            "product": "NASA GPM IMERG Final",
            "product_version": "07",
            "geometry": str(target["geojson"].relative_to(ROOT / "site")).replace("\\", "/"),
            "validation_status": target["validation_data"].get("status"),
            "method": "IMERG Final por solape de celdas ponderado por área de intersección con polígono DEM",
            "rain24": p24,
            "rain72": p72,
            "rain7d": p7d,
            "delta_vs_legacy_bbox_mm": {
                "rain24": delta(p24, event.get("rain24")),
                "rain72": delta(p72, event.get("rain72")),
                "rain7d": delta(p7d, event.get("rain7d")),
            },
            "series": ordered,
            "warning": "Dato experimental; no sustituye la serie histórica de referencia v0.7.1.",
        }
        print(
            " legado:", event.get("rain24"), event.get("rain72"), event.get("rain7d"),
            "polígono:", p24, p72, p7d,
        )

    payload["polygon_comparison_generated_at"] = datetime.now(timezone.utc).isoformat()
    HISTORY.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Histórico enriquecido:", HISTORY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
