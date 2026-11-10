#!/usr/bin/env python3
"""IRFEN v0.9 · validación histórica de crecidas (río Piura, 2017): captura acotada de fuentes en un runner.
RESEARCH_ONLY / TEST_ONLY. Guarda las respuestas tal cual con SHA-256; no interpreta nada (la extracción es aparte).

--stage pechp  Informes hidrometeorológicos mensuales del Proyecto Especial Chira-Piura (gob.pe): ene–abr de 2016,
               2017 y 2018. Respeta robots.txt de gob.pe; una solicitud por documento; sin reintentos indefinidos.
--stage emsr   Copernicus EMS Rapid Mapping EMSR199 «Floods in Peru» (2017): metadatos de la activación y paquetes
               vectoriales de las AOI de la cuenca del Piura (y Sullana/Chira, guardado aparte como línea distinta).

    python scripts/v09_hist_sources_capture.py --stage pechp
    python scripts/v09_hist_sources_capture.py --stage emsr
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.robotparser
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v09/sources/historical_floods"
UA = "Mozilla/5.0 (IRFEN research TEST_ONLY; bounded archival of public documents)"
LOG: list[dict] = []
STAGE = {"name": "unknown"}
PECHP_COLLECTION = "https://www.gob.pe/institucion/pechp/colecciones/6505-informe-hidrometereologico"
KNOWN_PECHP = {  # found by web search on 30/31-10-2026 (fallback if the collection page cannot be parsed)
    "2017-03": "https://cdn.www.gob.pe/uploads/document/file/3274125/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000003-2017.pdf",
    "2017-02": "https://cdn.www.gob.pe/uploads/document/file/3274122/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000002-2017.pdf",
    "2018-03": "https://cdn.www.gob.pe/uploads/document/file/3274145/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000003-2018.pdf",
    "2016-01": "https://cdn.www.gob.pe/uploads/document/file/3274104/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000001-2016.pdf",
    "2016-03": "https://cdn.www.gob.pe/uploads/document/file/3274110/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000003-2016.pdf",
}
WANTED = [f"{y}-{m:02d}" for y in (2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023) for m in (1, 2, 3, 4)]
DOCS = {  # documents with station metadata (coordinates, drainage areas, regulation), archived as-is
    "pnud_ctar_piura_2000_apendice_d.pdf": "https://siar.regionpiura.gob.pe/documentos/normativa/204.pdf",
    "plan_gestion_rrhh_cuenca_chira_piura.pdf": "https://cdn.www.gob.pe/uploads/document/file/4433253/Plan%20de%20gesti%C3%B3n%20de%20los%20recursos%20h%C3%ADdricos%20de%20la%20cuenca%20Chira%20-%20Piura.pdf",
}
EMSR_API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR199"
PIURA_AOI = re.compile(r"piura|ejidos|catacaos|castilla|sechura|parachique|tambogrande|chulucanas", re.I)
CHIRA_AOI = re.compile(r"sullana", re.I)


def checkpoint() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"requests_{STAGE['name']}.json").write_text(json.dumps(LOG, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def get(url: str, save: Path | None = None, timeout: int = 90, headers: dict | None = None) -> bytes | None:
    t0 = time.time()
    rec = dict(url=url, requested_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    if save is not None and save.is_file() and save.stat().st_size > 0 and save.suffix in (".pdf", ".zip"):
        LOG.append(dict(rec, status="ALREADY_ARCHIVED", file=str(save.relative_to(OUT))))
        return save.read_bytes()
    try:
        with urlopen(Request(url, headers=headers or {"User-Agent": UA}), timeout=timeout) as r:
            raw = r.read()
            rec.update(status="OK", http=r.status, content_type=r.headers.get("content-type"), final_url=r.geturl(),
                       last_modified=r.headers.get("last-modified"))
    except Exception as e:  # noqa: BLE001 - recorded, never hidden
        rec.update(status="ERROR", error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.time() - t0, 1))
        LOG.append(rec)
        checkpoint()
        print(f"::warning title=GET_ERROR::{url[:150]} {rec['error'][:120]}", flush=True)
        return None
    rec.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), seconds=round(time.time() - t0, 1))
    if save is not None:
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_bytes(raw)
        rec["file"] = str(save.relative_to(OUT))
    LOG.append(rec)
    checkpoint()
    return raw


def robots_allows(url: str) -> bool:
    u = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    raw = get(f"{u.scheme}://{u.netloc}/robots.txt", OUT / "pechp" / f"robots_{u.netloc}.txt")
    if raw is None:
        return True  # no robots.txt reachable: standard practice is to proceed, recorded in the log
    rp.parse(raw.decode("utf-8", "replace").splitlines())
    return rp.can_fetch(UA, url)


def month_key(title: str) -> str | None:
    """«Informes Técnicos hidro N° 00003-2017», its slug «…-hidro-n-00003-2017», or «… Marzo 2017» -> 2017-03.
    The PECHP numbering is monthly (N° 00003-2017 is the March 2017 report, checked against its own title page)."""
    t = unescape(title)
    m = re.search(r"hidro[\s-]+n[\s-]+0*(\d{1,2})[\s-]+(20\d{2})", t, re.I)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.search(r"N[°º]?\s*0*(\d{1,2})\s*-\s*(20\d{2})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"]
    m = re.search(r"(" + "|".join(months) + r"|septiembre)\D{0,12}(20\d{2})", t, re.I)
    if m:
        name = m.group(1).lower().replace("septiembre", "setiembre")
        return f"{m.group(2)}-{months.index(name) + 1:02d}"
    return None


def stage_pechp() -> dict:
    found: dict[str, str] = {}
    pages: list[str] = []
    if robots_allows(PECHP_COLLECTION):
        for page in range(1, 9):
            url = PECHP_COLLECTION + (f"?sheet={page}" if page > 1 else "")
            html = get(url, OUT / "pechp" / f"collection_page{page}.html")
            if not html:
                break
            text = html.decode("utf-8", "replace")
            links = set(re.findall(r'href="(/institucion/pechp/informes-publicaciones/[^"#?]+)"', text))
            new = [l for l in links if l not in pages]
            if not new:
                break
            pages += new
    else:
        LOG.append(dict(url=PECHP_COLLECTION, status="ROBOTS_DISALLOWED"))
    summary = dict(collection_document_pages=len(pages))
    for p in sorted(pages):
        slug = p.rsplit("/", 1)[-1]
        key = month_key(slug)
        if key not in WANTED or key in found:
            continue
        html = get(urljoin("https://www.gob.pe", p), OUT / "pechp" / f"doc_{key}.html")
        if not html:
            continue
        pdfs = re.findall(r'href="(https://cdn\.www\.gob\.pe/uploads/document/file/[^"?]+\.pdf)(?:\?[^"]*)?"', html.decode("utf-8", "replace"))
        if pdfs:
            found[key] = unescape(pdfs[0])
    for k, u in KNOWN_PECHP.items():
        found.setdefault(k, u)
    got = {}
    for key in sorted(found):
        raw = get(found[key], OUT / "pechp" / f"pechp_informe_hidrometeorologico_{key}.pdf", timeout=180)
        got[key] = bool(raw and raw[:4] == b"%PDF")
    summary.update(months_wanted=WANTED, months_found=sorted(found), pdf_ok=got)
    return summary


def stage_docs() -> dict:
    got = {}
    for name, url in DOCS.items():
        if not robots_allows(url):
            LOG.append(dict(url=url, status="ROBOTS_DISALLOWED"))
            got[name] = "ROBOTS_DISALLOWED"
            continue
        raw = get(url, OUT / "docs" / name, timeout=300)
        got[name] = "OK" if raw and raw[:4] == b"%PDF" else "NO_PDF"
    return dict(documents=got)


def stage_emsr() -> dict:
    browser = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
               "Accept": "application/json, text/plain, */*", "Referer": "https://rapidmapping.emergency.copernicus.eu/EMSR199"}
    raw = get(EMSR_API, OUT / "emsr199" / "activation_api.json") or get(EMSR_API, OUT / "emsr199" / "activation_api.json", headers=browser)
    summary: dict = {}
    if not raw:
        for alt in ("https://rapidmapping.emergency.copernicus.eu/EMSR199", "https://emergency.copernicus.eu/mapping/list-of-components/EMSR199"):
            get(alt, OUT / "emsr199" / (re.sub(r"[^A-Za-z0-9]+", "_", alt)[-60:] + ".html"), headers=browser)
        z = get("https://rapidmapping.emergency.copernicus.eu/backend/EMSR199/EMSR199_products.zip",
                OUT / "emsr199" / "EMSR199_products.zip", timeout=300, headers=browser)
        get("https://mapping.emergency.copernicus.eu/terms-and-conditions/", OUT / "emsr199" / "terms_and_conditions.html", headers=browser)
        return dict(status="API_UNAVAILABLE", alternatives_tried=2, products_zip=bool(z and z[:2] == b"PK"))
    doc = json.loads(raw)
    results = doc.get("results", doc if isinstance(doc, list) else [])
    act = results[0] if results else {}
    aois = act.get("aois") or []
    summary["api_top_keys"] = sorted(doc)[:20] if isinstance(doc, dict) else "list"
    summary["activation_keys"] = sorted(act)[:40]
    summary["aoi_keys"] = sorted(aois[0])[:40] if aois else []
    summary["product_keys"] = sorted((aois[0].get("products") or [{}])[0])[:40] if aois else []
    summary["aois"] = [a.get("name") for a in aois]
    get("https://emergency.copernicus.eu/mapping/list-of-components/EMSR199", OUT / "emsr199" / "legacy_list_of_components.html")
    downloads = []
    for a in aois:
        name = a.get("name") or ""
        line = "PIURA" if PIURA_AOI.search(name) else ("CHIRA" if CHIRA_AOI.search(name) else None)
        if not line:
            continue
        for p in a.get("products") or []:
            for d in p.get("downloads") or []:
                url = d.get("url") or d.get("link") or ""
                if url.endswith(".zip") and ("VECTOR" in url.upper() or "vector" in (d.get("name") or "").lower()):
                    downloads.append((line, name, p.get("type") or p.get("productType"), p.get("monitoring"), url))
    for line, name, ptype, mon, url in downloads[:40]:
        fname = re.sub(r"[^A-Za-z0-9_.-]+", "_", url.rsplit("/", 1)[-1])
        get(url, OUT / "emsr199" / line.lower() / fname, timeout=240)
    summary["vector_packages"] = [dict(line=l, aoi=n, type=t, monitoring=m, url=u) for l, n, t, m, u in downloads[:40]]
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("pechp", "emsr", "docs"), required=True)
    stage = ap.parse_args(argv).stage
    STAGE["name"] = stage
    summary = stage_pechp() if stage == "pechp" else stage_emsr() if stage == "emsr" else stage_docs()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"summary_{stage}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"::notice title={stage}::{json.dumps(summary, ensure_ascii=False)[:1800]}")
    print(f"::notice title={stage}_requests::ok={sum(r['status'] == 'OK' for r in LOG)} errors={sum(r['status'] != 'OK' for r in LOG)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
