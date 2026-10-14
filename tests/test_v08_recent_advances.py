"""'Avances integrados recientemente' is an interface grouping of three already
integrated candidates. It must not add geometry, scientific state or risk semantics."""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "site/v08-territorial.js"
MAP_LAYERS = ROOT / "site/data/map_layers.json"

RECENT = {
    "ica_pisco_san_andres": (
        "site/data/phase2/geometries/ica_pisco_san_andres_pisco_basin_context.geojson",
        "Quitasol/Paracas siguen sin geometría local ni outlet; no se promueven como evento.",
    ),
    "arequipa_acari_san_agustin": (
        "site/data/phase2/geometries/arequipa_acari_san_agustin_acari_basin_context.geojson",
        "San Agustín sigue como componente local con identidad hidrológica no resuelta; sin routing al Río Acarí.",
    ),
    "ica_palpa_changuillo": (
        "site/data/phase2/geometries/ica_palpa_changuillo_grande_basin_context.geojson",
        "Palpa/Changuillo conserva tramos locales no resueltos; Yauca/Curis/Macchanga no se vinculan a UH 1372.",
    ),
}
CONTEXT = "Cuenca oficial ANA · contexto de investigación"
DISCLAIMER = "No representa riesgo, inundación ni alerta."

NODE_PRELUDE = r'''
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
// Same record list the page builds in load().
const records=[...plan.candidates,...plan.discoveries,...plan.inventory,...plan.requests.filter(r=>['technical','monitored'].includes(r.listKind))];
const IDS=['ica_pisco_san_andres','arequipa_acari_san_agustin','ica_palpa_changuillo'];
'''


