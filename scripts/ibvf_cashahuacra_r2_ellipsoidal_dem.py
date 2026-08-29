#!/usr/bin/env python3
"""Build the frozen Cashahuacra R2 external DEM in WGS84 ellipsoidal heights.

RESEARCH_ONLY / TEST_ONLY. This script reads no Sentinel-1 response pixels and
performs no pre/post comparison. It applies the pre-registered EGM2008 vertical
shift at original cropped GLO-30 pixel centers, preserving the horizontal grid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyproj
import rasterio
import requests
from pyproj import Transformer
from rasterio.mask import mask as rio_mask
from shapely.geometry import box, mapping

UA = "IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); n = 0
    with path.open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b); n += len(b)
    return h.hexdigest(), n


def download(url: str, path: Path) -> dict:
    try:
        h=hashlib.sha256(); n=0
        with requests.get(url, stream=True, timeout=(30,600), headers={"User-Agent":UA}) as r:
            r.raise_for_status()
            with path.open("wb") as f:
                for b in r.iter_content(4*1024*1024):
                    if b:
                        f.write(b); h.update(b); n += len(b)
        return {"status":"SUCCESS","sha256":h.hexdigest(),"bytes":n,"url":url}
    except Exception as exc:
        if path.exists(): path.unlink()
        return {"status":"TRANSPORT_BLOCKED","scientific_data_status":"UNKNOWN_NOT_MISSING","url":url,"error":repr(exc)}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--prerequisites", required=True, type=Path)
    ap.add_argument("--output-dem", required=True, type=Path)
    ap.add_argument("--output-report", required=True, type=Path)
    a=ap.parse_args()
    cfg=load(a.contract); preq=load(a.prerequisites)
    for d in (cfg,preq):
        assert d["production_use"] is False and d["production_ready"] is False and d["operational_alerting_enabled"] is False
        assert d["uses_operational_event_none_labels"] is False
        assert d["territorial_activation_evidence_blinded"] is True
    assert cfg["pre_post_sar_values_read"] is False and cfg["pre_post_difference_allowed"] is False
    assert preq["r2_prerequisite_gate"]=="PASS" and preq["comparison_performed"] is False
    a.output_dem.parent.mkdir(parents=True, exist_ok=True); a.output_report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ibvf-ellipsoid-dem-") as td_raw:
        td=Path(td_raw); raw=td/"glo30.tif"; grid=td/cfg["vertical_grid"]["url"].rsplit("/",1)[-1]
        dem_dl=download(cfg["input_dem"]["url"],raw); grid_dl=download(cfg["vertical_grid"]["url"],grid)
        if dem_dl.get("status")!="SUCCESS" or grid_dl.get("status")!="SUCCESS":
            report={"schema_version":"irfen-ibvf-cashahuacra-r2-ellipsoidal-dem-v0.1","generated_at":now(),"case_id":cfg["case_id"],"deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED","input_dem_transport":dem_dl,"vertical_grid_transport":grid_dl,"ellipsoidal_dem_gate":"BLOCKED_TRANSPORT_UNKNOWN_NOT_MISSING","pre_post_sar_values_read":False,"comparison_performed":False,"activation_inference_allowed":False}
            a.output_report.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"gate":report["ellipsoidal_dem_gate"]})); return 0
        if dem_dl["sha256"] != cfg["input_dem"]["expected_sha256"]: raise RuntimeError("raw DEM SHA256 mismatch")
        if grid_dl["sha256"] != cfg["vertical_grid"]["expected_sha256"] or grid_dl["bytes"] != cfg["vertical_grid"]["expected_bytes"]: raise RuntimeError("vertical grid identity mismatch")
        bbox=cfg["process_bbox_wgs84"]
        with rasterio.open(raw) as src:
            if src.crs is None or src.crs.to_epsg()!=4326: raise RuntimeError(f"unexpected DEM CRS {src.crs}")
            source_nodata=src.nodata
            arr,tr=rio_mask(src,[mapping(box(*bbox))],crop=True,filled=True,nodata=-9999.0)
            z=arr[0].astype(np.float64)
            profile=src.profile.copy()
        valid=np.isfinite(z) & (z != -9999.0)
        if source_nodata is not None: valid &= z != float(source_nodata)
        input_valid=int(valid.sum()); input_nodata=int(z.size-input_valid)
        pipeline=f"+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=vgridshift +grids={grid} +multiplier=1 +step +proj=unitconvert +xy_in=rad +xy_out=deg"
        pyproj.network.set_network_enabled(False)
        transformer=Transformer.from_pipeline(pipeline)
        out=np.full(z.shape,-9999.0,dtype=np.float32)
        corr_min=float("inf"); corr_max=float("-inf"); corr_sum=0.0; corr_n=0; max_xy_delta=0.0
        block_rows=128
        cols=np.arange(z.shape[1],dtype=np.float64)
        for r0 in range(0,z.shape[0],block_rows):
            r1=min(z.shape[0],r0+block_rows); rows=np.arange(r0,r1,dtype=np.float64)
            cc,rr=np.meshgrid(cols,rows)
            xx=tr.c+(cc+0.5)*tr.a+(rr+0.5)*tr.b
            yy=tr.f+(cc+0.5)*tr.d+(rr+0.5)*tr.e
            vv=valid[r0:r1]
            if not vv.any(): continue
            xin=xx[vv]; yin=yy[vv]; zin=z[r0:r1][vv]
            x2,y2,z2=transformer.transform(xin,yin,zin,errcheck=True)
            x2=np.asarray(x2); y2=np.asarray(y2); z2=np.asarray(z2)
            if not np.isfinite(z2).all(): raise RuntimeError("non-finite transformed height")
            max_xy_delta=max(max_xy_delta,float(np.max(np.maximum(np.abs(x2-xin),np.abs(y2-yin)))))
            correction=z2-zin
            corr_min=min(corr_min,float(np.min(correction))); corr_max=max(corr_max,float(np.max(correction))); corr_sum+=float(np.sum(correction)); corr_n+=int(correction.size)
            block=out[r0:r1]; block[vv]=z2.astype(np.float32); out[r0:r1]=block
        if corr_n != input_valid: raise RuntimeError("transformed valid count mismatch")
        if corr_min < -150.0 or corr_max > 150.0: raise RuntimeError(f"vertical correction outside broad sanity range {corr_min},{corr_max}")
        if max_xy_delta > 1e-10: raise RuntimeError(f"unexpected horizontal movement {max_xy_delta}")
        profile.update(driver="GTiff",height=out.shape[0],width=out.shape[1],transform=tr,crs="EPSG:4326",count=1,dtype="float32",nodata=-9999.0,compress="deflate",predictor=3,tiled=True,blockxsize=256,blockysize=256)
        with rasterio.open(a.output_dem,"w",**profile) as dst:
            dst.write(out,1)
            dst.update_tags(IBVF_VERTICAL_SEMANTICS="WGS84_ELLIPSOIDAL_HEIGHT",IBVF_SOURCE_VERTICAL="EGM2008_EPSG3855",IBVF_RESEARCH_ONLY="true")
        out_sha,out_bytes=sha256_file(a.output_dem)
        with rasterio.open(a.output_dem) as chk:
            zchk=chk.read(1); output_valid=int(np.sum(np.isfinite(zchk)&(zchk!=chk.nodata)))
            output_shape=[chk.height,chk.width]; output_transform=list(chk.transform)[:6]; output_crs=str(chk.crs)
        passed=(output_valid==input_valid and output_shape==list(z.shape) and output_crs=="EPSG:4326")
        report={
          "schema_version":"irfen-ibvf-cashahuacra-r2-ellipsoidal-dem-v0.1","generated_at":now(),"case_id":cfg["case_id"],
          "deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED",
          "input_dem":{"item_id":cfg["input_dem"]["item_id"],"sha256":dem_dl["sha256"],"bytes":dem_dl["bytes"],"source_nodata":source_nodata,"cropped_shape":list(z.shape),"cropped_transform":list(tr)[:6],"valid_pixel_count":input_valid,"nodata_pixel_count":input_nodata},
          "vertical_grid":{"sha256":grid_dl["sha256"],"bytes":grid_dl["bytes"],"url":grid_dl["url"]},
          "conversion":{"pipeline":pipeline.replace(str(grid),cfg["vertical_grid"]["url"].rsplit("/",1)[-1]),"pyproj_version":pyproj.__version__,"proj_version":pyproj.proj_version_str,"network_enabled":False,"horizontal_max_abs_delta_degrees":max_xy_delta,"geoid_correction_min_m":corr_min,"geoid_correction_max_m":corr_max,"geoid_correction_mean_m":corr_sum/corr_n,"case_specific_height_adjustment_used":False},
          "output_dem":{"sha256":out_sha,"bytes":out_bytes,"shape":output_shape,"transform":output_transform,"horizontal_crs":output_crs,"vertical_semantics":"WGS84_ELLIPSOIDAL_HEIGHT","valid_pixel_count":output_valid,"nodata_value":-9999.0},
          "ellipsoidal_dem_gate":"PASS" if passed else "BLOCKED_VALIDATION","pre_post_sar_values_read":False,"comparison_performed":False,"activation_inference_allowed":False
        }
        a.output_report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps({"gate":report["ellipsoidal_dem_gate"],"output_sha256":out_sha,"valid":output_valid,"correction_min":corr_min,"correction_max":corr_max},sort_keys=True))
        if not passed: return 2
    return 0

if __name__=="__main__": raise SystemExit(main())
