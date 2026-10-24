#!/usr/bin/env python3
"""IRFEN v0.9 — independent scientific QA of the territorial viewer bundle (RESEARCH_ONLY / TEST_ONLY).

Written apart from scripts/v09_build_territory_bundle.py and deliberately does NOT import it: every check re-opens
the raw inputs (catalogue, geometry files, zone registry, rain state, INEI boundaries, national inventory, Pages gate)
and compares them with the committed bundle site/data/v09/territory_v0_1.json.

Checks (each PASS / FAIL with evidence):
  G1 provenance      every drawn feature resolves to an admitted catalogue entity, a v0.9 zone or an INEI province,
                     whose file exists with the recorded SHA-256, and every drawn vertex is a vertex of that source
                     feature (display simplification keeps a subset of vertices, rounded to 1e-4 degrees)
  G2 dem_not_official no geometry derived from a DEM (D8 delimitation, alternative or D8 node) is labelled official
  R1 rain_polygon    every rain value is attached to the polygon it was computed on: zone rain only on the zone's own
                     geometry (same SHA-256); zone values equal the rain engine output; quebrada rain names its area
  R2 missing_not_zero no missing window carries a number; the page shows old or missing data as hatched, never 0
  P1 pages_excluded  with the committed gate the viewer and its bundle are removed from the Pages artifact, and also
                     when only the panel demo gate is open
  I1 inventory_vs_catalogue  the documentary inventory never draws geometry and no inventory id is a map feature

  python scripts/v09_territory_independent_qa.py [--json out.json]     # exit 1 on any FAIL
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "site/data/v09/territory_v0_1.json"
DEM_ROLES = ("DEM_D8_CANDIDATE_CATCHMENT", "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED", "RECEIVER_HYDROLOGIC_INTERSECTION")


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def vertices(geom: dict) -> list[tuple[float, float]]:
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return [tuple(c[:2])]
    if t == "LineString":
        return [tuple(p[:2]) for p in c]
    if t in ("MultiLineString", "Polygon"):
        return [tuple(p[:2]) for part in c for p in part]
    if t == "MultiPolygon":
        return [tuple(p[:2]) for poly in c for ring in poly for p in ring]
    return []


TOL = 6e-5  # display rounding is 1e-4 (north) or 1e-5 (Rímac) degrees: a drawn vertex is within half a unit of a source vertex


def source_vertex_index(geom: dict) -> dict:
    grid: dict = {}
    for x, y in vertices(geom):
        grid.setdefault((math.floor(x * 1000), math.floor(y * 1000)), []).append((x, y))
    return grid


def near_source(v, grid: dict) -> bool:
    x, y = v
    kx, ky = math.floor(x * 1000), math.floor(y * 1000)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for sx, sy in grid.get((kx + dx, ky + dy), []):
                if abs(sx - x) <= TOL and abs(sy - y) <= TOL:
                    return True
    return False


def check_provenance(bundle: dict, out: list) -> None:
    catalog = {f["entity_id"]: f for f in jload(ROOT / "site/data/map_layers.json")["map_semantics"]["features"]}
    zones = {z["zone_id"]: z for z in jload(ROOT / "config/v09_north_surveillance_zones_v0_1.json")["zones"]}
    latest = jload(ROOT / "data/v09/admin_boundaries/latest.json")
    inei_path = ROOT / latest["path"]
    inei_ok = sha(inei_path) == latest["sha256"]
    inei = jload(inei_path)["features"] if inei_ok else []
    fails, n = [], 0
    for f in bundle["geometries"]["features"]:
        p, n = f["properties"], n + 1
        role = p["semantic_role"]
        if role == "V09_SURVEILLANCE_BASIN":
            z = zones.get(p["id"].split("#")[0])
            src_path = ROOT / z["geometry_path"] if z else None
            ok_sha = z is not None and sha(src_path) == z["geometry_sha256"]
            src_feats = jload(src_path).get("features", []) if ok_sha else []
        elif role == "INEI_REFERENTIAL_PROVINCE":
            ok_sha = inei_ok
            src_feats = inei
        else:
            c = catalog.get(p["id"])
            if not c or not c.get("map_eligible"):
                fails.append(f"{p['id']}: not an admitted catalogue entity")
                continue
            src_path = ROOT / "site" / c["path"]
            ok_sha = sha(src_path) == c["file_sha256"] == p.get("file_sha256")
            doc = jload(src_path) if src_path.is_file() else {}
            feats = doc.get("features") or [doc]
            src_feats = [feats[c["selector"]["feature_index"]]] if ok_sha else []
        if not ok_sha:
            fails.append(f"{p['id']}: source file missing or SHA-256 differs")
            continue
        grid: dict = {}
        for sf in src_feats:
            for k, v in source_vertex_index(sf["geometry"]).items():
                grid.setdefault(k, []).extend(v)
        foreign = [v for v in vertices(f["geometry"]) if not near_source(v, grid)]
        if foreign:
            fails.append(f"{p['id']}: {len(foreign)} drawn vertices are not vertices of the source geometry")
    out.append(dict(id="G1", name="provenance", result="PASS" if not fails else "FAIL", checked=n, evidence=fails[:20]))


def check_dem(bundle: dict, out: list) -> None:
    catalog = {f["entity_id"]: f for f in jload(ROOT / "site/data/map_layers.json")["map_semantics"]["features"]}
    fails, dem = [], 0
    for f in bundle["geometries"]["features"]:
        p = f["properties"]
        c = catalog.get(p["id"], {})
        text = json.dumps([p.get("semantic_role"), p.get("node_semantics"), p.get("confidence"), p.get("source_ids"),
                           c.get("semantic_role"), c.get("node_semantics"), c.get("confidence")])
        is_dem = p.get("semantic_role") in DEM_ROLES or p.get("node_semantics") == "REPRODUCIBLE_DERIVED" or bool(
            re.search(r"DEM|D8|COPERNICUS", text))
        if is_dem:
            dem += 1
            if p["evidence"] == "GEOMETRIA_OFICIAL":
                fails.append(f"{p['id']}: DEM-derived geometry labelled official")
            if p["semantic_role"] == "DEM_CANDIDATE_ALTERNATIVE_NOT_SELECTED" and p.get("default_visible") is not False:
                fails.append(f"{p['id']}: a non-selected alternative is visible by default")
    for q in bundle["quebradas"]:
        for alt in q["components"].get("catchment_alternatives", {}).get("drawn", []):
            if alt in q["components"]["catchment"]["drawn"]:
                fails.append(f"{q['quebrada_id']}: alternative {alt} used as the catchment")
    out.append(dict(id="G2", name="dem_not_official", result="PASS" if not fails and dem else "FAIL", dem_features=dem, evidence=fails))


def check_rain_polygon(bundle: dict, out: list) -> None:
    zones = {z["zone_id"]: z for z in jload(ROOT / "config/v09_north_surveillance_zones_v0_1.json")["zones"]}
    state = {z["zone_id"]: z for z in jload(ROOT / "data/v09/surveillance/zone_rain_state_v0_1.json")["zones"]}
    catalog = {f["entity_id"]: f for f in jload(ROOT / "site/data/map_layers.json")["map_semantics"]["features"]}
    fails, notes = [], []
    if bundle.get("inputs", {}).get("data/v09/surveillance/zone_rain_state_v0_1.json") != sha(ROOT / "data/v09/surveillance/zone_rain_state_v0_1.json"):
        notes.append("rain state changed after the bundle was built: value comparison skipped (the v0.9 workflows rebuild it)")
    else:
        for zid, zr in bundle["zone_rain"].items():
            eng = state[zid]["imerg"].get("windows", {})
            for k, w in zr["imerg"]["windows"].items():
                e = eng.get(k, {})
                if "accum_mm" in w and (e.get("status") != "CALCULADO" or e.get("accum_mm") != w["accum_mm"]):
                    fails.append(f"{zid} {k}: bundle {w.get('accum_mm')} vs engine {e.get('accum_mm')} ({e.get('status')})")
    for f in bundle["geometries"]["features"]:
        p = f["properties"]
        zid = p.get("v09_zone")
        if not zid or zid not in zones or p["semantic_role"] == "INEI_REFERENTIAL_PROVINCE":
            continue
        own = (p.get("file_sha256") or (catalog.get(p["id"]) or {}).get("file_sha256"))
        if p["semantic_role"] == "V09_SURVEILLANCE_BASIN":
            own = zones[zid]["geometry_sha256"]
        if own != zones[zid]["geometry_sha256"]:
            fails.append(f"{p['id']} ({p['semantic_role']}) is coloured with the rain of zone {zid}, computed on another polygon "
                         f"({zones[zid]['geometry_path']})")
    for q in bundle["quebradas"]:
        r = q.get("rain_v09")
        if r and (r["zone_id"] != q["rain"].get("v09_zone") or (state[r["zone_id"]].get("display_name") or r["zone_id"]) not in r.get("area_es", "")):
            fails.append(f"{q['quebrada_id']}: rain area not named or not the registered zone")
        for blk in (q.get("rain_v08") or {}, q.get("rain_v09") or {}):
            if blk and "area_es" not in blk:
                fails.append(f"{q['quebrada_id']}: rain block without the area it was computed on")
    out.append(dict(id="R1", name="rain_polygon", result="PASS" if not fails else "FAIL", evidence=fails[:20], notes=notes))


def check_missing_not_zero(bundle: dict, out: list) -> None:
    fails = []
    for zid, zr in bundle["zone_rain"].items():
        for k, w in zr["imerg"]["windows"].items():
            if "accum_mm" not in w and w.get("status") in (None, "CALCULADO"):
                fails.append(f"{zid} {k}: window without value and without a missing status")
            if "accum_mm" in w and w.get("status") not in (None, "CALCULADO"):
                fails.append(f"{zid} {k}: a value attached to a missing window")
    html = (ROOT / "site/v09/territorio.html").read_text(encoding="utf-8")
    for needle in ("imergUsableAt(", "no es lluvia cero", 'fill:"url(#hatch)"', "goesUsableAt(", "geosWindowsAt("):
        if needle not in html:
            fails.append(f"page lacks {needle!r}")
    if re.search(r"accum_mm\s*\?\?\s*0|\|\|\s*0\s*\)?\s*mm", html):
        fails.append("page defaults a missing accumulation to 0")
    out.append(dict(id="R2", name="missing_not_zero", result="PASS" if not fails else "FAIL", evidence=fails,
                    browser="tests/test_v09_territory.py::Browser (clock beyond the IMERG freshness limit → no value, hatch)"))


def check_pages(out: list) -> None:
    fails = []
    gate_script = ROOT / "scripts/v09_pages_publication_gate.py"
    committed_gate = jload(ROOT / "config/v09_public_demo_v0_1.json")
    for label, gate in (("committed gate", committed_gate),
                        ("panel gate open, no territorial approval", dict(committed_gate, publish_v09_dashboard=True, qa_approved_by="QA",
                                                                         qa_approved_at_utc="2026-10-14T00:00:00Z"))):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("scripts/v09_pages_publication_gate.py", "site/v09/territorio.html", "site/v09/shared_rules.js", "site/v09/index.html",
                        "site/data/v09/territory_v0_1.json", "site/data/v09/dashboard_v0_1.json"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, root / rel)
            (root / "config").mkdir()
            (root / "config/v09_public_demo_v0_1.json").write_text(json.dumps(gate), encoding="utf-8")
            subprocess.run([sys.executable, str(root / "scripts/v09_pages_publication_gate.py")], cwd=root, capture_output=True, check=True)
            left = [rel for rel in ("site/v09/territorio.html", "site/v09/shared_rules.js", "site/data/v09/territory_v0_1.json") if (root / rel).exists()]
            if left:
                fails.append(f"{label}: {left} would be published")
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        if "upload-pages-artifact" in text and (
                "v09_pages_publication_gate.py" not in text or text.index("v09_pages_publication_gate.py") > text.index("upload-pages-artifact")):
            fails.append(f"{wf.name}: uploads Pages without running the gate first")
    out.append(dict(id="P1", name="pages_excluded", result="PASS" if not fails and gate_script.is_file() else "FAIL", evidence=fails))


def check_independence(bundle: dict, out: list) -> None:
    inv = jload(ROOT / "config/phase2_national_inventory_completeness_audit_v0_1.json")["candidates"]
    inv_ids = {r["inventory_id"] for r in inv}
    feature_ids = {f["properties"]["id"] for f in bundle["geometries"]["features"]}
    fails = [f"inventory id drawn as a feature: {i}" for i in sorted(inv_ids & feature_ids)]
    for r in bundle.get("inventory_rows", []):
        if set(r) & {"geometry_coordinates", "coordinates", "geojson"} or r.get("map_publishable"):
            fails.append(f"inventory row {r['id']} carries geometry or is publishable")
    eligible = sum(1 for r in inv if r.get("map_eligible"))
    catalogue = (ROOT / "site/data/map_layers.json").read_text(encoding="utf-8")
    if "phase2_national_inventory_completeness_audit" in catalogue:
        fails.append("the map catalogue references the documentary inventory")
    out.append(dict(id="I1", name="inventory_vs_catalogue", result="PASS" if not fails else "FAIL", evidence=fails,
                    counts=dict(inventory_rows=len(inv), inventory_with_reproducible_geometry=sum(1 for r in inv if r["reproducible_geometry"].get("exists")),
                                inventory_map_eligible=eligible, drawn_features=len(feature_ids))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    bundle = jload(BUNDLE)
    out: list[dict] = []
    check_provenance(bundle, out)
    check_dem(bundle, out)
    check_rain_polygon(bundle, out)
    check_missing_not_zero(bundle, out)
    check_pages(out)
    check_independence(bundle, out)
    for c in out:
        print(f"{c['id']} {c['name']}: {c['result']}" + (f" — {c['evidence'][:3]}" if c.get("evidence") else ""))
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if any(c["result"] == "FAIL" for c in out) else 0


if __name__ == "__main__":
    sys.exit(main())
