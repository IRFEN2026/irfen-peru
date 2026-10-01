#!/usr/bin/env python3
"""Exact, all-or-nothing freeze of ANA 'Ríos y Quebradas' rows for the Zorritos
priority targets (la_tucilla, los_pozos, sechurita).

Raw response bytes are preserved and hashed; nothing is adjudicated, promoted,
digitised or inferred. Zero rows is recorded as NO_ROWS_NOT_NEGATIVE.

Modes:
  --capture      fetch live (CI runner), validate everything, then write
  --check-only   replay: verify manifest hashes against committed bytes
"""
import argparse
import hashlib
import json
import math
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "site/data/phase2/sources/tumbes_zorritos_priority_ana_vector_freeze_plan_v0_1.json"
OUT_DIR = ROOT / "site/data/phase2/sources/zorritos_priority_ana_capture"
MANIFEST = OUT_DIR / "manifest_v0_1.json"

SAFE = {
    "deployment_status": "RESEARCH_ONLY",
    "test_mode": "TEST_ONLY",
    "production_use": False,
    "production_ready": False,
    "operational_alerting_enabled": False,
    "activation_gate": "BLOCKED",
    "missing_data_rule": "UNKNOWN_NOT_LOW_RISK",
    "decision_thresholds": None,
    "hydraulic_factors": None,
}


class FreezeError(RuntimeError):
    pass


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fold(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()


def utm17s_to_lonlat(easting: float, northing: float) -> tuple[float, float]:
    """Inverse transverse Mercator, WGS84, UTM zone 17 south (EPSG:32717)."""
    a, f, k0 = 6378137.0, 1 / 298.257223563, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x, y = easting - 500000.0, northing - 10000000.0
    mu = (y / k0) / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p = (mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
         + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
         + (151 * e1**3 / 96) * math.sin(6 * mu) + (1097 * e1**4 / 512) * math.sin(8 * mu))
    c, t = ep2 * math.cos(p) ** 2, math.tan(p) ** 2
    n = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    r = a * (1 - e2) / (1 - e2 * math.sin(p) ** 2) ** 1.5
    d = x / (n * k0)
    lat = p - (n * math.tan(p) / r) * (d**2 / 2 - (5 + 3 * t + 10 * c - 4 * c**2 - 9 * ep2) * d**4 / 24
                                        + (61 + 90 * t + 298 * c + 45 * t**2 - 252 * ep2 - 3 * c**2) * d**6 / 720)
    lon = (d - (1 + 2 * t + c) * d**3 / 6 + (5 - 2 * c + 28 * t - 3 * c**2 + 8 * ep2 + 24 * t**2) * d**5 / 120) / math.cos(p)
    return -81.0 + math.degrees(lon), math.degrees(lat)


def load_plan() -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        if plan.get(key) != expected:
            raise FreezeError(f"UNSAFE_PLAN_GUARD_{key}")
    return plan


def metadata_url(plan: dict) -> str:
    return f"{plan['service']}/{plan['layer_id']}?f=pjson"


def query_url(plan: dict, token: str) -> str:
    env = plan["spatial_filter"]
    contract = plan["freeze_contract"]
    params = {
        "where": f"{plan['name_field']} LIKE '%{token.replace(chr(39), chr(39) * 2)}%'",
        "geometry": f"{env['xmin']},{env['ymin']},{env['xmax']},{env['ymax']}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": str(env["spatial_reference_epsg"]),
        "spatialRel": env["spatial_rel"],
        "outFields": contract["out_fields"],
        "returnGeometry": "true" if contract["return_geometry"] else "false",
        "outSR": str(contract["out_sr"]),
        "geometryPrecision": str(contract["geometry_precision"]),
        "orderByFields": "OBJECTID ASC",
        "f": contract["response_format"],
    }
    return f"{plan['service']}/{plan['layer_id']}/query?" + urlencode(params)


def http_fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "IRFEN-research-exact-freeze/1.0"})
    with urlopen(req, timeout=90) as response:
        if response.status != 200:
            raise FreezeError(f"HTTP_{response.status}")
        return response.read()


def parse(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"NON_JSON_{label}") from exc
    if isinstance(value, dict) and "error" in value:
        raise FreezeError(f"SERVICE_ERROR_{label}")
    return value


def validate_metadata(meta: dict, plan: dict) -> None:
    if meta.get("id") != plan["layer_id"]:
        raise FreezeError(f"UNEXPECTED_LAYER_ID_{meta.get('id')}")
    if meta.get("name") != plan["expected_layer_name"]:
        raise FreezeError("UNEXPECTED_LAYER_NAME")
    if meta.get("geometryType") != plan["expected_geometry_type"]:
        raise FreezeError("UNEXPECTED_GEOMETRY_TYPE")
    if "query" not in str(meta.get("capabilities") or "").lower():
        raise FreezeError("LAYER_NOT_QUERYABLE")
    names = {f.get("name") for f in meta.get("fields") or []}
    missing = [f for f in plan["required_fields"] if f not in names]
    if missing:
        raise FreezeError("MISSING_FIELDS_" + "_".join(missing))


