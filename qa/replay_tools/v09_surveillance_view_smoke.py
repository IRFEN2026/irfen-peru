#!/usr/bin/env python3
"""IRFEN v0.9 · prueba de humo de la vista privada de vigilancia (site/v09/vigilancia.html), escritorio y móvil.

Sirve `site/` en 127.0.0.1, abre la página con Chromium (Playwright) y comprueba:
0 errores JS, página lista, guardas visibles, pestañas, ventanas de lluvia, selección de departamento, «Ver en el mapa» de
un aviso, enlaces internos que responden 200, ausencia de desbordamiento horizontal y el semáforo experimental (pestaña,
filtros, ventana emergente y misma evaluación en el navegador que en scripts/v09_build_semaforo.py sobre casos sintéticos). Peticiones externas: se registran;
el mapa base OSM se bloquea en la prueba. `--local-leaflet DIR` sirve Leaflet desde DIR (entornos sin acceso a unpkg) y
retira el atributo integrity SOLO en la copia servida a la prueba.

    python qa/replay_tools/v09_surveillance_view_smoke.py --out /tmp/smoke [--local-leaflet DIR]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "site"))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def semaforo_cases():
    """Synthetic evaluation cases (times × confirmations × aviso links) with the generator's evaluate() as reference."""
    import copy
    import importlib.util
    from datetime import timedelta
    spec = importlib.util.spec_from_file_location("sem", ROOT / "scripts/v09_build_semaforo.py")
    sem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sem)
    D = json.loads((ROOT / "site/data/v09/surveillance_view_v0_1.json").read_text(encoding="utf-8"))["semaforo"]
    base = dict(rules=D["rules"], confirmations=[], aviso_check_utc=D["aviso_check_utc"], avisos=D["avisos"], rain_refs=D["rain_refs"])
    cut = sem.iso(D["cutoff_utc"])
    river = next(c for c in D["checkpoints"] if c["type"] == "rio")
    queb = next(c for c in D["checkpoints"] if c["type"] == "quebrada")
    confs = [[], [dict(system_id=river["system_id"], verified=True, source_kind="OFICIAL", observed_at_utc=(cut - timedelta(hours=1)).isoformat())],
             [dict(checkpoint_id=queb["id"], verified=True, source_kind="REGISTRO_VERIFICADO", observed_at_utc=(cut - timedelta(hours=2)).isoformat()),
              dict(checkpoint_id=river["id"], verified=False, observed_at_utc=cut.isoformat())]]
    cases = []
    for h in (0, 1, 3, 13, 50, 24 * 30):
        t = cut + timedelta(hours=h)
        for ci, cf in enumerate(confs):
            for strip in (False, True):
                S = dict(base, confirmations=cf)
                for cp in D["checkpoints"]:
                    c = copy.deepcopy(cp)
                    if strip:
                        c["avisos"] = []
                    r = sem.evaluate(c, S, t)
                    cases.append(dict(cp=c, S=S, t=t.isoformat(), expect=[r["state"], r["rule"], r["confidence"], r["context"]]))
    return cases


