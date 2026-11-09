"""Offline independent checks of downloaded #496 NASA artifact (no credentials)."""
import argparse
import hashlib
import json
from pathlib import Path
import h5py
import numpy as np


def verify(root):
    result = json.loads((root / 'result.json').read_text())
    samples = result['point_candidates']
    totals = {p['name']: np.zeros((3, 3), dtype=float) for p in samples}
    for item in result['originals']:
        path = root / 'originals' / item['filename']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
        with h5py.File(path) as f:
            g = f['Grid']; ds = g['precipitation']
            lat, lon = g['lat'][:], g['lon'][:]
            assert ds.shape == (1, len(lon), len(lat))
            assert float(ds.attrs.get('scale_factor', 1)) == 1
            assert float(ds.attrs.get('add_offset', 0)) == 0
            unit = ds.attrs['units']
            if isinstance(unit, bytes): unit = unit.decode()
            assert str(unit).strip() == 'mm/hr'
            for p in samples:
                i = int(np.argmin(abs(lon - p['longitude'])))
                j = int(np.argmin(abs(lat - p['latitude'])))
                a = np.asarray(ds[0, i-1:i+2, j-1:j+2], dtype=float)
                assert a.shape == (3, 3) and np.all(np.isfinite(a)) and np.all(a >= 0)
                totals[p['name']] += a * 0.5
    rows = []
    for p in samples:
        a = totals[p['name']]
        calculated = {'pixel_mm': float(a[1, 1]), 'neighborhood_mean_mm': float(a.mean()),
                      'neighborhood_max_mm': float(a.max()),
                      'neighborhood_p50_mm': float(np.percentile(a, 50)),
                      'neighborhood_p90_mm': float(np.percentile(a, 90))}
        delta = max(abs(v - p[k]) for k, v in calculated.items())
        assert delta < 1e-10
        rows.append({'name': p['name'], **calculated, 'maximum_difference_mm': delta})
    comparisons = json.loads((root / 'granule-comparisons.json').read_text())
    assert len(comparisons) == 7488
    assert all(c['delta_rate'] is not None for c in comparisons)
    assert max(abs(c['delta_rate']) for c in comparisons) <= 0.000051
    return {'mode': 'RESEARCH_ONLY/TEST_ONLY', 'verified_original_hashes': len(result['originals']),
            'comparison_rows': len(comparisons), 'independent_point_checks': rows,
            'method': 'Direct h5py indexing; no imports from IRFEN readers or samplers',
            'instrumental_station_pairs': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact_directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = verify(args.artifact_directory)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))