def run_node(body):
    result = subprocess.run(["node", "-e", NODE_PRELUDE + body], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


class RecentAdvancesTests(unittest.TestCase):
    def setUp(self):
        self.js = JS.read_text(encoding="utf-8")

    def test_script_is_syntactically_valid(self):
        result = subprocess.run(["node", "--check", str(JS)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exactly_the_three_integrated_candidates_with_catalog_titles(self):
        out = run_node(r'''
        assert.deepEqual(m.RECENT_ADVANCES.map(a=>a.candidateId),IDS);
        assert.deepEqual(Object.keys(m.RECENT_ADVANCES[0]).sort(),['candidateId','note']);
        const items=m.recentRecords(records);
        assert.equal(items.length,3);
        assert.deepEqual(items.map(x=>x.record.candidateId),IDS);
        for(const x of items){
          const zone=catalog.zones.find(z=>z.candidate_id===x.record.candidateId);
          assert(zone,'candidate must exist in the real catalog');
          assert.equal(x.record.title,zone.system_name,'card title comes from the catalog');
          assert.equal(x.record.kind,'candidate');
          assert.equal(x.record.status,'RESEARCH_ONLY');
          assert.equal(x.record.gate,'BLOCKED');
        }
        // A catalog without them yields no card; nothing is fabricated.
        assert.equal(m.recentRecords(records.filter(r=>!IDS.includes(r.candidateId))).length,0);
        assert.equal(JSON.stringify(inputs),before,'scientific inputs untouched');
        console.log(JSON.stringify(items.map(x=>[x.record.candidateId,x.advance.note])));
        ''')
        notes = dict(json.loads(out.strip().splitlines()[-1]))
        self.assertEqual(notes, {cid: note for cid, (_, note) in RECENT.items()})

    def test_recent_filter_returns_only_those_three_and_respects_search(self):
        run_node(r'''
        const recent=m.filterRecords(records,'recent','');
        assert.deepEqual(recent.map(r=>r.candidateId).sort(),[...IDS].sort());
        assert(recent.every(r=>r.kind==='candidate'));
        // discovery / technical / monitored / withheld records are excluded even if they exist.
        for(const kind of ['discovery','withheld'])assert(records.some(r=>r.kind===kind),'fixture has '+kind);
        assert(records.some(r=>r.listKind==='technical')&&records.some(r=>r.listKind==='monitored'));
        assert(!recent.some(r=>['discovery','withheld'].includes(r.kind)||['technical','monitored'].includes(r.listKind)));
        // A non-candidate record that reuses a recent id is still excluded.
        const impostors=['discovery','withheld'].map(kind=>({key:kind+':x',kind,candidateId:IDS[0],title:'x',layerKeys:[]}))
          .concat([{key:'t:x',kind:'catchment',listKind:'technical',candidateId:IDS[0],title:'x',layerKeys:[]}]);
        assert.equal(m.filterRecords(impostors,'recent','').length,0);
        // Search narrows inside the group and never widens it.
        assert.deepEqual(m.filterRecords(records,'recent','acari').map(r=>r.candidateId),['arequipa_acari_san_agustin']);
        assert.deepEqual(m.filterRecords(records,'recent','ACARÍ').map(r=>r.candidateId),['arequipa_acari_san_agustin']);
        assert.equal(m.filterRecords(records,'recent','huaycoloro').length,0);
        // Existing filters keep their behaviour.
        assert.equal(m.filterRecords(records,'all','').length,records.length);
        assert.deepEqual(m.filterRecords(records,'candidate','').map(r=>r.key),plan.candidates.map(r=>r.key));
        assert(m.filterRecords(records,'discovery','').every(r=>r.kind==='discovery'));
        assert(m.filterRecords(records,'pending','').every(r=>['candidate','discovery'].includes(r.kind)&&!r.layerKeys.length));
        ''')

    def test_existing_record_and_layer_keys_are_reused_without_new_geometry_routes(self):
        out = run_node(r'''
        const withFeature=JSON.stringify(m.buildPlan(...inputs).requests.map(r=>[r.key,r.path]));
        const out={};
        for(const x of m.recentRecords(records)){
          const r=x.record;
          assert.equal(r.key,'candidate:'+r.candidateId);
          assert(plan.candidates.includes(r),'the card points to the existing inventory record');
          assert.equal(r.layerKeys.length,1);
          const requests=plan.requests.filter(q=>r.layerKeys.includes(q.key));
          assert.equal(requests.length,1);
          const q=requests[0];
          assert.equal(q.recordKey,r.key);
          assert.equal(q.category,'CATCHMENT');
          assert.equal(q.kind,'catchment');
          assert.equal(q.sourceRef,'data/map_layers.json');
          const zone=layers.research_zones.find(z=>z.candidate_id===r.candidateId);
          assert.equal('site/'+q.path,zone.geometry.path,'route comes from map_layers.json');
          out[r.candidateId]=q.path;
        }
        // The grouping adds no request: the plan is identical with or without using it.
        assert.equal(JSON.stringify(plan.requests.map(r=>[r.key,r.path])),withFeature);
        assert.equal(plan.requests.filter(q=>IDS.includes(q.candidateId)).length,3);
        console.log(JSON.stringify(out));
        ''')
        paths = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(paths, {cid: path.removeprefix("site/") for cid, (path, _) in RECENT.items()})
        # No geometry route is written in the script for the grouping.
        self.assertNotIn(".geojson", self.js)
        self.assertNotIn("phase2/geometries", self.js)
        block = self.js[self.js.index("const RECENT_ADVANCES"):self.js.index("const RECENT_CONTEXT")]
        for token in ("path", "geometry", "style", "color", "status", "gate"):
            self.assertNotIn(token, block)

    def test_map_layers_records_are_unchanged_research_only_and_hidden_by_default(self):
        layers = json.loads(MAP_LAYERS.read_text(encoding="utf-8"))
        zones = {z["candidate_id"]: z for z in layers["research_zones"]}
        for candidate_id, (path, _) in RECENT.items():
            with self.subTest(candidate=candidate_id):
                zone = zones[candidate_id]
                self.assertEqual(zone["deployment_status"], "RESEARCH_ONLY")
                self.assertIs(zone["production_use"], False)
                self.assertIs(zone["alerting_enabled"], False)
                geometry = zone["geometry"]
                self.assertIs(geometry["map_eligible"], True)
                self.assertIs(geometry["default_visibility"], False)
                self.assertEqual(geometry["path"], path)
                self.assertTrue((ROOT / path).is_file())
        # The script never writes visibility or eligibility.
        self.assertNotIn("default_visibility", self.js)
        self.assertIsNone(re.search(r"map_eligible\s*=[^=]", self.js))

    def test_interface_texts_controls_and_reuse_of_select_record(self):
        js = self.js
        for text in (
            "Avances integrados recientemente",
            CONTEXT,
            DISCLAIMER,
            '<option value="recent">Avances recientes</option>',
            '<button id="ti-recent-btn">Ver avances recientes</button>',
            '<span class="ti-badge">Avance integrado</span>',
            *(note for _, note in RECENT.values()),
        ):
            self.assertIn(text, js)
        # Section sits right below ti-summary.
        self.assertRegex(js, r'<div id="ti-summary"[^>]*>[^<]*</div>\s*<div id="ti-recent" class="ti-recent"')
        # Cards reuse the existing selection path with focus=true.
        self.assertIn(
            "document.getElementById('ti-recent').addEventListener('click',e=>{const b=e.target.closest('[data-ti-record]');"
            "if(b)selectRecord(b.dataset.tiRecord,true);});",
            js,
        )
        self.assertIn("document.getElementById('ti-recent-btn').onclick=showRecent;", js)
        show = js[js.index("function showRecent()"):js.index("function selectRecord(key,focus)")]
        self.assertIn("state.mode='recent';state.query='';", show)
        self.assertIn("recordLayers(x.record)", show)  # only layers already loaded
        for token in ("fetchJSON", "L.polygon", "L.geoJSON", "union", "addLayer", ".checked"):
            self.assertNotIn(token, show)
        # The detail keeps status, gate, sources, assets and pending items next to the badge.
        detail = js[js.index("function selectRecord(key,focus)"):js.index("function applyVisibility()")]
        for token in ("r.status||'TEST_ONLY'", "dl('Activation gate'", "dl('Fuentes'", "dl('Activos'", "dl('Pendientes'"):
            self.assertIn(token, detail)

    def test_grouping_adds_no_risk_alert_probability_threshold_or_capacity_semantics(self):
        js = self.js
        start = js.index("// \"Avances recientes\" es una agrupación de interfaz")
        added = [js[start:js.index("function semanticsOf(maps)")],
                 js[js.index("function renderRecent()"):js.index("function selectRecord(key,focus)")],
                 js[js.index(".ti-recent{"):js.index("@media(max-width:1000px)")]]
        text = " ".join(added).lower().replace(DISCLAIMER.lower(), "")
        for token in ("riesgo", "risk", "alert", "probab", "umbral", "threshold", "capacidad", "capacity",
                      "semáforo", "semaforo", "score", "puntuaci", "peligro", "nivel", "mm/h",
                      "red", "#d84343", "#dc2626", "#f59e0b", "#16a34a", "orange", "green"):
            self.assertNotIn(token, text, token)
        # Cards use the neutral palette already present in the inventory list.
        for colour in re.findall(r"#[0-9a-fA-F]{6}", added[2]):
            self.assertIn(colour, js[:js.index(".ti-recent{")], colour)
        self.assertIn("NO una categoría científica", js)
        for forbidden in ("risk_score", "activation_score", "alert_score"):
            self.assertNotIn(forbidden, js)


if __name__ == "__main__":
    unittest.main()
