#!/usr/bin/env python3
"""IRFEN v0.9.1 · comprobación del visor privado en modo de actualización automática (RESEARCH_ONLY).

Sirve en 127.0.0.1 la página `site/v09/vigilancia.html` junto a una carpeta de datos con `current/` (la rama
`research/v091-live-data` o un directorio local), la abre con `?live=current/` en Chromium y comprueba:
0 errores JS, ciclo mostrado = ciclo del manifiesto, chip de estado, autocomprobación del semáforo, y paridad
Python/JS del semáforo en la hora del ciclo y más tarde (caducidad: todo gris). Con `--next-cycle DIR` sustituye después `current/` por otro ciclo y
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


class _CORS(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):  # like raw.githubusercontent.com: readable from another origin
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def serve(root: Path, cors: bool = False):
    handler = functools.partial(_CORS if cors else http.server.SimpleHTTPRequestHandler, directory=str(root))
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


def expiry(page, bundle: dict, built: str) -> dict:
    """Same package evaluated later in the browser (no new cycle): JS = Python, and once every local observation has
    expired (> 12 h IMERG, > 90 min GOES-19) nothing stays yellow or green; only a verified event could be red."""
    from datetime import timedelta
    spec = importlib.util.spec_from_file_location("sem_page_check2", ROOT / "scripts/v09_build_semaforo.py")
    sem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sem)
    sm = bundle.get("semaforo") or {}
    if sm.get("status") != "OK":
        return dict(checked=False)
    fr = sm["rules"]["freshness"]
    t0 = sem.iso(built)
    late = t0 + timedelta(hours=fr["imerg_max_age_hours"], minutes=5)
    res = {}
    for label, t in (("+0", t0), ("+2h", t0 + timedelta(hours=2)), ("caducado", late), ("+72h", t0 + timedelta(hours=72))):
        res[label] = parity(page, bundle, t.isoformat())
    confirmed = any(c.get("verified") for c in sm["confirmations"]["confirmations"])
    res["all_grey_after_expiry"] = set(res["caducado"]["states"]) <= ({"GRIS", "ROJO"} if confirmed else {"GRIS"})
    res["ok"] = res["all_grey_after_expiry"] and all(v["mismatches"] == 0 for k, v in res.items() if isinstance(v, dict))
    return res


def registry_parity(page, bundle: dict, built: str) -> dict:
    """Red only from a verified, https-sourced, located entry; unverified or unsourced entries stay «pendiente» (JS = Python)."""
    sm = bundle.get("semaforo") or {}
    if sm.get("status") != "OK":
        return dict(checked=False, ok=True)
    river = next(c for c in sm["checkpoints"] if c["type"] == "rio")
    base = dict(system_id=river["system_id"], observed_at_utc=built, event_es="prueba")
    b = json.loads(json.dumps(bundle))
    b["semaforo"]["confirmations"]["confirmations"] = [dict(base, verified=False, source_url="https://example.org/a"),
                                                        dict(base, verified=True, source_url="http://example.org/b")]
    pending_only = parity(page, b, built)
    b["semaforo"]["confirmations"]["confirmations"].append(dict(base, verified=True, source_url="https://example.org/c"))
    verified = parity(page, b, built)
    n = sum(1 for c in sm["checkpoints"] if c["type"] == "rio" and c["system_id"] == river["system_id"])
    ok = (pending_only["mismatches"] == verified["mismatches"] == 0 and "ROJO" not in pending_only["states"]
          and verified["states"].get("ROJO") == n)
    return dict(pending_only=pending_only["states"], with_verified=verified["states"], ok=ok)


def run(data_dir: Path, next_cycle: Path | None, local_leaflet: Path | None, out: Path, cross_origin: bool = False) -> dict:
    """cross_origin: the page is the deployable private site (scripts/v091_build_private_site.py) and the data come from
    another origin with CORS, as with raw.githubusercontent.com/<repo>/research/v091-live-data/current/."""
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="irfen_live_view_") as td, tempfile.TemporaryDirectory(prefix="irfen_live_data_") as dd:
        root = Path(td)
        droot = Path(dd) if cross_origin else root
        shutil.copytree(data_dir / "current", droot / "current")
        dhttpd = None
        if cross_origin:
            dhttpd, dorigin = serve(droot, cors=True)
            spec = importlib.util.spec_from_file_location("v091_site", ROOT / "scripts/v091_build_private_site.py")
            site = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(site)
            site.build(root, dorigin + "/current/")
            shutil.copy(root / "index.html", root / "vigilancia.html")
        else:
            dorigin = None
            shutil.copy(ROOT / "site/v09/vigilancia.html", root / "vigilancia.html")
        if local_leaflet:  # local Leaflet build (sandbox without unpkg): its bytes differ from the pinned SRI hashes
            pg = root / "vigilancia.html"
            pg.write_text(re.sub(r'\s+integrity="[^"]+"', "", pg.read_text(encoding="utf-8")), encoding="utf-8")
        httpd, origin = serve(root)
        rep = dict(origin=origin, data_origin=dorigin, cross_origin=cross_origin, runs=[])
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
                if dorigin and u.startswith(dorigin + "/"):
                    return r.continue_()
                if u.startswith(origin + "/"):
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
                man = json.loads((droot / "current/manifest.json").read_text(encoding="utf-8"))
                bundle = json.loads((droot / "current/surveillance_view_v0_1.json").read_text(encoding="utf-8"))
                page.locator("#t-semaforo").click()
                r = dict(tag=tag, manifest_cycle=man["cycle_id"], page_cycle=page.evaluate("document.body.dataset.liveCycle"),
                         chip=page.locator("#state").inner_text(), selfcheck=page.evaluate("document.body.dataset.semaforoSelfcheck"),
                         semaforo_counts=page.locator("#smCounts").inner_text()[:220],
                         north_rain_end=bundle["rain"]["north_zones"].get("end_utc"),
                         avisos_check=(bundle.get("semaforo") or {}).get("aviso_check_utc"),
                         parity_at_cycle=parity(page, bundle, man["built_at_utc"]),
                         expiry=expiry(page, bundle, man["built_at_utc"]),
                         registry=registry_parity(page, bundle, man["built_at_utc"]))
                page.locator("#bSources").click()
                r["sources_dialog"] = page.locator("dialog[open] .db").inner_text()[:400]
                r["live_sources"] = page.evaluate("""[...document.querySelectorAll('#liveSources tbody tr')].map(tr=>({id:tr.dataset.src,
                    attempt:tr.dataset.attempt,cells:[...tr.cells].map(c=>c.innerText.replace(/\\s+/g,' ').trim())}))""")
                page.locator("dialog[open] [data-close]").click()
                # Exercise a real basin popup rather than merely checking that JS initialises.
                if tag == "ciclo_1" and (bundle.get("semaforo") or {}).get("status") == "OK":
                    cid = "PIU-R-PIURA-BAJO"
                    if any(c["id"] == cid for c in bundle["semaforo"]["checkpoints"]):
                        row = page.locator('a[data-sm="' + cid + '"]')
                        if row.count() != 1:
                            raise AssertionError("Missing river checkpoint link in semaforo table: " + cid)
                        row.click()
                        popup = page.locator(".leaflet-popup-content")
                        popup.locator("details summary").first.click()
                        text = popup.inner_text()
                        if ("IMERG Early por cuenca" not in text or
                                not all(k in text for k in ("1h:", "3h:", "6h:", "24h:", "72h:")) or
                                "Cinco preguntas" not in text):
                            raise AssertionError("River popup missing catchment rainfall/complete-window labels: " + text[:500])
                        r["catchment_popup"] = dict(checkpoint=cid, rain_detail_present=True,
                                                    text_preview=text[:800])
                        page.screenshot(path=str(out / "live_catchment_popup.png"))
                        page.locator(".leaflet-popup-close-button").click()
                page.screenshot(path=str(out / f"live_{tag}.png"))
                return r

            page.goto(origin + ("/vigilancia.html?poll=30" if cross_origin else "/vigilancia.html?live=current/&poll=30"), wait_until="load")
            try:
                page.wait_for_selector("body[data-ready='1']", timeout=30000)
            except Exception:
                # Diagnostics are essential: a failed dynamic bundle must never be promoted,
                # but the QA log must explain *why* it failed rather than only reporting a timeout.
                diagnostic = dict(
                    page_errors=errors[-30:],
                    page_url=page.url,
                    ready=page.evaluate("document.body.dataset.ready||null"),
                    state=page.locator("#state").inner_text(timeout=3000),
                    javascript_loaded=page.evaluate("!!document.getElementById('app')"),
                    live_cycle=page.evaluate("document.body.dataset.liveCycle||null"),
                    semaforo_check=page.evaluate("document.body.dataset.semaforoSelfcheck||null"),
                    load_events=len(loads),
                    manifest_cycle=json.loads((droot / "current/manifest.json").read_text(encoding="utf-8")).get("cycle_id"))
                (out / "failure_diagnostics.json").write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
                page.screenshot(path=str(out / "failed_page.png"), full_page=False, timeout=5000)
                print("IRFEN_PRIVATE_VIEW_FAILURE " + json.dumps(diagnostic, ensure_ascii=False), flush=True)
                raise
            rep["runs"].append(snapshot("ciclo_1"))
            if next_cycle:
                page.locator("#t-avisos").click()  # a view state that must survive the automatic reload
                staged = droot / ".next"
                shutil.copytree(next_cycle / "current", staged)
                for n in ("surveillance_view_v0_1.json", "observation_feed_v0_1.json", "manifest.json"):  # manifest last
                    (staged / n).replace(droot / "current" / n)
                before = len(loads)
                page.wait_for_function("(c)=>document.body.dataset.ready==='1'&&document.body.dataset.liveCycle&&document.body.dataset.liveCycle!==c",
                                       arg=rep["runs"][0]["page_cycle"], timeout=120000)
                rep["auto_reloads"] = len(loads) - before
                rep["tab_after_reload"] = page.evaluate("[...document.querySelectorAll('.tabs button')].find(b=>b.getAttribute('aria-selected')==='true')?.id")
                rep["runs"].append(snapshot("ciclo_2"))
            rep["errors"] = errors
            b.close()
        httpd.shutdown()
        if dhttpd:
            dhttpd.shutdown()
    r1 = rep["runs"][0]
    rep["ok"] = (not rep["errors"] and all(x["page_cycle"] == x["manifest_cycle"] and x["parity_at_cycle"]["mismatches"] == 0
                                          and x["expiry"].get("ok", True) is True and x["registry"].get("ok") is True
                                          and len(set(x["selfcheck"].split("/"))) == 1 for x in rep["runs"])
                 and (not next_cycle or (rep["runs"][1]["page_cycle"] != r1["page_cycle"] and rep.get("tab_after_reload") == "t-avisos")))
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--next-cycle", type=Path)
    ap.add_argument("--local-leaflet", type=Path)
    ap.add_argument("--out", type=Path, default=Path("/tmp/irfen_live_check"))
    ap.add_argument("--cross-origin", action="store_true", help="test the deployable private site reading data from another origin")
    a = ap.parse_args(argv)
    rep = run(a.data_dir, a.next_cycle, a.local_leaflet, a.out, a.cross_origin)
    (a.out / "live_page_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:5000])
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
