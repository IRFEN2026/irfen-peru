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
* DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN — sin límites oficiales disponibles: el departamento registrado de la zona
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
    "DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN": dict(
        rank=3, kind="ADMINISTRATIVE_DEPARTMENT",
        label_es="El departamento registrado de la zona figura en el aviso",
        caveat_es="Coincidencia administrativa; la relación provincial es DESCONOCIDA hasta disponer de límites oficiales."),
    "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES": dict(
        rank=4, kind="SPATIAL_VERIFIED_NEGATIVE",
        label_es="La cuenca está en un departamento del aviso pero fuera de sus provincias enumeradas",
        caveat_es="Se muestra para revisión; el aviso no enumera las provincias de esta cuenca."),
}
ACTIVE = ("VIGENTE", "FUTURO")
SURVEILLED = ("VIGENTE", "FUTURO", "DESCONOCIDO")  # unknown validity is never treated as inactive
MIN_BOUNDARY_COVERAGE = 0.99  # a negative spatial result needs the whole basin covered by the official provinces
HEALTH = ROOT / "data/v09/senamhi_avisos/health_v0_1.json"


def _avisos_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("v09_senamhi_avisos_lib", ROOT / "scripts/v09_senamhi_avisos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AV = _avisos_module()


def fold(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", text or "") if unicodedata.category(c) != "Mn").upper()
    return " ".join(t.replace(".", " ").split())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def verify_overlay(overlay: dict | None, zones: list[dict]) -> tuple[dict, list[str]]:
    """Per-zone usable overlay rows, after provenance and coverage checks.

    The overlay is used only when its boundary file is archived with the SHA-256 it declares, and per zone only
    when it was computed from the same basin geometry (SHA-256). A zone whose basin is not fully covered by the
    official provinces keeps its positive intersections but never yields a negative result.
    Returns ({zone_id: {"rows": {(DEP, PROV): row}, "negative_allowed": bool, "coverage": float}}, notes).
    """
    if not overlay:
        return {}, ["no official overlay"]
    notes = []
    src = overlay.get("boundary_source") or {}
    path = ROOT / src["path"] if src.get("path") else None
    if not path or not path.is_file() or sha256_bytes(path.read_bytes()) != src.get("sha256"):
        return {}, ["overlay ignored: boundary file missing or SHA-256 differs from the overlay record"]
    zone_sha = {z["zone_id"]: z.get("geometry_sha256") for z in zones}
    out = {}
    for z in overlay.get("zones", []):
        if zone_sha.get(z["zone_id"]) != z.get("geometry_sha256"):
            notes.append(f"{z['zone_id']}: overlay computed from another geometry version; ignored")
            continue
        coverage = float(z.get("basin_fraction_covered_by_boundaries") or 0.0)
        out[z["zone_id"]] = dict(rows={(fold(i["department"]), fold(i["province"])): i for i in z.get("intersections", [])},
                                 negative_allowed=coverage >= MIN_BOUNDARY_COVERAGE, coverage=coverage)
    return out, notes


def links_for_aviso(aviso: dict, zones: list[dict], overlay: dict | None, verified: dict | None = None) -> list[dict]:
    """Relations between one aviso and the surveillance zones. Pure: tested offline."""
    cur = aviso.get("current", {})
    deps = [fold(d) for d in cur.get("departments") or []]
    provs = {fold(d): [fold(p) for p in ps] for d, ps in (cur.get("provinces_by_department") or {}).items()}
    printed = {fold(p): p for ps in (cur.get("provinces_by_department") or {}).values() for p in ps}
    idx = verified if verified is not None else verify_overlay(overlay, zones)[0]
    src_sha = (overlay or {}).get("boundary_source", {}).get("sha256")
    links = []
    for z in zones:
        if z["zone_type"] == "ADMINISTRATIVE_CONTEXT_NO_BASIN":
            dep = fold(z["registered_department"])
            if dep in provs:
                for p in provs[dep]:
                    links.append(dict(zone_id=f"{z['zone_id']}:{p}", base_zone_id=z["zone_id"], relation_method="LISTED_PROVINCE_CONTEXT_NO_BASIN",
                                      department=dep, province=p, province_as_printed=printed.get(p), evidence=dict(aviso_lists_province=True)))
            elif dep in deps:
                links.append(dict(zone_id=z["zone_id"], base_zone_id=z["zone_id"], relation_method="DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN",
                                  department=dep, province=None, evidence=dict(aviso_lists_department=True, provinces_listed=False)))
            continue
        zid = z["zone_id"]
        reg_dep = fold(z["registered_department"])
        if zid in idx:  # verified official overlay for this exact basin geometry
            ov = idx[zid]
            hits = [dict(department=d, province=p, area_km2=v.get("area_km2"), zone_fraction=v.get("zone_fraction"))
                    for (d, p), v in sorted(ov["rows"].items()) if p in provs.get(d, [])]
            zone_deps = sorted({d for d, _ in ov["rows"]} | {reg_dep})
            touched = [d for d in zone_deps if d in deps]
            if hits:
                links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="BASIN_INTERSECTS_LISTED_PROVINCE",
                                  department=hits[0]["department"], province=None,
                                  evidence=dict(intersections=hits, boundary_source_sha256=src_sha, boundary_coverage=ov["coverage"])))
            elif touched and ov["negative_allowed"] and all(d in provs for d in touched):
                links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES",
                                  department=touched[0], province=None,
                                  evidence=dict(zone_departments=zone_deps, listed_provinces={d: provs[d] for d in touched},
                                                boundary_source_sha256=src_sha, boundary_coverage=ov["coverage"])))
            elif touched:
                reason = ("department listed without provinces" if not all(d in provs for d in touched)
                          else f"official boundaries cover {ov['coverage']:.1%} of the basin (< {MIN_BOUNDARY_COVERAGE:.0%}): no negative result")
                links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN",
                                  department=touched[0], province=None, evidence=dict(aviso_lists_department=True, reason=reason,
                                                                                     boundary_coverage=ov["coverage"])))
            continue
        if reg_dep in deps:
            links.append(dict(zone_id=zid, base_zone_id=zid, relation_method="DEPARTMENT_LISTED_PROVINCIAL_RELATION_UNKNOWN", department=reg_dep,
                              province=None, evidence=dict(aviso_lists_department=True, provinces_listed=reg_dep in provs,
                                                           listed_provinces=provs.get(reg_dep), official_boundaries="NOT_AVAILABLE_OR_UNVERIFIED")))
    for link in links:
        meta = RELATION_METHODS[link["relation_method"]]
        link.update(relation_kind=meta["kind"], relation_rank=meta["rank"], label_es=meta["label_es"], caveat_es=meta["caveat_es"])
    return sorted(links, key=lambda l: (l["relation_rank"], l["zone_id"]))


