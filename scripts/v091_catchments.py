#!/usr/bin/env python3
"""IRFEN v0.9.1 · áreas de aportación experimentales por checkpoint fluvial (HydroSHEDS v1 15″) — RESEARCH_ONLY.

Herramientas sin red y reproducibles sobre los recortes HydroSHEDS archivados (DIR y ACC 15″):
  * snap(): ajusta un vértice IGN al cauce modelado (máxima acumulación en ±3 celdas), con distancia y acumulación;
  * upstream_mask(): todas las celdas que drenan al punto (D8 ESRI), vectorizado;
  * catchment(): área (km², celdas con su área real por latitud), fracción fuera del Perú, celdas IMERG de 0,1° con su
    fracción de cobertura (para medias areales), contorno poligonal exacto de las celdas y rectángulo envolvente.

HydroSHEDS NO es cartografía oficial: las áreas son experimentales y se contrastan con áreas documentadas cuando existen.
"""
from __future__ import annotations

import gzip
import io
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (ROOT / "data/v09/sources/hydrosheds_coast", ROOT / "data/v09/sources/hydrosheds_binational")
# ESRI D8 code -> (d_row, d_col); rows grow southwards
D8 = {1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)}
KM_PER_DEG = 111.32


class Grid:
    def __init__(self, src: Path):
        prov = json.loads((src / "provenance.json").read_text(encoding="utf-8"))
        self.src, self.prov = src, prov
        self.dir = np.load(io.BytesIO(gzip.decompress((src / "dir15.npy.gz").read_bytes())))
        self.acc = np.load(io.BytesIO(gzip.decompress((src / "acc15.npy.gz").read_bytes())))
        t = prov["dir15"]["transform"]
        assert prov["acc15"]["transform"] == t and self.dir.shape == self.acc.shape
        self.res, self.x0, self.y0 = t[0], t[2], t[5]
        self.nrow, self.ncol = self.dir.shape
        self.acc_nodata = prov["acc15"].get("nodata")
        self._down = None
        self._csr = None

    # ---- coordinates
    def rc(self, lon: float, lat: float):
        return int((self.y0 - lat) / self.res), int((lon - self.x0) / self.res)

    def lonlat(self, r, c):
        return self.x0 + (np.asarray(c) + 0.5) * self.res, self.y0 - (np.asarray(r) + 0.5) * self.res

    def inside(self, r, c, margin=0):
        return margin <= r < self.nrow - margin and margin <= c < self.ncol - margin

    # ---- flow graph
    def down(self):
        if self._down is None:
            n = self.nrow * self.ncol
            d = self.dir.reshape(-1).astype(np.int64)
            rr, cc = np.divmod(np.arange(n, dtype=np.int64), self.ncol)
            out = np.full(n, -1, dtype=np.int64)
            for code, (dr, dc) in D8.items():
                m = d == code
                r2, c2 = rr[m] + dr, cc[m] + dc
                ok = (r2 >= 0) & (r2 < self.nrow) & (c2 >= 0) & (c2 < self.ncol)
                idx = np.flatnonzero(m)[ok]
                out[idx] = r2[ok] * self.ncol + c2[ok]
            self._down = out
        return self._down

    def csr(self):
        """upstream adjacency: for cell k, its direct upstream cells are ups[indptr[k]:indptr[k+1]]."""
        if self._csr is None:
            down = self.down()
            src = np.flatnonzero(down >= 0)
            tgt = down[src]
            order = np.argsort(tgt, kind="stable")
            ups = src[order]
            counts = np.bincount(tgt, minlength=down.size)
            indptr = np.zeros(down.size + 1, dtype=np.int64)
            np.cumsum(counts, out=indptr[1:])
            self._csr = (indptr, ups)
        return self._csr

    def upstream_mask(self, r: int, c: int) -> np.ndarray:
        indptr, ups = self.csr()
        seen = np.zeros(self.nrow * self.ncol, dtype=bool)
        frontier = np.array([r * self.ncol + c], dtype=np.int64)
        seen[frontier] = True
        while frontier.size:
            starts, ends = indptr[frontier], indptr[frontier + 1]
            cnt = ends - starts
            if cnt.sum() == 0:
                break
            idx = np.repeat(starts - np.concatenate(([0], np.cumsum(cnt)[:-1])), cnt) + np.arange(cnt.sum())
            nxt = ups[idx]
            nxt = nxt[~seen[nxt]]
            seen[nxt] = True
            frontier = nxt
        return seen.reshape(self.nrow, self.ncol)

    # ---- snapping and catchment
    def snap(self, lon: float, lat: float, w: int = 3):
        r, c = self.rc(lon, lat)
        if not self.inside(r, c, w):
            return None
        win = self.acc[r - w:r + w + 1, c - w:c + w + 1].astype(float)
        if self.acc_nodata is not None:
            win[win == self.acc_nodata] = -1
        if win.max() <= 0:
            return None
        i, j = np.unravel_index(int(np.argmax(win)), win.shape)
        rs, cs = r - w + i, c - w + j
        x, y = self.lonlat(rs, cs)
        dist = math.hypot((float(x) - lon) * KM_PER_DEG * math.cos(math.radians(lat)), (float(y) - lat) * KM_PER_DEG)
        return dict(row=int(rs), col=int(cs), lon=round(float(x), 5), lat=round(float(y), 5), snap_km=round(dist, 2),
                    acc_cells=int(self.acc[rs, cs]))

    def snap_channel(self, lon: float, lat: float, w: int = 4, main_frac: float = 0.5, min_cells: int = 100):
        """Nearest cell of the dominant modelled channel around a mapped vertex.

        ``snap`` (max accumulation in the window) systematically jumps to the most downstream cell of the window, i.e. 1–2 km
        away from the vertex. Here the candidates are the cells of the main stem (accumulation ≥ ``main_frac`` × window max and
        ≥ ``min_cells``) and the nearest one is taken; ties go to the larger accumulation."""
        r, c = self.rc(lon, lat)
        if not self.inside(r, c, w):
            return None
        win = self.acc[r - w:r + w + 1, c - w:c + w + 1].astype(float)
        if self.acc_nodata is not None:
            win[win == self.acc_nodata] = -1
        mx = win.max()
        if mx < min_cells:
            return None
        ii, jj = np.nonzero(win >= max(main_frac * mx, min_cells))
        rs, cs = r - w + ii, c - w + jj
        x, y = self.lonlat(rs, cs)
        d = np.hypot((x - lon) * KM_PER_DEG * math.cos(math.radians(lat)), (y - lat) * KM_PER_DEG)
        k = int(np.lexsort((-win[ii, jj], d))[0])
        rs, cs = int(rs[k]), int(cs[k])
        return dict(row=rs, col=cs, lon=round(float(x[k]), 5), lat=round(float(y[k]), 5), snap_km=round(float(d[k]), 2),
                    acc_cells=int(self.acc[rs, cs]), window_max_acc_cells=int(mx), method="cauce_principal_mas_cercano")

    def cell_area_km2(self, rows: np.ndarray) -> np.ndarray:
        lat = self.y0 - (rows + 0.5) * self.res
        return (self.res * KM_PER_DEG) ** 2 * np.cos(np.radians(lat))

    def catchment(self, r: int, c: int, outside_peru=None) -> dict:
        m = self.upstream_mask(r, c)
        rows, cols = np.nonzero(m)
        area = self.cell_area_km2(rows)
        touches = bool(rows.min() == 0 or cols.min() == 0 or rows.max() == self.nrow - 1 or cols.max() == self.ncol - 1)
        lon, lat = self.lonlat(rows, cols)
        # IMERG 0.1° cells: fraction of each cell covered by the catchment (24 x 24 HydroSHEDS cells per IMERG cell at 15")
        ci = np.floor(lon * 10 + 1e-9).astype(np.int64)
        cj = np.floor(lat * 10 + 1e-9).astype(np.int64)
        uniq, inv = np.unique(np.stack([ci, cj]), axis=1, return_inverse=True)
        inv = inv.reshape(-1)
        w = np.bincount(inv, weights=area)
        cells = []
        for (i, j), a in zip(uniq.T.tolist(), w.tolist()):
            full = (0.1 * KM_PER_DEG) ** 2 * math.cos(math.radians(j / 10 + 0.05))
            cells.append(dict(lon_center=round(i / 10 + 0.05, 2), lat_center=round(j / 10 + 0.05, 2), fraction_inside=round(min(1.0, a / full), 4)))
        out = dict(outlet=dict(row=r, col=c), cells_15s=int(rows.size), area_km2=round(float(area.sum()), 1),
                   touches_crop_edge=touches, bbox=[round(float(lon.min()) - self.res / 2, 4), round(float(lat.min()) - self.res / 2, 4),
                                                    round(float(lon.max()) + self.res / 2, 4), round(float(lat.max()) + self.res / 2, 4)],
                   imerg_cells=cells)
        if outside_peru is not None:
            outp = outside_peru(lon, lat)
            out["fraction_outside_peru"] = round(float(area[outp].sum() / area.sum()), 4)
        out["_mask"] = m
        return out


