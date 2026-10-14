"""Owner decision 13-10-2026: no automated direct queries to SENAMHI hosts.

The official-outcome archive and the Piura source-status collector keep their other sources (INDECI/COEN, ANIN,
IGP-CENDEHUA, PECHP, GORE Piura) and never request a SENAMHI host unless IRFEN_SENAMHI_DIRECT_ACCESS=enabled is set
explicitly, which no workflow does. Skipped SENAMHI sources are recorded as unknown, never as zero. Offline: every
HTTP call is intercepted (SYNTHETIC responses).
"""
import importlib.util
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OUTCOME = load("archive_official_outcome_sources")
PIURA = load("fetch_piura_source_status")
NOW = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)


class OutcomeArchive(unittest.TestCase):
    def test_senamhi_sources_are_not_requested_and_stay_unknown(self):
        requested = []

        def fake_fetch(sources, captured_at, snapshot_date):
            requested.extend(s["url"] for s in sources)
            return [dict(source_id=s["source_id"], url=s["url"], capture_status="CAPTURED") for s in sources]

        with mock.patch.dict(os.environ, {}, clear=False), mock.patch.object(OUTCOME, "fetch_sources", side_effect=fake_fetch):
            os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
            rows = OUTCOME.fetch_policy_sources(NOW, "2026-10-13")
        self.assertFalse([u for u in requested if "senamhi.gob.pe" in u])
        self.assertIn("https://portal.indeci.gob.pe/emergencias/", requested)
        self.assertEqual([r["source_id"] for r in rows], [s["source_id"] for s in OUTCOME.SOURCES])  # order kept
        for r in rows:
            if r["source_id"] in OUTCOME.SENAMHI_DIRECT_SOURCE_IDS:
                self.assertEqual(r["capture_status"], "NOT_QUERIED_POLICY")
                self.assertIs(r["unknown_not_zero"], True)
            else:
                self.assertEqual(r["capture_status"], "CAPTURED")

    def test_explicit_opt_in_is_the_only_way(self):
        requested = []
        fake = lambda sources, *a: requested.extend(s["url"] for s in sources) or []
        with mock.patch.dict(os.environ, {"IRFEN_SENAMHI_DIRECT_ACCESS": "enabled"}), mock.patch.object(OUTCOME, "fetch_sources", side_effect=fake):
            OUTCOME.fetch_policy_sources(NOW, "2026-10-13")
        self.assertTrue(any("senamhi.gob.pe" in u for u in requested))
        for value in ("1", "true", "yes", "ENABLED"):
            with mock.patch.dict(os.environ, {"IRFEN_SENAMHI_DIRECT_ACCESS": value}):
                self.assertFalse(OUTCOME.senamhi_direct_access_enabled(), value)


class PiuraSourceStatus(unittest.TestCase):
    def test_gore_piura_kept_senamhi_not_requested(self):
        calls = []

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return [{"fkey": "2026-10-13"}]

        def fake_get(url, **kw):
            calls.append(url)
            if "senamhi.gob.pe" in url:
                raise AssertionError("SENAMHI host requested")
            return Resp()

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "piura_source_status.json"
            out.write_text(json.dumps(dict(senamhi=dict(latest_forecast_bulletin_date="2026-03-01",
                                                        latest_verified_forecast_bulletin_url="https://example.invalid/b.pdf",
                                                        forecast_catalog_document_checks=[dict(document_status="VERIFIED_HYDROLOGICAL_BULLETIN",
                                                                                               catalog_date="2026-03-01",
                                                                                               url="https://example.invalid/b.pdf")]))))
            env = {k: v for k, v in os.environ.items() if k != "IRFEN_SENAMHI_DIRECT_ACCESS"}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(PIURA, "OUT", out), \
                    mock.patch.object(PIURA.requests, "get", side_effect=fake_get), mock.patch("builtins.print"):
                PIURA.main()
            status = json.loads(out.read_text())
        self.assertTrue(calls and all("regionpiura.gob.pe" in u for u in calls))
        self.assertEqual(status["gore_piura"]["catalog_status"], "available")
        sen = status["senamhi"]
        self.assertEqual(sen["forecast_page_access_status"], "not_queried_policy")
        self.assertIs(sen["forecast_bulletin_stale"], True)  # the last verified bulletin is carried forward as stale
        self.assertIs(sen["numeric_river_state_available"], False)


