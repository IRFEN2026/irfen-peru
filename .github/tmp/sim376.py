import importlib.util, json, os, sys
from pathlib import Path
from unittest import mock
ROOT = Path.cwd()
os.environ.pop("IRFEN_SENAMHI_DIRECT_ACCESS", None)
calls = []
def load(n):
    s = importlib.util.spec_from_file_location(n, ROOT / f"scripts/{n}.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
O = load("archive_official_outcome_sources"); P = load("fetch_piura_source_status")
class Resp:
    def __init__(self, url): self.url = url; self.status = 200; self.headers = {"Content-Type": "text/html; charset=utf-8"}
    def read(self, n=-1): return b"<html><body><a href='/emergencias/x/'>Reporte 13/10/2026</a></body></html>"
    def geturl(self): return self.url
    def getheader(self, k, d=None): return self.headers.get(k, d)
    def __enter__(self): return self
    def __exit__(self, *a): pass
def fake_open(req, timeout=35):
    url = getattr(req, "full_url", req); calls.append(url)
    assert "senamhi.gob.pe" not in url, url
    return Resp(url)
with mock.patch.object(O, "urlopen", side_effect=fake_open), mock.patch("sys.argv", ["x", "--snapshot-date", "2026-10-13"]):
    O.main()
class R:
    status_code = 200; is_redirect = False; headers = {}
    def raise_for_status(self): pass
    def json(self): return [{"fkey": "2026-10-14"}]
def fake_get(url, **kw):
    calls.append(url); assert "senamhi.gob.pe" not in url, url; return R()
with mock.patch.object(P.requests, "get", side_effect=fake_get):
    P.main()
print("HTTP calls:", len(calls), "SENAMHI calls:", sum("senamhi" in c for c in calls))
print("hosts:", sorted({c.split("/")[2] for c in calls}))
