#!/usr/bin/env python3
"""PRIMARY6 R2 prerequisite runner using frozen POEORB overlap resolution v0.2.

RESEARCH_ONLY / TEST_ONLY. The v0.1 runner remains the source of dataset,
guardrail, vertical-grid, hashing and identity logic. This wrapper replaces
only precise-orbit resolution with the globally frozen metadata-only overlap
rule and then corrects the legacy manifest label that the v0.1 runner writes
unconditionally. No selected window, Sentinel-1 pair, SAR response, rainfall,
outcome, role, or R2/R3/R4 science value is read to make that correction.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import ibvf_primary6_sentinel1_r2_prerequisites as base
from ibvf_sentinel1_r2_orbit_resolver_v02 import RULE, freeze_orbit

CONTRACT = Path('site/data/validation/ibvf_primary6_sentinel1_poeorb_overlap_resolution_v01.json')
LEGACY_LABEL = 'EXACTLY_ONE_AUX_POEORB_VALIDITY_INTERVAL_COVERS_FROZEN_ACQUISITION_UTC'

base.freeze_orbit = freeze_orbit


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_arg() -> Path:
    i = sys.argv.index('--output')
    return Path(sys.argv[i + 1])


def normalize_manifest(path: Path) -> None:
    d = json.loads(path.read_text(encoding='utf-8'))
    c = json.loads(CONTRACT.read_text(encoding='utf-8'))
    assert c['deployment_status'] == 'RESEARCH_ONLY' and c['test_only'] is True
    assert c['production_use'] is False and c['production_ready'] is False
    assert c['operational_alerting_enabled'] is False and c['uses_operational_event_none_labels'] is False
    assert c['territorial_activation_evidence_blinded'] is True
    assert c['decision_timing']['made_before_primary6_r2_science_pixels_read'] is True
    assert c['decision_timing']['sar_pre_post_response_read'] is False
    assert c['decision_timing']['territorial_outcomes_used'] is False
    assert c['frozen_selection_rule']['if_multiple_candidates'] == 'SELECT_UNIQUE_MAXIMUM_FILE_CREATION_TIMESTAMP'
    assert c['frozen_selection_rule']['same_rule_for_all_primary6_units_seasons_and_windows'] is True
    assert c['frozen_selection_rule']['per_case_tuning_allowed'] is False

    for row in d['entries']:
        for side in ('pre', 'post'):
            o = row['precise_orbits'][side]
            assert o.get('status') == 'PASS'
            # The v0.1 assembler overwrites this field after the v0.2 resolver
            # has already selected and hash-frozen the correct resource.
            assert o.get('selection_rule') == LEGACY_LABEL
            assert o.get('selection_uses_science_values') is False
            assert o.get('selection_uses_outcomes') is False
            assert o.get('selection_uses_known_event_dates') is False
            assert o.get('selected_creation_utc')
            assert o.get('selected_filename')
            assert o.get('zip_sha256') and o.get('inner_eof_sha256')
            o['selection_rule'] = RULE
            o['legacy_assembler_selection_rule_label_corrected'] = True

    d['schema_version'] = 'irfen-ibvf-primary6-sentinel1-r2-prerequisites-v0.2'
    d['source_poeorb_overlap_resolution_contract'] = str(CONTRACT)
    d['source_poeorb_overlap_resolution_contract_sha256'] = sha256_file(CONTRACT)
    d['poeorb_overlap_resolution_rule'] = RULE
    d['poeorb_overlap_resolution_is_global_metadata_only'] = True
    d['poeorb_overlap_resolution_uses_sar_response'] = False
    d['poeorb_overlap_resolution_uses_rainfall'] = False
    d['poeorb_overlap_resolution_uses_known_event_dates'] = False
    d['poeorb_overlap_resolution_uses_territorial_outcomes'] = False
    d['poeorb_overlap_resolution_uses_case_control_roles'] = False
    path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main() -> int:
    rc = base.main()
    if rc != 0:
        return rc
    normalize_manifest(output_arg())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
