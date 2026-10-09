#!/usr/bin/env python3
"""IRFEN v0.9 — cruce TEST_ONLY entre avisos SENAMHI (vía INDECI/COEN) y zonas de vigilancia IRFEN.

Entradas: el registro de avisos (data/v09/senamhi_avisos/registry_v0_1.json), las zonas del norte
(config/v09_north_surveillance_zones_v0_1.json) y, si existe, la superposición precalculada de cada cuenca con
los límites provinciales oficiales (data/v09/zone_admin_overlay_v0_1.json, construida por
scripts/v09_build_zone_admin_overlay.py a partir de un archivo oficial INEI/IGN archivado con SHA-256).

Métodos de relación, de más a menos preciso (vocabulario cerrado):
* BASIN_INTERSECTS_LISTED_PROVINCE — la geometría oficial de la cuenca interseca el polígono oficial de una
  provincia que el aviso enumera. Es una intersección espacial verificada con la representación administrativa
  del aviso, nunca con la huella real del aviso (SENAMHI no la publica por este canal).
* BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES — la cuenca está en un departamento del aviso pero no
  interseca ninguna de las provincias enumeradas (se muestra, con menor atención).
* REGISTERED_DEPARTMENT_LISTED — sin límites oficiales disponibles: el departamento registrado de la zona
  figura en el aviso. Coincidencia administrativa, no espacial; la relación provincial queda DESCONOCIDA.
* LISTED_PROVINCE_CONTEXT_NO_BASIN — Piura: cada provincia enumerada es una zona de contexto; no se dibuja ni
  se infiere ninguna cuenca.

Nunca: polígonos inventados, usar los registros documentales 400–418 como geometría, afirmar que una quebrada
se activará o mezclar el nivel oficial de SENAMHI con prioridades IRFEN.

  python scripts/v09_aviso_zone_crossing.py           # escribe data/v09/surveillance/aviso_zone_links_v0_1.json si cambió
  python scripts/v09_aviso_zone_crossing.py --check   # verifica que el archivo está al día y las guardas
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/v09/senamhi_avisos/registry_v0_1.json"
ZONES = ROOT / "config/v09_north_surveillance_zones_v0_1.json"
OVERLAY = ROOT / "data/v09/zone_admin_overlay_v0_1.json"
OUT = ROOT / "data/v09/surveillance/aviso_zone_links_v0_1.json"
GUARDS = {
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
RELATION_METHODS = {
    "BASIN_INTERSECTS_LISTED_PROVINCE": dict(
        rank=1, kind="SPATIAL_VERIFIED_ADMINISTRATIVE",
        label_es="La cuenca interseca una provincia enumerada en el aviso (límites oficiales)",
        caveat_es="Intersección con la representación administrativa del aviso, no con su huella real."),
    "LISTED_PROVINCE_CONTEXT_NO_BASIN": dict(
        rank=2, kind="ADMINISTRATIVE_PROVINCE",
        label_es="Provincia enumerada en el aviso, sin cuenca validada",
        caveat_es="Contexto territorial: no hay cuenca IRFEN validada en esta provincia."),
    "REGISTERED_DEPARTMENT_LISTED": dict(
        rank=3, kind="ADMINISTRATIVE_DEPARTMENT",
        label_es="El departamento registrado de la zona figura en el aviso",
        caveat_es="Coincidencia administrativa; la relación provincial es DESCONOCIDA hasta disponer de límites oficiales."),
    "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES": dict(
        rank=4, kind="SPATIAL_VERIFIED_NEGATIVE",
        label_es="La cuenca está en un departamento del aviso pero fuera de sus provincias enumeradas",
        caveat_es="Se muestra para revisión; el aviso no enumera las provincias de esta cuenca."),
}
ACTIVE = ("VIGENTE", "FUTURO")


def fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn").upper()
    return " ".join(t.replace(".", " ").split())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def overlay_index(overlay: dict | None) -> dict:
    """zone_id -> {(DEPARTMENT, PROVINCE): {area_km2, zone_fraction}} from the precomputed official overlay."""
    if not overlay:
        return {}
    out = {}
    for z in overlay.get("zones", []):
        out[z["zone_id"]] = {(fold(i["department"]), fold(i["province"])): i for i in z.get("intersections", [])}
    return out


def links_for_aviso(aviso: dict, zones: list[dict], overlay: dict | None) -> list[dict]:
    """Relations between one aviso and the surveillance zones. Pure: tested offline."""
    cur = aviso.get("current", {})
    deps = [fold(d) for d in cur.get("departments") or []]
    provs = {fold(d): [fold(p) for p in ps] for d, ps in (cur.get("provinces_by_department") or {}).items()}
    printed = {fold(p): p for ps in (cur.get("provinces_by_department") or {}).values() for p in ps}
    idx = overlay_index(overlay)
    links = []
    for z in zones:
        if z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN":
            dep = fold(z["registered_department"])
            if dep in provs:
                for p in provs[dep]:
                    links.append(dict(zone_id=f"{z['zone_id']}:{p}", base_zone_id=z["zone_id"], relation_method="LISTED_PROVINCE_CONTEXT_NO_BASIN",
                                      department=dep, province=p, province_as_printed=printed.get(p), evidence=dict(aviso_lists_province=True)))
            elif dep in deps:
                links.append(dict(zone_id=z["zone_id"], base_zone_id=z["zone_id"], relation_method="REGISTERED_DEPARTMENT_LISTED",
                                  department=dep, province=None, evidence=dict(aviso_lists_department=True, provinces_listed=False)))
            continue
        zid = z["zone_id"]
        if zid in idx:  # official boundaries available: spatial relation with the listed provinces
            hits = [dict(department=d, province=p, area_km2=v.get("area_km2"), zone_fraction=v.get("zone_fraction"))
                    for (d, p), v in sorted(idx[zid].items()) if p in provs.get(d, [])]
            dep_only = [d for d in deps if d not in provs]  # department listed without provinces
            if hits:
                links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="BASIN_INTERSECTS_LISTED_PROVINCE",
                                  department=hits[0]["department"], province=None, evidence=dict(intersections=hits,
                                  boundary_source_sha256=(overlay or {}).get("boundary_source", {}).get("sha256"))))
            else:
                zone_deps = sorted({d for d, _ in idx[zid]})
                touched = [d for d in zone_deps if d in deps]
                if touched and all(d in provs for d in touched):
                    links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES",
                                      department=touched[0], province=None, evidence=dict(zone_departments=zone_deps,
                                      listed_provinces={d: provs[d] for d in touched})))
                elif touched:
                    links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="REGISTERED_DEPARTMENT_LISTED",
                                      department=touched[0], province=None, evidence=dict(aviso_lists_department=True, provinces_listed=False,
                                                                                         departments_without_provinces=dep_only)))
            continue
        dep = fold(z["registered_department"])
        if dep in deps:
            links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="REGISTERED_DEPARTMENT_LISTED", department=dep, province=None,
                              evidence=dict(aviso_lists_department=True, provinces_listed=dep in provs,
                                            listed_provinces=provs.get(dep), official_boundaries="NOT_AVAILABLE")))
    for link in links:
        meta = RELATION_METHODS[link["relation_method"]]
        link.update(relation_kind=meta["kind"], relation_rank=meta["rank"], label_es=meta["label_es"], caveat_es=meta["caveat_es"])
    return sorted(links, key=lambda l: (l["relation_rank"], l["zone_id"]))


def surveillance_list(registry: dict, zones_cfg: dict, overlay: dict | None) -> dict:
    zones = zones_cfg["zones"]
    by_zone: dict[str, dict] = {}
    aviso_links = {}
    for key in sorted(registry.get("avisos", {})):
        aviso = registry["avisos"][key]
        links = links_for_aviso(aviso, zones, overlay)
        aviso_links[key] = dict(status=aviso.get("status"), product=aviso.get("product"),
                                official_url=aviso.get("official_url"), links=links)
        if aviso.get("status") not in ACTIVE:
            continue
        for link in links:
            z = by_zone.setdefault(link["zone_id"], dict(zone_id=link["zone_id"], base_zone_id=link["base_zone_id"],
                                                         department=link["department"], province=link.get("province"),
                                                         province_as_printed=link.get("province_as_printed"), avisos=[]))
            z["avisos"].append(dict(aviso_key=key, status=aviso["status"], product=aviso.get("product"),
                                    relation_method=link["relation_method"], relation_rank=link["relation_rank"],
                                    validity_start=aviso["current"].get("validity_start"), validity_end=aviso["current"].get("validity_end"),
                                    official_level=aviso["current"].get("official_level"),
                                    official_level_note=None if aviso["current"].get("official_level") else "NOT_STATED_IN_TEXT"))
    zone_meta = {z["zone_id"]: z for z in zones}
    rows = []
    for zid, z in by_zone.items():
        best = min(a["relation_rank"] for a in z["avisos"])
        base = zone_meta[z["base_zone_id"]]
        missing = []
        if base["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN":
            missing.append("no validated basin geometry in this department")
        elif not overlay:
            missing.append("official provincial boundaries not archived: provincial relation unknown, and a basin "
                           "crossing into another department is not detected")
        missing.append("observations (IMERG/GOES/stations) not yet attached (phase 3)")
        rows.append(dict(z, display_name=base["display_name"] + (f" · {z.get('province_as_printed') or z['province']}" if z.get("province") else ""),
                         zone_type=base["zone_type"], best_relation_rank=best,
                         best_relation_method=next(a["relation_method"] for a in z["avisos"] if a["relation_rank"] == best),
                         any_vigente=any(a["status"] == "VIGENTE" for a in z["avisos"]),
                         why_es=sorted({RELATION_METHODS[a["relation_method"]]["label_es"] + f" ({a['aviso_key']}, {a['status']})" for a in z["avisos"]}),
                         missing_data=missing))
    # Ordering is for reading, not a risk score: VIGENTE before FUTURO, then the most precise relation.
    rows.sort(key=lambda r: (not r["any_vigente"], r["best_relation_rank"], r["zone_id"]))
    return dict(schema_version="0.1", output_id="irfen-v09-aviso-zone-links:v0.1", **GUARDS, map_publishable=False,
                inputs=dict(registry_sha256=sha256_bytes(REGISTRY.read_bytes()) if REGISTRY.is_file() else None,
                            zones_sha256=sha256_bytes(ZONES.read_bytes()),
                            overlay_sha256=sha256_bytes(OVERLAY.read_bytes()) if OVERLAY.is_file() else None),
                official_boundaries="AVAILABLE" if overlay else "NOT_AVAILABLE",
                relation_methods=RELATION_METHODS,
                ordering_note_es="El orden facilita la lectura (vigente antes que futuro; relación más precisa primero). "
                                 "No es una puntuación de riesgo ni una probabilidad de activación.",
                surveillance_zones=rows, aviso_links=aviso_links)


def build() -> tuple[bytes, dict]:
    out = surveillance_list(load(REGISTRY) or {"avisos": {}}, load(ZONES), load(OVERLAY))
    return (json.dumps(out, ensure_ascii=False, indent=1) + "\n").encode("utf-8"), out


def check_zones(cfg: dict) -> list[str]:
    errors = []
    for key, value in GUARDS.items():
        if cfg.get(key) != value:
            errors.append(f"zones guard {key} must be {value!r}")
    for z in cfg["zones"]:
        if z.get("activation_gate") != "BLOCKED":
            errors.append(f"{z['zone_id']}: activation_gate must be BLOCKED")
        if z["zone_type"] == "BASIN_GEOMETRY":
            p = ROOT / z["geometry_path"]
            if not p.is_file() or sha256_bytes(p.read_bytes()) != z["geometry_sha256"]:
                errors.append(f"{z['zone_id']}: geometry missing or SHA-256 mismatch")
            if not (ROOT / z["validation_path"]).is_file():
                errors.append(f"{z['zone_id']}: validation file missing")
        elif z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN":
            if z.get("geometry_path"):
                errors.append(f"{z['zone_id']}: an administrative context zone must not carry a basin geometry")
        else:
            errors.append(f"{z['zone_id']}: unknown zone_type")
        if "phase2_national_inventory_completeness_audit" in json.dumps(z):
            errors.append(f"{z['zone_id']}: documentary inventory rows are not geometry")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    errors = check_zones(load(ZONES))
    data, out = build()
    if args.check:
        if OUT.is_file() and OUT.read_bytes() != data:
            errors.append("aviso_zone_links is stale: run scripts/v09_aviso_zone_crossing.py")
        if errors:
            print("FAIL:\n  - " + "\n  - ".join(errors))
            return 1
        print(f"OK: {len(out['surveillance_zones'])} surveillance zones; boundaries {out['official_boundaries']}")
        return 0
    if errors:
        print("FAIL:\n  - " + "\n  - ".join(errors))
        return 1
    if not OUT.is_file() or OUT.read_bytes() != data:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(data)
        print("written")
    print(json.dumps([(r["zone_id"], r["best_relation_method"]) for r in out["surveillance_zones"]], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