class Workflows(unittest.TestCase):
    def test_no_workflow_enables_direct_senamhi_access(self):
        for wf in (ROOT / ".github/workflows").glob("*.yml"):
            self.assertNotRegex(wf.read_text(encoding="utf-8"), r"IRFEN_SENAMHI_DIRECT_ACCESS\s*:\s*['\"]?enabled", wf.name)

    def test_collectors_request_senamhi_only_behind_the_policy(self):
        for name in ("archive_official_outcome_sources", "fetch_piura_source_status"):
            code = (ROOT / f"scripts/{name}.py").read_text(encoding="utf-8")
            self.assertIn("IRFEN_SENAMHI_DIRECT_ACCESS", code)
            self.assertTrue(re.search(r"senamhi_direct_access_enabled\(\)", code))


class IndirectRedirects(unittest.TestCase):
    """An allowed source (INDECI, gob.pe, IGP, GORE Piura) that redirected to SENAMHI must not be followed."""

    def test_urllib_redirect_to_senamhi_is_refused(self):
        from urllib.error import URLError
        from urllib.request import Request
        h = OUTCOME.NoSenamhiRedirect()
        req = Request("https://portal.indeci.gob.pe/emergencias/")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
            for target in ("https://www.senamhi.gob.pe/x", "http://senamhi.gob.pe/", "https://idesep.SENAMHI.gob.pe/a"):
                with self.assertRaises(URLError):
                    h.redirect_request(req, None, 302, "Found", {}, target)
            self.assertIsNotNone(h.redirect_request(req, None, 302, "Found", {}, "https://portal.indeci.gob.pe/emergencias/page/2/"))
            self.assertFalse(OUTCOME.is_senamhi_host("https://senamhi.gob.pe.example.org/"))

    def test_requests_hook_refuses_senamhi_redirect(self):
        class R:
            is_redirect = True
            url = "https://servicios.regionpiura.gob.pe/x"
            def __init__(self, loc): self.headers = {"Location": loc}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
            with self.assertRaises(PIURA.requests.exceptions.InvalidURL):
                PIURA.refuse_senamhi_redirect(R("https://www.senamhi.gob.pe/main.php"))
            self.assertIsNotNone(PIURA.refuse_senamhi_redirect(R("/otra-ruta")))

    def test_every_http_call_goes_through_a_guard(self):
        code = (ROOT / "scripts/archive_official_outcome_sources.py").read_text(encoding="utf-8")
        self.assertNotIn("from urllib.request import Request, urlopen", code)  # urlopen is the guarded opener
        piura = (ROOT / "scripts/fetch_piura_source_status.py").read_text(encoding="utf-8")
        ungated = piura[:piura.index("if not senamhi_direct_access_enabled():", piura.index("def main"))]
        for call in re.findall(r"requests\.get\([^\n]*", ungated[ungated.index("def main"):]):
            self.assertIn("refuse_senamhi_redirect", call)