def evaluate(aviso: dict, now) -> tuple[str, str]:
    """Status from the documented validity and the given clock (never from the stored status alone)."""
    return AV.compute_status(aviso.get("current", {}), now)


def next_transition(registry: dict, now) -> str | None:
    from datetime import datetime

    times = []
    for a in registry.get("avisos", {}).values():
        for k in ("validity_start", "validity_end"):
            v = a.get("current", {}).get(k)
            if v and datetime.fromisoformat(v) > now:
                times.append(datetime.fromisoformat(v))
    return min(times).astimezone(AV.timezone.utc).isoformat() if times else None


def surveillance_list(registry: dict, zones_cfg: dict, overlay: dict | None, now, source_state: str | None = None) -> dict:
    zones = zones_cfg["zones"]
    verified, overlay_notes = verify_overlay(overlay, zones)
    by_zone: dict[str, dict] = {}
    aviso_links = {}
    for key in sorted(registry.get("avisos", {})):
        aviso = registry["avisos"][key]
        status, basis = evaluate(aviso, now)
        links = links_for_aviso(aviso, zones, overlay, verified)
        aviso_links[key] = dict(status=status, status_basis=basis, product=aviso.get("product"),
                                validity_start=aviso.get("current", {}).get("validity_start"),
                                validity_end=aviso.get("current", {}).get("validity_end"),
                                official_url=aviso.get("official_url"), in_surveillance=status in SURVEILLED, links=links)
        if status not in SURVEILLED:
            continue  # expired / cancelled / superseded: kept above as history, not as current surveillance
        for link in links:
            z = by_zone.setdefault(link["zone_id"], dict(zone_id=link["zone_id"], base_zone_id=link["base_zone_id"],
                                                         department=link["department"], province=link.get("province"),
                                                         province_as_printed=link.get("province_as_printed"), avisos=[]))
            z["avisos"].append(dict(aviso_key=key, status=status, product=aviso.get("product"),
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
        elif zid not in verified:
            missing.append("official provincial boundaries not available or not verified: provincial relation unknown, and a basin "
                           "crossing into another department is not detected")
        if any(a["status"] == "DESCONOCIDO" for a in z["avisos"]):
            missing.append("aviso validity not readable: status DESCONOCIDO (not treated as inactive)")
        rows.append(dict(z, display_name=base["display_name"] + (f" · {z.get('province_as_printed') or z['province']}" if z.get("province") else ""),
                         zone_type=base["zone_type"], best_relation_rank=best,
                         best_relation_method=next(a["relation_method"] for a in z["avisos"] if a["relation_rank"] == best),
                         any_vigente=any(a["status"] == "VIGENTE" for a in z["avisos"]),
                         why_es=sorted({RELATION_METHODS[a["relation_method"]]["label_es"] + f" ({a['aviso_key']}, {a['status']})" for a in z["avisos"]}),
                         missing_data=missing))
    order = {"VIGENTE": 0, "FUTURO": 1, "DESCONOCIDO": 2}
    # Ordering is for reading, not a risk score: VIGENTE, FUTURO, unknown validity; then the most precise relation.
    rows.sort(key=lambda r: (min(order[a["status"]] for a in r["avisos"]), r["best_relation_rank"], r["zone_id"]))
    return dict(schema_version="0.2", output_id="irfen-v09-aviso-zone-links:v0.1", **GUARDS, map_publishable=False,
                inputs=dict(registry_sha256=sha256_bytes(REGISTRY.read_bytes()) if REGISTRY.is_file() else None,
                            zones_sha256=sha256_bytes(ZONES.read_bytes()),
                            overlay_sha256=sha256_bytes(OVERLAY.read_bytes()) if OVERLAY.is_file() else None),
                official_boundaries="VERIFIED" if verified else "NOT_AVAILABLE_OR_UNVERIFIED", overlay_notes=overlay_notes,
                source_state=source_state, possibly_incomplete=source_state not in (None, "AL_DIA"),
                statuses_valid_until_utc=next_transition(registry, now),
                reader_rule_es="Los estados se calcularon con la vigencia documentada en el instante evaluated_at_utc. Después de "
                               "statuses_valid_until_utc, o si la fuente no está AL_DIA, quien lea este archivo debe recalcular los "
                               "estados con su reloj o mostrar la lista como desactualizada.",
                relation_methods=RELATION_METHODS,
                ordering_note_es="El orden facilita la lectura (vigente, futuro, vigencia desconocida; relación más precisa primero). "
                                 "No es una puntuación de riesgo ni una probabilidad de activación.",
                surveillance_zones=rows, aviso_links=aviso_links)


def build(now=None) -> tuple[bytes, dict]:
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    health = load(HEALTH)
    out = surveillance_list(load(REGISTRY) or {"avisos": {}}, load(ZONES), load(OVERLAY), now,
                            (health or {}).get("source_health", {}).get("state"))
    return (json.dumps(out, ensure_ascii=False, indent=1) + "\n").encode("utf-8"), out


def with_timestamp(out: dict, now) -> bytes:
    stamped = dict(out, evaluated_at_utc=now.isoformat())
    return (json.dumps(stamped, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def content_equal(committed: dict, fresh: dict) -> bool:
    return {k: v for k, v in committed.items() if k != "evaluated_at_utc"} == fresh


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
    """Write when the content changes (statuses are re-evaluated with the clock every run).

    --check is clock-independent: it replays the build at the committed evaluated_at_utc and requires the same
    content, and requires the recorded input hashes to match the current registry, zones and overlay.
    """
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    errors = check_zones(load(ZONES))
    if args.check:
        committed = load(OUT)
        if committed is None:
            errors.append("aviso_zone_links missing: run scripts/v09_aviso_zone_crossing.py")
        else:
            at = datetime.fromisoformat(committed["evaluated_at_utc"])
            _, replay = build(at)
            if not content_equal(committed, replay):
                errors.append("aviso_zone_links does not match its inputs: run scripts/v09_aviso_zone_crossing.py")
            for key, value in GUARDS.items():
                if committed.get(key) != value:
                    errors.append(f"output guard {key} must be {value!r}")
        if errors:
            print("FAIL:\n  - " + "\n  - ".join(errors))
            return 1
        print(f"OK: {len(committed['surveillance_zones'])} surveillance zones at {committed['evaluated_at_utc']}; "
              f"boundaries {committed['official_boundaries']}")
        return 0
    if errors:
        print("FAIL:\n  - " + "\n  - ".join(errors))
        return 1
    now = datetime.now(timezone.utc)
    _, out = build(now)
    committed = load(OUT)
    if committed is None or not content_equal(committed, out):
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(with_timestamp(out, now))
        print("written")
    print(json.dumps([(r["zone_id"], r["best_relation_method"]) for r in out["surveillance_zones"]], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
