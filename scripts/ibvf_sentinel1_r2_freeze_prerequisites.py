#!/usr/bin/env python3
"""Freeze Sentinel-1 R2 vertical-grid and precise-orbit prerequisites.

RESEARCH_ONLY / TEST_ONLY. No SAR pre/post response is read or compared here.
Network failure is TRANSPORT_BLOCKED/UNKNOWN, never evidence of missing data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests

UA = "IRFEN-IBVF/0.1 RESEARCH_ONLY TEST_ONLY"
VALIDITY_RE = re.compile(r"_V(\d{8}T\d{6})_(\d{8}T\d{6})\.EOF(?:\.zip)?$", re.I)
HREF_RE = re.compile(r'href=["\']([^"\']*AUX_POEORB[^"\']*\.EOF\.zip)["\']', re.I)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); n = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk); n += len(chunk)
    return h.hexdigest(), n


def get(url: str, timeout: int = 120) -> requests.Response:
    r = requests.get(url, timeout=(20, timeout), headers={"User-Agent": UA})
    r.raise_for_status(); return r


def download(url: str, path: Path) -> dict:
    try:
        h = hashlib.sha256(); n = 0
        with requests.get(url, stream=True, timeout=(30, 600), headers={"User-Agent": UA}) as r:
            r.raise_for_status()
            with path.open("wb") as f:
                for chunk in r.iter_content(4 * 1024 * 1024):
                    if chunk:
                        f.write(chunk); h.update(chunk); n += len(chunk)
        return {"status":"SUCCESS","url":url,"sha256":h.hexdigest(),"bytes":n}
    except Exception as exc:
        if path.exists(): path.unlink()
        return {"status":"TRANSPORT_BLOCKED","scientific_data_status":"UNKNOWN_NOT_MISSING","url":url,"error":repr(exc)}


def parse_utc(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def filename_interval(name: str) -> tuple[datetime, datetime] | None:
    m = VALIDITY_RE.search(name)
    if not m: return None
    return tuple(datetime.strptime(x, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc) for x in m.groups())  # type: ignore


def freeze_orbit(root: str, acquisition: str, side: str, tmp: Path) -> dict:
    t = parse_utc(acquisition)
    month_url = f"{root.rstrip('/')}/{t.year:04d}/{t.month:02d}/"
    try:
        html = get(month_url).text
    except Exception as exc:
        return {"side":side,"acquisition_utc":acquisition,"directory_url":month_url,"status":"TRANSPORT_BLOCKED","scientific_data_status":"UNKNOWN_NOT_MISSING","error":repr(exc)}
    names = sorted(set(HREF_RE.findall(html)))
    covering = []
    for href in names:
        name = Path(href).name
        iv = filename_interval(name)
        if iv and iv[0] <= t <= iv[1]:
            covering.append((href, iv))
    inventory = {"directory_url":month_url,"directory_inventory_success":True,"aux_poeorb_zip_count":len(names),"covering_count":len(covering)}
    if len(covering) != 1:
        return {"side":side,"acquisition_utc":acquisition,"status":"MISSING" if len(covering)==0 else "AMBIGUOUS_BLOCK_R2",**inventory,"covering_files":[Path(x[0]).name for x in covering]}
    href, iv = covering[0]
    url = urljoin(month_url, href)
    zpath = tmp / f"{side}.EOF.zip"
    dl = download(url, zpath)
    if dl["status"] != "SUCCESS": return {"side":side,"acquisition_utc":acquisition,**inventory,**dl}
    try:
        with zipfile.ZipFile(zpath) as z:
            members = [n for n in z.namelist() if n.upper().endswith(".EOF")]
            if len(members) != 1: raise ValueError(f"expected one EOF member, got {members}")
            eof_path = tmp / f"{side}.EOF"
            eof_path.write_bytes(z.read(members[0]))
        eof_sha, eof_bytes = sha_file(eof_path)
        text = eof_path.read_text(encoding="utf-8", errors="replace")
        product_ok = "AUX_POEORB" in text or "AUX_POEORB" in Path(href).name
        validity_ok = iv[0] <= t <= iv[1]
        return {"side":side,"acquisition_utc":acquisition,"status":"PASS" if product_ok and validity_ok else "INTEGRITY_BLOCK_R2",**inventory,"filename":Path(href).name,"url":url,"validity_start":iv[0].isoformat(),"validity_stop":iv[1].isoformat(),"zip_sha256":dl["sha256"],"zip_bytes":dl["bytes"],"inner_eof_member":members[0],"inner_eof_sha256":eof_sha,"inner_eof_bytes":eof_bytes,"product_class_aux_poeorb_confirmed":product_ok,"validity_covers_acquisition":validity_ok}
    except Exception as exc:
        return {"side":side,"acquisition_utc":acquisition,"status":"INTEGRITY_BLOCK_R2",**inventory,"url":url,"zip_sha256":dl.get("sha256"),"error":repr(exc)}


def freeze_vertical(cfg: dict, tmp: Path) -> dict:
    v = cfg["vertical_transform"]
    p = tmp / v["grid_name"]
    dl = download(v["grid_url"], p)
    if dl["status"] != "SUCCESS": return dl
    sig = p.read_bytes()[:4]
    tiff_ok = sig[:2] in (b"II", b"MM")
    try:
        pv = subprocess.run(["projinfo", "--version"], text=True, capture_output=True, timeout=30)
        # Some PROJ builds print version via `proj` rather than projinfo --version.
        proj_version = (pv.stdout + pv.stderr).strip()
        env = dict(__import__("os").environ)
        grid_dir = str(tmp)
        existing = env.get("PROJ_DATA") or env.get("PROJ_LIB")
        env["PROJ_DATA"] = grid_dir + ((":" + existing) if existing else "")
        cmd = ["projinfo", "-s", "EPSG:4326+3855", "-t", "EPSG:4979", "--spatial-test", "intersects"]
        op = subprocess.run(cmd, text=True, capture_output=True, timeout=60, env=env)
        op_text = (op.stdout + op.stderr).strip()
        lower = op_text.lower()
        grid_named = v["grid_name"].lower() in lower
        ballpark = "ballpark" in lower
        op_ok = op.returncode == 0 and grid_named and not ballpark
        return {"status":"PASS" if tiff_ok and op_ok else "BLOCK_R2","url":v["grid_url"],"sha256":dl["sha256"],"bytes":dl["bytes"],"tiff_signature_valid":tiff_ok,"proj_version_output":proj_version,"projinfo_command":" ".join(cmd),"projinfo_returncode":op.returncode,"selected_operation_mentions_frozen_grid":grid_named,"ballpark_detected":ballpark,"projinfo_output":op_text}
    except FileNotFoundError as exc:
        return {"status":"BLOCK_R2_PROJ_NOT_AVAILABLE","url":v["grid_url"],"sha256":dl["sha256"],"bytes":dl["bytes"],"tiff_signature_valid":tiff_ok,"error":repr(exc)}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--contract", required=True); ap.add_argument("--output", required=True); args=ap.parse_args()
    cfg=json.loads(Path(args.contract).read_text(encoding="utf-8"))
    assert cfg["production_use"] is False and cfg["production_ready"] is False and cfg["operational_alerting_enabled"] is False
    with tempfile.TemporaryDirectory(prefix="ibvf-r2-prereq-") as d:
        tmp=Path(d)
        vertical=freeze_vertical(cfg,tmp)
        pre=freeze_orbit(cfg["precise_orbits"]["archive_root"],cfg["precise_orbits"]["pre_acquisition_utc"],"pre",tmp)
        post=freeze_orbit(cfg["precise_orbits"]["archive_root"],cfg["precise_orbits"]["post_acquisition_utc"],"post",tmp)
    passed=vertical.get("status")=="PASS" and pre.get("status")=="PASS" and post.get("status")=="PASS"
    report={"schema_version":"irfen-ibvf-sentinel1-r2-prerequisite-freeze-v0.1","generated_at":now(),"case_id":cfg["case_id"],"deployment_status":"RESEARCH_ONLY","test_only":True,"production_use":False,"production_ready":False,"operational_alerting_enabled":False,"uses_operational_event_none_labels":False,"territorial_activation_evidence_blinded":True,"serious_modeling_gate":"CLOSED_MINIMUM_DATASET_NOT_REACHED","vertical_transform_resource":vertical,"precise_orbits":{"pre":pre,"post":post,"same_quality_class":"AUX_POEORB"},"r2_prerequisite_gate":"PASS" if passed else "BLOCKED","pre_post_response_inspected":False,"comparison_performed":False,"activation_inference_allowed":False}
    Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"gate":report["r2_prerequisite_gate"],"vertical":vertical.get("status"),"pre_orbit":pre.get("status"),"post_orbit":post.get("status")},sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