class EveryWorkflowThatCanReachSenamhi(unittest.TestCase):
    """A workflow that runs a script naming a SENAMHI host either goes through the policy gate (default disabled)
    or can only be started by hand (workflow_dispatch). Push triggers were removed on 14-10-2026: a push to main
    touching e.g. site/data/latest.json started the WIS2 discovery without anyone deciding it."""

    HOST = re.compile(r"https?://[\w.-]*senamhi\.gob\.pe")
    # Scripts that only carry a SENAMHI URL as data (synthetic review fixtures), with no HTTP client.
    URL_AS_DATA_ONLY = ("run_v08_regression_tests",)

    def _workflows(self):
        for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
            text = wf.read_text(encoding="utf-8")
            block = re.search(r"^on:[ \t]*(.*?)\n(.*?)(?=^\S)", text, re.S | re.M)  # no PyYAML in the CI image
            inline = block.group(1).strip()
            if inline:
                triggers = set(re.findall(r"[\w]+", inline))
            else:
                triggers = set(re.findall(r"^  ([a-z_]+):", block.group(2), re.M))
            scripts = [s for s in sorted(set(re.findall(r"scripts/(\w+)\.py", text))) if (ROOT / f"scripts/{s}.py").is_file()]
            yield wf.name, triggers, [s for s in scripts if self.HOST.search((ROOT / f"scripts/{s}.py").read_text(encoding="utf-8"))]

    def test_ungated_senamhi_scripts_are_manual_only(self):
        seen = []
        for name, triggers, scripts in self._workflows():
            for s in scripts:
                code = (ROOT / f"scripts/{s}.py").read_text(encoding="utf-8")
                if "senamhi_direct_access_enabled()" in code:
                    continue  # behind the policy gate, disabled by default
                if s in self.URL_AS_DATA_ONLY:
                    self.assertNotRegex(code, r"import requests|urllib\.request|urlopen|http\.client|httpx", s)
                    continue
                seen.append(name)
                self.assertEqual(triggers, {"workflow_dispatch"}, f"{name} runs {s} (SENAMHI host) and can start without a person")
        self.assertIn("senamhi-wis2-discovery.yml", seen)

    def test_fallback_never_dispatches_them(self):
        spec = importlib.util.spec_from_file_location("scheduler_fallback", ROOT / "scripts/scheduler_fallback.py")
        fb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fb)
        for name, _, scripts in self._workflows():
            if scripts and name not in ("pr-validation.yml", "update-and-deploy.yml"):
                self.assertNotIn(name, fb.TARGETS)


if __name__ == "__main__":
    unittest.main()


SENAMHI_SPELLINGS = (
    "https://www.senamhi.gob.pe./", "https://www.senamhi.gob.pe../x", "https://www.senamhi.gob.pe.../x",
    "HTTPS://WWW.SENAMHI.GOB.PE./", "https://senamhi.gob.pe.", "https://a.b.senamhi.gob.pe./x",
    "https://www%2Esenamhi%2Egob%2Epe/", "https://www．senamhi．gob．pe/", "https://www。senamhi。gob。pe/",
    "https://portal.indeci.gob.pe@www.senamhi.gob.pe./", "https://www.senamhi.gob.pe.:443/main.php", " https://WwW.SeNaMhI.gOb.Pe./ ",
)
LEGITIMATE = ("https://portal.indeci.gob.pe/emergencias/feed/", "https://www.gob.pe/institucion/anin/noticias", "https://www.gob.pe/que/pechp",
              "https://www.igp.gob.pe/servicios/", "https://servicios.regionpiura.gob.pe/datos/x", "https://senamhi.gob.pe.example.org/",
              "https://notsenamhi.gob.pe/", "https://portal.indeci.gob.pe./emergencias/")


class HostSpellings(unittest.TestCase):
    """Independent review 14-10: 'https://www.senamhi.gob.pe./' (trailing root dot) passed the old check. Every
    spelling that resolves to a SENAMHI host is now refused; INDECI, gob.pe, IGP and GORE Piura are not."""

    def test_every_spelling_is_senamhi(self):
        for mod in (OUTCOME, PIURA):
            for url in SENAMHI_SPELLINGS:
                self.assertTrue(mod.is_senamhi_host(url), (mod.__name__, url))
            for url in LEGITIMATE:
                self.assertFalse(mod.is_senamhi_host(url), (mod.__name__, url))


