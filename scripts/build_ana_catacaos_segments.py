#!/usr/bin/env python3
"""Construye tramos críticos ANA 2026 georreferenciados para Catacaos.

Usa únicamente filas del anexo Excel oficial y confirma WGS84/UTM en la ficha
PDF asociada. Convierte UTM 17S a WGS84 y contrasta distancia inicio-fin contra
la longitud declarada. Solo geometrías consistentes se publican en el GeoJSON.
No son polígonos de inundación ni modifican alertas/impacto.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math
import re

from pyproj import Geod, Transformer
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
SOURCE = SITE / 'data/hydrology/ana_piura_critical_points_2026.json'
CONTEXT = SITE / 'data/hydrology/catacaos_official_context.geojson'
OUT = SITE / 'data/hydrology/ana_catacaos_critical_segments_2026.geojson'
REPORT = SITE / 'data/hydrology/ana_catacaos_critical_segments_2026_validation.json'

TRANSFORM = Transformer.from_crs('EPSG:32717', 'EPSG:4326', always_xy=True)
GEOD = Geod(ellps='WGS84')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def number(value):
    try:
        return float(str(value).strip().replace(',', '.'))
    except Exception:
        return None


def ftr_key(text):
    m = re.search(r'(?:N[°º]?\s*)?(\d{4})-2026-ANA', str(text), re.I)
    return m.group(1) if m else None


def main():
    src = load(SOURCE)
    context = load(CONTEXT)
    context_geoms = [shape(f['geometry']) for f in context.get('features', [])]

    pdf_by_key = {}
    for item in src.get('relevant_files', []):
        key = ftr_key(item.get('file_name', ''))
        if key:
            pdf_by_key[key] = item

    features = []
    validations = []

    for row in src.get('spreadsheet_relevant_rows', []):
        fields = row.get('fields') or {}
        if str(fields.get('DISTRITO', '')).strip().lower() != 'catacaos':
            continue
        key = ftr_key(fields.get('B', ''))
        pdf = pdf_by_key.get(key) or {}
        crs = set((pdf.get('structured') or {}).get('crs_tokens') or [])

        e1, n1 = number(fields.get('INICIO')), number(fields.get('N'))
        e2, n2 = number(fields.get('FIN')), number(fields.get('P'))
        zone = str(fields.get('ZONA', '')).strip()
        declared_km = number(fields.get('CANT')) if str(fields.get('UND', '')).strip().lower() == 'km' else None

        base = {
            'ftr': fields.get('B'),
            'ftr_key': key,
            'sector': fields.get('SECTOR'),
            'district': fields.get('DISTRITO'),
            'description': fields.get('DESCRIPCIÓN'),
            'declared_length_km': declared_km,
            'inhabitants_reference': number(fields.get('Nº de Habitantes')),
            'housing_reference': number(fields.get('N° Viviendas (Und)')),
            'hazard_reference': fields.get('AG'),
            'hazard_level_reference': fields.get('AH'),
            'source_document_id': row.get('source_document_id'),
            'source_page': row.get('source_page'),
            'source_excel': row.get('file_name'),
            'source_excel_row': row.get('row_number'),
            'production_use': False,
        }

        errors = []
        if not key or not pdf:
            errors.append('matching_pdf_not_found')
        if not {'WGS84', 'UTM'}.issubset(crs):
            errors.append('pdf_does_not_confirm_wgs84_utm')
        if zone != '17':
            errors.append('excel_zone_not_17')
        if None in (e1, n1, e2, n2):
            errors.append('missing_start_end_coordinates')
        if declared_km is None or declared_km <= 0:
            errors.append('missing_declared_length')

        if errors:
            validations.append({**base, 'status': 'FAIL', 'errors': errors})
            continue

        lon1, lat1 = TRANSFORM.transform(e1, n1)
        lon2, lat2 = TRANSFORM.transform(e2, n2)
        _, _, distance_m = GEOD.inv(lon1, lat1, lon2, lat2)
        straight_km = distance_m / 1000.0
        ratio = straight_km / declared_km
        relative_difference_pct = abs(straight_km - declared_km) / declared_km * 100.0

        start_in_context = any(g.covers(Point(lon1, lat1)) for g in context_geoms)
        end_in_context = any(g.covers(Point(lon2, lat2)) for g in context_geoms)
        spatial_ok = start_in_context and end_in_context

        # Para un tramo simple, la cuerda inicio-fin debe aproximar la longitud.
        # Si la longitud declarada es mucho mayor, probablemente hay curvatura o
        # múltiples subtramos y no dibujamos una recta engañosa.
        length_ok = 0.85 <= ratio <= 1.15
        status = 'PASS' if length_ok and spatial_ok else 'REVIEW'

        validation = {
            **base,
            'status': status,
            'source_crs_tokens': sorted(crs),
            'excel_utm_zone': zone,
            'hemisphere': 'S',
            'hemisphere_basis': 'Catacaos/Piura is south of the equator; UTM northings are consistent with southern-hemisphere false northing.',
            'source_coordinates': {
                'start': {'easting': e1, 'northing': n1},
                'end': {'easting': e2, 'northing': n2},
                'crs_used_for_conversion': 'EPSG:32717 WGS84 / UTM zone 17S',
            },
            'wgs84_coordinates': {
                'start': {'lon': round(lon1, 7), 'lat': round(lat1, 7)},
                'end': {'lon': round(lon2, 7), 'lat': round(lat2, 7)},
            },
            'straight_line_km': round(straight_km, 3),
            'straight_vs_declared_ratio': round(ratio, 4),
            'length_relative_difference_pct': round(relative_difference_pct, 2),
            'start_inside_official_document_context': start_in_context,
            'end_inside_official_document_context': end_in_context,
            'geometry_publication': 'allowed_as_reference_segment' if status == 'PASS' else 'withheld_to_avoid_false_alignment',
        }
        validations.append(validation)

        if status != 'PASS':
            continue

        features.append({
            'type': 'Feature',
            'properties': {
                **base,
                'geometry_status': 'PASS',
                'geometry_role': 'ANA_2026_critical_reach_reference_segment',
                'is_flood_polygon': False,
                'is_inundation_extent': False,
                'source_crs': 'WGS84 / UTM zone 17S',
                'straight_line_km': round(straight_km, 3),
                'length_relative_difference_pct': round(relative_difference_pct, 2),
            },
            'geometry': {
                'type': 'LineString',
                'coordinates': [[round(lon1, 7), round(lat1, 7)], [round(lon2, 7), round(lat2, 7)]],
            },
        })

    collection = {
        'type': 'FeatureCollection',
        'name': 'ANA 2026 critical reference reaches — Catacaos',
        'properties': {
            'version': '0.8-experimental',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'production_use': False,
            'source': 'Autoridad Nacional del Agua / SIGRID-CENEPRED',
            'warning': 'Tramos críticos/referencias de intervención ANA 2026. No son polígonos de inundación ni sustituyen un modelo hidráulico.',
        },
        'features': features,
    }
    report = {
        'version': '0.8-experimental',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'production_use': False,
        'status': 'PASS' if features else 'NO_PUBLISHABLE_GEOMETRY',
        'published_segment_count': len(features),
        'review_or_failed_count': sum(1 for v in validations if v['status'] != 'PASS'),
        'validation_rule': 'WGS84+UTM confirmed in PDF, zone 17 in Excel, endpoints inside official Catacaos document context, straight-line length within ±15% of declared intervention length.',
        'validations': validations,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding='utf-8')
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'status': report['status'],
        'published_segment_count': report['published_segment_count'],
        'review_or_failed_count': report['review_or_failed_count'],
        'segments': [
            {'sector': f['properties']['sector'], 'length_km': f['properties']['declared_length_km'], 'difference_pct': f['properties']['length_relative_difference_pct']}
            for f in features
        ],
        'withheld': [
            {'sector': v.get('sector'), 'status': v['status'], 'ratio': v.get('straight_vs_declared_ratio')}
            for v in validations if v['status'] != 'PASS'
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
