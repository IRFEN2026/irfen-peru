#!/usr/bin/env python3
"""IRFEN v0.9.1 · HydroSHEDS v1 15″ (DIR, ACC) y HydroRIVERS para TODA la vertiente pacífica peruana (RESEARCH_ONLY).

Mismos archivos oficiales y misma versión que #459/#460 (se comprueba el SHA-256 del zip contra la captura binacional
archivada; si cambia, se registra y no se oculta). Recorte lon −81,4…−69,0 / lat −18,6…−3,0: cubre las cuencas que
drenan al Pacífico desde Puyango-Tumbes (con su cabecera en Ecuador) hasta Tacna, incluidas sus cabeceras andinas.
HydroRIVERS se filtra a tramos con área aportante ≥ 100 km² (contraste independiente de áreas; no se usa para dibujar).
HydroSHEDS NO es cartografía oficial del Perú: sirve para delimitar áreas de aportación experimentales.

    python scripts/v091_hydrosheds_coast_capture.py      # runner con red; un intento por archivo
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/hydrosheds_coast"
BOX = (-81.4, -18.6, -69.0, -3.0)  # lon_min, lat_min, lon_max, lat_max
MIN_UPLAND_KM2 = 100
PREV = ROOT / "data/v09/sources/hydrosheds_binational/provenance.json"


def _hs():
    spec = importlib.util.spec_from_file_location("hs_coast", ROOT / "scripts/v09_hydrosheds_capture.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.BOX, m.OUT = BOX, OUT
    return m


def rivers(hs, zbytes: bytes) -> dict:
    import geopandas as gpd
    from shapely.geometry import box
    keep = ["HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "LENGTH_KM", "UPLAND_SKM", "DIS_AV_CMS", "ORD_STRA"]
    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(zbytes)).extractall(td)
        shp = next(Path(td).rglob("*.shp"), None)
        if shp is None:
            return dict(status="NO_SHP_IN_ZIP")
        g = gpd.read_file(shp, bbox=BOX)
        g = g[g.intersects(box(*BOX)) & (g["UPLAND_SKM"] >= MIN_UPLAND_KM2)]
        g = g[[c for c in keep if c in g.columns] + ["geometry"]]
        text = g.to_json(drop_id=True)
    (OUT / "rivers.geojson.gz").write_bytes(gzip.compress(text.encode(), mtime=0))
    return dict(status="OK", file="rivers.geojson.gz", features=len(g), min_upland_km2=MIN_UPLAND_KM2, crs="EPSG:4326",
                geojson_sha256=hashlib.sha256(text.encode()).hexdigest(), fields=keep)


def main() -> int:
    hs = _hs()
    OUT.mkdir(parents=True, exist_ok=True)
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    res = dict(box=list(BOX), provenance="HydroSHEDS v1 (Lehner et al. 2008), derivado de SRTM; NO es cartografía oficial",
               licence_page=prev.get("licence_page"), deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY")
    for key in ("dir15", "acc15", "rivers"):
        url = prev[key]["url"]
        z = hs.fetch(url, timeout=900)
        if z is None:
            res[key] = dict(url=url, status="DESCARGA_FALLIDA")
            continue
        sha = hashlib.sha256(z).hexdigest()
        meta = rivers(hs, z) if key == "rivers" else hs.crop_raster(z, key)
        res[key] = dict(url=url, zip_sha256=sha, same_release_as_binational=(sha == prev[key]["zip_sha256"]), **meta)
        del z
    res["requests"] = hs.LOG
    (OUT / "provenance.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ok = all(res.get(k, {}).get("status") == "OK" for k in ("dir15", "acc15"))
    print(json.dumps({k: res.get(k, {}).get("status") for k in ("dir15", "acc15", "rivers")}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