class RedirectChains(unittest.TestCase):
    """End to end against a local HTTP server: chained redirects (local -> local -> SENAMHI spelling) are cut before
    any DNS lookup or connection to SENAMHI; legitimate chains still arrive. No external network."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/ok":
                    body = b"ok"
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                hops = {"/a": "/b", "/b": "/c", "/legit-a": "/legit-b", "/legit-b": "/ok"}
                if self.path in hops:
                    target = hops[self.path]
                elif self.path.startswith("/c"):
                    from urllib.parse import unquote
                    target = unquote(self.path.split("?to=", 1)[1]) if "?to=" in self.path else self.server.final_target
                else:
                    target = "/ok"
                from urllib.parse import quote
                self.send_response(302)
                # HTTP headers are Latin-1: a non-ASCII Location travels percent-encoded, as real servers send it
                self.send_header("Location", quote(target, safe=":/?#[]@!$&'()*+,;=%~"))
                self.end_headers()

        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def spy(self):
        import socket

        real_conn, real_gai = socket.create_connection, socket.getaddrinfo
        self.touched = []

        def conn(address, *a, **k):
            self.touched.append(str(address[0]))
            if "senamhi" in str(address[0]).lower():
                raise AssertionError(f"connection to {address[0]}")
            return real_conn(address, *a, **k)

        def gai(host, *a, **k):
            self.touched.append(str(host))
            if "senamhi" in str(host).lower():
                raise AssertionError(f"DNS lookup of {host}")
            return real_gai(host, *a, **k)

        import contextlib
        import http.client

        real_tunnel = http.client.HTTPConnection.set_tunnel

        def tunnel(self_conn, host, *a, **k):  # an HTTPS request through a proxy (CONNECT host) never opens a socket to host
            self.touched.append(str(host))
            if "senamhi" in str(host).lower():
                raise AssertionError(f"proxy tunnel to {host}")
            return real_tunnel(self_conn, host, *a, **k)

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("socket.create_connection", side_effect=conn))
        stack.enter_context(mock.patch("socket.getaddrinfo", side_effect=gai))
        stack.enter_context(mock.patch.object(http.client.HTTPConnection, "set_tunnel", tunnel))
        return stack, contextlib.nullcontext()

    def no_senamhi_touched(self):
        self.assertFalse([h for h in self.touched if "senamhi" in h.lower()], self.touched)

    def test_urllib_chain_to_any_spelling_is_cut(self):
        from urllib.error import URLError
        from urllib.request import Request
        os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
        for target in SENAMHI_SPELLINGS[:10]:
            self.srv.final_target = target.strip()
            a, b = self.spy()
            with a, b:
                with self.assertRaises(URLError, msg=target):
                    OUTCOME.urlopen(Request(self.base + "/a"), timeout=10)
            self.no_senamhi_touched()

    def test_urllib_direct_request_is_refused_before_dns(self):
        from urllib.error import URLError
        from urllib.request import Request
        os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
        for target in ("https://www.senamhi.gob.pe./", "https://WWW.SENAMHI.GOB.PE../", "https://x.senamhi.gob.pe./"):
            a, b = self.spy()
            with a, b:
                with self.assertRaises(URLError):
                    OUTCOME.urlopen(Request(target), timeout=10)
            self.no_senamhi_touched()

    def test_requests_chain_to_any_spelling_is_cut(self):
        os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
        for target in SENAMHI_SPELLINGS[:10]:
            self.srv.final_target = target.strip()
            a, b = self.spy()
            with a, b:
                with self.assertRaises(PIURA.requests.exceptions.InvalidURL, msg=target):
                    PIURA.requests.get(self.base + "/a", timeout=10, hooks={"response": PIURA.refuse_senamhi_redirect})
            self.no_senamhi_touched()

    def test_legitimate_chains_still_arrive(self):
        from urllib.request import Request
        a, b = self.spy()
        with a, b:
            with OUTCOME.urlopen(Request(self.base + "/legit-a"), timeout=10) as r:
                self.assertEqual(r.read(), b"ok")
            r = PIURA.requests.get(self.base + "/legit-a", timeout=10, hooks={"response": PIURA.refuse_senamhi_redirect})
            self.assertEqual((r.status_code, r.text), (200, "ok"))
        self.no_senamhi_touched()