def classify_rows(fc: dict, plan: dict, target: dict, label: str) -> tuple[list, list]:
    if fc.get("type") != "FeatureCollection":
        raise FreezeError(f"NOT_FEATURE_COLLECTION_{label}")
    if fc.get("exceededTransferLimit") or (fc.get("properties") or {}).get("exceededTransferLimit"):
        raise FreezeError(f"EXCEEDED_TRANSFER_LIMIT_{label}")
    candidates, quarantine = [], []
    for feature in fc.get("features") or []:
        props = feature.get("properties") or {}
        geom = feature.get("geometry") or {}
        if geom.get("type") not in {"LineString", "MultiLineString"} or not geom.get("coordinates"):
            raise FreezeError(f"NON_LINE_OR_EMPTY_GEOMETRY_{label}")
        name = fold(props.get(plan["name_field"]))
        row = {
            "objectid": props.get("OBJECTID"),
            "name": props.get(plan["name_field"]),
            "codigo_ca": props.get("CODIGO_CA"),
            "codigo_uh": props.get("CODIGO_UH"),
            "feature_sha256": sha256(canonical(feature)),
        }
        hit = next((tok for tok in target["lexical_neighbour_exclusions"] if tok in name), None)
        if hit:
            row["lexical_neighbour_token"] = hit
            quarantine.append(row)
        else:
            candidates.append(row)
    return candidates, quarantine


def build_capture(plan: dict, fetch) -> tuple[dict, dict[str, bytes]]:
    """Fetch and validate every request in memory. Returns (manifest, files)."""
    files: dict[str, bytes] = {}
    meta_url = metadata_url(plan)
    meta_raw = fetch(meta_url)
    validate_metadata(parse(meta_raw, "METADATA"), plan)
    files["layer_metadata.raw.json"] = meta_raw

    targets = {}
    for target in sorted(plan["priority_targets"], key=lambda t: t["priority"]):
        cid = target["component_id"]
        requests = []
        for token in target["tokens"]:
            url = query_url(plan, token)
            raw = fetch(url)
            label = f"{cid}_{token}"
            fc = parse(raw, label)
            candidates, quarantine = classify_rows(fc, plan, target, label)
            fname = f"{cid}__{token.lower()}.raw.geojson"
            files[fname] = raw
            requests.append({
                "token": token,
                "url": url,
                "raw_file": fname,
                "raw_sha256": sha256(raw),
                "canonical_sha256": sha256(canonical(fc)),
                "row_count": len(fc.get("features") or []),
                "candidate_rows": candidates,
                "lexical_neighbour_quarantine": quarantine,
            })
        n_candidates = sum(len(r["candidate_rows"]) for r in requests)
        targets[cid] = {
            "priority": target["priority"],
            "capture_status": "ROWS_CAPTURED_NOT_ADJUDICATED" if n_candidates else "NO_ROWS_NOT_NEGATIVE",
            "candidate_row_count": n_candidates,
            "requests": requests,
            "reference_anchor_ids": target["reference_anchor_ids"],
            "identity_adjudicated": False,
            "outlet_verified": False,
            "map_publishable": False,
        }

    manifest = {
        "schema_version": "0.1",
        **SAFE,
        "status": "RESEARCH_ONLY_EXACT_CAPTURE_NOT_ADJUDICATED",
        "plan": str(PLAN.relative_to(ROOT)),
        "plan_sha256": sha256(PLAN.read_bytes()),
        "service": plan["service"],
        "layer_id": plan["layer_id"],
        "metadata_url": meta_url,
        "metadata_raw_file": "layer_metadata.raw.json",
        "metadata_raw_sha256": sha256(meta_raw),
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "targets": targets,
        "promotion_policy": plan["promotion_policy"],
    }
    return manifest, files


def write_capture(manifest: dict, files: dict[str, bytes], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in files.items():
        (out_dir / name).write_bytes(raw)
    (out_dir / "manifest_v0_1.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_capture(out_dir: Path) -> str:
    manifest_path = out_dir / "manifest_v0_1.json"
    if not manifest_path.exists():
        return "NO_CAPTURE_PRESENT"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, expected in SAFE.items():
        if manifest.get(key) != expected:
            raise FreezeError(f"UNSAFE_MANIFEST_GUARD_{key}")
    if sha256((out_dir / manifest["metadata_raw_file"]).read_bytes()) != manifest["metadata_raw_sha256"]:
        raise FreezeError("METADATA_HASH_MISMATCH")
    for cid, target in manifest["targets"].items():
        if target["map_publishable"] is not False or target["identity_adjudicated"] is not False:
            raise FreezeError(f"PROMOTION_FLAG_SET_{cid}")
        for req in target["requests"]:
            raw = (out_dir / req["raw_file"]).read_bytes()
            if sha256(raw) != req["raw_sha256"]:
                raise FreezeError(f"RAW_HASH_MISMATCH_{req['raw_file']}")
    return "PASS_CAPTURE_REPLAY_HASHES_MATCH"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", action="store_true")
    mode.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only:
        load_plan()
        print(check_capture(OUT_DIR))
        return 0
    manifest, files = build_capture(load_plan(), http_fetch)
    write_capture(manifest, files, OUT_DIR)
    print(json.dumps({t: v["capture_status"] for t, v in manifest["targets"].items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
