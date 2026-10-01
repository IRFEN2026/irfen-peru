"""Preregistered C6d comparison: union of the frozen N7 children vs a frozen N6 parent.

Pure functions, stdlib only. This module was written and hashed into
config/phase2_casma_n6_parent_c6d_preregistration_v0_1.json BEFORE any parent
geometry was retrieved; changing it after capture is a protocol deviation.

Inputs are rings of (lon, lat) WGS84 degrees. Areas are computed in the
Lambert cylindrical equal-area projection on the WGS84 ellipsoid; distances in
a local tangent-plane frame (see ``local_frame``).
"""
from __future__ import annotations

import math

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)
WGS84_E = math.sqrt(WGS84_E2)


# --------------------------------------------------------------------------
# Projections
# --------------------------------------------------------------------------

def _q(lat_deg: float) -> float:
    s = math.sin(math.radians(lat_deg))
    return (1 - WGS84_E2) * (s / (1 - WGS84_E2 * s * s) - (1 / (2 * WGS84_E)) * math.log((1 - WGS84_E * s) / (1 + WGS84_E * s)))


def cea(lon: float, lat: float) -> tuple[float, float]:
    """Lambert cylindrical equal-area on the WGS84 ellipsoid (metres)."""
    return WGS84_A * math.radians(lon), WGS84_A * _q(lat) / 2


def local_frame(lon0: float, lat0: float):
    """Tangent-plane frame at (lon0, lat0): x = N cos(lat0) dlon, y = M dlat (metres)."""
    s = math.sin(math.radians(lat0))
    n_radius = WGS84_A / math.sqrt(1 - WGS84_E2 * s * s)
    m_radius = WGS84_A * (1 - WGS84_E2) / (1 - WGS84_E2 * s * s) ** 1.5
    kx = n_radius * math.cos(math.radians(lat0)) * math.pi / 180
    ky = m_radius * math.pi / 180

    def to_xy(lon: float, lat: float) -> tuple[float, float]:
        return kx * (lon - lon0), ky * (lat - lat0)

    return to_xy


# --------------------------------------------------------------------------
# Ring helpers
# --------------------------------------------------------------------------

def signed_area(ring) -> float:
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:])) / 2


def normalize(rings):
    """Orient a polygon (list of closed rings) so its total signed area is positive."""
    total = sum(signed_area(r) for r in rings)
    return [list(reversed(r)) for r in rings] if total < 0 else [list(r) for r in rings]


def segments(rings):
    return [(a, b) for r in rings for a, b in zip(r, r[1:]) if a != b]


class StripIndex:
    """Horizontal strips for fast winding-number queries."""

    def __init__(self, segs, strips=1024):
        ys = [c for s in segs for c in (s[0][1], s[1][1])]
        self.y0, y1 = min(ys), max(ys)
        self.h = ((y1 - self.y0) or 1.0) / strips
        self.n = strips
        self.bins = [[] for _ in range(strips)]
        for seg in segs:
            lo = self._bin(min(seg[0][1], seg[1][1]))
            hi = self._bin(max(seg[0][1], seg[1][1]))
            for i in range(lo, hi + 1):
                self.bins[i].append(seg)

    def _bin(self, y):
        return min(self.n - 1, max(0, int((y - self.y0) / self.h)))

    def winding(self, p) -> int:
        px, py = p
        w = 0
        for a, b in self.bins[self._bin(py)]:
            if a[1] <= py < b[1]:
                if (b[0] - a[0]) * (py - a[1]) - (px - a[0]) * (b[1] - a[1]) > 0:
                    w += 1
            elif b[1] <= py < a[1]:
                if (b[0] - a[0]) * (py - a[1]) - (px - a[0]) * (b[1] - a[1]) < 0:
                    w -= 1
        return w


class SegmentGrid:
    def __init__(self, segs, cell):
        self.cell = cell
        self.cells = {}
        for idx, (a, b) in enumerate(segs):
            for key in self._keys(a, b):
                self.cells.setdefault(key, []).append(idx)
        self.segs = segs
        keys = list(self.cells)
        self.bounds = (min(k[0] for k in keys), min(k[1] for k in keys), max(k[0] for k in keys), max(k[1] for k in keys))

    def _keys(self, a, b):
        c = self.cell
        for ix in range(int(math.floor(min(a[0], b[0]) / c)), int(math.floor(max(a[0], b[0]) / c)) + 1):
            for iy in range(int(math.floor(min(a[1], b[1]) / c)), int(math.floor(max(a[1], b[1]) / c)) + 1):
                yield ix, iy

    def nearest_distance(self, p) -> float:
        c = self.cell
        cx, cy = int(math.floor(p[0] / c)), int(math.floor(p[1] / c))
        best = math.inf
        seen = set()
        max_r = max(abs(cx - self.bounds[0]), abs(cx - self.bounds[2]), abs(cy - self.bounds[1]), abs(cy - self.bounds[3])) + 1
        r = 0
        while r <= max_r:
            for ix in range(cx - r, cx + r + 1):
                for iy in (range(cy - r, cy + r + 1) if ix in (cx - r, cx + r) else (cy - r, cy + r)):
                    for idx in self.cells.get((ix, iy), ()):
                        if idx in seen:
                            continue
                        seen.add(idx)
                        best = min(best, point_segment_distance(p, *self.segs[idx]))
            if best <= r * c:
                break
            r += 1
        return best


