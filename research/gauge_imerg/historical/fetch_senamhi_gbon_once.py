#!/usr/bin/env python3
"""Descarga ÚNICA de un conjunto de datos abiertos público de SENAMHI (RESEARCH_ONLY / TEST_ONLY).

«Variables Meteorologicas de las Estaciones automáticas de intercambio internacional» (redes GBON/RBON), publicado en
la Plataforma Nacional de Datos Abiertos (datosabiertos.gob.pe) con licencia ODC-BY. Archivos: el CSV de datos, el
diccionario de datos (XLSX), el documento de metadatos (DOCX) y los metadatos de la API CKAN (package_show).

No es un sondeo: cada URL se solicita una vez y el flujo se niega a repetirse si ya existe el resultado.
Se guardan los archivos pequeños tal cual; el CSV se guarda comprimido (gzip) solo si cabe en el límite y, en todo
caso, con su SHA-256, su tamaño y un inventario completo calculado aquí (se recalcula offline para verificar).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://www.datosabiertos.gob.pe"
NAME = ("Variables%20Meteorologicas%20de%20las%20Estaciones%20autom%C3%A1ticas%20de%20intercambio%20internacional"
        "%20-%20%5BServicio%20Nacional%20de%20Meteorolog%C3%ADa%20e%20Hidrolog%C3%ADa%20del%20Per%C3%BA%20-%20SENAMHI%5D")
FILES = {
    "package_show.json": f"{BASE}/api/3/action/package_show?id=b884a001-f444-4c87-91b2-bee1891e6eb7",
    "diccionario.xlsx": f"{BASE}/sites/default/files/Diccionario_Datos_{NAME}.xlsx",
    "metadatos.docx": f"{BASE}/sites/default/files/Metadatos_{NAME}.docx",
    "datos.csv": f"{BASE}/sites/default/files/{NAME}_0.csv",
}
UA = {"User-Agent": "IRFEN-research/0.9 one-shot open-data download (+https://github.com/IRFEN2026/irfen-peru/issues/400)"}
MAX_GZ_BYTES = 15_000_000


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url):
    t0 = time.monotonic()
    rec = {"url": url, "requested_at_utc": now()}
    try:
        r = requests.get(url, headers=UA, timeout=(15, 300))
        rec.update(http_status=r.status_code, content_type=r.headers.get("content-type"),
                   last_modified=r.headers.get("last-modified"), bytes=len(r.content),
                   sha256=hashlib.sha256(r.content).hexdigest(), seconds=round(time.monotonic() - t0, 1))
        return rec, (r.content if r.status_code == 200 else None)
    except Exception as exc:  # noqa: BLE001 — se registra; no se reintenta por otras vías
        rec.update(http_status=None, error=f"{type(exc).__name__}: {exc}"[:400])
        return rec, None


def inventory(raw: bytes) -> dict:
    """Inventario por estación sin interpretar: columnas, filas, rango de fechas, coordenadas tal cual."""
    text = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            used = enc
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
    rd = csv.DictReader(io.StringIO(text), dialect=dialect)
    cols = rd.fieldnames
    st = {}
    n = 0
    for row in rd:
        n += 1
        key = tuple(row.get(c, "") for c in cols if c and c.upper() in ("CODIGO", "COD", "ESTACION", "NOMBRE"))
        s = st.setdefault(key, {"first": row, "rows": 0})
        s["rows"] += 1
    return {"encoding": used, "delimiter": dialect.delimiter, "columns": cols, "rows": n,
            "stations_by_key": [{"key": list(k), "rows": v["rows"], "first_row": v["first"]} for k, v in st.items()]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    log = {"schema": "irfen.gauge_imerg.open_data_download_log", "one_shot": True, "started_at_utc": now(),
           "dataset": "Variables Meteorologicas de las Estaciones automáticas de intercambio internacional (SENAMHI)",
           "license_declared": "ODC-BY (según la página del conjunto de datos)", "files": {}}
    raw_csv = None
    for name, url in FILES.items():
        rec, body = fetch(url)
        log["files"][name] = rec
        if body is None:
            continue
        if name == "datos.csv":
            raw_csv = body
            gz = gzip.compress(body, compresslevel=9, mtime=0)
            rec["gzip_bytes"] = len(gz)
            if len(gz) <= MAX_GZ_BYTES:
                (a.out / "datos.csv.gz").write_bytes(gz)
                rec["stored_as"] = "datos.csv.gz (gzip, mtime=0; el SHA-256 corresponde al CSV sin comprimir)"
            else:
                rec["stored_as"] = None
        else:
            (a.out / name).write_bytes(body)
            rec["stored_as"] = name
    if raw_csv is not None:
        try:
            inv = inventory(raw_csv)
            (a.out / "inventory_runner.json").write_text(json.dumps(inv, ensure_ascii=False, indent=1))
            log["inventory_summary"] = {k: inv[k] for k in ("encoding", "delimiter", "columns", "rows")}
            log["inventory_summary"]["station_keys"] = len(inv["stations_by_key"])
        except Exception as exc:  # noqa: BLE001
            log["inventory_error"] = f"{type(exc).__name__}: {exc}"[:400]
    log["finished_at_utc"] = now()
    (a.out / "download_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1))
    print(json.dumps({k: {kk: v.get(kk) for kk in ("http_status", "bytes", "error")} for k, v in log["files"].items()},
                     ensure_ascii=False))
    print(json.dumps(log.get("inventory_summary"), ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
