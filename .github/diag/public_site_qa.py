"""Read-only real-browser QA of the PUBLIC site (GitHub Pages). Prints one ::warning:: line per finding."""
import json, re, sys
from playwright.sync_api import sync_playwright

import os
URL = os.environ.get("QA_URL", "https://irfen2026.github.io/irfen-peru/")
LEAF = os.environ.get("QA_LEAFLET_DIR")  # local dry-run only
W = '#territorial-inventory [data-iw="{}"]'
CLAIMS = ("no hay precipitación", "sin lluvia", "no hay lluvia", "disponible")


def ann(title, msg):
    msg = str(msg).replace("%", "%25").replace("\n", " ")[:1800]
    print(f"::warning title={title}::{msg}", flush=True)


def tap(page, sel):
    page.evaluate("s => { const e = document.querySelector(s); e.scrollIntoView({block:'center'}); e.click(); }", sel)


def run(p, tag, vp, gibs_mode):
    b = p.chromium.launch()
    page = b.new_page(viewport=vp)
    errors, gibs = [], {"imerg": [], "status": []}
    page.on("pageerror", lambda e: errors.append(str(e)[:200]))
    def route(r, *_):
        u = r.request.url
        if LEAF and "unpkg.com/leaflet@1.9.4/dist/" in u:
            return r.fulfill(path=os.path.join(LEAF, u.rsplit("/dist/", 1)[1]))
        if LEAF and ("tile.openstreetmap.org" in u or "gibs.earthdata.nasa.gov" in u) and not ("IMERG" in u and gibs_mode != "real"):
            if "IMERG" in u:
                m = re.search(r"[?&]time=([^&]+)", u, re.I); gibs["imerg"].append(m.group(1) if m else None)
            return r.fulfill(path=os.path.join(LEAF, "tile_clear.png"), content_type="image/png")
        if "gibs.earthdata.nasa.gov" in u and "IMERG" in u:
            m = re.search(r"[?&]time=([^&]+)", u, re.I); gibs["imerg"].append(m.group(1) if m else None)
            if gibs_mode == "fail" or (gibs_mode == "partial" and len(gibs["imerg"]) % 2 == 0):
                return r.abort()
        return r.continue_()
    page.route("**/*", route)
    page.on("response", lambda resp: gibs["status"].append(resp.status) if "gibs.earthdata.nasa.gov" in resp.url and "IMERG" in resp.url else None)
    resp = page.goto(URL, wait_until="networkidle", timeout=90000)
    out = {"http": resp.status if resp else None}
    page.evaluate("document.querySelector('.tab[data-tab=\"territorial-inventory\"]').click()")
    page.wait_for_function("document.querySelectorAll('#ti-map .leaflet-overlay-pane path').length > 0", timeout=60000)
    page.wait_for_timeout(1500)
    ev = page.evaluate
    out["map_top"] = round(ev("document.getElementById('ti-map').getBoundingClientRect().top - document.getElementById('territorial-inventory').getBoundingClientRect().top"))
    out["map_h"] = round(ev("document.getElementById('ti-map').getBoundingClientRect().height"))
    out["scrollW"] = ev("document.documentElement.scrollWidth")
    out["recent_open"] = ev("document.getElementById('ti-recent-box').open")
    out["context_open"] = ev("document.getElementById('ti-context').open")
    out["layers_hidden"] = ev("document.getElementById('ti-layers-panel').hidden")
    out["meteo_hidden"] = ev(f"document.querySelector('{W.format('panel')}').hidden")
    a = page.query_selector("#ti-layers-btn").bounding_box(); w = page.query_selector(W.format("toggle")).bounding_box()
    out["buttons_overlap"] = a["x"] + a["width"] > w["x"]
    paths = lambda: ev("document.querySelectorAll('#ti-map .leaflet-overlay-pane path').length")
    n0 = paths(); tap(page, "#ti-layers-btn"); tap(page, '[data-ti-all-layers="off"]'); n1 = paths(); c1 = page.inner_text("#ti-layers-count")
    tap(page, '[data-ti-all-layers="on"]'); n2 = paths(); page.keyboard.press("Escape")
    out["layers_paths_all_none_all"] = [n0, n1, n2, c1]
    # search
    rows0 = ev("document.querySelectorAll('#ti-list [data-ti-record]').length")
    page.fill("#ti-search", "Huaycoloro"); page.wait_for_timeout(300)
    rows1 = ev("document.querySelectorAll('#ti-list [data-ti-record]').length")
    page.fill("#ti-search", ""); page.wait_for_timeout(200)
    out["search_rows_all_huaycoloro"] = [rows0, rows1]
    tap(page, "#ti-recent-btn"); out["recent_btn_filter"] = ev("document.getElementById('ti-filter').value"); out["recent_open_after_btn"] = ev("document.getElementById('ti-recent-box').open")
    # meteorology
    tap(page, W.format("toggle")); out["layers_closed_when_meteo_opens"] = ev("document.getElementById('ti-layers-panel').hidden")
    ev(f"(()=>{{const e=document.querySelector('{W.format('rain')}');if(!e.checked)e.click();}})()")
    try:
        page.wait_for_function(f"!['CARGANDO','APAGADA'].includes(document.querySelector('{W.format('rain-pill')}').textContent)", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    out["pill"] = page.inner_text(W.format("rain-pill"))
    st = page.inner_text(W.format("status")); out["status"] = st[:230]
    out["slot_label"] = ev(f"document.querySelector('{W.format('slot')}').selectedOptions[0].textContent")
    out["imerg_time_param"] = sorted(set(x for x in gibs["imerg"] if x))[:3]
    out["imerg_http"] = sorted(set(gibs["status"]))
    low = (st + page.inner_text(W.format("panel"))).lower()
    out["claims_found"] = [c for c in CLAIMS if c in low]
    out["absence_sentence"] = bool(re.search(r"no (equivale|significa) a?\s?ausencia de lluvia", low))
    out["js_errors"] = errors
    ann(f"{tag} gibs={gibs_mode}", json.dumps(out, ensure_ascii=False))
    if gibs_mode == "real":
        page.screenshot(path=f"/tmp/shots/{tag}_meteo.png")
        # legacy operational map
        page.evaluate("document.querySelector('.tab[data-tab=\"op\"]').click()"); page.wait_for_timeout(1500)
        op = page.evaluate("document.querySelectorAll('#op [data-iw=\"toggle\"]').length")
        ann(f"{tag} legacy op map", f"weather controls={op} js_errors={errors}")
    b.close()


with sync_playwright() as p:
    import os; os.makedirs("/tmp/shots", exist_ok=True)
    for tag, vp in (("desktop", dict(width=1440, height=900)), ("mobile", dict(width=390, height=844))):
        for mode in ("real", "partial", "fail"):
            try:
                run(p, tag, vp, mode)
            except Exception as e:
                ann(f"{tag} gibs={mode} ERROR", repr(e)[:600])
