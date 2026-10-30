"""Real-network check of site/v09/peru.html: Leaflet from unpkg (browser verifies SRI) and real OSM tiles."""
import functools, http.server, threading, sys, json
from playwright.sync_api import sync_playwright
site, html_path, out, tag = sys.argv[1:5]
html = open(html_path, encoding="utf-8").read()
GEOM = open("qa_tmp/geom.js").read()
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=site))
threading.Thread(target=srv.serve_forever, daemon=True).start()
o = f"http://127.0.0.1:{srv.server_port}/"
res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for n, vp in (("desktop", dict(width=1440, height=900)), ("mobile", dict(width=390, height=844))):
        ctx = b.new_context(viewport=vp)
        ctx.route(o + "v09/peru.html", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))
        pg = ctx.new_page(); cons = []
        pg.on("console", lambda m: cons.append(m.text[:180]) if m.type == "error" else None)
        pg.goto(o + "v09/peru.html"); pg.wait_for_timeout(7000)
        if n == "mobile":
            pg.evaluate("window.scrollTo(0, document.getElementById('map').getBoundingClientRect().top + window.scrollY - 60)"); pg.wait_for_timeout(1500)
        res[n] = dict(pg.evaluate(GEOM), console=cons[:3])
        pg.screenshot(path=f"{out}/{tag}_{n}_peru.png")
        if n == "desktop":
            for dep in ("ANCASH", "LIMA", "ICA", "AREQUIPA", "MOQUEGUA", "TACNA"):
                pg.evaluate(f"location.hash='dep={dep}'"); pg.wait_for_timeout(5000)
                res[f"{n}/{dep}"] = pg.evaluate(GEOM); pg.screenshot(path=f"{out}/{tag}_{n}_{dep.lower()}.png")
            pg.evaluate("location.hash='punto=ANA2017-C43-080'"); pg.wait_for_timeout(5000)
            pg.screenshot(path=f"{out}/{tag}_{n}_punto_arequipa.png")
        ctx.close()
    b.close()
srv.shutdown()
for k, v in res.items():
    print(f"::notice title=PERU_REAL_{tag}_{k}::" + json.dumps(v, ensure_ascii=False))
