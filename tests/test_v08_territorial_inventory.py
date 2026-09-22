"""The full inventory is visible without granting new scientific map eligibility."""
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TerritorialInventoryTests(unittest.TestCase):
    def test_canonical_catalogs_and_no_fabricated_geometries(self):
        code = r'''
        const assert=require('node:assert/strict'), fs=require('node:fs');
        const m=require('./site/v08-territorial.js');
        const read=p=>JSON.parse(fs.readFileSync('./site/'+p));
        const catalog=read('data/phase2/catalog.json');
        const spatial=read('data/phase2/spatial_observation_contracts_v0_1.json');
        const layers=read('data/map_layers.json');
        const remaining=read('data/phase2/w1_remaining_geometry_catalog.json');
        const inputs=[catalog,spatial,layers,remaining];
        const before=JSON.stringify(inputs);
        const plan=m.buildPlan(...inputs);
        assert.equal(JSON.stringify(inputs),before,'Do not modify scientific inputs');
        assert.deepEqual(plan.candidates.map(r=>r.candidateId),catalog.zones.map(z=>z.candidate_id));
        assert.equal(plan.candidates.length,18);
        assert.equal(plan.summary.monitoredSubunits,spatial.summary.research_subunit_contract_count);
        assert.equal(plan.summary.technicalLayers,5);
        assert.equal(plan.pilotIds.length,3);
        assert(plan.requests.some(r=>r.title.includes('San Ildefonso')));
        assert(plan.requests.some(r=>r.title.includes('Huaycoloro')));
        assert(plan.requests.some(r=>r.title.includes('Catacaos')));
        assert(plan.requests.some(r=>r.candidateId==='lima_este_lurin_cieneguilla'));

        // Malanche still has no reproducible machine-readable geometry and must remain absent.
        const malanche=plan.candidates.find(r=>r.candidateId==='lima_sur_malanche');
        assert(malanche); assert.equal(malanche.layerKeys.length,0);
        assert(!plan.requests.some(r=>r.candidateId==='lima_sur_malanche'));
        assert(!Object.hasOwn(malanche,'coordinates'));

        // Huerta Vieja now has reproducible official ANA faja-margin alignments. They are
        // intentionally map context only: one context request, never a catchment or sampling area.
        const huerta=plan.candidates.find(r=>r.candidateId==='lima_norte_huerta_vieja');
        assert(huerta); assert.deepEqual(huerta.layerKeys,['context:lima_norte_huerta_vieja']);
        assert(!Object.hasOwn(huerta,'coordinates'));
        const huertaRequest=plan.requests.find(r=>r.key==='context:lima_norte_huerta_vieja');
        assert(huertaRequest); assert.equal(huertaRequest.kind,'context');
        assert.equal(huertaRequest.path,'data/phase2/geometries/lima_norte_huerta_vieja_faja_context.geojson');
        const huertaDoc=read(huertaRequest.path);
        const huertaFeatures=m.selectFeatures(huertaDoc,huertaRequest);
        assert.equal(huertaFeatures.length,2);
        assert.deepEqual(new Set(huertaFeatures.map(f=>f.geometry.type)),new Set(['LineString']));
        for(const f of huertaFeatures) {
          assert.equal(f.properties.not_catchment,true);
          assert.equal(f.properties.not_event_footprint,true);
          assert.equal(f.properties.production_use,false);
          assert.equal(f.properties.production_ready,false);
          assert(m.semanticLabel(f,huertaRequest).includes('NO es cuenca') || m.semanticLabel(f,huertaRequest).includes('NO delimita'));
        }
        assert(huerta.reason.includes('REVIEW_ONLY'));

        const grouper=plan.candidates.find(r=>r.historicalGrouper);
        assert(grouper);assert.equal(grouper.layerKeys.length,2);
        assert(!plan.requests.some(r=>r.key==='context:'+grouper.candidateId));
        let seen=new Set(), featureCount=0;
        for(const request of plan.requests) {
          assert(request.path);const doc=read(request.path);
          const features=m.selectFeatures(doc,request);
          for(const f of features) {
            const signature=JSON.stringify(f.geometry);
            assert(!seen.has(signature),'Do not draw duplicate sampling/context polygons');
            seen.add(signature);featureCount++;
            if(f.properties?.context_only) assert(m.semanticLabel(f,request).includes('NO es cuenca'));
            if(f.properties?.feature_role?.includes('margin')) assert(m.semanticLabel(f,request).includes('NO es cuenca'));
          }
        }
        assert(featureCount>plan.summary.monitoredSubunits);
        assert.equal(m.dataPath('https://example.com/a.geojson'),null);
        assert.equal(m.dataPath('site/data/../a.geojson'),null);
        assert.equal(m.dataPath('site/data/a.geojson'),'data/a.geojson');
        assert.equal(m.safeURL('javascript:alert(1)'),null);
        const missing=m.buildPlan(catalog,{}, {}, {});
        assert.equal(missing.candidates.length,18);
        assert.equal(missing.requests.length,0);
        const changed=structuredClone(layers);
        changed.research_zones.find(r=>r.candidate_id==='lima_este_lurin_cieneguilla').geometry.map_eligible=false;
        assert(!m.buildPlan(catalog,spatial,changed,remaining).requests.some(r=>r.key==='context:lima_este_lurin_cieneguilla'));
        assert.throws(()=>m.buildPlan({...catalog,production_use:true},spatial,layers,remaining));
        assert.throws(()=>m.buildPlan({...catalog,zones:[catalog.zones[0],catalog.zones[0]]}));
        assert.throws(()=>m.selectFeatures({type:'FeatureCollection',features:[]},{kind:'monitored'}));
        console.log('Full inventory, source geometry, guardrails and missing-data tests PASS');
        '''
        result=subprocess.run(['node','-e',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_main_site_loads_inventory_and_keeps_monitoring(self):
        html=(ROOT/'site/index.html').read_text(encoding='utf-8')
        self.assertIn('src="v08-territorial.js"',html)
        self.assertIn('src="v08-monitoring.js"',html)
        js=(ROOT/'site/v08-territorial.js').read_text(encoding='utf-8')
        for value in ['Mapa e inventario','Todo el inventario','Sin geometría representable',
                      'No se crean marcadores para suplir geometrías faltantes',
                      "g.map_eligible !== true",'Agrupador histórico no activable',
                      'Los elementos geométricos no se cuentan como nuevas quebradas']:
            self.assertIn(value,js)
        for forbidden in ['risk_score','activation_score','alert_score']:
            self.assertNotIn(forbidden,js)


if __name__=='__main__':
    unittest.main()