@lru_cache(maxsize=2)
def grid(prefer_coast: bool = True) -> Grid:
    for s in SOURCES if prefer_coast else SOURCES[::-1]:
        if (s / "dir15.npy.gz").is_file() and (s / "acc15.npy.gz").is_file():
            return Grid(s)
    raise FileNotFoundError("no archived HydroSHEDS crop")


# ---------------------------------------------------------------- polygons
def mask_outline(g: Grid, m: np.ndarray, simplify_deg: float = 0.002) -> dict:
    """Exact outline of a raster mask as a GeoJSON (Multi)Polygon from cell edges (no external libraries), then a
    light Douglas–Peucker simplification (≤ half a 15″ cell) for display and zonal sampling."""
    rows, cols = np.nonzero(m)
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    sub = np.zeros((r1 - r0 + 2, c1 - c0 + 2), dtype=bool)
    sub[1:-1, 1:-1] = m[r0:r1, c0:c1]
    edges = {}
    # directed boundary edges with the region on the left (counter-clockwise exterior in row/col space)
    R, C = np.nonzero(sub)
    for r, c in zip(R.tolist(), C.tolist()):
        if not sub[r - 1, c]:
            edges[(r, c + 1)] = edges.get((r, c + 1), []) + [(r, c)]
        if not sub[r + 1, c]:
            edges[(r + 1, c)] = edges.get((r + 1, c), []) + [(r + 1, c + 1)]
        if not sub[r, c - 1]:
            edges[(r, c)] = edges.get((r, c), []) + [(r + 1, c)]
        if not sub[r, c + 1]:
            edges[(r + 1, c + 1)] = edges.get((r + 1, c + 1), []) + [(r, c + 1)]
    rings = []
    while edges:
        start = next(iter(edges))
        ring, cur = [start], start
        while True:
            nxts = edges.get(cur)
            if not nxts:
                break
            nxt = nxts.pop()
            if not nxts:
                del edges[cur]
            cur = nxt
            if cur == start:
                break
            ring.append(cur)
        if len(ring) >= 3:
            rings.append(ring)

    def to_lonlat(p):
        r, c = p
        return [round(g.x0 + (c + c0 - 1) * g.res, 6), round(g.y0 - (r + r0 - 1) * g.res, 6)]

    def area(ring):
        return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1]))

    def dp(pts, eps):
        if len(pts) < 3:
            return pts
        a, b = np.array(pts[0]), np.array(pts[-1])
        ab = b - a
        n = np.hypot(*ab) or 1e-12
        d = [abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / n for p in pts[1:-1]]
        i = int(np.argmax(d)) + 1
        if d[i - 1] > eps:
            return dp(pts[:i + 1], eps)[:-1] + dp(pts[i:], eps)
        return [pts[0], pts[-1]]

    polys = []
    ll = [[to_lonlat(p) for p in ring] for ring in rings]
    ll = [r for r in ll if len(r) >= 4]
    ext = [r for r in ll if area(r) > 0]
    holes = [r for r in ll if area(r) <= 0]
    for e in ext:
        e2 = dp(e + [e[0]], simplify_deg)
        if len(e2) < 4:
            e2 = e + [e[0]]
        polys.append([e2 if e2[0] == e2[-1] else e2 + [e2[0]]])
    if holes and polys:
        polys[0] += [h + [h[0]] for h in holes]  # holes are rare in D8 catchments; attached to the main ring
    return dict(type="MultiPolygon" if len(polys) > 1 else "Polygon", coordinates=polys if len(polys) > 1 else polys[0])


