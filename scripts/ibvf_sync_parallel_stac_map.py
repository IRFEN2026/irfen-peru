#!/usr/bin/env python3
"""Project blind multipista A1 STAC preflight into the scientific map manifest.

This is a projection only: it does not select windows, assign case/control roles,
read territorial outcomes, or create any operational inference.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--map', required=True)
    ap.add_argument('--preflight', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    map_path = Path(args.map)
    preflight_path = Path(args.preflight)
    m = json.loads(map_path.read_text(encoding='utf-8'))
    p = json.loads(preflight_path.read_text(encoding='utf-8'))

    for d in (m, p):
        assert d['deployment_status'] == 'RESEARCH_ONLY'
        assert d['test_only'] is True
        assert d['production_use'] is False
        assert d['production_ready'] is False
        assert d['operational_alerting_enabled'] is False
        assert d['uses_operational_event_none_labels'] is False
        assert d['territorial_activation_evidence_blinded'] is True
        assert d['serious_modeling_gate'] == 'CLOSED_MINIMUM_DATASET_NOT_REACHED'
    assert p['blind_window_selection_performed'] is False
    assert p['case_control_assignment_performed'] is False
    assert p['sensor_availability_deletes_calendar_days'] is False
    assert p['territorial_outcome_fields_read'] is False
    assert p['transport_failure_is_missing_data'] is False
    assert p['status'] == 'A1_SENSOR_CATALOG_PREFLIGHT_COMPLETE_NO_WINDOW_SELECTED'
    assert p['summary']['transport_blocked_aggregate_results'] == 0
    assert p['summary']['transport_blocked_fixed_requests'] == 0

    by_unit = {t['unit_id']: t for t in p['tracks']}
    expected_tracks = set((m.get('parallel_a0_pool_summary') or {}).get('tracks') or [])
    assert expected_tracks == set(by_unit)

    for case in m['cases']:
        unit_id = case.get('unit_id')
        if unit_id not in by_unit:
            continue
        track = by_unit[unit_id]
        assert case.get('blind_window') == 'NOT_YET_SELECTED_FROM_FROZEN_POOL'
        assert case.get('a0_case_control_role') == 'UNASSIGNED'
        collections = {c['collection']: c for c in track['collections']}
        assert set(collections) == {'sentinel-1-grd', 'landsat-c2-l2', 'cop-dem-glo-30'}
        assert all(c['scientific_data_status'] == 'PRESENT_CATALOG' for c in collections.values())
        assert all(c['transport_status'] == 'SUCCESS' for c in collections.values())

        case['framework_stage'] = 'A1_SENSOR_CATALOG_PREFLIGHT_COMPLETE_A0_POOL_FROZEN_NO_WINDOW_SELECTED'
        case['remote_sensing_status'] = 'A1_STAC_CATALOG_PRESENT_S1_LANDSAT_COPDEM_WINDOW_NOT_SELECTED'
        case['a1_stac_preflight_path'] = 'data/validation/ibvf_parallel_stac_preflight.json'
        case['a1_stac_preflight_status'] = p['status']
        case['a1_stac_catalog'] = {
            'sentinel1': collections['sentinel-1-grd']['scientific_data_status'],
            'landsat': collections['landsat-c2-l2']['scientific_data_status'],
            'cop_dem_glo30': collections['cop-dem-glo-30']['scientific_data_status'],
            'count_semantics': 'CATALOG_PRESENCE_CONFIRMED_COUNTS_MAY_BE_LOWER_BOUNDS_WHERE_STAC_NEXT_LINK_PRESENT',
        }
        # A3 is deliberately untouched; no blind window or outcome role exists yet.
        assert case['imerg_status'] == 'NOT_STARTED'
        assert case['blind_status'] == 'TERRITORIAL_EVIDENCE_SEALED'

    m['version'] = 'irfen-independent-basin-validation-map-v2.1'
    m['generated_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    acq = m.setdefault('acquisition_contract', {})
    acq['parallel_a1_stac_preflight_script'] = 'scripts/ibvf_parallel_stac_preflight.py'
    acq['parallel_a1_stac_preflight_report'] = 'site/data/validation/ibvf_parallel_stac_preflight.json'
    acq['parallel_a1_stac_preflight_status'] = p['status']
    acq['parallel_a1_stac_fixed_requests'] = p['summary']['fixed_stac_requests_executed']
    m['parallel_a0_pool_status'] = 'FROZEN_EXHAUSTIVE_FOUR_TRACK_CALENDAR_NO_WINDOW_SELECTED'
    m['meteorological_ranking_status'] = 'PREREGISTERED_NOT_EXECUTED_NO_WINDOW_SELECTED'

    Path(args.output).write_text(json.dumps(m, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({
        'version': m['version'],
        'parallel_tracks_updated': sorted(expected_tracks),
        'a1_status': p['status'],
        'blind_windows_selected': 0,
        'case_control_roles_assigned': 0,
        'serious_modeling_gate': m['serious_modeling_gate'],
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
