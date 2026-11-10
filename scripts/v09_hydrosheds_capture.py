#!/usr/bin/env python3
"""IRFEN v0.9 · investigación: datos HydroSHEDS v1 (WWF / USGS; NO oficiales del Perú) para delimitar de forma
experimental las cuencas de aportación del río Piura hasta sus estaciones de aforo. RESEARCH_ONLY / TEST_ONLY.
Runner con red; guarda recortes pequeños y reproducibles en el repositorio con el SHA-256 del archivo original.

1. Busca los enlaces oficiales de descarga en las páginas de HydroSHEDS (no se inventan rutas).
2. Descarga dirección de drenaje (DIR) y acumulación (ACC) a 15″ de Sudamérica, HydroBASINS nivel 12 y
   HydroRIVERS de Sudamérica (límite de tamaño, un intento por archivo).
3. Recorta al recuadro lon −81,3…−79,1 / lat −6,6…−4,0 y guarda: DIR y ACC como .npy comprimidos (+ transformación
   afín), HydroBASINS nivel 12 y HydroRIVERS del recuadro como GeoJSON.

    python scripts/v09_hydrosheds_capture.py
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/hydrosheds_piura"
BOX = (-81.3, -6.6, -79.1, -4.0)  # lon_min, lat_min, lon_max, lat_max
UA = {"User-Agent": "Mozilla/5.0 (IRFEN research TEST_ONLY; bounded download of public HydroSHEDS data)"}
PAGES = ["https://www.hydrosheds.org/products/hydrosheds", "https://www.hydrosheds.org/products/hydrobasins",
         "https://www.hydrosheds.org/products/hydrorivers", "https://www.hydrosheds.org/downloads-archive",
         "https://www.hydrosheds.org/hydrosheds-core-downloads"]
WANT = {
    "dir15": re.compile(r"hyd_sa_dir_15s\.zip$", re.I),
    "acc15": re.compile(r"hyd_sa_acc_15s\.zip$", re.I),
    "hybas12": re.compile(r"hybas_sa_lev12_v1c\.zip$", re.I),
    "rivers": re.compile(r"HydroRIVERS_v10_sa_shp\.zip$", re.I),
}
MAX_BYTES = 1_500_000_000
LOG: list[dict] = []


def fetch(url: str, timeout=600) -> bytes | None:
    t0 = time.time()
    try:
        with urlopen(Request(url, headers=UA), timeout=timeout) as r:
            raw = r.read(MAX_BYTES + 1)
        rec = dict(url=url, status="OK" if len(raw) <= MAX_BYTES else "TOO_LARGE", bytes=len(raw),
                   sha256=hashlib.sha256(raw).hexdigest(), seconds=round(time.time() - t0, 1))
    except Exception as e:  # noqa: BLE001
        rec = dict(url=url, status="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.time() - t0, 1))
        raw = None
    rec["at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    LOG.append(rec)
    print(f"{rec['status']} {url[:120]} {rec.get('bytes')}", flush=True)
    return raw if rec["status"] == "OK" else None


def crop_raster(zbytes: bytes, name: str) -> dict:
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(zbytes)).extractall(td)
        cands = [p for p in Path(td).rglob("*") if p.suffix.lower() in (".tif", ".adf", ".bil") or p.name.lower() == "hdr.adf"]
        src_path = next((p for p in cands if p.suffix.lower() == ".tif"), None) or next((p.parent for p in cands if p.name.lower() == "hdr.adf"), None)
        if src_path is None:
            return dict(status="NO_RASTER_IN_ZIP", files=[p.name for p in Path(td).rglob("*")][:20])
        with rasterio.open(src_path) as src:
            win = from_bounds(*BOX, transform=src.transform).round_offsets().round_lengths()
            arr = src.read(1, window=win)
            tr = src.window_transform(win)
            meta = dict(crs=str(src.crs), dtype=str(arr.dtype), nodata=src.nodata, shape=list(arr.shape),
                        transform=[tr.a, tr.b, tr.c, tr.d, tr.e, tr.f], source_res=[src.res[0], src.res[1]])
    buf = io.BytesIO()
    np.save(buf, arr)
    raw = buf.getvalue()
    (OUT / f"{name}.npy.gz").write_bytes(gzip.compress(raw, mtime=0))
    meta.update(status="OK", file=f"{name}.npy.gz", npy_sha256=hashlib.sha256(raw).hexdigest())
    return meta


def crop_vector(zbytes: bytes, name: str, keep: list[str]) -> dict:
    import geopandas as gpd
    from shapely.geometry import box
    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(zbytes)).extractall(td)
        shp = next(Path(td).rglob("*.shp"), None)
        if shp is None:
            return dict(status="NO_SHP_IN_ZIP")
        g = gpd.read_file(shp, bbox=BOX)
        g = g[g.intersects(box(*BOX))]
        cols = [c for c in keep if c in g.columns]
        g = g[cols + ["geometry"]]
        text = g.to_json(drop_id=True)
    (OUT / f"{name}.geojson.gz").write_bytes(gzip.compress(text.encode(), mtime=0))
    return dict(status="OK", file=f"{name}.geojson.gz", features=len(g), crs="EPSG:4326",
                geojson_sha256=hashlib.sha256(text.encode()).hexdigest(), fields=cols)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    links = set()
    for p in PAGES:
        html = fetch(p, timeout=60)
        if html:
            links |= set(re.findall(r'https://data\.hydrosheds\.org/file/[^"\'\s<>]+', html.decode("utf-8", "replace")))
    chosen = {k: next((l for l in sorted(links) if rx.search(l)), None) for k, rx in WANT.items()}
    result = dict(links_found=len(links), chosen=chosen, box=BOX,
                  provenance="HydroSHEDS v1 (Lehner et al. 2008, WWF/USGS), derivado de SRTM; NO es cartografía oficial del Perú",
                  licence_page="https://www.hydrosheds.org/terms-of-use")
    licence = fetch("https://www.hydrosheds.org/terms-of-use", timeout=60)
    if licence:
        (OUT / "terms_of_use.html").write_bytes(licence)
    for key, url in chosen.items():
        if not url:
            result[key] = dict(status="LINK_NOT_FOUND")
            continue
        z = fetch(url)
        if not z:
            result[key] = dict(status="DOWNLOAD_FAILED", url=url)
            continue
        try:
            if key in ("dir15", "acc15"):
                result[key] = dict(url=url, zip_sha256=hashlib.sha256(z).hexdigest(), **crop_raster(z, key))
            elif key == "hybas12":
                result[key] = dict(url=url, zip_sha256=hashlib.sha256(z).hexdigest(),
                                   **crop_vector(z, key, ["HYBAS_ID", "NEXT_DOWN", "NEXT_SINK", "MAIN_BAS", "DIST_SINK", "DIST_MAIN",
                                                          "SUB_AREA", "UP_AREA", "PFAF_ID", "ORDER"]))
            else:
                result[key] = dict(url=url, zip_sha256=hashlib.sha256(z).hexdigest(),
                                   **crop_vector(z, key, ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "UPLAND_SKM", "DIS_AV_CMS", "ORD_STRA"]))
        except Exception as e:  # noqa: BLE001
            result[key] = dict(status="PROCESSING_FAILED", url=url, error=f"{type(e).__name__}: {str(e)[:200]}")
    result["requests"] = LOG
    (OUT / "provenance.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title=hydrosheds::{json.dumps({k: (v.get('status') if isinstance(v, dict) else v) for k, v in result.items() if k not in ('requests',)}, ensure_ascii=False)[:1500]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