# ---------------------------------------------------------------- country test (Natural Earth, from the bundle reference)
def outside_peru_fn(reference: dict):
    peru = [f for f in reference["countries"]["features"] if (f["properties"].get("iso") == "PER")]
    rings = []
    for f in peru:
        g = f["geometry"]
        for poly in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            rings.append(np.array(poly[0], dtype=float))

    def inside_ring(x, y, ring):
        res = np.zeros(x.shape, dtype=bool)
        xs, ys = ring[:, 0], ring[:, 1]
        for i in range(len(ring) - 1):
            x1, y1, x2, y2 = xs[i], ys[i], xs[i + 1], ys[i + 1]
            cond = ((y1 > y) != (y2 > y))
            with np.errstate(divide="ignore", invalid="ignore"):
                xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            res ^= cond & (x < xin)
        return res

    def f(lon, lat):
        lon, lat = np.asarray(lon, float), np.asarray(lat, float)
        # aggregate to 0.05° for speed (country borders are 1:10m generalisations anyway)
        q = np.stack([np.round(lon * 20).astype(np.int64), np.round(lat * 20).astype(np.int64)])
        uniq, inv = np.unique(q, axis=1, return_inverse=True)
        inv = inv.reshape(-1)
        ux, uy = uniq[0] / 20.0, uniq[1] / 20.0
        ins = np.zeros(ux.shape, dtype=bool)
        for ring in rings:
            ins |= inside_ring(ux, uy, ring)
        return ~ins[inv]
    return f
