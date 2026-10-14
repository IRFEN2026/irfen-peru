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


if __name__ == "__main__":
    unittest.main()
