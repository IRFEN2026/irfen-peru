#!/usr/bin/env python3
"""Descubre controles espaciales oficiales ANA/SIGRID para Pedregal y Quirio.

Objetivo único: obtener geometría/vértices de las fajas marginales oficiales y
usarlos como control de los candidatos DEM. No convierte la faja marginal en
cuenca ni define outlets automáticamente.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import io, json, re, tempfile, zipfile

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site/data/calibration/chosica_ana_faja_controls.json"
BASE = "https://sigrid4.cenepred.gob.pe/sigridv4"
DOCS = {
    "pedregal": {"id": 6066, "resolution": "2070-2015-ANA-AAA.CAÑETE-FORTALEZA", "vertices": 41, "length_km": 2.5},
    "quirio": {"id": 6067, "resolution": "2256-2015-ANA-AAA.CAÑETE-FORTALEZA", "vertices": 32, "length_km": 2.5},
}
HEADERS = {"User-Agent": "Mozilla/5.0 IRFEN-research/0.8"}


def req(url, timeout=60):
    r = requests.get(url, headers=HEADERS, timeout=(15, timeout), allow_redirects=True)
    return r


def url_candidates(html, doc_id):
    soup = BeautifulSoup(html, "html.parser")
    vals = set()
    for tag in soup.find_all(True):
        for key in ("href", "src", "action", "onclick", "data-url", "data-href"):
            v = tag.get(key)
            if v and (str(doc_id) in str(v) or "ambito" in str(v).lower()):
                vals.add(str(v))
    for m in re.finditer(r"[^\"'\s<>]{0,100}(?:ambito|%C3%A1mbito|6066|6067)[^\"'\s<>]{0,180}", html, re.I):
        vals.add(m.group(0))
    return sorted(vals)[:200]


def inspect_bytes(content, content_type):
    info = {"bytes": len(content), "content_type": content_type}
    if content.startswith(b"%PDF"):
        info["kind"] = "pdf"
        try:
            reader = PdfReader(io.BytesIO(content))
            texts = []
            pages_with_coords = []
            coord_tokens = []
            for i, page in enumerate(reader.pages, start=1):
                try: text = page.extract_text() or ""
                except Exception: text = ""
                if text.strip(): texts.append(i)
                hits = re.findall(r"\b(?:2\d{5,6}|8\d{6}|9\d{6})[.,]?\d*\b", text)
                if len(hits) >= 4:
                    pages_with_coords.append(i)
                    coord_tokens.extend(hits[:80])
            info.update({"page_count": len(reader.pages), "text_layer_pages": len(texts), "pages_with_coordinate_like_tokens": pages_with_coords, "coordinate_like_tokens": coord_tokens[:250]})
        except Exception as exc:
            info["parse_error"] = str(exc)
    elif content[:2] == b"PK":
        info["kind"] = "zip"
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                info["members"] = z.namelist()[:250]
                info["has_shapefile"] = any(x.lower().endswith(".shp") for x in z.namelist())
                info["has_geojson"] = any(x.lower().endswith((".geojson", ".json")) for x in z.namelist())
                info["has_kml"] = any(x.lower().endswith(".kml") for x in z.namelist())
        except Exception as exc:
            info["parse_error"] = str(exc)
    elif content.lstrip().startswith((b"{", b"[")):
        info["kind"] = "json"
    elif b"<html" in content[:1000].lower() or b"<!doctype" in content[:1000].lower():
        info["kind"] = "html"
    else:
        info["kind"] = "other"
    return info


def main():
    report = {
        "version": "0.8-experimental",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_use": False,
        "authority": "ANA official marginal-strip controls via SIGRID",
        "principle": "Faja marginal valida ubicación/recorrido del cauce; no equivale a la cuenca ni define automáticamente el outlet DEM.",
        "targets": {},
    }
    for name, meta in DOCS.items():
        did = meta["id"]
        page_url = f"{BASE}/documento/{did}"
        map_url = f"{BASE}/mapa?id_ambito={did}"
        download_url = f"{BASE}/biblioteca/documento/{did}/descargar"
        row = {**meta, "page_url": page_url, "map_url": map_url, "download_url": download_url, "tests": []}
        html = ""
        for label, url in (("document_page", page_url), ("map_page", map_url), ("download", download_url)):
            try:
                r = req(url, 120)
                test = {"label": label, "requested_url": url, "status": r.status_code, "final_url": r.url}
                test.update(inspect_bytes(r.content, r.headers.get("content-type", "")))
                row["tests"].append(test)
                if label == "document_page" and test.get("kind") == "html":
                    html = r.text
                if label == "map_page" and test.get("kind") == "html":
                    row["map_html_markers"] = url_candidates(r.text, did)
            except Exception as exc:
                row["tests"].append({"label": label, "requested_url": url, "error_type": type(exc).__name__, "error": str(exc)})
        if html:
            row["document_html_markers"] = url_candidates(html, did)
        row["usable_official_geometry_found"] = any(
            t.get("kind") in ("zip", "json") and (t.get("has_shapefile") or t.get("has_geojson") or t.get("has_kml") or t.get("kind") == "json")
            for t in row["tests"]
        )
        row["usable_pdf_coordinates_found"] = any(t.get("pages_with_coordinate_like_tokens") for t in row["tests"])
        report["targets"][name] = row
    report["status"] = "official_controls_discovered" if any(
        x.get("usable_official_geometry_found") or x.get("usable_pdf_coordinates_found") for x in report["targets"].values()
    ) else "official_documents_reached_but_geometry_route_unresolved"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "targets": {k: {"geometry": v["usable_official_geometry_found"], "pdf_coordinates": v["usable_pdf_coordinates_found"]} for k,v in report["targets"].items()}}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
