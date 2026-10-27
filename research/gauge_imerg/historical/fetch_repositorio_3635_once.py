#!/usr/bin/env python3
"""Consulta ÚNICA del Repositorio Institucional de SENAMHI, registro hdl:20.500.12542/3635 (RESEARCH_ONLY).

Fuente institucional distinta del portal datosabiertos.gob.pe (que respondió HTTP 418; ese portal NO se vuelve a
consultar). Cada URL se pide una sola vez, con cadena de redirecciones registrada; el flujo no se repite si existe el
resultado. Se guardan respuestas pequeñas tal cual y el CSV comprimido (gzip, mtime=0) con el SHA-256 del original.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

H = "20.500.12542/3635"
REPO = "https://repositorio.senamhi.gob.pe"
CSV_PATH = "/bitstream/20.500.12542/3635/3/Variables-meteorologicas-estaciones-autom%c3%a1ticas-intercambio-internacional_2024.csv"
URLS = [
    ("handle_api.json", f"https://hdl.handle.net/api/handles/{H}"),          # resolución oficial del handle (CNRI)
    ("handle_redirect.txt", f"https://hdl.handle.net/{H}"),                   # sin seguir redirecciones
    ("item_full.html", f"{REPO}/handle/{H}?show=full"),                      # metadatos Dublin Core completos
    ("item_rest.json", f"{REPO}/rest/handle/{H}?expand=bitstreams,metadata"),  # DSpace 6 REST, si existe
    ("datos_2024.csv", f"{REPO}{CSV_PATH}"),                                   # bitstream ya conocido (catálogo 19-sep)
]
UA = {"User-Agent": "IRFEN-research/0.9 one-shot institutional repository query (+https://github.com/IRFEN2026/irfen-peru/issues/400)"}
MAX_SMALL, MAX_GZ = 5_000_000, 15_000_000


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    log = {"schema": "irfen.gauge_imerg.repository_query_log", "one_shot": True, "handle": H,
           "started_at_utc": now(), "requests": {}}
    for name, url in URLS:
        rec = {"url": url, "requested_at_utc": now()}
        t0 = time.monotonic()
        try:
            follow = name != "handle_redirect.txt"
            r = requests.get(url, headers=UA, timeout=(15, 300), allow_redirects=follow)
            body = r.content
            rec.update(http_status=r.status_code, final_url=r.url,
                       redirect_chain=[{"status": h.status_code, "location": h.headers.get("location")} for h in r.history],
                       location=r.headers.get("location"), content_type=r.headers.get("content-type"),
                       content_length_header=r.headers.get("content-length"), last_modified=r.headers.get("last-modified"),
                       etag=r.headers.get("etag"), bytes=len(body), sha256=hashlib.sha256(body).hexdigest(),
                       md5=hashlib.md5(body).hexdigest(), seconds=round(time.monotonic() - t0, 1))
            if r.status_code == 200 and body:
                if name.endswith(".csv"):
                    gz = gzip.compress(body, compresslevel=9, mtime=0)
                    rec["gzip_bytes"] = len(gz)
                    if len(gz) <= MAX_GZ:
                        (a.out / (name + ".gz")).write_bytes(gz)
                        rec["stored_as"] = name + ".gz"
                    head = body[:4000].decode("utf-8-sig", errors="replace").splitlines()[:6]
                    rec["first_lines"] = head
                    rec["line_count"] = body.count(b"\n")
                elif len(body) <= MAX_SMALL:
                    (a.out / name).write_bytes(body)
                    rec["stored_as"] = name
            elif name == "handle_redirect.txt" and r.headers.get("location"):
                (a.out / name).write_text(r.headers["location"] + "\n")
                rec["stored_as"] = name
        except Exception as exc:  # noqa: BLE001 — se registra; no se reintenta por otras vías
            rec.update(http_status=None, error=f"{type(exc).__name__}: {exc}"[:400], seconds=round(time.monotonic() - t0, 1))
        log["requests"][name] = rec
    log["finished_at_utc"] = now()
    (a.out / "query_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    for k, v in log["requests"].items():
        print(k, v.get("http_status"), v.get("bytes"), v.get("final_url"), v.get("error"))


if __name__ == "__main__":
    main()
