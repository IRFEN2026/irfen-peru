"""v0.9 aviso capture (INDECI/COEN only): a redirect from an INDECI URL to a SENAMHI host is refused before the
redirected request is sent, recorded and not retried; ordinary redirects keep working. Local HTTP server, no internet."""
import functools
import http.client
import http.server
import importlib.util
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("v09_senamhi_avisos_guard", ROOT / "scripts/v09_senamhi_avisos.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/to-senamhi":
            self.send_response(302)
            self.send_header("Location", "https://www.senamhi.gob.pe/main.php?p=aviso")
            self.end_headers()
        elif self.path == "/to-senamhi-subdomain":
            self.send_response(301)
            self.send_header("Location", "http://WIS.Senamhi.gob.pe/oapi")
            self.end_headers()
        elif self.path == "/moved":
            self.send_response(301)
            self.send_header("Location", "/feed")
            self.end_headers()
        elif self.path == "/feed":
            body = b"<rss>ok</rss>"
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


class RedirectGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def get(self, path):
        hosts = []
        real = http.client.HTTPConnection.connect
        real_s = http.client.HTTPSConnection.connect

        def spy(conn):
            hosts.append(conn.host)
            return real(conn)

        def spy_s(conn):
            hosts.append(conn.host)
            raise AssertionError(f"HTTPS connection attempted to {conn.host}")

        with mock.patch.object(http.client.HTTPConnection, "connect", spy), mock.patch.object(http.client.HTTPSConnection, "connect", spy_s), \
                mock.patch.object(M.time, "sleep"):
            data, meta = M.http_get(self.base + path, 5, 10_000)
        return data, meta, hosts

    def test_redirect_to_senamhi_is_refused_before_sending(self):
        for path in ("/to-senamhi", "/to-senamhi-subdomain"):
            data, meta, hosts = self.get(path)
            self.assertIsNone(data)
            self.assertEqual(meta["error"], "REDIRECT_TO_SENAMHI_REFUSED_POLICY")
            self.assertEqual(meta["attempts"], 1)  # a policy refusal is not retried
            self.assertIn("senamhi.gob.pe", meta["redirect_target"].lower())
            self.assertFalse([h for h in hosts if "senamhi" in h.lower()])

    def test_ordinary_redirect_still_works_and_is_recorded(self):
        data, meta, _ = self.get("/moved")
        self.assertEqual(data, b"<rss>ok</rss>")
        self.assertTrue(meta["redirected_to"].endswith("/feed"))
        self.assertNotIn("error", meta)

    def test_direct_senamhi_url_is_never_requested(self):
        with mock.patch.object(http.client.HTTPSConnection, "connect", side_effect=AssertionError("network")):
            data, meta = M.http_get("https://www.senamhi.gob.pe/?p=aviso", 5, 10_000)
        self.assertIsNone(data)
        self.assertEqual(meta["error"], "SENAMHI_HOST_NOT_QUERIED_POLICY")

    def test_indeci_hosts_are_not_senamhi(self):
        for url in ("https://portal.indeci.gob.pe/emergencias/feed/", "https://www.gob.pe/x", "https://senamhi.gob.pe.example.org/"):
            self.assertFalse(M.is_senamhi_host(url), url)
        self.assertTrue(M.is_senamhi_host("https://idesep.senamhi.gob.pe/a"))


# Independent review 14-10-2026: "https://www.senamhi.gob.pe./" (trailing root dot) passed the old host check, so the
# capture would have followed a redirect to it. Every spelling below names a SENAMHI host and must be refused.
SENAMHI_SPELLINGS = (
    "https://www.senamhi.gob.pe./", "https://www.senamhi.gob.pe../x", "https://www.senamhi.gob.pe.../x",
    "HTTPS://WWW.SENAMHI.GOB.PE./", "https://senamhi.gob.pe.", "https://a.b.senamhi.gob.pe./x",
    "https://www%2Esenamhi%2Egob%2Epe/", "https://www\uff0esenamhi\uff0egob\uff0epe/", "https://www\u3002senamhi\u3002gob\u3002pe/",
    "https://portal.indeci.gob.pe@www.senamhi.gob.pe./", "https://www.senamhi.gob.pe.:443/main.php", " https://WwW.SeNaMhI.gOb.Pe./ ",
)
LEGITIMATE = ("https://portal.indeci.gob.pe/emergencias/feed/", "https://portal.indeci.gob.pe./emergencias/feed/",
              "https://www.gob.pe/institucion/indeci/noticias", "https://servicios.regionpiura.gob.pe/datos/x",
              "https://senamhi.gob.pe.example.org/", "https://notsenamhi.gob.pe/")


class ChainHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        from urllib.parse import quote, unquote

        if self.path == "/ok":
            body = b"<rss>ok</rss>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        hops = {"/a": "/b", "/b": "/c", "/legit-a": "/legit-b", "/legit-b": "/ok"}
        target = hops.get(self.path) or (unquote(self.path.split("?to=", 1)[1]) if "?to=" in self.path else self.server.final_target)
        self.send_response(302)
        self.send_header("Location", quote(target, safe=":/?#[]@!$&'()*+,;=%~"))  # headers are Latin-1
        self.end_headers()


class TrailingDotAndChains(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ChainHandler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def guarded(self):
        """Spies on DNS, TCP connect and proxy CONNECT: any of them naming a SENAMHI host fails the test."""
        import contextlib
        import socket

        self.touched = []
        real_conn, real_gai, real_tunnel = socket.create_connection, socket.getaddrinfo, http.client.HTTPConnection.set_tunnel

        def check(host):
            self.touched.append(str(host))
            if "senamhi" in str(host).lower():
                raise AssertionError(f"network attempt to {host}")

        def conn(address, *a, **k):
            check(address[0])
            return real_conn(address, *a, **k)

        def gai(host, *a, **k):
            check(host)
            return real_gai(host, *a, **k)

        def tunnel(c, host, *a, **k):
            check(host)
            return real_tunnel(c, host, *a, **k)

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch("socket.create_connection", side_effect=conn))
        stack.enter_context(mock.patch("socket.getaddrinfo", side_effect=gai))
        stack.enter_context(mock.patch.object(http.client.HTTPConnection, "set_tunnel", tunnel))
        stack.enter_context(mock.patch.object(M.time, "sleep"))
        return stack

    def assert_no_senamhi(self):
        self.assertFalse([h for h in self.touched if "senamhi" in h.lower()], self.touched)

    def test_every_spelling_is_senamhi_and_legitimate_hosts_are_not(self):
        for url in SENAMHI_SPELLINGS:
            self.assertTrue(M.is_senamhi_host(url), url)
        for url in LEGITIMATE:
            self.assertFalse(M.is_senamhi_host(url), url)

    def test_chained_redirect_to_any_spelling_is_refused_and_not_retried(self):
        for target in SENAMHI_SPELLINGS:
            self.srv.final_target = target.strip()
            with self.guarded():
                data, meta = M.http_get(self.base + "/a", 5, 10_000)
            self.assertIsNone(data, target)
            self.assertEqual(meta.get("error"), "REDIRECT_TO_SENAMHI_REFUSED_POLICY", (target, meta))
            self.assertEqual(meta["attempts"], 1, target)
            self.assert_no_senamhi()

    def test_direct_request_to_any_spelling_is_never_sent(self):
        for target in SENAMHI_SPELLINGS:
            with self.guarded():
                data, meta = M.http_get(target, 5, 10_000)
            self.assertIsNone(data, target)
            self.assertEqual((meta.get("error"), meta["attempts"]), ("SENAMHI_HOST_NOT_QUERIED_POLICY", 0), target)
            self.assert_no_senamhi()

    def test_opener_refuses_senamhi_before_connecting_even_without_http_get(self):
        from urllib.request import Request

        for target in ("https://www.senamhi.gob.pe./", "http://WWW.SENAMHI.GOB.PE../", "https://x.senamhi.gob.pe./"):
            with self.guarded():
                with self.assertRaises(M.SenamhiRedirectRefused):
                    M._guarded_opener().open(Request(target), timeout=5)
            self.assert_no_senamhi()

    def test_legitimate_chain_still_arrives(self):
        with self.guarded():
            data, meta = M.http_get(self.base + "/legit-a", 5, 10_000)
        self.assertEqual(data, b"<rss>ok</rss>")
        self.assertTrue(meta["redirected_to"].endswith("/ok"))
        self.assert_no_senamhi()


if __name__ == "__main__":
    unittest.main()
