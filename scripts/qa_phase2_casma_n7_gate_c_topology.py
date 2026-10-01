#!/usr/bin/env python3
"""Gate C topology QA for the nine frozen Casma N7 polygons (research only).

Reads only the immutable Gate A capture, evaluates the preregistered checks in
config/phase2_casma_n7_gate_c_topology_contract_v0_1.json and writes (or
verifies) a deterministic fail-closed report. Geometric predicates are exact:
a floating-point filter (Shewchuk's orient2d error bound) falls back to rational
arithmetic, and vertices are compared by exact value with no snapping.

This QA never modifies Gate B, never asserts equivalence to INRENA Uh_pfas100
and never authorizes map publication.

Exit codes: 0 = report reproduced and gate not FAIL; 1 = gate FAIL;
2 = report drift or input/integrity error.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config/phase2_casma_n7_gate_c_topology_contract_v0_1.json"
RECOVERY_SCRIPT = ROOT / "scripts/recover_phase2_casma_minam_n7.py"
RECOVERY_CONTRACT = ROOT / "config/phase2_casma_minam_n7_recovery_contract_v0_1.json"
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
PASS, FAIL, NOT_EVALUABLE = "PASS", "FAIL", "NOT_EVALUABLE"

# WGS84
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
WGS84_E = math.sqrt(WGS84_E2)
# Albers equal-area parameters used only for the implementation cross-check.
ALBERS_LAT1, ALBERS_LAT2, ALBERS_LAT0, ALBERS_LON0 = -8.5, -10.0, -9.25, -78.0

CCW_ERRBOUND_A = (3.0 + 16.0 * 2.0**-53) * 2.0**-53


class GateCError(RuntimeError):
    pass


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def guard(doc: dict, label: str) -> None:
    for key, expected in SAFE.items():
        if doc.get(key) != expected:
            raise GateCError(f"UNSAFE_{label}_{key}")


# --------------------------------------------------------------------------
# Exact predicates
# --------------------------------------------------------------------------

def orient(a, b, c) -> int:
    """Exact sign of the orientation determinant of (a, b, c)."""
    detleft = (a[0] - c[0]) * (b[1] - c[1])
    detright = (a[1] - c[1]) * (b[0] - c[0])
    det = detleft - detright
    bound = CCW_ERRBOUND_A * (abs(detleft) + abs(detright))
    if det > bound:
        return 1
    if -det > bound:
        return -1
    ax, ay, bx, by, cx, cy = (Fraction(v) for v in (a[0], a[1], b[0], b[1], c[0], c[1]))
    exact = (ax - cx) * (by - cy) - (ay - cy) * (bx - cx)
    return (exact > 0) - (exact < 0)


def _within(p, q1, q2) -> bool:
    return min(q1[0], q2[0]) <= p[0] <= max(q1[0], q2[0]) and min(q1[1], q2[1]) <= p[1] <= max(q1[1], q2[1])


def segment_relation(p1, p2, q1, q2):
    """Classify two closed segments.

    Returns (kind, points) with kind in DISJOINT, PROPER, TOUCH,
    COLLINEAR_OVERLAP or IDENTICAL; points holds the touch point(s).
    """
    if (
        max(p1[0], p2[0]) < min(q1[0], q2[0]) or max(q1[0], q2[0]) < min(p1[0], p2[0])
        or max(p1[1], p2[1]) < min(q1[1], q2[1]) or max(q1[1], q2[1]) < min(p1[1], p2[1])
    ):
        return "DISJOINT", ()
    if {p1, p2} == {q1, q2}:
        return "IDENTICAL", (p1, p2)
    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return "PROPER", ()
    if d1 == 0 and d2 == 0:
        axis = 0 if p1[0] != p2[0] else 1
        lo = max(min(p1[axis], p2[axis]), min(q1[axis], q2[axis]))
        hi = min(max(p1[axis], p2[axis]), max(q1[axis], q2[axis]))
        if lo < hi:
            return "COLLINEAR_OVERLAP", ()
        if lo == hi:
            pts = tuple(sorted({p for p in (p1, p2, q1, q2) if p[axis] == lo}))
            return "TOUCH", pts
        return "DISJOINT", ()
    points = set()
    if d1 == 0 and _within(p1, q1, q2):
        points.add(p1)
    if d2 == 0 and _within(p2, q1, q2):
        points.add(p2)
    if d3 == 0 and _within(q1, p1, p2):
        points.add(q1)
    if d4 == 0 and _within(q2, p1, p2):
        points.add(q2)
    if points:
        return "TOUCH", tuple(sorted(points))
    return "DISJOINT", ()


def signed_area2(ring) -> Fraction:
    """Twice the exact signed area of a closed ring (positive = counter-clockwise)."""
    total = Fraction(0)
    for a, b in zip(ring, ring[1:]):
        total += Fraction(a[0]) * Fraction(b[1]) - Fraction(b[0]) * Fraction(a[1])
    return total


def sign(value) -> int:
    return (value > 0) - (value < 0)


class SegmentGrid:
    """Uniform grid over segment bounding boxes for candidate pair generation."""

    def __init__(self, segments, cells_per_side=256):
        xs = [c for s in segments for c in (s[0][0], s[1][0])]
        ys = [c for s in segments for c in (s[0][1], s[1][1])]
        self.x0, self.y0 = min(xs), min(ys)
        span = max(max(xs) - self.x0, max(ys) - self.y0) or 1.0
        self.size = span / cells_per_side
        self.cells: dict[tuple[int, int], list[int]] = {}
        for idx, (a, b) in enumerate(segments):
            for key in self._keys(a, b):
                self.cells.setdefault(key, []).append(idx)

    def _keys(self, a, b):
        ix0 = int((min(a[0], b[0]) - self.x0) // self.size)
        ix1 = int((max(a[0], b[0]) - self.x0) // self.size)
        iy0 = int((min(a[1], b[1]) - self.y0) // self.size)
        iy1 = int((max(a[1], b[1]) - self.y0) // self.size)
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                yield ix, iy

    def candidate_pairs(self):
        seen = set()
        for members in self.cells.values():
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    key = (a, b) if a < b else (b, a)
                    if key not in seen:
                        seen.add(key)
                        yield key


# --------------------------------------------------------------------------
# Input loading
# --------------------------------------------------------------------------

def load_recovery_module():
    spec = importlib.util.spec_from_file_location("casma_recovery_for_gate_c", RECOVERY_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    return module


def input_hashes(manifest: dict) -> dict:
    paths = [manifest["metadata_archive_path"], manifest["geometry_path"], manifest["sha256sums_path"]]
    for row in manifest["features"]:
        paths.extend([row["native_archive_path"], row["raw_archive_path"]])
    return {p: sha256_file(ROOT / p) for p in sorted(paths)}


def load_native(manifest: dict) -> dict:
    units = {}
    for row in manifest["features"]:
        doc = json.loads((ROOT / row["native_archive_path"]).read_bytes())
        units[row["code"]] = {
            "features": doc.get("features") or [],
            "spatial_reference": doc.get("spatialReference"),
        }
    return units


def load_normalized(manifest: dict) -> dict:
    doc = json.loads((ROOT / manifest["geometry_path"]).read_bytes())
    units = {}
    for feature in doc.get("features", []):
        code = str(feature.get("properties", {}).get("n7_code"))
        units.setdefault(code, []).append(feature)
    return units


def native_polygons(units: dict) -> tuple[dict, dict, list]:
    polygons, attributes, anomalies = {}, {}, []
    for code, unit in sorted(units.items()):
        feats = unit["features"]
        if len(feats) != 1:
            anomalies.append({"check": "C1_RING_STRUCTURE", "code": "FEATURE_COUNT", "units": [code], "detail": {"count": len(feats)}})
            continue
        rings = (feats[0].get("geometry") or {}).get("rings") or []
        polygons[code] = [[(float(x), float(y)) for x, y in ring] for ring in rings]
        attributes[code] = feats[0].get("attributes") or {}
    return polygons, attributes, anomalies


def normalized_polygons(units: dict) -> tuple[dict, list]:
    polygons, anomalies = {}, []
    for code, feats in sorted(units.items()):
        if len(feats) != 1:
            anomalies.append({"check": "C1_RING_STRUCTURE", "code": "FEATURE_COUNT", "units": [code], "detail": {"count": len(feats)}})
            continue
        geom = feats[0].get("geometry") or {}
        if geom.get("type") == "Polygon":
            rings = geom["coordinates"]
        elif geom.get("type") == "MultiPolygon":
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        else:
            anomalies.append({"check": "C1_RING_STRUCTURE", "code": "GEOMETRY_TYPE", "units": [code], "detail": {"type": geom.get("type")}})
            continue
        polygons[code] = [[(float(x), float(y)) for x, y in ring] for ring in rings]
    return polygons, anomalies


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_ring_structure(polygons: dict) -> list:
    anomalies = []
    for code, rings in sorted(polygons.items()):
        if not rings:
            anomalies.append({"check": "C1_RING_STRUCTURE", "code": "NO_RINGS", "units": [code], "detail": {}})
        for r_idx, ring in enumerate(rings):
            where = {"ring": r_idx}
            if len(ring) < 4:
                anomalies.append({"check": "C1_RING_STRUCTURE", "code": "TOO_FEW_POSITIONS", "units": [code], "detail": {**where, "positions": len(ring)}})
                continue
            if ring[0] != ring[-1]:
                anomalies.append({"check": "C1_RING_STRUCTURE", "code": "RING_NOT_CLOSED", "units": [code], "detail": {**where, "first": list(ring[0]), "last": list(ring[-1])}})
            seen = {}
            for idx, point in enumerate(ring[:-1]):
                if point in seen:
                    kind = "REPEATED_CONSECUTIVE_VERTEX" if idx - seen[point] == 1 else "REPEATED_VERTEX_SELF_TOUCH"
                    anomalies.append({"check": "C1_RING_STRUCTURE", "code": kind, "units": [code], "detail": {**where, "indices": [seen[point], idx], "point": list(point)}})
                seen[point] = idx
            if signed_area2(ring) == 0:
                anomalies.append({"check": "C1_RING_STRUCTURE", "code": "ZERO_AREA_RING", "units": [code], "detail": where})
    return anomalies


def check_orientation(polygons: dict, *, require_clockwise_shells: bool) -> tuple[list, int | None, dict]:
    anomalies, shell_signs = [], {}
    for code, rings in sorted(polygons.items()):
        signs = [sign(signed_area2(r)) for r in rings if len(r) >= 4]
        if not signs:
            continue
        shell_signs[code] = signs[0]
        for r_idx, s in enumerate(signs[1:], start=1):
            if s == signs[0]:
                anomalies.append({"check": "C2_ORIENTATION", "code": "HOLE_SAME_ORIENTATION_AS_SHELL", "units": [code], "detail": {"ring": r_idx}})
    distinct = set(shell_signs.values())
    shell_sign = None
    if len(distinct) == 1:
        shell_sign = distinct.pop()
    elif distinct:
        anomalies.append({"check": "C2_ORIENTATION", "code": "MIXED_SHELL_ORIENTATION", "units": sorted(shell_signs), "detail": {c: ("CCW" if s > 0 else "CW") for c, s in sorted(shell_signs.items())}})
    if require_clockwise_shells and shell_sign is not None and shell_sign != -1:
        anomalies.append({"check": "C2_ORIENTATION", "code": "ESRI_SHELL_NOT_CLOCKWISE", "units": sorted(shell_signs), "detail": {}})
    info = {"shell_orientation": None if shell_sign is None else ("CCW" if shell_sign > 0 else "CW")}
    return anomalies, shell_sign, info


def ring_segments(polygons: dict):
    """Flatten to (code, ring_idx, seg_idx, n_segs, a, b)."""
    out = []
    for code, rings in sorted(polygons.items()):
        for r_idx, ring in enumerate(rings):
            n = len(ring) - 1
            for s_idx in range(n):
                out.append((code, r_idx, s_idx, n, ring[s_idx], ring[s_idx + 1]))
    return out


def check_intersections(polygons: dict) -> list:
    """C3 (same ring) and C4 (different units) segment-level checks."""
    segs = ring_segments(polygons)
    if not segs:
        return []
    grid = SegmentGrid([(s[4], s[5]) for s in segs])
    anomalies = []
    for i, j in grid.candidate_pairs():
        ci, ri, si, ni, a, b = segs[i]
        cj, rj, sj, nj, c, d = segs[j]
        kind, pts = segment_relation(a, b, c, d)
        if kind == "DISJOINT":
            continue
        if ci == cj and ri == rj:
            adjacent = abs(si - sj) == 1 or {si, sj} == {0, ni - 1}
            if adjacent:
                if kind == "COLLINEAR_OVERLAP":
                    anomalies.append({"check": "C3_SELF_INTERSECTION", "code": "SPIKE_FOLD_BACK", "units": [ci], "detail": {"ring": ri, "segments": sorted([si, sj])}})
                continue
            anomalies.append({"check": "C3_SELF_INTERSECTION", "code": f"SELF_{kind}", "units": [ci], "detail": {"ring": ri, "segments": sorted([si, sj]), "points": [list(p) for p in pts]}})
            continue
        if ci == cj:
            anomalies.append({"check": "C3_SELF_INTERSECTION", "code": f"INTER_RING_{kind}", "units": [ci], "detail": {"rings": [ri, rj], "segments": [si, sj]}})
            continue
        units = sorted([ci, cj])
        if kind == "IDENTICAL":
            continue
        if kind == "TOUCH":
            endpoints_a, endpoints_b = {a, b}, {c, d}
            bad = [p for p in pts if not (p in endpoints_a and p in endpoints_b)]
            if bad:
                anomalies.append({"check": "C4_SIBLING_OVERLAP", "code": "T_JUNCTION_NON_NODED", "units": units, "detail": {"points": [list(p) for p in bad]}})
            continue
        code = "PROPER_CROSSING" if kind == "PROPER" else "COLLINEAR_PARTIAL_OVERLAP"
        anomalies.append({"check": "C4_SIBLING_OVERLAP", "code": code, "units": units, "detail": {"segments": {ci: [ri, si], cj: [rj, sj]}}})
    return anomalies


def point_in_ring(point, ring) -> int:
    """Exact winding test: 1 strictly inside, 0 on boundary, -1 outside."""
    px, py = point
    winding = 0
    for a, b in zip(ring, ring[1:]):
        o = orient(a, b, point)
        if o == 0 and min(a[0], b[0]) <= px <= max(a[0], b[0]) and min(a[1], b[1]) <= py <= max(a[1], b[1]):
            return 0
        if a[1] <= py:
            if b[1] > py and o > 0:
                winding += 1
        elif b[1] <= py and o < 0:
            winding -= 1
    return 1 if winding != 0 else -1


def loop_side(loop, outer) -> int:
    """Side of a non-crossing loop relative to the outer loop (1 in, -1 out, 0 undecidable)."""
    outer_vertices = set(outer)
    for p in loop[:-1]:
        if p not in outer_vertices:
            state = point_in_ring(p, outer)
            if state != 0:
                return state
    outer_edges = {frozenset(e) for e in zip(outer, outer[1:])}
    for a, b in zip(loop, loop[1:]):
        if frozenset((a, b)) not in outer_edges:
            mid = ((Fraction(a[0]) + Fraction(b[0])) / 2, (Fraction(a[1]) + Fraction(b[1])) / 2)
            state = point_in_ring(mid, outer)
            if state != 0:
                return state
    return 0


def edge_topology(polygons: dict):
    """Directed-edge bookkeeping shared by C4, C5 and C6c."""
    undirected: dict[tuple, list] = {}
    for code, rings in sorted(polygons.items()):
        for ring in rings:
            for a, b in zip(ring, ring[1:]):
                key = (a, b) if a <= b else (b, a)
                undirected.setdefault(key, []).append((code, 1 if (a, b) == key else -1))
    owners_of = {key: sorted({u for u, _ in uses}) for key, uses in undirected.items()}
    anomalies, reduced, shared_length = [], [], {}
    for key, uses in undirected.items():
        owners = [u for u, _ in uses]
        net = sum(direction for _, direction in uses)
        if len(uses) > 2:
            anomalies.append({"check": "C4_SIBLING_OVERLAP", "code": "EDGE_MULTIPLICITY_GT_2", "units": sorted(set(owners)), "detail": {"edge": [list(key[0]), list(key[1])], "uses": len(uses)}})
        elif len(uses) == 2:
            if owners[0] == owners[1]:
                anomalies.append({"check": "C4_SIBLING_OVERLAP", "code": "INTRA_UNIT_DUPLICATE_EDGE", "units": [owners[0]], "detail": {"edge": [list(key[0]), list(key[1])]}})
            elif net != 0:
                anomalies.append({"check": "C4_SIBLING_OVERLAP", "code": "SAME_DIRECTION_SHARED_EDGE", "units": sorted(owners), "detail": {"edge": [list(key[0]), list(key[1])]}})
            else:
                pair = tuple(sorted(owners))
                length = math.hypot(key[1][0] - key[0][0], key[1][1] - key[0][1])
                shared_length[pair] = shared_length.get(pair, 0.0) + length
        if net > 0:
            reduced.extend([key] * net)
        elif net < 0:
            reduced.extend([(key[1], key[0])] * (-net))
    return anomalies, reduced, shared_length, owners_of


def extract_cycles(reduced: list):
    anomalies = []
    outgoing: dict[tuple, list] = {}
    indeg: dict[tuple, int] = {}
    for a, b in reduced:
        outgoing.setdefault(a, []).append(b)
        indeg[b] = indeg.get(b, 0) + 1
    vertices = set(outgoing) | set(indeg)
    for v in sorted(vertices):
        out_d, in_d = len(outgoing.get(v, [])), indeg.get(v, 0)
        if out_d != in_d:
            anomalies.append({"check": "C5_UNION_GAPS", "code": "OPEN_BOUNDARY_CHAIN", "units": [], "detail": {"point": list(v), "in": in_d, "out": out_d}})
        elif out_d > 1:
            anomalies.append({"check": "C5_UNION_GAPS", "code": "PINCH_VERTEX", "units": [], "detail": {"point": list(v), "degree": out_d}})
    for v in outgoing:
        outgoing[v].sort()
    cycles = []
    for start in sorted(outgoing):
        while outgoing.get(start):
            ring = [start]
            current = start
            while True:
                nxt_list = outgoing.get(current)
                if not nxt_list:
                    break
                nxt = nxt_list.pop(0)
                ring.append(nxt)
                current = nxt
                if current == start:
                    break
            cycles.append(ring)
    return cycles, anomalies


def check_union(polygons: dict, shell_sign: int | None):
    topo_anoms, reduced, shared_length, owners_of = edge_topology(polygons)
    cycles, cyc_anoms = extract_cycles(reduced)
    anomalies = topo_anoms + cyc_anoms
    unit_area2 = sum((signed_area2(r) for rings in polygons.values() for r in rings), Fraction(0))
    cycle_rows = []
    for ring in cycles:
        a2 = signed_area2(ring) if len(ring) >= 4 and ring[0] == ring[-1] else Fraction(0)
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        owners = sorted({u for a, b in zip(ring, ring[1:]) for u in owners_of.get((a, b) if a <= b else (b, a), [])})
        cycle_rows.append({"ring": ring, "area2": a2, "bbox": [min(xs), min(ys), max(xs), max(ys)], "positions": len(ring), "owners": owners})
    cycle_rows.sort(key=lambda r: abs(r["area2"]), reverse=True)
    outer = None
    if cycle_rows and shell_sign is not None and sign(cycle_rows[0]["area2"]) == shell_sign:
        outer = cycle_rows[0]
    for row in cycle_rows:
        if row is outer:
            continue
        detail = {"area2_abs": float(abs(row["area2"])), "bbox": row["bbox"], "positions": row["positions"]}
        s = sign(row["area2"])
        side = loop_side(row["ring"], outer["ring"]) if outer is not None else 0
        if s == 0:
            anomalies.append({"check": "C5_UNION_GAPS", "code": "DEGENERATE_ZERO_AREA_LOOP", "units": row["owners"], "detail": detail})
        elif shell_sign is not None and s == -shell_sign:
            anomalies.append({"check": "C5_UNION_GAPS", "code": "UNEXPLAINED_GAP", "units": row["owners"], "detail": {**detail, "inside_outer_loop": side == 1}})
        elif side == 1:
            # Same orientation as the shells and inside the outer loop: winding 2, i.e. overlap.
            anomalies.append({"check": "C4_SIBLING_OVERLAP", "code": "OVERLAP_REGION", "units": row["owners"], "detail": detail})
        else:
            anomalies.append({"check": "C5_UNION_GAPS", "code": "DETACHED_COMPONENT", "units": row["owners"], "detail": {**detail, "side": side}})
    if outer is None:
        anomalies.append({"check": "C5_UNION_GAPS", "code": "NO_OUTER_LOOP_WITH_SHELL_ORIENTATION", "units": [], "detail": {}})
    else:
        loop_anoms = check_intersections({"__union__": [outer["ring"]]})
        for anomaly in loop_anoms:
            anomalies.append({"check": "C5_UNION_GAPS", "code": f"UNION_LOOP_{anomaly['code']}", "units": [], "detail": anomaly["detail"]})
    cycle_area2 = sum((r["area2"] for r in cycle_rows), Fraction(0))
    identity_holds = cycle_area2 == unit_area2
    if not identity_holds:
        anomalies.append({"check": "C7_AREAS", "code": "UNION_AREA_IDENTITY_BROKEN", "units": [], "detail": {"sum_units_area2": float(unit_area2), "sum_loops_area2": float(cycle_area2)}})
    summary = {
        "reduced_boundary_loops": len(cycle_rows),
        "outer_loop_positions": None if outer is None else outer["positions"],
        "outer_loop_area_abs": None if outer is None else float(abs(outer["area2"]) / 2),
        "sum_unit_area_abs": float(abs(unit_area2) / 2),
        "union_area_identity_exact": identity_holds,
    }
    return anomalies, shared_length, summary


def check_pfafstetter(contract: dict, polygons: dict, attributes: dict | None, shared_length: dict) -> tuple[list, dict]:
    parent = contract["inputs"]["parent_code"]
    expected = {f"{parent}{d}" for d in range(1, 10)}
    anomalies = []
    found = set(polygons)
    if found != expected:
        anomalies.append({"check": "C6_PARENT_COHERENCE", "code": "PFAFSTETTER_CHILD_SET_MISMATCH", "units": sorted(found ^ expected), "detail": {"missing": sorted(expected - found), "extra": sorted(found - expected)}})
    if attributes is not None:
        for code, attrs in sorted(attributes.items()):
            if str(attrs.get("CODIGO")) != code or str(attrs.get("NIVEL7")) != code or int(attrs.get("NIVEL", -1)) != 7:
                anomalies.append({"check": "C6_PARENT_COHERENCE", "code": "PFAFSTETTER_ATTRIBUTE_MISMATCH", "units": [code], "detail": {k: attrs.get(k) for k in ("CODIGO", "NIVEL7", "NIVEL")}})
    required = [tuple(sorted(p)) for p in contract["checks"]["C6_PARENT_COHERENCE"]["required_adjacency_pairs"]]
    for pair in required:
        if shared_length.get(pair, 0.0) <= 0.0:
            anomalies.append({"check": "C6_PARENT_COHERENCE", "code": "REQUIRED_PFAFSTETTER_ADJACENCY_MISSING", "units": list(pair), "detail": {}})
    extra = sorted(p for p in shared_length if p not in set(required))
    info = {
        "shared_boundary_length": {f"{a}-{b}": round(v, 6) for (a, b), v in sorted(shared_length.items())},
        "required_pairs": [f"{a}-{b}" for a, b in required],
        "additional_adjacencies": [f"{a}-{b}" for a, b in extra],
    }
    return anomalies, info


# --------------------------------------------------------------------------
# Areas
# --------------------------------------------------------------------------

def utm18s_inverse(easting: float, northing: float) -> tuple[float, float]:
    """WGS84 UTM zone 18S -> (lon, lat) degrees (Krueger 6th-order series)."""
    n = WGS84_F / (2 - WGS84_F)
    k0, lon0, fe, fn = 0.9996, math.radians(-75.0), 500000.0, 10000000.0
    big_a = WGS84_A / (1 + n) * (1 + n**2 / 4 + n**4 / 64 + n**6 / 256)
    beta = [
        None,
        n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96 - n**4 / 360 - 81 * n**5 / 512 + 96199 * n**6 / 604800,
        n**2 / 48 + n**3 / 15 - 437 * n**4 / 1440 + 46 * n**5 / 105 - 1118711 * n**6 / 3870720,
        17 * n**3 / 480 - 37 * n**4 / 840 - 209 * n**5 / 4480 + 5569 * n**6 / 90720,
        4397 * n**4 / 161280 - 11 * n**5 / 504 - 830251 * n**6 / 7257600,
        4583 * n**5 / 161280 - 108847 * n**6 / 3991680,
        20648693 * n**6 / 638668800,
    ]
    xi = (northing - fn) / (k0 * big_a)
    eta = (easting - fe) / (k0 * big_a)
    xp = xi - sum(beta[j] * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j in range(1, 7))
    ep = eta - sum(beta[j] * math.cos(2 * j * xi) * math.sinh(2 * j * eta) for j in range(1, 7))
    chi = math.asin(math.sin(xp) / math.cosh(ep))
    t = math.tan(chi)
    tau = t
    for _ in range(20):
        s = math.sinh(WGS84_E * math.atanh(WGS84_E * tau / math.sqrt(1 + tau**2)))
        tp = tau * math.sqrt(1 + s**2) - s * math.sqrt(1 + tau**2)
        tau += (t - tp) / (math.sqrt(1 + tp**2) * math.sqrt(1 + tau**2)) * (
            1 + (1 - WGS84_E2) * tau**2
        ) / ((1 - WGS84_E2) * math.sqrt(1 + tau**2))
    return math.degrees(lon0 + math.atan2(math.sinh(ep), math.cos(xp))), math.degrees(math.atan(tau))


def _q(lat_deg: float) -> float:
    s = math.sin(math.radians(lat_deg))
    return (1 - WGS84_E2) * (s / (1 - WGS84_E2 * s * s) - (1 / (2 * WGS84_E)) * math.log((1 - WGS84_E * s) / (1 + WGS84_E * s)))


def cea_xy(lon: float, lat: float) -> tuple[float, float]:
    """Lambert cylindrical equal-area on the WGS84 ellipsoid (Snyder 10-15)."""
    return WGS84_A * math.radians(lon), WGS84_A * _q(lat) / 2


def _albers_constants():
    def m(lat):
        s = math.sin(math.radians(lat))
        return math.cos(math.radians(lat)) / math.sqrt(1 - WGS84_E2 * s * s)

    m1, m2 = m(ALBERS_LAT1), m(ALBERS_LAT2)
    q1, q2, q0 = _q(ALBERS_LAT1), _q(ALBERS_LAT2), _q(ALBERS_LAT0)
    n = (m1 * m1 - m2 * m2) / (q2 - q1)
    c = m1 * m1 + n * q1
    rho0 = WGS84_A * math.sqrt(c - n * q0) / n
    return n, c, rho0


_ALBERS = _albers_constants()


def albers_xy(lon: float, lat: float) -> tuple[float, float]:
    """Albers equal-area conic on the WGS84 ellipsoid (Snyder 14-1..14-4)."""
    n, c, rho0 = _ALBERS
    rho = WGS84_A * math.sqrt(c - n * _q(lat)) / n
    theta = n * math.radians(lon - ALBERS_LON0)
    return rho * math.sin(theta), rho0 - rho * math.cos(theta)


def planar_area(ring) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2


def area_report(contract: dict, native: dict, attributes: dict, normalized: dict) -> tuple[list, dict]:
    recovery = load(RECOVERY_CONTRACT)
    hist = {u["code"]: float(u["area_km2"]) for u in recovery["units"]}
    rows, anomalies = {}, []
    totals = {k: 0.0 for k in ("planar_utm18s_km2", "ellipsoidal_cea_km2", "ellipsoidal_albers_km2", "ellipsoidal_from_normalized_4326_km2", "service_AREA_KM2", "service_AREA_FINAL", "inventory_2007_km2")}
    bound = contract["tolerances"]["equal_area_implementation_cross_check"]["value"]
    for code in sorted(native):
        shell = native[code][0]
        geo = [utm18s_inverse(x, y) for x, y in shell]
        planar = float(abs(signed_area2(shell)) / 2) / 1e6
        cea = planar_area([cea_xy(lon, lat) for lon, lat in geo]) / 1e6
        alb = planar_area([albers_xy(lon, lat) for lon, lat in geo]) / 1e6
        norm = planar_area([cea_xy(lon, lat) for lon, lat in normalized[code][0]]) / 1e6 if code in normalized else None
        rel = abs(cea - alb) / cea
        if rel > bound:
            anomalies.append({"check": "C7_AREAS", "code": "EQUAL_AREA_CROSS_CHECK_EXCEEDED", "units": [code], "detail": {"relative_difference": rel, "bound": bound}})
        attrs = attributes.get(code, {})
        row = {
            "planar_utm18s_km2": planar,
            "ellipsoidal_cea_km2": cea,
            "ellipsoidal_albers_km2": alb,
            "ellipsoidal_from_normalized_4326_km2": norm,
            "service_AREA_KM2": float(attrs["AREA_KM2"]) if attrs.get("AREA_KM2") is not None else None,
            "service_AREA_FINAL": float(attrs["AREA_FINAL"]) if attrs.get("AREA_FINAL") is not None else None,
            "inventory_2007_km2": hist.get(code),
        }
        for key, value in row.items():
            if value is not None:
                totals[key] += value
        row["delta_service_AREA_KM2_minus_planar_km2"] = None if row["service_AREA_KM2"] is None else row["service_AREA_KM2"] - planar
        row["delta_service_AREA_KM2_minus_ellipsoidal_km2"] = None if row["service_AREA_KM2"] is None else row["service_AREA_KM2"] - cea
        row["delta_service_AREA_FINAL_minus_ellipsoidal_km2"] = None if row["service_AREA_FINAL"] is None else row["service_AREA_FINAL"] - cea
        row["delta_inventory_2007_minus_planar_km2"] = None if row["inventory_2007_km2"] is None else row["inventory_2007_km2"] - planar
        rows[code] = {k: (None if v is None else round(v, 6)) for k, v in row.items()}
    totals_rounded = {k: round(v, 6) for k, v in totals.items()}
    totals_rounded["planar_over_ellipsoidal_ratio"] = round(totals["planar_utm18s_km2"] / totals["ellipsoidal_cea_km2"], 9)
    return anomalies, {
        "per_unit": rows,
        "totals": totals_rounded,
        "semantics": {
            "planar_utm18s_km2": "Exact shoelace area in the storage CRS EPSG:32718 (includes UTM scale distortion; Casma lies ~345 km west of the zone-18 central meridian).",
            "ellipsoidal_cea_km2": "WGS84 ellipsoidal area via Lambert cylindrical equal-area of vertices inverse-projected from EPSG:32718 (straight edges in the projection).",
            "ellipsoidal_albers_km2": "Independent implementation cross-check with Albers equal-area conic.",
            "ellipsoidal_from_normalized_4326_km2": "Same CEA computation on the frozen server-projected EPSG:4326 vertices.",
            "comparisons": "Service AREA_KM2, AREA_FINAL and 2007 inventory deltas are reported only; no tolerance is authorized and none is used to assert historical equivalence.",
        },
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def status_of(anomalies: list, check: str) -> str:
    return FAIL if any(a["check"] == check for a in anomalies) else PASS


def run_dataset(contract: dict, dataset_id: str, polygons: dict, attributes: dict | None, pre_anoms: list, require_clockwise: bool) -> dict:
    anomalies = list(pre_anoms)
    anomalies += check_ring_structure(polygons)
    orient_anoms, shell_sign, orient_info = check_orientation(polygons, require_clockwise_shells=require_clockwise)
    anomalies += orient_anoms
    anomalies += check_intersections(polygons)
    union_anoms, shared_length, union_info = check_union(polygons, shell_sign)
    anomalies += union_anoms
    pf_anoms, pf_info = check_pfafstetter(contract, polygons, attributes, shared_length)
    anomalies += pf_anoms
    for a in anomalies:
        a["dataset"] = dataset_id
    checks = {c: status_of(anomalies, c) for c in ("C1_RING_STRUCTURE", "C2_ORIENTATION", "C3_SELF_INTERSECTION", "C4_SIBLING_OVERLAP", "C5_UNION_GAPS")}
    c6 = {
        "C6a_PFAFSTETTER_COMPLETENESS": FAIL if any(a["code"] in ("PFAFSTETTER_CHILD_SET_MISMATCH", "PFAFSTETTER_ATTRIBUTE_MISMATCH") for a in anomalies) else PASS,
        "C6b_UNION_SIMPLY_CONNECTED": checks["C5_UNION_GAPS"],
        "C6c_PFAFSTETTER_ADJACENCY": FAIL if any(a["code"] == "REQUIRED_PFAFSTETTER_ADJACENCY_MISSING" for a in anomalies) else PASS,
    }
    rfc7946 = None
    if dataset_id == "normalized_publication_crs":
        rfc7946 = orient_info["shell_orientation"] == "CCW"
    return {
        "checks": checks,
        "parent_coherence_subchecks": c6,
        "orientation": orient_info,
        "rfc7946_right_hand_rule_shells": rfc7946,
        "union": union_info,
        "pfafstetter": pf_info,
        "vertex_count": sum(len(r) for rings in polygons.values() for r in rings),
        "anomalies": anomalies,
    }


def _load_script(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def union_loop(polygons: dict):
    """The C5 outer loop (largest reduced boundary cycle) of the children."""
    _, reduced, _, _ = edge_topology(polygons)
    cycles, _ = extract_cycles(reduced)
    return max(cycles, key=len) if cycles else None


def _round(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    return value


def c6d_diagnostics(c6d, prereg: dict, union: list, parent_shell: list) -> dict:
    """Non-gating, post-capture description of where the boundaries differ.

    Uses only public functions of the frozen comparison module; never feeds
    the C6d decision.
    """
    lon0, lat0 = prereg["local_frame_origin_lonlat"]
    frame = c6d.local_frame(lon0, lat0)
    kx, ky = frame(lon0 + 1, lat0)[0], frame(lon0, lat0 + 1)[1]
    u_xy, p_xy = [[frame(*p) for p in union]], [[frame(*p) for p in parent_shell]]
    cell = prereg["distance_grid_cell_m"]
    spacing = prereg["metrics"]["M1_p90_boundary_distance"]["densification_spacing_m"]
    out = {}
    for label, samples, target in (("union_to_parent", c6d.densify(u_xy, spacing), p_xy), ("parent_to_union", c6d.densify(p_xy, spacing), u_xy)):
        grid = c6d.SegmentGrid(c6d.segments(target), cell)
        dist = [(grid.nearest_distance(p), p) for p in samples]
        clusters = []
        for value, p in sorted((d for d in dist if d[0] > 1.0), reverse=True):
            for c in clusters:
                if math.hypot(c["p"][0] - p[0], c["p"][1] - p[1]) < 500.0:
                    c["samples_over_1m"] += 1
                    break
            else:
                clusters.append({"p": p, "max_m": value, "samples_over_1m": 1})
        out[label] = {
            "samples": len(dist),
            "samples_over_1m": sum(1 for d, _ in dist if d > 1.0),
            "samples_over_0_01m": sum(1 for d, _ in dist if d > 0.01),
            "largest_deviation_clusters": [
                {"lon": round(c["p"][0] / kx + lon0, 5), "lat": round(c["p"][1] / ky + lat0, 5), "max_m": round(c["max_m"], 3), "samples_over_1m": c["samples_over_1m"]}
                for c in clusters[:6]
            ],
        }
    key = lambda p: (round(p[0], 7), round(p[1], 7))
    out["vertices"] = {
        "union_positions": len(union),
        "parent_positions": len(parent_shell),
        "parent_positions_matching_union_vertex_1e-7_deg": len({key(p) for p in parent_shell[:-1]} & {key(p) for p in union[:-1]}),
    }
    return out


def evaluate_c6d(source: dict | None, native: dict, c5_passed: bool) -> dict:
    """C6d: preregistered comparison with the independently frozen N6 parent.

    Metrics are computed only by the preregistered comparison module, whose
    SHA-256 must match the preregistration; this function only checks
    evaluability and wires inputs.
    """
    if source is None:
        return {"status": NOT_EVALUABLE, "reasons": ["NO_EXTERNAL_PARENT_SOURCE"]}
    reasons = []
    prereg_path = ROOT / source["preregistration"]
    prereg = load(prereg_path)
    try:
        capture = _load_script(source["capture_script"], "casma_parent_capture_for_gate_c")
        manifest = capture.verify()
    except Exception as exc:
        return {"status": NOT_EVALUABLE, "reasons": [f"PARENT_CAPTURE_VERIFY_FAILED {type(exc).__name__}: {exc}"]}
    module_path = ROOT / prereg["comparison_module_path"]
    if sha256_file(module_path) != prereg["comparison_module_sha256"]:
        reasons.append("COMPARISON_MODULE_HASH_MISMATCH")
    if manifest["preregistration_sha256_at_capture"] != sha256_file(prereg_path):
        reasons.append("PREREGISTRATION_CHANGED_AFTER_CAPTURE")
    raw = json.loads((ROOT / manifest["raw_archive_path"]).read_bytes())
    rings = [[(float(x), float(y)) for x, y in ring] for ring in raw["features"][0]["geometry"]["rings"]]
    validity = check_ring_structure({"137596": rings}) + check_intersections({"137596": rings})
    if validity:
        reasons.append("PARENT_GEOMETRY_INVALID")
    if not c5_passed:
        reasons.append("CHILDREN_UNION_NOT_A_SINGLE_SIMPLE_LOOP")
    base = {
        "source": {
            "capture_manifest": source["capture_manifest"],
            "capture_manifest_sha256": sha256_file(ROOT / source["capture_manifest"]),
            "layer_url": manifest["source"]["layer_url"],
            "query_url": manifest["query_url"],
            "raw_response_sha256": manifest["raw_response_sha256"],
            "metadata_sha256": manifest["metadata_sha256"],
            "retrieved_at_utc": manifest["retrieved_at_utc"],
            "response_spatial_reference": manifest["crs"]["response_spatial_reference"],
            "layer_source_spatial_reference_wkid": manifest["crs"]["layer_source_spatial_reference"].get("wkid"),
            "identity": manifest["identity"],
        },
        "preregistration_sha256": sha256_file(prereg_path),
        "comparison_module_sha256": sha256_file(module_path),
        "parent_validity_anomalies": validity,
        "parent_ring_count": len(rings),
        "parent_position_count": sum(len(r) for r in rings),
    }
    if reasons:
        return {"status": NOT_EVALUABLE, "reasons": reasons, **base}
    c6d = _load_script(prereg["comparison_module_path"], "c6d_parent_comparison_for_gate_c")
    loop = union_loop(native)
    union = [utm18s_inverse(x, y) for x, y in loop]
    children = {code: [utm18s_inverse(x, y) for x, y in rings_[0]] for code, rings_ in sorted(native.items())}
    result = c6d.compare(union, rings, prereg, children)
    result["report_only"]["post_capture_diagnostics"] = c6d_diagnostics(c6d, prereg, union, rings[0])
    attr_area = manifest["identity"].get("AREA_KM2")
    result["report_only"]["parent_AREA_KM2_attribute"] = attr_area
    if attr_area is not None:
        result["report_only"]["parent_AREA_KM2_minus_computed_km2"] = float(attr_area) - result["report_only"]["area_parent_km2"]
    return {"status": result["decision"], "reasons": [], **base, "metrics": _round(result)}


def evaluate(contract_path: Path = DEFAULT_CONTRACT) -> dict:
    contract = load(contract_path)
    guard(contract, "CONTRACT")
    manifest_path = ROOT / contract["inputs"]["gate_a_manifest"]
    manifest = load(manifest_path)
    recovery = load_recovery_module()
    integrity = []
    try:
        recovery.verify_existing(load(RECOVERY_CONTRACT))
    except Exception as exc:  # fail closed on any Gate A integrity failure
        integrity.append({"check": "C0_INPUT_INTEGRITY", "code": "GATE_A_VERIFY_FAILED", "units": [], "detail": {"error": str(exc)}, "dataset": "gate_a"})
    if manifest.get("gate_b_lineage_equivalence") != "NOT_ESTABLISHED" or manifest.get("historical_geometry_equivalence_to_Uh_pfas100") is not False:
        integrity.append({"check": "C0_INPUT_INTEGRITY", "code": "GATE_B_STATE_UNEXPECTED", "units": [], "detail": {}, "dataset": "gate_a"})
    before = input_hashes(manifest)
    manifest_hashes = {row["native_archive_path"]: row["native_response_sha256"] for row in manifest["features"]}
    manifest_hashes.update({row["raw_archive_path"]: row["raw_response_sha256"] for row in manifest["features"]})
    manifest_hashes[manifest["geometry_path"]] = manifest["geometry_sha256"]
    manifest_hashes[manifest["metadata_archive_path"]] = manifest["metadata_sha256"]
    manifest_hashes[manifest["sha256sums_path"]] = manifest["sha256sums_sha256"]
    for path, digest in sorted(manifest_hashes.items()):
        if before.get(path) != digest:
            integrity.append({"check": "C0_INPUT_INTEGRITY", "code": "INPUT_HASH_MISMATCH", "units": [], "detail": {"path": path}, "dataset": "gate_a"})

    native_units = load_native(manifest)
    wkids = {u["spatial_reference"].get("wkid") for u in native_units.values() if u["spatial_reference"]}
    if wkids != {32718}:
        integrity.append({"check": "C0_INPUT_INTEGRITY", "code": "NATIVE_CRS_UNEXPECTED", "units": [], "detail": {"wkids": sorted(map(str, wkids))}, "dataset": "gate_a"})
    native, attributes, native_pre = native_polygons(native_units)
    normalized, normalized_pre = normalized_polygons(load_normalized(manifest))

    datasets = {
        "native_storage_crs": run_dataset(contract, "native_storage_crs", native, attributes, native_pre, True),
        "normalized_publication_crs": run_dataset(contract, "normalized_publication_crs", normalized, None, normalized_pre, False),
    }
    if datasets["native_storage_crs"]["pfafstetter"]["shared_boundary_length"].keys() != datasets["normalized_publication_crs"]["pfafstetter"]["shared_boundary_length"].keys():
        integrity.append({"check": "C4_SIBLING_OVERLAP", "code": "ADJACENCY_DIFFERS_BETWEEN_DATASETS", "units": [], "detail": {}, "dataset": "cross_dataset"})
    area_anoms, areas = area_report(contract, native, attributes, normalized)
    for a in area_anoms:
        a["dataset"] = "native_storage_crs"
    union_identity = all(d["union"]["union_area_identity_exact"] for d in datasets.values())

    after = input_hashes(manifest)
    hash_stable = before == after
    if not hash_stable:
        integrity.append({"check": "C8_HASH_STABILITY", "code": "INPUT_CHANGED_DURING_QA", "units": [], "detail": {}, "dataset": "gate_a"})

    anomalies = integrity + area_anoms + [a for d in datasets.values() for a in d["anomalies"]]
    anomalies.sort(key=lambda a: (a["dataset"], a["check"], a["code"], a["units"], json.dumps(a["detail"], sort_keys=True)))

    def agg(check: str) -> str:
        return FAIL if any(a["check"] == check for a in anomalies) else PASS

    parent_sub = {}
    for key in ("C6a_PFAFSTETTER_COMPLETENESS", "C6b_UNION_SIMPLY_CONNECTED", "C6c_PFAFSTETTER_ADJACENCY"):
        parent_sub[key] = FAIL if any(d["parent_coherence_subchecks"][key] == FAIL for d in datasets.values()) else PASS
    c6d_result = evaluate_c6d(
        contract["checks"]["C6_PARENT_COHERENCE"]["external_parent_source"],
        native,
        datasets["native_storage_crs"]["checks"]["C5_UNION_GAPS"] == PASS,
    )
    parent_sub["C6d_EXTERNAL_PARENT_POLYGON"] = c6d_result["status"]
    c6_status = FAIL if FAIL in parent_sub.values() else (NOT_EVALUABLE if NOT_EVALUABLE in parent_sub.values() else PASS)
    summary = {
        "C0_INPUT_INTEGRITY": agg("C0_INPUT_INTEGRITY"),
        "C1_RING_STRUCTURE": agg("C1_RING_STRUCTURE"),
        "C2_ORIENTATION": agg("C2_ORIENTATION"),
        "C3_SELF_INTERSECTION": agg("C3_SELF_INTERSECTION"),
        "C4_SIBLING_OVERLAP": agg("C4_SIBLING_OVERLAP"),
        "C5_UNION_GAPS": agg("C5_UNION_GAPS"),
        "C6_PARENT_COHERENCE": c6_status,
        "C7_AREAS": FAIL if (agg("C7_AREAS") == FAIL or not union_identity) else PASS,
        "C8_HASH_STABILITY": PASS if hash_stable else FAIL,
    }
    statuses = set(summary.values())
    gate = "FAIL" if FAIL in statuses else ("NOT_PASS_PENDING" if NOT_EVALUABLE in statuses else "PASS")
    return {
        "schema_version": "0.1",
        "report_id": "casma_n7_gate_c_topology_report_v0_1",
        **SAFE,
        "contract_path": str(contract_path.relative_to(ROOT)),
        "contract_sha256": sha256_file(contract_path),
        "qa_script_sha256": sha256_file(Path(__file__).resolve()),
        "gate_a_manifest_sha256": sha256_file(manifest_path),
        "input_sha256": before,
        "checks": summary,
        "parent_coherence_subchecks": parent_sub,
        "gate_c_status": gate,
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
        "datasets": {k: {kk: vv for kk, vv in v.items() if kk != "anomalies"} for k, v in datasets.items()},
        "areas": areas,
        "c6d_external_parent": c6d_result,
        "certificate": (
            "If every unit ring is simple and consistently oriented (C1-C3), shared edges are exactly noded and "
            "used once in each direction (C4), and the reduced boundary chain is one simple loop with the shell "
            "orientation (C5), then the sum of the nine unit indicator functions equals the indicator of that "
            "loop almost everywhere: no positive-area overlap and no internal gap."
        ),
        "gate_b_lineage_equivalence": "NOT_ESTABLISHED",
        "historical_geometry_equivalence_to_Uh_pfas100": False,
        "map_publication_authorized": False,
        "map_eligible_as_research_context": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--write", action="store_true", help="write the report instead of verifying it")
    args = parser.parse_args()
    contract_path = args.contract if args.contract.is_absolute() else ROOT / args.contract
    try:
        report = evaluate(contract_path)
    except Exception as exc:  # fail closed: any unexpected error blocks Gate C
        print(f"GATE_C_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    report_path = ROOT / load(contract_path)["outputs"]["report_path"]
    text = canonical(report)
    if args.write:
        report_path.write_text(text, encoding="utf-8")
    elif not report_path.is_file() or report_path.read_text(encoding="utf-8") != text:
        print("GATE_C_REPORT_DRIFT: committed report differs from recomputation", file=sys.stderr)
        return 2
    print(json.dumps({"gate_c_status": report["gate_c_status"], "checks": report["checks"], "anomaly_count": report["anomaly_count"]}, sort_keys=True))
    return 1 if report["gate_c_status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
