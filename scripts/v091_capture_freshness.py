#!/usr/bin/env python3
"""IRFEN v0.9.1 · frescura de la lluvia y actualización encadenada tras cada captura IMERG válida (RESEARCH_ONLY).

Se ejecuta al final de la captura de main (v09-rain-north) o, en pruebas, sobre una copia de sus archivos. Hace tres cosas:

1. Registra la ÚLTIMA OBSERVACIÓN REALMENTE DISPONIBLE (no la hora del archivo ni la del último intento): inicio y fin
   de la media hora más reciente archivada, antigüedad a la hora de evaluación, latencia con que se escribió, estado de
   la fuente y huecos de las últimas 24 h, para el archivo de cuencas y el del norte.
2. Decide si hay que reconstruir el visor: solo si la última observación AVANZÓ respecto a la última reconstrucción
   pedida con éxito, el archivo pasa los controles de integridad (sin duplicados, fechas futuras ni horas fuera de la
   rejilla de 30 min) y la clave (observación + SHA del archivo) no se pidió ya (ejecución duplicada). Si la petición
   anterior falló, se reintenta en la captura siguiente aunque no haya dato nuevo (recuperación), hasta un máximo.
3. Si procede, pide UNA reconstrucción (workflow_dispatch del actualizador en modo `after_capture`, que no encadena
   otra), con reintentos acotados y espera creciente, y lo deja todo en el registro (ledger).

No captura, no publica, no notifica. Un fallo aquí nunca rompe la captura: se registra y se sale con 0.

    python3 scripts/v091_capture_freshness.py --catchments data/v09/rain/imerg_early_catchments_v0_1.json \
        --north data/v09/rain/imerg_early_north_v0_1.json --ledger data/v09/rain/freshness_ledger_v0_1.json \
        --dispatch-workflow v091-live-refresh.yml --dispatch-ref research/v091-live-integration-20261102 [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

UTC = timezone.utc
STALE_AFTER_H = 12.0          # same limit as the semáforo and the catchment view
FUTURE_TOLERANCE = timedelta(minutes=10)
MAX_RETRIES_ACROSS_RUNS = 3   # a failed dispatch is retried at most this many later captures
DISPATCH_ATTEMPTS = 3
DISPATCH_BACKOFF_S = (15, 45)
HISTORY_MAX = 300
GUARDS = dict(deployment_status="RESEARCH_ONLY", test_mode="TEST_ONLY", production_use=False, public_alerting=False,
              notifications_enabled=False, activation_gate="BLOCKED")


def iso(s: str) -> datetime:
    d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {s}")
    return d.astimezone(UTC)


def observation_state(archive: dict | None, raw: bytes | None, now: datetime, name: str) -> dict:
    """Last observation actually available in an IMERG archive, with integrity checks. Missing file -> SIN_DATOS."""
    if archive is None:
        return dict(source=name, state="SIN_DATOS", freshness="SIN_DATOS", trigger_ok=False, problems=["archivo ausente"])
    probs = []
    times = []
    for g in archive.get("granules", []):
        try:
            times.append(iso(g["time_utc"]))
        except (KeyError, ValueError):
            probs.append(f"hora ilegible: {g.get('time_utc')!r}")
    dup = sorted(t.isoformat() for t, n in Counter(times).items() if n > 1)
    off = sorted(t.isoformat() for t in times if t.minute not in (0, 30) or t.second or t.microsecond)
    fut = sorted(t.isoformat() for t in times if t + timedelta(minutes=30) > now + FUTURE_TOLERANCE)
    if dup:
        probs.append(f"medias horas duplicadas: {dup[:3]}")
    if off:
        probs.append(f"horas fuera de la rejilla de 30 min: {off[:3]}")
    if fut:
        probs.append(f"observaciones en el futuro: {fut[:3]}")
    st = archive.get("status") or {}
    out = dict(source=name, archive_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None,
               source_state=st.get("state"), written_at_utc=st.get("written_at_utc"), source_since_utc=st.get("since_utc"),
               granules=len(times), problems=probs)
    valid = sorted(set(times) - {iso(x) for x in fut})
    if not valid:
        out.update(state="SIN_DATOS", freshness="SIN_DATOS", trigger_ok=False)
        return out
    last = valid[-1]
    end = last + timedelta(minutes=30)
    age = (now - end).total_seconds() / 3600
    span = [end - timedelta(minutes=30 * k) for k in range(1, 49)]
    have = set(valid)
    out.update(last_observation_start_utc=last.isoformat(), last_observation_end_utc=end.isoformat(), age_hours=round(age, 2),
               freshness="RECIENTE" if age <= STALE_AFTER_H else "CADUCADA",
               missing_half_hours_24h=sorted(t.isoformat() for t in span if t not in have))
    if st.get("written_at_utc"):
        try:
            out["latency_at_write_hours"] = round((iso(st["written_at_utc"]) - end).total_seconds() / 3600, 2)
        except ValueError:
            probs.append("written_at_utc ilegible")
    out["state"] = "INVALIDO" if probs else "OK"
    out["trigger_ok"] = not probs
    return out


def decide(prev: dict | None, obs: dict, main_sha: str | None) -> dict:
    """Whether to request one viewer rebuild now. Pure function (tested)."""
    prev = prev or {}
    last = prev.get("last_dispatch") or {}
    pending = prev.get("pending_retry")
    if not obs.get("trigger_ok"):
        return dict(action="NO", reason="archivo sin datos o con problemas de integridad: no se reconstruye", key=None)
    key = f"{obs['last_observation_start_utc']}|{obs['archive_sha256']}"
    if pending and pending.get("key") and pending.get("retries", 0) < MAX_RETRIES_ACROSS_RUNS:
        # recover a failed request even without new data (the newest key wins if the data advanced meanwhile)
        return dict(action="REINTENTO", reason=f"la petición anterior falló ({pending.get('error')}); reintento {pending.get('retries', 0) + 1}",
                    key=key, retries=pending.get("retries", 0) + 1)
    if last.get("key") == key and last.get("result") in ("OK", "PEDIDA"):
        return dict(action="NO", reason="ejecución duplicada: esta observación ya se pidió con éxito", key=key)
    prev_obs = last.get("observation_start_utc")
    if prev_obs and iso(obs["last_observation_start_utc"]) <= iso(prev_obs):
        return dict(action="NO", reason="sin observación nueva (la última no avanzó)", key=key)
    return dict(action="SI", reason="observación nueva y válida", key=key, retries=0)


def dispatch(cmd: list[str], sleep=time.sleep, run=subprocess.run) -> dict:
    """Run the dispatch command with bounded retries and growing waits. Never raises."""
    attempts = []
    for i in range(DISPATCH_ATTEMPTS):
        try:
            r = run(cmd, capture_output=True, text=True, timeout=60)
            ok = r.returncode == 0
            attempts.append(dict(attempt=i + 1, ok=ok, error=None if ok else (r.stderr or r.stdout or "").strip()[:200]))
        except Exception as exc:  # noqa: BLE001 - recorded, retried
            attempts.append(dict(attempt=i + 1, ok=False, error=f"{type(exc).__name__}: {str(exc)[:160]}"))
        if attempts[-1]["ok"]:
            return dict(result="OK", attempts=attempts)
        if i + 1 < DISPATCH_ATTEMPTS:
            sleep(DISPATCH_BACKOFF_S[min(i, len(DISPATCH_BACKOFF_S) - 1)])
    return dict(result="FALLO", attempts=attempts, error=attempts[-1]["error"])


def dispatch_pending(ledger_path: Path, now: datetime, dispatch_cmd: list[str], sleep=time.sleep, runner=subprocess.run,
                     run_id: str | None = None) -> dict:
    """Phase 2 (after the capture commit is pushed, so the rebuild reads the new data): send the request that phase 1
    recorded as PEDIDA. A failure becomes FALLO + pending_retry (retried by the next capture). Returns the ledger.

    Only the request recorded by THIS capture run (`run_id`) is sent. A successful send is not committed (no churn), so
    the committed ledger keeps an older PEDIDA; when the next capture has no new data phase 1 does not rewrite the file,
    and without this guard phase 2 would send the same rebuild again every 30 min."""
    led = json.loads(ledger_path.read_text(encoding="utf-8"))
    last = led.get("last_dispatch") or {}
    if last.get("result") != "PEDIDA":
        led["phase2"] = dict(at_utc=now.isoformat(), action="NADA_PENDIENTE")
        return led
    if run_id is not None and last.get("capture_run_id") != run_id:
        led["phase2"] = dict(at_utc=now.isoformat(), action="NADA_PENDIENTE",
                             reason="la petición registrada es de otra ejecución de captura (ya tratada); no se repite")
        return led
    res = dispatch(dispatch_cmd, sleep=sleep, run=runner)
    last.update(result=res["result"], attempts=res["attempts"], sent_at_utc=now.isoformat())
    led["last_dispatch"] = last
    if res["result"] == "FALLO":
        led["pending_retry"] = dict(key=last["key"], retries=(led.get("decision") or {}).get("retries", 0), error=res.get("error"),
                                    since_utc=now.isoformat())
    else:
        led.pop("pending_retry", None)
    if led.get("history"):
        led["history"][-1]["result"] = res["result"]
    led["phase2"] = dict(at_utc=now.isoformat(), action="ENVIADA", result=res["result"])
    ledger_path.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return led


def run_once(catchments: Path, north: Path | None, ledger_path: Path, now: datetime, main_sha: str | None, run_id: str | None,
             dispatch_cmd: list[str] | None, dry_run: bool, sleep=time.sleep, runner=subprocess.run, defer: bool = False) -> dict:
    def load(p):
        if p is None or not p.is_file():
            return None, None
        raw = p.read_bytes()
        try:
            return json.loads(raw), raw
        except json.JSONDecodeError:
            return {"granules": [], "status": {"state": "ARCHIVO_CORRUPTO"}}, raw
    ca, craw = load(catchments)
    na, nraw = load(north)
    obs = observation_state(ca, craw, now, "imerg_early_catchments")
    obs_n = observation_state(na, nraw, now, "imerg_early_north") if north is not None else None
    if craw is not None and ca.get("status", {}).get("state") == "ARCHIVO_CORRUPTO":
        obs.update(state="INVALIDO", trigger_ok=False, problems=obs["problems"] + ["JSON corrupto"])
    prev = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else None
    dec = decide(prev, obs, main_sha)
    led = dict(schema_version="irfen_v091_capture_freshness_ledger_v0_1", **GUARDS, **({} if prev is None else
               {k: prev[k] for k in ("last_dispatch", "pending_retry") if k in prev}))
    led["evaluated_at_utc"] = now.isoformat()
    led["main_sha"] = main_sha
    led["capture_run_id"] = run_id
    led["last_observation_available"] = obs
    if obs_n is not None:
        led["north_last_observation_available"] = obs_n
    led["decision"] = dec
    if dec["action"] in ("SI", "REINTENTO"):
        if dry_run:  # also in phase 1: with the dispatch switch off nothing is ever requested (no PEDIDA left behind)
            res = dict(result="SIMULADO", attempts=[], command=dispatch_cmd)
        elif defer:
            res = dict(result="PEDIDA", attempts=[])  # sent by phase 2 after the capture commit is pushed
        elif not dispatch_cmd:
            res = dict(result="SIMULADO", attempts=[], command=dispatch_cmd)
        else:
            res = dispatch(dispatch_cmd, sleep=sleep, run=runner)
        entry = dict(key=dec["key"], observation_start_utc=obs["last_observation_start_utc"], requested_at_utc=now.isoformat(),
                     result=res["result"], attempts=res["attempts"], capture_run_id=run_id, main_sha=main_sha)
        led["last_dispatch"] = entry
        if res["result"] == "FALLO":
            led["pending_retry"] = dict(key=dec["key"], retries=dec.get("retries", 0), error=res.get("error"), since_utc=now.isoformat())
        else:
            led.pop("pending_retry", None)
        if dec["action"] == "REINTENTO" and res["result"] == "FALLO" and dec.get("retries", 0) >= MAX_RETRIES_ACROSS_RUNS:
            led.pop("pending_retry", None)
            led["gave_up"] = dict(key=dec["key"], at_utc=now.isoformat(), note_es="Reintentos agotados: el visor sigue con el último paquete bueno.")
    if defer and dec["action"] == "NO" and prev:
        po = prev.get("last_observation_available") or {}
        if all(po.get(k) == obs.get(k) for k in ("last_observation_start_utc", "state", "freshness", "source_state")):
            led["written"] = False  # nothing changed: no new commit in the capture repository (avoids churn every 30 min)
            return led
    hist = (prev or {}).get("history", [])
    hist.append(dict(at_utc=now.isoformat(), capture_run_id=run_id, observation_start_utc=obs.get("last_observation_start_utc"),
                     age_hours=obs.get("age_hours"), freshness=obs.get("freshness"), state=obs.get("state"),
                     action=dec["action"], result=(led.get("last_dispatch") or {}).get("result") if dec["action"] in ("SI", "REINTENTO") else None))
    led["history"] = hist[-HISTORY_MAX:]
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(led, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return led


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catchments", type=Path, required=True)
    ap.add_argument("--north", type=Path)
    ap.add_argument("--ledger", type=Path, required=True)
    ap.add_argument("--now")
    ap.add_argument("--main-sha")
    ap.add_argument("--run-id")
    ap.add_argument("--dispatch-workflow")
    ap.add_argument("--dispatch-ref")
    ap.add_argument("--dispatch-repo", default="IRFEN2026/irfen-peru")
    ap.add_argument("--dispatch-input", action="append", default=[], help="k=v passed with -f")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--phase", choices=("all", "decide", "dispatch"), default="all",
                    help="decide: record the decision (PEDIDA) before the capture commit; dispatch: send it after the push")
    a = ap.parse_args(argv)
    now = iso(a.now) if a.now else datetime.now(UTC)
    cmd = None
    if a.dispatch_workflow and a.dispatch_ref:
        cmd = ["gh", "workflow", "run", a.dispatch_workflow, "--repo", a.dispatch_repo, "--ref", a.dispatch_ref]
        for kv in a.dispatch_input:
            cmd += ["-f", kv]
    try:
        if a.phase == "dispatch":
            if not a.run_id:
                raise ValueError("--phase dispatch requiere --run-id (la misma ejecución que registró la petición)")
            led = dispatch_pending(a.ledger, now, cmd, run_id=a.run_id) if cmd and not a.dry_run else json.loads(a.ledger.read_text(encoding="utf-8"))
            print(f"::notice title=V091_FRESHNESS_DISPATCH::{json.dumps(led.get('phase2'), ensure_ascii=False)}")
            return 0
        led = run_once(a.catchments, a.north, a.ledger, now, a.main_sha, a.run_id, cmd, a.dry_run, defer=a.phase == "decide")
    except Exception as exc:  # noqa: BLE001 - never break the capture
        print(f"::warning title=V091_FRESHNESS::{type(exc).__name__}: {exc}")
        return 0
    o = led["last_observation_available"]
    print(f"::notice title=V091_FRESHNESS::last_obs_end={o.get('last_observation_end_utc')} age_h={o.get('age_hours')} "
          f"{o.get('freshness')} state={o.get('state')} action={led['decision']['action']} "
          f"dispatch={(led.get('last_dispatch') or {}).get('result')} reason={led['decision']['reason']}")
    print(json.dumps({k: led[k] for k in ("last_observation_available", "decision")}, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
