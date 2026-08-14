#!/usr/bin/env python3
"""Reproduce eventos históricos con la fórmula operativa v0.7.1.

Objetivo: medir qué habría indicado el índice provisional ante eventos reales.
No modifica umbrales, impactos, alertas ni producción; produce evidencia para
calibración y detección de falsos negativos potenciales.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'site'
OUT = SITE / 'data/calibration/historical_replay.json'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def clamp(x):
    return max(0.0, min(1.35, float(x)))


def threat(r24, r72, r7d, thresholds):
    raw = 100.0 * (
        0.38 * clamp(float(r24) / float(thresholds['rain24'])) +
        0.30 * clamp(float(r72) / float(thresholds['rain72'])) +
        0.32 * clamp(float(r7d) / float(thresholds['rain7d']))
    ) / 1.35
    return round(raw)


def klass(value):
    if value >= 80: return 'Crítica'
    if value >= 60: return 'Muy alta'
    if value >= 40: return 'Alta'
    if value >= 20: return 'Vigilancia'
    return 'Baja'


def result_for(values, thresholds, impact):
    th = threat(values['rain24'], values['rain72'], values['rain7d'], thresholds)
    pr = round(th * float(impact) / 100.0)
    return {
        'rain24': values['rain24'],
        'rain72': values['rain72'],
        'rain7d': values['rain7d'],
        'threshold_ratios': {
            'rain24': round(float(values['rain24']) / float(thresholds['rain24']), 3),
            'rain72': round(float(values['rain72']) / float(thresholds['rain72']), 3),
            'rain7d': round(float(values['rain7d']) / float(thresholds['rain7d']), 3),
        },
        'threat_score': th,
        'threat_class': klass(th),
        'priority_score': pr,
        'priority_class': klass(pr),
        'would_reach_vigilance': th >= 20,
        'would_reach_high': th >= 40,
        'would_reach_very_high': th >= 60,
    }


def main():
    history = load(SITE / 'data/history.json')
    latest = load(SITE / 'data/latest.json')
    zones = {z['id']: z for z in latest.get('zones', [])}
    cases = []

    for event in history.get('events', []):
        zid = event.get('zone_id')
        zone = zones.get(zid)
        if not zone or any(event.get(k) is None for k in ('rain24', 'rain72', 'rain7d')):
            continue
        thresholds = zone.get('thresholds_provisional') or {}
        if not all(thresholds.get(k) for k in ('rain24', 'rain72', 'rain7d')):
            continue
        impact = zone.get('impact_score', 0)
        legacy = result_for(event, thresholds, impact)
        polygon = None
        exp = event.get('experimental_polygon')
        if exp and exp.get('production_use') is False and all(exp.get(k) is not None for k in ('rain24', 'rain72', 'rain7d')):
            polygon = result_for(exp, thresholds, impact)

        diagnostic = 'REVIEW_THRESHOLDS_OR_INPUT_SCALE' if legacy['threat_score'] < 40 else 'EVENT_REACHES_HIGH_OR_MORE'
        cases.append({
            'event_id': event.get('id'),
            'zone_id': zid,
            'zone_name': zone.get('name'),
            'date': event.get('date'),
            'event': event.get('event'),
            'known_event_confidence': event.get('confidence'),
            'source': event.get('source'),
            'source_url': event.get('url'),
            'flow_m3s_reference': event.get('flow_m3s'),
            'thresholds_provisional': thresholds,
            'impact_score_current': impact,
            'legacy_sampling_replay': legacy,
            'polygon_sampling_replay': polygon,
            'diagnostic': diagnostic,
            'production_use': False,
            'warning': 'El replay evalúa la fórmula actual, no prueba causalidad ni valida el umbral. Un score bajo en un evento conocido exige investigación, no ajuste automático.',
        })

    low_capture = [c['event_id'] for c in cases if c['legacy_sampling_replay']['threat_score'] < 40]
    report = {
        'version': '0.8-experimental',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'production_use': False,
        'formula': 'v0.7.1: 38% rain24 + 30% rain72 + 32% rain7d; ratios capped 1.35; /1.35',
        'purpose': 'Diagnóstico retrospectivo de eventos conocidos; no calibra automáticamente.',
        'case_count': len(cases),
        'events_below_high_class': low_capture,
        'cases': cases,
        'interpretation_gate': {
            'status': 'CALIBRATION_REQUIRED',
            'reason': 'Los eventos conocidos deben contrastarse con controles lluviosos sin impacto, estaciones terrestres y características de respuesta de cuenca antes de modificar umbrales.',
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({
        'case_count': report['case_count'],
        'events_below_high_class': report['events_below_high_class'],
        'scores': [
            {
                'event_id': c['event_id'],
                'legacy_threat': c['legacy_sampling_replay']['threat_score'],
                'polygon_threat': c['polygon_sampling_replay']['threat_score'] if c['polygon_sampling_replay'] else None,
            } for c in cases
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
