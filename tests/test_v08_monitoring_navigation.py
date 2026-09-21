"""Executable frontend contracts: no DOM/network needed; Node runs production helpers."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MonitoringNavigationTests(unittest.TestCase):
    def test_production_javascript_contracts(self):
        code = r'''
        const assert = require('node:assert/strict');
        const m = require('./site/v08-monitoring.js');
        assert.equal(m.fmt(0), '0');
        assert.equal(m.fmt(null), '—');
        assert.equal(m.fmt(undefined), '—');
        assert.equal(m.fmt(false), '—');
        assert.equal(m.fmt(1000, 0), '1000');
        assert.equal(m.fmt(Infinity), '—');
        assert.equal(m.usableWindow({available:true,accum_mm:null}), false);
        assert.equal(m.usableWindow({available:true,accum_mm:'0'}), false);
        assert.equal(m.usableWindow({available:true,accum_mm:-1}), false);
        assert.equal(m.usableWindow({available:false,accum_mm:1}), false);
        assert.equal(m.usableWindow({available:true,accum_mm:0}), true);
        for (const s of ['SOURCE_TEMPORARILY_UNAVAILABLE','NOT_READY','NOT_YET_CALIBRATED','BLOCKED_INCOMPLETE_OBSERVATION']) {
            assert.equal(m.statusClass(s), 'v08-bad');
        }
        assert.equal(m.statusClass('OBSERVATION_DATA_AVAILABLE'), 'v08-ok');
        assert.throws(() => m.geometryPath({path:'https://example.com/a.geojson'}));
        assert.throws(() => m.geometryPath({path:'site/data/../secret.geojson'}));
        assert.equal(m.geometryPath({path:'site/data/phase2/test.geojson'}), 'data/phase2/test.geojson');
        const doc = {type:'FeatureCollection',features:[{properties:{unit_id:'a'}},{properties:{unit_id:'b'}}]};
        assert.equal(m.selectFeature(doc,{property:'unit_id',value:'b'}).length,1);
        assert.equal(m.selectFeature(doc,null).length,0);
        assert.equal(m.selectFeature(doc,{property:'unit_id',value:'unknown'}).length,0);
        function row(t, v=0) {return {time_utc:t,granule:t,targets:[{target_id:'x',accum_30min_mm:v}]};}
        // Six records are not six consecutive slots in the requested three hours.
        let archive = {granules:[0,1,2,3,8,9].map(i=>row(new Date(Date.UTC(2026,8,21,0,i*30)).toISOString()))};
        let d=m.continuityForTarget(archive,'x',6);
        assert.equal(d.present,2); assert.equal(d.missing.length,4);
        assert.equal(d.anchor,'2026-09-21T04:30:00.000Z');
        archive={granules:[0,1,2,3,4,5].map(i=>row(new Date(Date.UTC(2026,8,21,0,i*30)).toISOString()))};
        d=m.continuityForTarget(archive,'x',6);
        assert.equal(d.present,6);assert.equal(d.missing.length,0);
        // Conflicting values for the same interval stay unconfirmed.
        archive.granules.push(row('2026-09-21T02:30:00Z',2));
        assert.equal(m.continuityForTarget(archive,'x',6).present,5);
        assert.equal(m.continuityForTarget({granules:[]},'x').missing,null);
        assert.equal(m.continuityForTarget(archive,'absent',6).present,0);
        assert.equal(m.ageText(null), 'no calculable');
        assert.equal(m.ageText('2026-09-21T00:00:00Z',Date.parse('2026-09-21T01:30:00Z')), '1.5 h');
        console.log('Frontend helper assertions PASS');
        '''
        result = subprocess.run(['node', '-e', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_navigation_and_error_contract(self):
        js = (ROOT / 'site/v08-monitoring.js').read_text()
        for required in ('v08unitSelect', 'data-v08-target', 'Geometrías esperadas:',
                         'Con error:', 'permanent: true', 'Consulta de pantalla:',
                         'Registro de adquisición Early:', 'Antigüedad de esa muestra:',
                         'if (!state.mapFitted && layers.size) fitAll();',
                         'if (state.loading) return;', 'Promise.allSettled'):
            self.assertIn(required, js)


if __name__ == '__main__':
    unittest.main()
