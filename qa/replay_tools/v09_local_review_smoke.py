"""Local review smoke test of the private v0.9 map (RESEARCH_ONLY / TEST_ONLY). Serves site/ on 127.0.0.1 only, opens
the cover, the panel, the territorial viewer and the national inventory in Chromium (Playwright) at desktop and mobile size, walks the main interactions
and reports JavaScript errors, failed or external requests, horizontal overflow and forbidden states.

    python qa/replay_tools/v09_local_review_smoke.py            # prints a JSON report; exit 1 on any problem

Nothing is published: the server binds to 127.0.0.1 and every non-local request is aborted and reported.
"""
from __future__ import annotations

import functools
import http.server
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIEWPORTS = {"desktop": dict(width=1440, height=900), "mobile": dict(width=390, height=844)}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def review(page, origin: str, name: str) -> dict:
    out = dict(viewport=name, problems=[], checks={})
    errors, failed, external = [], [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    # a request cancelled by a page navigation (net::ERR_ABORTED, e.g. nav.js availability checks) is not a missing resource
    page.on("requestfailed", lambda r: failed.append(f"{r.failure} {r.url}") if r.url.startswith(origin) and "ERR_ABORTED" not in str(r.failure) else None)
    page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.url.startswith(origin) and r.status >= 400 else None)
    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(origin) else (external.append(r.request.url), r.abort()))

    def overflow():
        return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")

    # cover page (resumen.html): three freshness indicators and coverage maps drawn from the bundle only
    page.goto(origin + "v09/resumen.html")
    page.wait_for_selector("#maps svg", timeout=20000)
    c = out["checks"]
    c["cover_indicators"] = page.locator("#status .st").count()
    c["cover_shapes"] = page.locator("#maps [data-feature]").count()
    c["cover_no_negative_age"] = "hace -" not in page.inner_text("body")
    c["cover_overflow_px"] = overflow()
    page.click("#irfen-nav a[data-section=lluvia]")
    # panel
    page.wait_for_url("**/v09/index.html")
    page.wait_for_selector("#chips .chip", timeout=20000)
    body = page.inner_text("body")
    c["panel_guards_visible"] = "RESEARCH_ONLY" in body or "TEST_ONLY" in body or "production_use=false" in body
    c["panel_no_negative_age"] = "hace -" not in body
    c["panel_overflow_px"] = overflow()
    # navigation panel -> viewer -> panel
    page.click("a[href='territorio.html']")
    page.wait_for_selector("#map svg path", timeout=20000)
    c["nav_panel_to_viewer"] = page.url.endswith("territorio.html")
    status = page.inner_text("#status")
    c["viewer_status_chips"] = page.locator("#status .st").count()
    c["viewer_no_negative_age"] = "hace -" not in status
    c["viewer_layers"] = page.locator("[data-layer]").count()
    # toggle every layer off and on: the map redraws
    paths_on = page.locator("#map svg path").count()
    for cb in page.query_selector_all("[data-layer]"):
        cb.click()
    paths_off = page.locator("#map svg path").count()
    for cb in page.query_selector_all("[data-layer]"):
        cb.click()
    c["layers_toggle_paths_on_off_on"] = [paths_on, paths_off, page.locator("#map svg path").count()]
    # rain representation: a missing / old window is hatched, never coloured as zero
    page.select_option("#rain-mode", index=1)
    c["rain_hatched_paths"] = page.locator('#map path[fill="url(#hatch)"]').count()
    c["rain_text_no_es_lluvia_cero"] = "no es lluvia cero" in page.inner_text("body")
    # territorial selection and documentary card, both regions
    sel = {}
    for region in ("costa_norte", "rimac"):
        page.click(f"nav [data-region={region}]")
        page.wait_for_timeout(300)
        qs = page.locator("[data-q]")
        sel[region] = dict(quebradas=qs.count())
        if qs.count():
            qs.first.click()
            detail = page.inner_text("#detail")
            sel[region]["card_chars"] = len(detail)
            sel[region]["card_mentions_missing_or_pending"] = any(w in detail.lower() for w in ("pendiente", "no disponible", "falta", "sin "))
    c["regions"] = sel
    # inventory view: three states kept apart, nothing publishable
    page.click("nav [data-view=inventario]")
    page.wait_for_selector("#rows-table tr", timeout=10000)
    c["zone_summary_rows"] = page.locator("#inv-table tr").count() - 1
    c["inventory_count_text"] = page.inner_text("#f-count")
    c["inventory_rows_shown"] = page.locator("#rows-table tr").count() - 1
    geo = page.eval_on_selector("#f-geometry", "s => [...s.options].map(o => [o.value, o.text])")
    repro = next((v for v, t in geo if "reproducible" in t.lower()), None)
    if repro is not None:
        page.select_option("#f-geometry", repro)
        page.wait_for_timeout(200)
        c["inventory_reproducible_geometry_rows"] = page.locator("#rows-table tr").count() - 1
        page.select_option("#f-geometry", geo[0][0])
    page.fill("#f-text", "Huaycoloro")
    page.wait_for_timeout(200)
    c["inventory_search_huaycoloro_rows"] = page.locator("#rows-table tr").count() - 1
    page.fill("#f-text", "")
    table = page.inner_text("#rows-table").lower()
    header = page.eval_on_selector("#rows-table", "t => t.rows[0] ? [...t.rows[0].cells].map(c => c.innerText) : []")
    col = next((i for i, h in enumerate(header) if "public" in h.lower()), None)
    vals = page.eval_on_selector("#rows-table", f"t => [...t.rows].slice(1).map(r => r.cells[{col}] ? r.cells[{col}].innerText : '')") if col is not None else []
    c["inventory_publishable_column_values"] = sorted(set(vals))
    c["inventory_mentions_publishable_yes"] = any(v.strip().lower() in ("sí", "si", "yes", "true") for v in vals)
    c["pending_table_rows"] = page.locator("#pending-table tr").count() - 1
    page.click("nav [data-view=mapa]")
    c["legend_present"] = len(page.inner_text("#legend").strip()) > 0
    c["viewer_overflow_px"] = overflow()
    page.click("a[href='index.html']")
    page.wait_for_selector("#chips .chip", timeout=20000)
    c["nav_viewer_to_panel"] = page.url.endswith("index.html")
    # national documentary inventory (inventario.html): every master row, fichas also without GIS, nothing drawn
    page.click("#irfen-nav a[data-section=inventario]")
    page.wait_for_selector("body[data-ready='1']", timeout=20000)
    c["national_rows"] = int(page.inner_text("#n-shown"))
    c["national_map_eligible"] = int(page.inner_text("#n-map"))
    page.select_option("#f-geo", "REPRODUCIBLE")
    c["national_reproducible"] = int(page.inner_text("#n-shown"))
    page.click("#f-clear")
    page.select_option("#f-geo", "SIN_GEOMETRIA")
    page.click("#rows [data-open]")
    page.wait_for_selector("#ficha:not([hidden])")
    c["national_ficha_no_gis_sections"] = page.locator("#ficha [data-section]").count()
    c["national_ficha_reasons"] = page.locator("#ficha-reasons li").count()
    c["national_drawn_elements"] = page.locator("main svg, main canvas, #ficha svg, #ficha canvas").count()
    c["national_overflow_px"] = overflow()
    page.keyboard.press("Escape")

    out["js_errors"], out["failed_local_requests"], out["external_requests_blocked"] = errors, failed, sorted(set(external))
    if errors:
        out["problems"].append("javascript errors")
    if failed:
        out["problems"].append("missing local resources")
    if not (c["panel_no_negative_age"] and c["viewer_no_negative_age"]):
        out["problems"].append("negative age shown")
    if c["cover_indicators"] != 3 or not c["cover_shapes"] or not c["cover_no_negative_age"]:
        out["problems"].append("cover page")
    if c["national_rows"] != 400 or c["national_map_eligible"] or c["national_drawn_elements"] or c["national_ficha_no_gis_sections"] < 9:
        out["problems"].append("national inventory page")
    if c["panel_overflow_px"] > 0 or c["viewer_overflow_px"] > 0 or c["cover_overflow_px"] > 0 or c["national_overflow_px"] > 0:
        out["problems"].append("horizontal overflow")
    if not c["legend_present"]:
        out["problems"].append("legend missing")
    if c["inventory_mentions_publishable_yes"] or "publicables en mapa: 0" not in c["inventory_count_text"]:
        out["problems"].append("inventory row shown as publishable")
    if not (c["nav_panel_to_viewer"] and c["nav_viewer_to_panel"]):
        out["problems"].append("navigation between panel and viewer")
    if c["layers_toggle_paths_on_off_on"][1] >= c["layers_toggle_paths_on_off_on"][0]:
        out["problems"].append("layer switches do not change the map")
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT / "site")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_port}/"
    reports = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(args=["--no-proxy-server"])
            for name, vp in VIEWPORTS.items():
                ctx = b.new_context(viewport=vp)
                reports.append(review(ctx.new_page(), origin, name))
                ctx.close()
            b.close()
    finally:
        srv.shutdown()
    print(json.dumps(reports, ensure_ascii=False, indent=1))
    return 1 if any(r["problems"] for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