def point_segment_distance(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    denom = dx * dx + dy * dy
    t = 0.0 if denom == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def densify(rings, spacing):
    """Boundary samples: every vertex plus evenly spaced points at <= spacing."""
    pts = []
    for a, b in segments(rings):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, math.ceil(length / spacing))
        for i in range(k):
            t = i / k
            pts.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return pts


# --------------------------------------------------------------------------
# Intersection area (boundary integral over split boundaries)
# --------------------------------------------------------------------------

def _split_params(segs_a, segs_b, cell):
    """Parameters t in (0,1) where each segment of A/B meets the other set."""
    grid = SegmentGrid(segs_b, cell)
    split_a = [set() for _ in segs_a]
    split_b = [set() for _ in segs_b]
    for i, (p1, p2) in enumerate(segs_a):
        cand = set()
        for key in grid._keys(p1, p2):
            cand.update(grid.cells.get(key, ()))
        for j in cand:
            q1, q2 = segs_b[j]
            rx, ry = p2[0] - p1[0], p2[1] - p1[1]
            sx, sy = q2[0] - q1[0], q2[1] - q1[1]
            den = rx * sy - ry * sx
            qpx, qpy = q1[0] - p1[0], q1[1] - p1[1]
            if den != 0:
                t = (qpx * sy - qpy * sx) / den
                u = (qpx * ry - qpy * rx) / den
                if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
                    if 0.0 < t < 1.0:
                        split_a[i].add(t)
                    if 0.0 < u < 1.0:
                        split_b[j].add(u)
            elif qpx * ry - qpy * rx == 0:
                rr = rx * rx + ry * ry
                ss = sx * sx + sy * sy
                if rr == 0 or ss == 0:
                    continue
                for q in (q1, q2):
                    t = ((q[0] - p1[0]) * rx + (q[1] - p1[1]) * ry) / rr
                    if 0.0 < t < 1.0:
                        split_a[i].add(t)
                for p in (p1, p2):
                    u = ((p[0] - q1[0]) * sx + (p[1] - q1[1]) * sy) / ss
                    if 0.0 < u < 1.0:
                        split_b[j].add(u)
    return split_a, split_b


def _pieces(seg, params):
    a, b = seg
    ts = [0.0] + sorted(params) + [1.0]
    pts = [(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])) for t in ts]
    pts[0], pts[-1] = a, b
    return list(zip(pts, pts[1:]))


def intersection_area(rings_a, rings_b, cell) -> dict:
    """Area of A ∩ B for polygons given as closed rings in a planar frame.

    Boundary integral: sum the shoelace terms of A's boundary pieces inside B
    and B's pieces inside A. Pieces shared by both boundaries count once when
    the interiors lie on the same side and not at all otherwise.
    """
    ra, rb = normalize(rings_a), normalize(rings_b)
    sa, sb = segments(ra), segments(rb)
    split_a, split_b = _split_params(sa, sb, cell)
    idx_a, idx_b = StripIndex(sa), StripIndex(sb)
    pieces_a = [p for seg, prm in zip(sa, split_a) for p in _pieces(seg, prm)]
    pieces_b = [p for seg, prm in zip(sb, split_b) for p in _pieces(seg, prm)]
    directed_b = {}
    for p in pieces_b:
        directed_b[p] = directed_b.get(p, 0) + 1
    shared_same = {p for p in pieces_a if p in directed_b}
    shared_opposite = {p for p in pieces_a if (p[1], p[0]) in directed_b}
    twice = 0.0
    for a, b in pieces_a:
        if (a, b) in shared_same:
            twice += a[0] * b[1] - b[0] * a[1]
            continue
        if (a, b) in shared_opposite:
            continue
        if idx_b.winding(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) != 0:
            twice += a[0] * b[1] - b[0] * a[1]
    for a, b in pieces_b:
        if (a, b) in shared_same or (b, a) in shared_opposite:
            continue
        if idx_a.winding(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) != 0:
            twice += a[0] * b[1] - b[0] * a[1]
    return {
        "area": twice / 2,
        "shared_same_direction_pieces": len(shared_same),
        "shared_opposite_direction_pieces": len(shared_opposite),
    }


