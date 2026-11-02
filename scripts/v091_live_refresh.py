#!/usr/bin/env python3
"""IRFEN v0.9.1 · reconstrucción del paquete del visor privado tras cada captura válida (RESEARCH_ONLY / TEST_ONLY).

No captura nada. Lee de `main` (una referencia git) los archivos que ya escriben los workflows existentes
(v09-rain-north: IMERG Early norte + GOES-19 RRQPE por zona + panel; v09-senamhi-avisos-capture: avisos INDECI/COEN),
los valida, y si cambiaron reconstruye semáforo, paquete del visor y estado de fuentes. Publica en un directorio de
datos (la rama `research/v091-live-data` en el workflow) de forma atómica:

    current/surveillance_view_v0_1.json   paquete completo + bloque `live`
    current/observation_feed_v0_1.json    estado de cada fuente (#469)
    current/manifest.json                 ciclo, entradas (sha256, hora de fuente, validez), salidas, ciclo anterior
    cycles/<cycle_id>.json                copia del manifiesto (historial; la versión anterior es recuperable en git)

Reglas: una entrada inválida (JSON roto, guardas alteradas, fecha futura) no se usa: se toma la última versión
aceptada (`--fallback-ref`, normalmente el commit de main del ciclo anterior) y se marca. Si una fuente falla, el
paquete se construye igual con esa fuente gris; si falla la construcción o el control de calidad, no se publica nada
y el visor sigue con el último paquete bueno. Nunca convierte dato ausente en cero ni en verde.

Códigos de salida: 0 publicado · 10 sin cambios en las entradas · 2 construcción fallida · 3 control de calidad fallido.

    python3 scripts/v091_live_refresh.py --main-ref origin/main --data-dir ../live-data [--as-of ISO] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config/v091_live_refresh.json"
BUNDLE = ROOT / "site/data/v09/surveillance_view_v0_1.json"
SEMAFORO = ROOT / "data/v09/research/semaforo/semaforo_v0_1.json"
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", public_alerting=False, notifications_enabled=False,
              predictive=False, official_alert=False, merged_into_main=False)


def iso(s):
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def git_show(ref: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def git_rev(ref: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", ref], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def pick(d, keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def validate(raw: bytes | None, spec: dict, now: datetime) -> tuple[str, dict]:
    """ACEPTADA / AUSENTE / JSON_INVALIDO / GUARDAS_ALTERADAS / FECHA_FUTURA, plus the source times found."""
    if raw is None:
        return "AUSENTE", {}
    try:
        doc = json.loads(raw)
    except ValueError:
        return "JSON_INVALIDO", {}
    if doc.get("deployment_status", "RESEARCH_ONLY") != "RESEARCH_ONLY" or doc.get("production_use", False) is not False \
            or doc.get("operational_alerting_enabled", False) is not False or doc.get("public_alerting", False) is not False:
        return "GUARDAS_ALTERADAS", {}
    times = {}
    for tf in spec.get("time_fields", []):
        v = pick(doc, tf)
        if v:
            try:
                t = iso(v)
            except ValueError:
                return "FECHA_INVALIDA", {}
            if t > now + timedelta(minutes=10):
                return "FECHA_FUTURA", {".".join(tf): v}
            times[".".join(tf)] = v
    return "ACEPTADA", times


def run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def qa(bundle: dict, now: datetime) -> list[str]:
    """Invariants checked on every cycle with real data, at cycle time."""
    errs = []
    for k in ("deployment_status", "test_mode"):
        if bundle.get(k) not in ("RESEARCH_ONLY", "TEST_ONLY"):
            errs.append(f"guard {k}")
    for k in ("public_alerting", "notifications_enabled", "predictive_engine_enabled", "production_use"):
        if bundle.get(k) is not False:
            errs.append(f"guard {k}")
    sm = bundle.get("semaforo") or {}
    if sm.get("status") != "OK":
        return errs  # no semáforo in this cycle: nothing coloured, nothing to check
    spec = importlib.util.spec_from_file_location("sem_live_qa", ROOT / "scripts/v09_build_semaforo.py")
    sem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sem)
    S = dict(rules=sm["rules"], confirmations=sm["confirmations"]["confirmations"], aviso_check_utc=sm["aviso_check_utc"],
             avisos=sm["avisos"], rain_refs=sm["rain_refs"])
    fr = sm["rules"]["freshness"]
    if sm["rules"]["territorial_context"]["affects_colour"] is not False:
        errs.append("avisos must not colour points")
    for cp in sm["checkpoints"]:
        r = sem.evaluate(cp, S, now)
        bare = sem.evaluate(dict(cp, avisos=[]), S, now)
        if r["state"] != bare["state"]:
            errs.append(f"{cp['id']}: an aviso changed the colour")
        rr = S["rain_refs"].get(cp.get("rain_ref") or "")
        i_ok = bool(rr and rr["imerg"]["end_utc"] and timedelta(0) <= now - iso(rr["imerg"]["end_utc"]) <= timedelta(hours=fr["imerg_max_age_hours"])
                    and rr["imerg"]["windows"].get("24h") is not None)
        g_ok = not (rr and rr.get("goes")) or bool(rr["goes"].get("scan_end_utc") and timedelta(0) <= now - iso(rr["goes"]["scan_end_utc"])
                                                      <= timedelta(minutes=fr["goes_max_age_minutes"]))
        if r["state"] == "VERDE" and not (i_ok and g_ok):
            errs.append(f"{cp['id']}: false green (stale or missing local data)")
        if r["state"] == "ROJO" and not any(c.get("verified") and c.get("source_url") for c in S["confirmations"]):
            errs.append(f"{cp['id']}: red without a verified, sourced confirmation")
        if r["state"] == "AMARILLO" and r["rule"] != "LLUVIA_SATELITAL":
            errs.append(f"{cp['id']}: yellow not from satellite rain")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-ref", default="origin/main")
    ap.add_argument("--fallback-ref", help="ref with the last accepted inputs (defaults to the main sha of the previous cycle)")
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--as-of", help="evaluation time (tests); default now")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--record-failure", help="only write status/last_failure.json (the previous package stays in current/)")
    ap.add_argument("--log", type=Path)
    a = ap.parse_args(argv)
    if a.record_failure:
        (a.data_dir / "status").mkdir(parents=True, exist_ok=True)
        log = a.log.read_text(encoding="utf-8", errors="replace")[-2000:] if a.log and a.log.is_file() else None
        (a.data_dir / "status/last_failure.json").write_text(json.dumps(dict(
            failed_at_utc=datetime.now(timezone.utc).isoformat(), reason=a.record_failure, log=log, **GUARDS,
            note_es="Ciclo no publicado: el visor sigue con el último paquete bueno."), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    now = iso(a.as_of) if a.as_of else datetime.now(timezone.utc)
    cur = a.data_dir / "current"
    prev = json.loads((cur / "manifest.json").read_text(encoding="utf-8")) if (cur / "manifest.json").is_file() else None
    main_sha = git_rev(a.main_ref)
    fallback = a.fallback_ref or (prev or {}).get("main_sha")
    inputs, blobs = {}, {}
    for spec in cfg["inputs_from_main"]:
        p = spec["path"]
        raw = git_show(a.main_ref, p)
        status, times = validate(raw, spec, now)
        used = "MAIN"
        if status != "ACEPTADA":  # keep the last accepted version, never an empty or broken file
            old = git_show(fallback, p) if fallback else None
            st2, times2 = validate(old, spec, now)
            if st2 == "ACEPTADA":
                raw, times, used = old, times2, "ULTIMA_ACEPTADA"
            else:
                raw, used = None, "NINGUNA"
        inputs[p] = dict(status=status, used=used, sha256=sha(raw) if raw else None, source_times=times, role=spec["role"], producer=spec["producer"])
        blobs[p] = raw
    fingerprint = sha(json.dumps({p: v["sha256"] for p, v in inputs.items()}, sort_keys=True).encode())
    if prev and prev.get("inputs_fingerprint") == fingerprint and not a.force:
        print(json.dumps(dict(result="SIN_CAMBIOS", fingerprint=fingerprint, previous_cycle=prev.get("cycle_id")), ensure_ascii=False))
        return 10
    for p, raw in blobs.items():
        if raw is not None:
            (ROOT / p).write_bytes(raw)
        elif (ROOT / p).is_file():
            (ROOT / p).unlink()  # no accepted version: the source is absent (grey), never the copy frozen in this branch
    cycle_id = now.strftime("%Y%m%dT%H%M%SZ")
    steps = {}
    for name, cmd in (("semaforo", ["scripts/v09_build_semaforo.py"]), ("bundle", ["scripts/v09_build_surveillance_view.py"]),
                      ("feed", ["scripts/v091_build_observation_feed.py", "--as-of", now.isoformat(), "--output", str(a.data_dir / ".staging/observation_feed_v0_1.json")])):
        rc, out = run(cmd)
        steps[name] = dict(rc=rc, log=out.strip().splitlines()[-1:] if out.strip() else [])
        if rc != 0:
            print(json.dumps(dict(result="CONSTRUCCION_FALLIDA", step=name, log=out[-800:]), ensure_ascii=False))
            return 2
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    errs = qa(bundle, now)
    if errs:
        print(json.dumps(dict(result="CALIDAD_FALLIDA", errors=errs[:20]), ensure_ascii=False))
        return 3
    feed = json.loads((a.data_dir / ".staging/observation_feed_v0_1.json").read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("sem_live_counts", ROOT / "scripts/v09_build_semaforo.py")
    sem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sem)
    sm = bundle["semaforo"]
    counts = {}
    if sm.get("status") == "OK":
        S = dict(rules=sm["rules"], confirmations=sm["confirmations"]["confirmations"], aviso_check_utc=sm["aviso_check_utc"], avisos=sm["avisos"], rain_refs=sm["rain_refs"])
        for cp in sm["checkpoints"]:
            st = sem.evaluate(cp, S, now)["state"]
            counts[st] = counts.get(st, 0) + 1
    live = dict(mode="LIVE_RESEARCH", **GUARDS, cycle_id=cycle_id, built_at_utc=now.isoformat(), main_sha=main_sha,
                previous_cycle_id=(prev or {}).get("cycle_id"), inputs=inputs, feed=feed, not_connected_es=cfg["not_connected_es"],
                note_es="Paquete reconstruido automáticamente tras una captura de los workflows existentes de main. Investigación privada: no es una alerta.")
    bundle["live"] = live
    text = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    manifest = dict(schema_version="irfen_v091_live_manifest_v0_1", **GUARDS, cycle_id=cycle_id, built_at_utc=now.isoformat(), main_ref=a.main_ref,
                    main_sha=main_sha, inputs_fingerprint=fingerprint, inputs=inputs, steps=steps,
                    sources={s["id"]: dict(status=s["status"], source_time_utc=s["source_time_utc"], age_minutes=s["age_minutes"]) for s in feed["sources"]},
                    semaforo_at_build=counts, bundle=dict(path="current/surveillance_view_v0_1.json", sha256=sha(text.encode()), bytes=len(text.encode())),
                    previous=dict(cycle_id=(prev or {}).get("cycle_id"), bundle_sha256=((prev or {}).get("bundle") or {}).get("sha256")))
    # atomic publication: write to staging, then rename into current/
    stg = a.data_dir / ".staging"
    stg.mkdir(parents=True, exist_ok=True)
    (stg / "surveillance_view_v0_1.json").write_text(text, encoding="utf-8")
    (stg / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    cur.mkdir(parents=True, exist_ok=True)
    (a.data_dir / "cycles").mkdir(parents=True, exist_ok=True)
    for n in ("surveillance_view_v0_1.json", "observation_feed_v0_1.json", "manifest.json"):
        (stg / n).replace(cur / n)  # manifest last: a reader never sees a manifest pointing to a bundle not yet written
    (a.data_dir / "cycles" / f"{cycle_id}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    stg.rmdir()
    print(json.dumps(dict(result="PUBLICADO", cycle_id=cycle_id, semaforo=counts, sources=manifest["sources"],
                          inputs={p: (v["status"], v["used"]) for p, v in inputs.items()}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
