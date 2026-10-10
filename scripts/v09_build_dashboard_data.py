#!/usr/bin/env python3
"""IRFEN v0.9 — paquete de datos TEST_ONLY para el panel experimental «Vigilancia SENAMHI» (site/v09/).

Reúne, sin recalcular nada, el registro de avisos y su historial, la salud de la fuente, el cruce territorial, el
estado de lluvia por zona y geometrías simplificadas para el mapa (cuencas verificadas y provincias INEI
referenciales del norte). Las geometrías se simplifican solo para dibujar (Douglas–Peucker); los cálculos usan
siempre las geometrías originales.

El panel recalcula en el navegador los estados FUTURO/VIGENTE/VENCIDO con la vigencia documentada y la hora del
lector, y marca la fuente como DESACTUALIZADA si la instantánea es antigua. No es un sistema de alertas.

  python scripts/v09_build_dashboard_data.py           # escribe site/data/v09/dashboard_v0_1.json si cambió
  python scripts/v09_build_dashboard_data.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/v09/senamhi_avisos/registry_v0_1.json"
HEALTH = ROOT / "data/v09/senamhi_avisos/health_v0_1.json"
CONTRACT = ROOT / "config/v09_senamhi_avisos_contract_v0_1.json"
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
LINKS = ROOT / "data/v09/surveillance/aviso_zone_links_v0_1.json"
RAIN = ROOT / "data/v09/surveillance/zone_rain_state_v0_1.json"
BOUNDARIES_LATEST = ROOT / "data/v09/admin_boundaries/latest.json"
OUT = ROOT / "site/data/v09/dashboard_v0_1.json"
NORTH = ("TUMBES", "PIURA", "LAMBAYEQUE", "LA LIBERTAD", "CAJAMARCA")
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, production_ready=False,
              operational_alerting_enabled=False, activation_gate="BLOCKED", missing_data_rule="UNKNOWN_NOT_LOW_RISK",
              decision_thresholds=None, hydraulic_factors=None)


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _dp(points: list, tol: float) -> list:
    """Douglas–Peucker on a lon/lat ring (display only)."""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5
    best, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm if norm else ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [points[0], points[-1]]
    return _dp(points[: idx + 1], tol)[:-1] + _dp(points[idx:], tol)


def simplify_geometry(geom: dict, tol: float) -> dict | None:
    def ring(r):
        out = [[round(x, 4), round(y, 4)] for x, y in _dp([tuple(p[:2]) for p in r], tol)]
        if out[0] != out[-1]:
            out.append(out[0])
        return out if len(out) >= 4 else None

    def poly(p):
        rings = [x for x in (ring(r) for r in p) if x]
        return rings if rings else None

    if geom["type"] == "Polygon":
        p = poly(geom["coordinates"])
        return dict(type="Polygon", coordinates=p) if p else None
    if geom["type"] == "MultiPolygon":
        ps = [x for x in (poly(p) for p in geom["coordinates"]) if x]
        return dict(type="MultiPolygon", coordinates=ps) if ps else None
    return None


def build() -> dict:
    reg, health, contract = load(REGISTRY) or {}, load(HEALTH) or {}, load(CONTRACT) or {}
    zones_cfg, links, rain = load(ZONES), load(LINKS) or {}, load(RAIN) or {}
    avisos = []
    for key, a in sorted(reg.get("avisos", {}).items()):
        c = a.get("current", {})
        avisos.append(dict(
            aviso_key=key, product=a.get("product"), aviso_number=a.get("aviso_number"), aviso_year=a.get("aviso_year"),
            phenomenon=c.get("phenomenon"), rain_related=c.get("rain_related") if c.get("rain_related") is not None else None,
            validity_start=c.get("validity_start"), validity_end=c.get("validity_end"), validity_text=c.get("validity_text"),
            validity_basis=c.get("validity_basis"), official_level=c.get("official_level"),
            official_level_note=c.get("official_level_note"), official_level_source=c.get("official_level_source"),
            departments=c.get("departments") or [], provinces_by_department=c.get("provinces_by_department"),
            description=c.get("description"), cancellation_text=c.get("cancellation_text"), superseded_by=c.get("superseded_by"),
            extends_aviso_number=c.get("extends_aviso_number"), official_url=a.get("official_url"),
            official_url_kind=a.get("official_url_kind"), stored_status=a.get("status"),
            status_history=a.get("status_history", []),
            revisions=[dict(revision=r["revision"], observed_at_utc=r["observed_at_utc"], document_type=r.get("document_type"),
                            changed_fields=r["changed_fields"]) for r in a.get("revisions", [])],
            documents=a.get("documents", [])))
    events = list(reversed(reg.get("events", [])[-60:]))
    geoms = []
    for z in zones_cfg["zones"]:
        if z["zone_type"] == "BASIN_GEOMETRY":
            doc = load(ROOT / z["geometry_path"])
            for f in doc.get("features") or [doc]:
                g = simplify_geometry(f["geometry"], 0.002)
                if g:
                    geoms.append(dict(type="Feature", geometry=g, properties=dict(kind="BASIN", zone_id=z["zone_id"], name=z["display_name"],
                                                                                 validation_status=z.get("validation_status"))))
    latest = load(BOUNDARIES_LATEST)
    boundary_source = None
    if latest:
        fc = load(ROOT / latest["path"])
        prov = load(ROOT / latest["provenance"])
        boundary_source = {k: prov.get(k) for k in ("institution", "dataset_title", "service_url", "legal_status", "scale", "sha256",
                                                     "obtained_at_utc", "feature_registration_documents")}
        for f in fc["features"]:
            p = f["properties"]
            if p["NOMBDEP"] in NORTH:
                g = simplify_geometry(f["geometry"], 0.005)
                if g:
                    geoms.append(dict(type="Feature", geometry=g, properties=dict(kind="PROVINCE", department=p["NOMBDEP"], province=p["NOMBPROV"])))
    policy = contract.get("snapshot_policy", {})
    return dict(schema_version="0.1", bundle_id="irfen-v09-dashboard:v0.1", **GUARDS, map_publishable=False,
                public_alerting=False,
                disclaimer_es=("Vista experimental de investigación (RESEARCH_ONLY / TEST_ONLY). No es un sistema de alerta, no "
                               "sustituye a SENAMHI, INDECI ni a las autoridades, y no predice activaciones de quebradas ni desbordes. "
                               "Los avisos se reproducen de los boletines de INDECI/COEN; consulte siempre el boletín oficial."),
                source=dict(channel="INDECI/COEN (reproducción oficial de avisos SENAMHI)",
                            senamhi_direct_access=reg.get("senamhi_direct_access"),
                            health=health.get("source_health"), snapshot=health.get("snapshot"),
                            last_check=({k: v for k, v in (health.get("last_check") or {}).items() if k != "request_log"}),
                            checks=(health.get("checks") or [])[-48:],
                            viewer_stale_after_minutes=policy.get("snapshot_stale_after_minutes", 180)),
                avisos=avisos, events=events,
                relation_methods=links.get("relation_methods"), surveillance_zones=links.get("surveillance_zones", []),
                links_evaluated_at_utc=links.get("evaluated_at_utc"), official_boundaries=links.get("official_boundaries"),
                boundary_source=boundary_source,
                rain=dict(evaluated_at_utc=rain.get("evaluated_at_utc"), review_priorities=rain.get("review_priorities"),
                          rules_es=rain.get("rules_es"), zones=rain.get("zones", [])),
                geometries=dict(type="FeatureCollection", features=geoms,
                                note="Simplified for display only (Douglas-Peucker 0.002° basins, 0.005° provinces)."))


def content_equal(a: dict, b: dict) -> bool:
    return {k: v for k, v in a.items() if k != "built_at_utc"} == {k: v for k, v in b.items() if k != "built_at_utc"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = build()
    committed = load(OUT)
    if args.check:
        ok = committed is not None and content_equal(committed, out)
        print("OK" if ok else "FAIL: dashboard bundle does not match its inputs")
        return 0 if ok else 1
    if committed is None or not content_equal(committed, out):
        out["built_at_utc"] = datetime.now(timezone.utc).isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"written {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
