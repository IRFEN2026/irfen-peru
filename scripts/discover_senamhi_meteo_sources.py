#!/usr/bin/env python3
"""Descubre rutas públicas SENAMHI para estaciones y lluvia acumulada.

Las consultas se ejecutan concurrentemente y con límites estrictos para que
rutas lentas/no disponibles no bloqueen CI. Todo resultado es de validación
paralela; no sustituye IMERG ni alimenta alertas.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import json
import re
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'site/data/stations/senamhi_source_discovery.json'
BASE = 'https://www.senamhi.gob.pe'
DEPARTMENTS = {'san_ildefonso': 'la-libertad', 'chosica': 'lima', 'catacaos': 'piura'}
PAGES = ['estaciones', 'lluvia-acumulada', 'descarga-datos-meteorologicos']
HEADERS = {'User-Agent': 'Mozilla/5.0 IRFEN-research/0.8', 'Accept': 'text/html,application/xhtml+xml,*/*'}
PAGE_TIMEOUT = 12
PROBE_TIMEOUT = 8
MAX_CANDIDATES = 30


def fetch(url, timeout):
    try:
        r = requests.get(url, headers=HEADERS, timeout=(5, timeout), allow_redirects=True)
        return r, None
    except Exception as exc:
        return None, {'type': type(exc).__name__, 'message': str(exc)}


def urls_from_html(html, base):
    values = []
    patterns = [
        r'<iframe[^>]+src=["\']([^"\']+)',
        r'<script[^>]+src=["\']([^"\']+)',
        r'["\'](https?://[^"\']+)["\']',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html or '', re.I):
            u = urljoin(base, m.group(1).strip())
            if u.startswith('http') and u not in values:
                values.append(u)
    return values


def classify(url):
    low = url.lower()
    groups = {
        'station': ['estacion', 'estaciones', 'meteo', 'meteorolog'],
        'hydro': ['hidro', 'caudal', 'nivel'],
        'data': ['json', 'ajax', 'api', 'datos', 'data'],
        'rain': ['lluvia', 'precip'],
        'map': ['mapa', 'map'],
        'script': ['.js'],
    }
    return [tag for tag, needles in groups.items() if any(n in low for n in needles)]


def useful_candidate(url):
    tags = classify(url)
    # Ignorar librerías genéricas salvo que la URL también sugiera datos/estaciones.
    meaningful = {'station', 'hydro', 'data', 'rain', 'map'}
    return tags, bool(meaningful.intersection(tags))


def probe(url):
    r, err = fetch(url, PROBE_TIMEOUT)
    if err:
        return {'url': url, 'status': 'error', 'error': err, 'tags': classify(url)}
    ctype = r.headers.get('content-type', '')
    title = None
    if ('text' in ctype or 'html' in ctype or 'javascript' in ctype or not ctype) and len(r.content) <= 2_000_000:
        text = r.text[:120000]
        m = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
        title = re.sub(r'\s+', ' ', m.group(1)).strip() if m else None
    return {
        'url': url,
        'status': 'available' if r.status_code == 200 else 'http_error',
        'http_status': r.status_code,
        'content_type': ctype,
        'bytes': len(r.content),
        'title': title,
        'tags': classify(url),
    }


def main():
    report = {
        'version': '0.8-experimental',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'production_use': False,
        'purpose': 'Descubrir canales públicos SENAMHI para validación meteorológica en tierra; no sustituye IMERG.',
        'zones': [],
        'candidate_endpoints': [],
        'limits': {'page_timeout_s': PAGE_TIMEOUT, 'probe_timeout_s': PROBE_TIMEOUT, 'max_candidates': MAX_CANDIDATES},
    }

    requests_to_zone = {}
    page_urls = []
    for zone, dp in DEPARTMENTS.items():
        for page in PAGES:
            url = f'{BASE}/servicios/main.php?dp={dp}&p={page}'
            page_urls.append(url)
            requests_to_zone[url] = (zone, dp, page)

    page_results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, url, PAGE_TIMEOUT): url for url in page_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                page_results[url] = future.result()
            except Exception as exc:
                page_results[url] = (None, {'type': type(exc).__name__, 'message': str(exc)})

    zone_map = {zone: {'zone_id': zone, 'department_slug': dp, 'pages': []} for zone, dp in DEPARTMENTS.items()}
    candidates = []
    seen = set()

    for url in page_urls:
        zone, dp, page = requests_to_zone[url]
        r, err = page_results.get(url, (None, {'type': 'MissingResult', 'message': 'Sin resultado'}))
        item = {'page': page, 'url': url}
        if err:
            item.update({'status': 'error', 'error': err})
        else:
            item.update({
                'status': 'available' if r.status_code == 200 else 'http_error',
                'http_status': r.status_code,
                'content_type': r.headers.get('content-type', ''),
                'bytes': len(r.content),
            })
            discovered = urls_from_html(r.text if len(r.content) <= 3_000_000 else '', url)
            kept = []
            for u in discovered:
                host = urlparse(u).netloc.lower()
                if 'senamhi.gob.pe' not in host or u in seen:
                    continue
                tags, useful = useful_candidate(u)
                if not useful:
                    continue
                seen.add(u)
                kept.append(u)
                candidates.append(u)
                if len(candidates) >= MAX_CANDIDATES:
                    break
            item['discovered_candidate_urls'] = kept
        zone_map[zone]['pages'].append(item)

    candidates = candidates[:MAX_CANDIDATES]
    probed = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(probe, u): u for u in candidates}
        for future in as_completed(futures):
            try:
                probed.append(future.result())
            except Exception as exc:
                u = futures[future]
                probed.append({'url': u, 'status': 'error', 'error': {'type': type(exc).__name__, 'message': str(exc)}, 'tags': classify(u)})

    probed.sort(key=lambda x: (x.get('status') != 'available', x.get('url', '')))
    report['zones'] = [zone_map[z] for z in DEPARTMENTS]
    report['candidate_endpoints'] = probed
    report['summary'] = {
        'pages_available': sum(1 for z in report['zones'] for p in z['pages'] if p.get('status') == 'available'),
        'candidate_endpoints': len(probed),
        'available_candidates': sum(1 for p in probed if p.get('status') == 'available'),
        'timed_out_candidates': sum(1 for p in probed if p.get('error', {}).get('type') in {'ReadTimeout', 'ConnectTimeout'}),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'summary': report['summary'], 'available': [p for p in probed if p.get('status') == 'available']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
