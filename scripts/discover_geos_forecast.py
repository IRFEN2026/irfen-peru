#!/usr/bin/env python3
"""Descubre variables meteorológicas reutilizables del forecast público GEOS-CF v2.

Fase exploratoria: solo inspecciona metadatos y escribe un reporte. No alimenta
alertas ni modifica latest.json.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "forecast" / "geos_cf_discovery.json"
STORE = "s3://smce-geos-cf-public/geos-cf-v2-fcst-latest.zarr"


def main():
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NASA GMAO GEOS-CF v2 latest forecast",
        "store": STORE,
        "status": "unknown",
        "production_use": False,
        "warning": "Exploración científica. Los pronósticos GEOS son productos de investigación y no alimentan alertas IRFEN.",
    }
    try:
        ds = xr.open_zarr(STORE, storage_options={"anon": True}, consolidated=None)
        variables = sorted(str(v) for v in ds.data_vars)
        coords = sorted(str(v) for v in ds.coords)
        keys = ("prec", "rain", "tprec", "prcp")
        precip = [v for v in variables if any(k in v.lower() for k in keys)]
        meteorology = [
            v for v in variables
            if any(k in v.lower() for k in ("temp", "t2m", "wind", "rh", "slp", "prec", "rain", "tprec"))
        ]
        detail = {}
        for v in precip[:30]:
            da = ds[v]
            detail[v] = {
                "dims": list(da.dims),
                "shape": list(da.shape),
                "units": str(da.attrs.get("units", "")),
                "long_name": str(da.attrs.get("long_name", "")),
            }
        time_info = {}
        for name in ("time", "forecast_time", "valid_time"):
            if name in ds.coords:
                c = ds.coords[name]
                time_info[name] = {
                    "size": int(c.size),
                    "first": str(c.values[0]) if c.size else None,
                    "last": str(c.values[-1]) if c.size else None,
                }
        report.update({
            "status": "accessible",
            "n_variables": len(variables),
            "coordinates": coords,
            "precipitation_candidates": precip,
            "meteorology_candidates": meteorology[:80],
            "precipitation_details": detail,
            "time": time_info,
            "decision": "candidate_for_precipitation_prototype" if precip else "no_precipitation_variable_identified",
        })
        ds.close()
    except Exception as exc:
        report.update({
            "status": "access_error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "decision": "review_access_method",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # El descubrimiento no debe romper la plataforma por una fuente experimental.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
