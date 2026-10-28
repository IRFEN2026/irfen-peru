"""Offline Playwright QA for IRFEN national documentary/signal screening (TEST_ONLY).
Run from repo root after playwright + Chromium are installed.
"""
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def check(page, origin: str, width: int, height: int) -> None:
    errors = []
    failed = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("response", lambda r: failed.append(str(r.status) + " " + r.url)
            if r.url.startswith(origin) and r.status >= 400 else None)
    page.route("**/*", lambda route: route.continue_()
               if route.request.url.startswith(origin) else route.abort())
    page.goto(origin + "v09/vigilancia_nacional.html")
    page.wait_for_selector("#tiles button[data-dep]", timeout=15000)
    assert page.locator("#tiles button").count() == 25, (width, "territories")
    assert page.locator("#zones [data-zone]").count() > 0, (width, "Tumbes evidence")
    assert "400" in page.inner_text("#stats"), (width, "inventario")
    assert "22" in page.inner_text("#stats"), (width, "zonas")
    assert page.get_attribute('#irfen-nav a[aria-current="page"]', "data-section") == "nacional", width
    assert page.locator("main svg, main canvas").count() == 0, (width, "no invented coordinates")
    page.click('button[data-dep="Áncash"]')
    assert "34 registros documentales" in page.inner_text("#dept-summary"), (width, "Áncash")
    assert "Sin zona meteorológica" in page.inner_text("#zones"), (width, "no coverage is not low risk")
    assert page.locator("#docs a").count() > 0
    page.click('button[data-dep="Tumbes"]')
    assert "68 registros documentales" in page.inner_text("#dept-summary")
    assert page.locator("#zones [data-zone]").count() >= 1
    assert page.locator("#docs a[href^='inventario.html#id=']").count() > 0
    assert "no es una alerta" in page.inner_text("body").lower(), width
    overflow = page.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
    assert overflow <= 1, (width, "overflow", overflow)
    assert not errors, (width, errors)
    assert not failed, (width, failed)


def main() -> None:
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT / "site")))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_port}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-proxy-server"])
            for width, height in ((1440, 900), (390, 844)):
                ctx = browser.new_context(viewport={"width": width, "height": height})
                check(ctx.new_page(), origin, width, height)
                ctx.close()
            browser.close()
    finally:
        srv.shutdown()
    print("NATIONAL_BROWSER_TEST_ONLY_OK: 25 departments; 22 zones; 400 identities; desktop/mobile; no JS errors/false GIS.")


if __name__ == "__main__":
    main()
