#!/usr/bin/env python3
"""Descubre interfaces oficiales de datos hidrometeorológicos de GORE Piura.

Fase exploratoria. No alimenta el índice operativo. Intenta identificar enlaces
reutilizables del informe diario Chira-Piura y del catálogo nacional de datos
abiertos, para disponer de una fuente hidrológica complementaria a SENAMHI.
"""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import json
import re

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "hydrology" / "gore_piura_discovery.json"

PAGES = [
    {
        "id": "gore_daily",
        "institution": "Gobierno Regional de Piura / Proyecto Especial Chira Piura",
        "url": "https://servicios.regionpiura.gob.pe/datosh",
        "role": "Informe diario del estado hidrometeorológico de la cuenca Chira Piura",
    },
    {
        "id": "datos_abiertos",
        "institution": "Plataforma Nacional de Datos Abiertos / GORE Piura",
        "url": "https://www.datosabiertos.gob.pe/dataset/datos-hidrometereol%C3%B3gicos-gobierno-regional-piura",
        "role": "Dataset público hidrometeorológico del Sistema Hidráulico Mayor",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; IRFEN-research/0.8; public-data-discovery)",
    "Accept": "text/html,application/xhtml+xml,application/json,text/plain,*/*",
}


def compact(text, limit=500):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def unique(items, limit=150):
    out = []
    seen = set()
    for item in items:
        item = compact(item)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def fetch(url):
    last = None
    for timeout in (20, 45, 75):
        try:
            r = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
            return r
        except Exception as exc:
            last = exc
    raise last


def inspect_page(spec):
    r = fetch(spec["url"])
    text = r.text
    soup = BeautifulSoup(text, "html.parser")

    hrefs = []
    for tag in soup.find_all(["a", "link", "script", "form"]):
        raw = tag.get("href") or tag.get("src") or tag.get("action")
        if raw:
            hrefs.append(urljoin(r.url, raw))

    inline = "\n".join(x.get_text(" ", strip=False) for x in soup.find_all("script") if not x.get("src"))
    quoted = re.findall(r"[\"']([^\"']{3,300})[\"']", inline)
    inline_urls = []
    for raw in quoted:
        low = raw.lower()
        if any(k in low for k in ("api", "ajax", "datos", "data", "download", "descarga", ".csv", ".xlsx", ".pdf", ".json", "fetch", "http")):
            inline_urls.append(urljoin(r.url, raw))

    forms = []
    for form in soup.find_all("form"):
        forms.append({
            "action": urljoin(r.url, form.get("action") or ""),
            "method": (form.get("method") or "GET").upper(),
            "fields": [
                {
                    "name": field.get("name"),
                    "id": field.get("id"),
                    "type": field.get("type") or field.name,
                    "value": field.get("value"),
                }
                for field in form.find_all(["input", "select", "button"])
                if field.get("name") or field.get("id")
            ][:80],
        })

    refs = unique(hrefs + inline_urls)
    candidates = [
        u for u in refs
        if any(k in u.lower() for k in (
            ".csv", ".xlsx", ".xls", ".pdf", ".json", "api", "ajax", "download",
            "descarga", "datosh", "hidro", "report", "informe", "archivo", "file"
        ))
    ]

    snippets = []
    for match in re.finditer(
        r"fetch\s*\(|\$\.ajax|axios|\.csv|\.xlsx|\.pdf|download|descarg|datosh|hidromet|fecha|mes|anio|año",
        text,
        flags=re.I,
    ):
        a = max(0, match.start() - 220)
        b = min(len(text), match.end() + 380)
        snippets.append(text[a:b])

    return {
        **spec,
        "http_status": r.status_code,
        "final_url": r.url,
        "content_type": r.headers.get("content-type"),
        "response_bytes": len(r.content),
        "page_title": compact(soup.title.get_text(" ") if soup.title else ""),
        "forms": forms[:20],
        "references": refs,
        "candidate_data_references": unique(candidates),
        "javascript_snippets": unique(snippets, 50),
    }


def main():
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Descubrir fuente oficial reutilizable para estado hidrológico de Catacaos/Bajo Piura.",
        "production_use": False,
        "sources": [],
        "summary": {},
    }

    for spec in PAGES:
        try:
            report["sources"].append(inspect_page(spec))
        except Exception as exc:
            report["sources"].append({
                **spec,
                "status": "access_error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    candidates = []
    for source in report["sources"]:
        candidates.extend(source.get("candidate_data_references", []))

    direct_files = [
        u for u in unique(candidates, 300)
        if urlparse(u).path.lower().endswith((".csv", ".xlsx", ".xls", ".pdf", ".json"))
    ]
    report["summary"] = {
        "accessible_sources": sum(1 for x in report["sources"] if x.get("http_status") == 200),
        "candidate_reference_count": len(unique(candidates, 300)),
        "direct_file_candidates": direct_files[:100],
        "decision": (
            "build_daily_ingestor" if direct_files
            else "inspect_dynamic_endpoint" if candidates
            else "keep_as_metadata_only"
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for source in report["sources"]:
        print(source.get("id"), source.get("http_status"), source.get("error_type", ""))
        for u in source.get("candidate_data_references", [])[:20]:
            print(" ", u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