def semaforo_checks(page, out, name) -> dict:
    r = {}
    page.locator("#t-semaforo").click()
    r["selfcheck"] = page.evaluate("document.body.dataset.semaforoSelfcheck")
    r["guard"] = "no es una alerta oficial" in page.locator("#tab-semaforo .guard").inner_text()
    r["rows_now"] = page.locator("#tab-semaforo tbody tr").count()
    r["states_now"] = sorted(set(page.eval_on_selector_all("#tab-semaforo tbody tr", "rs=>rs.map(x=>x.dataset.state)")))
    r["map_points"] = page.locator(".leaflet-sema-pane .sm-pt").count()
    r["map_squares_ana"] = page.locator(".leaflet-sema-pane .sm-sq").count()
    r["context_box"] = page.locator("#smCtx").inner_text()[:160]
    page.select_option("#smType", "rio")
    r["rows_rios"] = page.locator("#tab-semaforo tbody tr").count()
    page.select_option("#smType", "quebrada")
    r["rows_quebradas"] = page.locator("#tab-semaforo tbody tr").count()
    page.select_option("#smType", "ALL")
    page.select_option("#smState", "ATENCION")
    r["rows_attention"] = page.locator("#tab-semaforo tbody tr").count()
    page.select_option("#smState", "ALL")
    page.select_option("#smDep", "PIURA")
    r["pending_dep_msg"] = "pendiente" in page.locator("#tab-semaforo .empty").inner_text()
    page.select_option("#smDep", "LAMBAYEQUE")
    page.locator("#tab-semaforo button[data-smmode=CORTE]").click()
    r["states_cutoff"] = sorted(set(page.eval_on_selector_all("#tab-semaforo tbody tr", "rs=>rs.map(x=>x.dataset.state)")))
    page.locator("#tab-semaforo a[data-sm]").first.click()
    page.wait_for_selector(".leaflet-popup-content", timeout=5000)
    page.wait_for_timeout(400)  # popup fade-in
    pop = page.locator(".leaflet-popup-content").inner_text()
    r["popup_fields"] = all(k in pop for k in ("confianza", "Evaluado", "IMERG 24 h", "GOES-19", "no es una alerta oficial",
                                                "Contexto territorial", "posible crecida"))
    page.screenshot(path=str(out / f"{name}_semaforo_popup.png"), full_page=False)
    page.locator(".leaflet-popup-close-button").click()
    page.locator("#tab-semaforo button[data-smmode=AHORA]").click()
    page.select_option("#smDep", "ALL")
    cases = semaforo_cases()
    got = page.evaluate("cs=>cs.map(c=>{const r=window.IRFEN_SEMAFORO_EVAL(c.cp,c.S,c.t);return [r.state,r.rule,r.confidence,r.context];})",
                        [dict(cp=c["cp"], S=c["S"], t=c["t"]) for c in cases])
    bad = [(c["cp"]["id"], c["t"], c["expect"], g) for c, g in zip(cases, got) if g != c["expect"]]
    from collections import Counter
    # the audited case: a regional aviso is in force but the point's local data are stale → grey, aviso kept as context
    reg = [c for c in cases if c["expect"][3]["vigentes"] and c["expect"][1] == "NO_EVALUABLE"]
    r["js_vs_python"] = dict(cases=len(cases), mismatches=len(bad), first=bad[:3], states=dict(Counter(c["expect"][0] for c in cases)),
                             regional_aviso_with_stale_local_data=dict(cases=len(reg), all_grey=all(c["expect"][0] == "GRIS" for c in reg)))
    return r


