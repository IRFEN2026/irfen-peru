#!/usr/bin/env python3
"""IRFEN v0.9.1 · browser check of a downloadable private-viewer HTML (desktop and mobile), RESEARCH_ONLY.

Opens the self-contained HTML from disk in Chromium (Leaflet from unpkg with its SRI, as a user would), and checks:
no JavaScript errors, page ready, semáforo self-check 536/536, department summary with recent rain per contributing
area for 11 departments (no departmental mean), the historical coast snapshot kept apart and closed, the #496 caveat in
the summary, the semáforo tab and a checkpoint popup, and the department card table. Screenshots for each viewport.

    python3 qa/replay_tools/v091_e2e_browser_check.py viewer.html out_dir   # exit 1 if any check fails
"""
import json
import os
import sys
from pathlib import Path


def run(html: Path, out: Path, local_leaflet: Path | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, vp in (("escritorio", dict(width=1440, height=900)), ("movil", dict(width=390, height=844))):
            ctx = b.new_context(viewport=vp, device_scale_factor=int(os.environ.get("IRFEN_SHOT_SCALE", "1")))
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("console", lambda m: errs.append(m.text) if m.type == "error" and "tile" not in m.text and "ERR_" not in m.text else None)
            if local_leaflet:
                def route(r):
                    u = r.request.url
                    if u.startswith("https://unpkg.com/leaflet@1.9.4/dist/"):
                        f = local_leaflet / u.rsplit("/dist/", 1)[1]
                        if f.is_file():
                            return r.fulfill(body=f.read_bytes(), headers={"content-type": "text/css" if f.suffix == ".css" else "application/javascript",
                                                                            "access-control-allow-origin": "*"})
                    return r.continue_() if u.startswith("file:") else r.abort()
                page.route("**/*", route)
            page.goto(html.resolve().as_uri())
            page.wait_for_selector("body[data-ready='1']", timeout=30000)
            page.wait_for_timeout(1500)
            c = dict(errors=errs)
            c["leaflet"] = page.evaluate("!!window.L")
            c["summary_rows"] = page.locator("#sumTable tbody tr").count()
            c["summary_header"] = page.locator("#sumTable thead").inner_text()
            c["freshness_tags"] = page.locator("#sumTable [data-freshness]").count()
            c["freshness_states"] = sorted(set(page.eval_on_selector_all("#sumTable [data-freshness]", "e=>e.map(x=>x.dataset.freshness)")))
            c["historical_sections"] = page.locator("#tab-resumen details[data-historical]").count()
            c["historical_open"] = page.evaluate("[...document.querySelectorAll('#tab-resumen details[data-historical]')].some(d=>d.open)")
            c["caveat_summary"] = page.locator("#tab-resumen [data-caveat='P0-496']").count()
            c["dept_cells"] = page.eval_on_selector_all("#sumTable [data-crdep]", "e=>e.map(x=>x.dataset.crdep+': '+x.textContent)")
            page.screenshot(path=str(out / f"{name}_resumen.png"), full_page=False)
            page.locator("#sumTable").scroll_into_view_if_needed()  # on a phone the panel sits below the map
            c["summary_table_visible"] = page.locator("#sumTable").is_visible()
            page.screenshot(path=str(out / f"{name}_tabla_resumen.png"), full_page=False)
            page.select_option("#dept", "TACNA")
            page.wait_for_timeout(500)
            c["dept_table_rows_tacna"] = page.locator("#tab-resumen table[data-crtable=TACNA] tbody tr").count()
            page.locator("#tab-resumen table[data-crtable=TACNA]").scroll_into_view_if_needed()
            page.screenshot(path=str(out / f"{name}_ficha_tacna.png"), full_page=False)
            page.locator("#t-semaforo").click()
            page.wait_for_timeout(600)
            c["selfcheck"] = page.evaluate("document.body.dataset.semaforoSelfcheck")
            c["caveat_semaforo"] = page.locator("#tab-semaforo [data-caveat='P0-496']").count()
            page.select_option("#smType", "rio")
            page.locator("#tab-semaforo a[data-sm]").first.click()
            page.wait_for_selector(".leaflet-popup-content", timeout=10000)
            page.wait_for_timeout(400)
            c["caveat_popup"] = page.locator(".leaflet-popup-content [data-caveat='P0-496']").count()
            page.screenshot(path=str(out / f"{name}_ficha_punto.png"), full_page=False)
            ok = (not errs and c["leaflet"] and c["summary_rows"] == 11 and c["freshness_tags"] == 11 and "media / máx" not in c["summary_header"]
                  and c["historical_sections"] == 1 and not c["historical_open"] and c["caveat_summary"] >= 1 and c["caveat_semaforo"] >= 1
                  and c["caveat_popup"] >= 1 and c["selfcheck"] == "536/536" and c["dept_table_rows_tacna"] > 0 and c["summary_table_visible"])
            c["ok"] = bool(ok)
            res[name] = c
            ctx.close()
        b.close()
    return res


if __name__ == "__main__":
    r = run(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
    Path(sys.argv[2], "browser_check.json").write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in ("ok", "errors", "selfcheck", "freshness_states", "caveat_popup", "dept_table_rows_tacna")} for k, v in r.items()},
                     ensure_ascii=False, indent=1))
    sys.exit(0 if all(v["ok"] for v in r.values()) else 1)