# --------------------------------------------------------------------------
# Preregistered comparison
# --------------------------------------------------------------------------

def nearest_rank_percentile(values, pct) -> float:
    ordered = sorted(values)
    k = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[k - 1]


def compare(union_lonlat, parent_lonlat_rings, prereg: dict, children_lonlat: dict | None = None) -> dict:
    """Compute preregistered metrics and the PASS/FAIL decision.

    ``union_lonlat`` is the closed union ring of the children; ``parent_lonlat_rings``
    the parent's closed rings. Evaluability (identity, CRS, hashes, validity) is
    decided by the caller before calling this function.
    """
    m = prereg["metrics"]
    frame = local_frame(*prereg["local_frame_origin_lonlat"])
    u_cea = [[cea(*p) for p in union_lonlat]]
    p_cea = [[cea(*p) for p in r] for r in parent_lonlat_rings]
    area_u = abs(sum(signed_area(r) for r in normalize(u_cea)))
    area_p = abs(sum(signed_area(r) for r in normalize(p_cea)))
    inter = intersection_area(u_cea, p_cea, prereg["intersection_grid_cell_m"])
    area_i = inter["area"]
    sym = area_u + area_p - 2 * area_i
    sdr = sym / area_p

    spacing = m["M1_p90_boundary_distance"]["densification_spacing_m"]
    u_xy = [[frame(*p) for p in union_lonlat]]
    p_xy = [[frame(*p) for p in r] for r in parent_lonlat_rings]
    cell = prereg["distance_grid_cell_m"]
    grid_u, grid_p = SegmentGrid(segments(u_xy), cell), SegmentGrid(segments(p_xy), cell)
    d_up = [grid_p.nearest_distance(p) for p in densify(u_xy, spacing)]
    d_pu = [grid_u.nearest_distance(p) for p in densify(p_xy, spacing)]
    pooled = d_up + d_pu
    p90 = nearest_rank_percentile(pooled, 90)

    tau = prereg["tolerance"]["tau_m"]
    sdr_bound = prereg["tolerance"]["sdr_bound"]
    m1_pass = p90 <= tau
    m2_pass = sdr <= sdr_bound
    result = {
        "M1_p90_boundary_distance_m": p90,
        "M1_threshold_m": tau,
        "M1_pass": m1_pass,
        "M2_symmetric_difference_ratio": sdr,
        "M2_threshold": sdr_bound,
        "M2_pass": m2_pass,
        "decision": "PASS" if (m1_pass and m2_pass) else "FAIL",
        "report_only": {
            "area_union_children_km2": area_u / 1e6,
            "area_parent_km2": area_p / 1e6,
            "area_intersection_km2": area_i / 1e6,
            "area_symmetric_difference_km2": sym / 1e6,
            "area_union_minus_parent_km2": (area_u - area_p) / 1e6,
            "area_ratio_union_over_parent": area_u / area_p,
            "iou": area_i / (area_u + area_p - area_i),
            "children_area_outside_parent_km2": (area_u - area_i) / 1e6,
            "parent_area_outside_children_km2": (area_p - area_i) / 1e6,
            "hausdorff_m": max(pooled),
            "directed_max_union_to_parent_m": max(d_up),
            "directed_max_parent_to_union_m": max(d_pu),
            "mean_boundary_distance_m": sum(pooled) / len(pooled),
            "median_boundary_distance_m": nearest_rank_percentile(pooled, 50),
            "p99_boundary_distance_m": nearest_rank_percentile(pooled, 99),
            "fraction_samples_within_tau": sum(1 for d in pooled if d <= tau) / len(pooled),
            "boundary_samples": {"union": len(d_up), "parent": len(d_pu)},
            "shared_boundary_pieces_same_direction": inter["shared_same_direction_pieces"],
            "shared_boundary_pieces_opposite_direction": inter["shared_opposite_direction_pieces"],
        },
    }
    if children_lonlat:
        per_child = {}
        for code, ring in sorted(children_lonlat.items()):
            c_cea = [[cea(*p) for p in ring]]
            a_c = abs(sum(signed_area(r) for r in normalize(c_cea)))
            a_ci = intersection_area(c_cea, p_cea, prereg["intersection_grid_cell_m"])["area"]
            per_child[code] = {"area_km2": a_c / 1e6, "area_outside_parent_km2": (a_c - a_ci) / 1e6, "fraction_outside_parent": (a_c - a_ci) / a_c}
        result["report_only"]["per_child"] = per_child
    return result