def run(out: Path, local_leaflet: Path | None) -> dict:
    from playwright.sync_api import sync_playwright
    httpd, origin = serve()
    out.mkdir(parents=True, exist_ok=True)
    report = dict(origin=origin, runs=[])
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, vp in (("desktop", dict(width=1440, height=900)), ("mobile", dict(width=390, height=844))):
            ctx = b.new_context(viewport=vp, device_scale_factor=1)
            page = ctx.new_page()
            errors, external, bad = [], [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "tile.openstreetmap" not in m.text and "ERR_FAILED" not in m.text else None)

            def route(r):
                u = r.request.url
                if u.startswith(origin):
                    if local_leaflet and u.endswith("/v09/vigilancia.html"):
                        resp = r.fetch()
                        html = re.sub(r'\s+integrity="[^"]+"', "", resp.text())
                        return r.fulfill(response=resp, body=html)
                    return r.continue_()
                if local_leaflet and u.startswith("https://unpkg.com/leaflet@1.9.4/dist/"):
                    f = local_leaflet / u.rsplit("/dist/", 1)[1]
                    if f.is_file():
                        ctype = "text/css" if f.suffix == ".css" else "application/javascript" if f.suffix == ".js" else "image/png"
                        return r.fulfill(body=f.read_bytes(), headers={"content-type": ctype, "access-control-allow-origin": "*"})
                external.append(u.split("?")[0][:80])
                if "unpkg.com" in u and not local_leaflet:
                    return r.continue_()
                return r.abort()
            page.route("**/*", route)
            page.goto(origin + "/v09/vigilancia.html", wait_until="load")
            page.wait_for_selector("body[data-ready='1']", timeout=20000)
            chk = {}
            page.screenshot(path=str(out / f"{name}_load.png"), full_page=False)
            chk["map_share_of_viewport"] = page.evaluate("(()=>{const r=document.getElementById('map').getBoundingClientRect();"
                                                         "return Math.round(100*Math.max(0,Math.min(r.bottom,innerHeight)-Math.max(r.top,0))*r.width/(innerWidth*innerHeight))})()")
            chk["bar_height"] = page.evaluate("Math.round(document.getElementById('bar').getBoundingClientRect().height)")
            chk["state_chip"] = page.locator("#state").inner_text()
            chk["viewing_box"] = page.locator("#viewing").inner_text()[:160]
            chk["leaflet"] = page.evaluate("!!window.L")
            page.locator("#bInfo").click()
            chk["guard_visible"] = page.locator("#guard").is_visible()
            page.locator("#dlg-info [data-close]").click()
            for btn in ("bSources", "bLimits"):
                page.locator(f"#{btn}").click()
                chk[btn] = page.locator("dialog[open] .db").inner_text()[:60]
                page.locator("dialog[open] [data-close]").click()
            if not page.locator("#layers").is_visible():
                page.locator("#bLayers").click()
            chk["layers"] = page.locator("#layers input").count()
            chk["layers_unavailable"] = page.locator("#layers .na-item").count()
            for w in ("1 h", "3 h", "6 h", "72 h", "24 h"):
                page.locator("#win button", has_text=w).click()
            page.locator("#layers input[data-layer=ana]").check()
            page.locator("#layers input[data-layer=uh]").check()
            chk["legend"] = page.locator("#viewing .legend").last.inner_text()[:80]
            chk["hydro_legend"] = page.locator("#viewing .legend").first.inner_text()[:60]
            page.screenshot(path=str(out / f"{name}_layers.png"), full_page=False)
            page.locator("#bLayers").click()
            page.fill("#search", "Chiclayo")
            page.locator("#searchForm button").click()
            chk["search_zoom"] = page.evaluate("document.querySelector('.leaflet-container') && Math.round(window.__z||0)")
            page.screenshot(path=str(out / f"{name}_chiclayo.png"), full_page=False)
            page.fill("#search", "Arequipa (departamento)")
            page.locator("#searchForm button").click()
            chk["summary_rows"] = page.locator("#tab-resumen tbody tr").count()
            chk["dept_card"] = page.locator("#tab-resumen .card h2").first.inner_text()
            page.select_option("#dept", "PIURA")
            chk["dept_card_select"] = page.locator("#tab-resumen .card h2").first.inner_text()
            page.screenshot(path=str(out / f"{name}_piura.png"), full_page=False)
            tabs = {}
            for t in ("lluvia", "avisos", "rios", "quebradas"):
                page.locator(f"#t-{t}").click()
                tabs[t] = len(page.locator(f"#tab-{t}").inner_text())
            chk["tabs_text_len"] = tabs
            chk["semaforo"] = semaforo_checks(page, out, name)
            page.locator("#t-avisos").click()
            page.select_option("#fst", "ALL")
            hl = page.locator("#tab-avisos a[data-hl]")
            chk["aviso_highlight_links"] = hl.count()
            if hl.count():
                hl.first.click()
                chk["highlight_msg"] = page.locator("#msg").inner_text()[:100]
            page.locator("#t-rios").click()
            chk["river_chart"] = page.locator("#tab-rios svg.chart").count()
            chk["overflow_x"] = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 1")
            links = page.evaluate("[...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href'))")
            internal = sorted({l.split('#')[0] for l in links if l and not l.startswith(('http', '#', 'mailto'))})
            for l in internal:
                st = page.request.get(origin + "/v09/" + l).status
                if st != 200:
                    bad.append((l, st))
            ext = sorted({l for l in links if l and l.startswith("http")})
            chk["external_links"] = dict(count=len(ext), hosts=sorted({l.split("/")[2] for l in ext}))
            run_rep = dict(name=name, viewport=vp, errors=errors, external_requests=sorted({u.split("/")[2] for u in external}), broken_internal_links=bad, checks=chk)
            report["runs"].append(run_rep)
            ctx.close()
        b.close()
    httpd.shutdown()
    report["ok"] = all(not r["errors"] and not r["broken_internal_links"] and not r["checks"]["overflow_x"] and r["checks"]["guard_visible"]
                       and r["checks"]["summary_rows"] == 11 and r["checks"]["map_share_of_viewport"] >= 55
                       and r["checks"]["semaforo"]["js_vs_python"]["mismatches"] == 0 for r in report["runs"])
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("/tmp/irfen_surveillance_smoke"))
    ap.add_argument("--local-leaflet", type=Path)
    a = ap.parse_args(argv)
    rep = run(a.out, a.local_leaflet)
    (a.out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:6000])
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
