#!/usr/bin/env python3
"""IRFEN v0.9.1 · comprobación del visor privado en modo de actualización automática (RESEARCH_ONLY).

Sirve en 127.0.0.1 la página `site/v09/vigilancia.html` junto a una carpeta de datos con `current/` (la rama
`research/v091-live-data` o un directorio local), la abre con `?live=current/` en Chromium y comprueba:
0 errores JS, ciclo mostrado = ciclo del manifiesto, chip de estado, autocomprobación del semáforo, y paridad
Python/JS del semáforo en la hora del ciclo. Con `--next-cycle DIR` sustituye después `current/` por otro ciclo y
verifica que la página detecta el paquete nuevo y se recarga sola (sin intervención), conservando la vista.

    python qa/replay_tools/v091_live_page_check.py --data-dir LIVE [--next-cycle LIVE2] [--local-leaflet DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import importlib.util
import json
import re
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def serve(root: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def parity(page, bundle: dict, at: str) -> dict:
    spec = importlib.util.spec_from_file_location("sem_page_check", ROOT / "scripts/v09_build_semaforo.py")
    sem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sem)
    sm = bundle.get("semaforo") or {}
    if sm.get("status") != "OK":
        return dict(cases=0, mismatches=0)
    S = dict(rules=sm["rules"], confirmations=sm["confirmations"]["confirmations"], aviso_check_utc=sm["aviso_check_utc"],
             avisos=sm["avisos"], rain_refs=sm["rain_refs"])
    t = sem.iso(at)
    exp = [sem.evaluate(cp, S, t) for cp in sm["checkpoints"]]
    got = page.evaluate("a=>a.cps.map(cp=>window.IRFEN_SEMAFORO_EVAL(cp,a.S,a.t))", dict(cps=sm["checkpoints"], S=S, t=at))
    bad = [cp["id"] for cp, e, g in zip(sm["checkpoints"], exp, got)
           if [e["state"], e["rule"], e["confidence"], e["context"]] != [g["state"], g["rule"], g["confidence"], g["context"]]]
    from collections import Counter
    return dict(cases=len(exp), mismatches=len(bad), first=bad[:3], states=dict(Counter(e["state"] for e in exp)))


def run(data_dir: Path, next_cycle: Path | None, local_leaflet: Path | None, out: Path) -> dict:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="irfen_live_view_") as td:
        root = Path(td)
        shutil.copy(ROOT / "site/v09/vigilancia.html", root / "vigilancia.html")
        shutil.copytree(data_dir / "current", root / "current")
        httpd, origin = serve(root)
        rep = dict(origin=origin, runs=[])
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport=dict(width=1440, height=900))
            page = ctx.new_page()
            errors, loads = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "tile" not in m.text and "ERR_FAILED" not in m.text else None)
            page.on("load", lambda *_: loads.append(1))

            def route(r):
                u = r.request.url
                if u.startswith(origin):
                    if local_leaflet and u.split("?")[0].endswith("/vigilancia.html"):
                        resp = r.fetch()
                        return r.fulfill(response=resp, body=re.sub(r'\s+integrity="[^"]+"', "", resp.text()))
                    return r.continue_()
                if local_leaflet and u.startswith("https://unpkg.com/leaflet@1.9.4/dist/"):
                    f = local_leaflet / u.rsplit("/dist/", 1)[1]
                    if f.is_file():
                        return r.fulfill(body=f.read_bytes(), headers={"content-type": "text/css" if f.suffix == ".css" else "application/javascript"})
                if "unpkg.com" in u and not local_leaflet:
                    return r.continue_()
                return r.abort()  # no external tiles in the check
            page.route("**/*", route)

            def snapshot(tag):
                man = json.loads((root / "current/manifest.json").read_text(encoding="utf-8"))
                bundle = json.loads((root / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
                page.locator("#t-semaforo").click()
                r = dict(tag=tag, manifest_cycle=man["cycle_id"], page_cycle=page.evaluate("document.body.dataset.liveCycle"),
                         chip=page.locator("#state").inner_text(), selfcheck=page.evaluate("document.body.dataset.semaforoSelfcheck"),
                         semaforo_counts=page.locator("#smCounts").inner_text()[:220],
                         north_rain_end=bundle["rain"]["north_zones"].get("end_utc"),
                         avisos_check=(bundle.get("semaforo") or {}).get("aviso_check_utc"),
                         parity_at_cycle=parity(page, bundle, man["built_at_utc"]))
                page.locator("#bSources").click()
                r["sources_dialog"] = page.locator("dialog[open] .db").inner_text()[:400]
                page.locator("dialog[open] [data-close]").click()
                page.screenshot(path=str(out / f"live_{tag}.png"))
                return r

            page.goto(origin + "/vigilancia.html?live=current/&poll=30", wait_until="load")
            page.wait_for_selector("body[data-ready='1']", timeout=30000)
            rep["runs"].append(snapshot("ciclo_1"))
            if next_cycle:
                page.locator("#t-avisos").click()  # a view state that must survive the automatic reload
                staged = root / ".next"
                shutil.copytree(next_cycle / "current", staged)
                for n in ("surveillance_view_v0_1.json", "observation_feed_v0_1.json", "manifest.json"):  # manifest last
                    (staged / n).replace(root / "current" / n)
                before = len(loads)
                page.wait_for_function("(c)=>document.body.dataset.ready==='1'&&document.body.dataset.liveCycle&&document.body.dataset.liveCycle!==c",
                                       arg=rep["runs"][0]["page_cycle"], timeout=120000)
                rep["auto_reloads"] = len(loads) - before
                rep["tab_after_reload"] = page.evaluate("[...document.querySelectorAll('.tabs button')].find(b=>b.getAttribute('aria-selected')==='true')?.id")
                rep["runs"].append(snapshot("ciclo_2"))
            rep["errors"] = errors
            b.close()
        httpd.shutdown()
    r1 = rep["runs"][0]
    rep["ok"] = (not rep["errors"] and all(x["page_cycle"] == x["manifest_cycle"] and x["parity_at_cycle"]["mismatches"] == 0
                                          and len(set(x["selfcheck"].split("/"))) == 1 for x in rep["runs"])
                 and (not next_cycle or (rep["runs"][1]["page_cycle"] != r1["page_cycle"] and rep.get("tab_after_reload") == "t-avisos")))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--next-cycle", type=Path)
    ap.add_argument("--local-leaflet", type=Path)
    ap.add_argument("--out", type=Path, default=Path("/tmp/irfen_live_check"))
    a = ap.parse_args(argv)
    rep = run(a.data_dir, a.next_cycle, a.local_leaflet, a.out)
    (a.out / "live_page_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:5000])
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
