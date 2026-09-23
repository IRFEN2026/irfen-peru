/* Informational territorial inventory. Reads existing catalogs; never promotes a zone. */
(() => {
  'use strict';
  const PATHS = {
    catalog: 'data/phase2/catalog.json',
    spatial: 'data/phase2/spatial_observation_contracts_v0_1.json',
    layers: 'data/map_layers.json',
    remaining: 'data/phase2/w1_remaining_geometry_catalog.json'
  };
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
  const list = v => Array.isArray(v) ? v : [];
  const label = id => ({cashahuacra:'Cashahuacra', shingolay:'Shingolay',
    lambayeque_chancay_lambayeque_chongoyape:'Chancay–Lambayeque / Chongoyape',
    lambayeque_zana_oyotun:'Zaña / Oyotún'}[id] || String(id || '').replace(/_/g,' '));
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  function dataPath(value, extension = 'geojson') {
    if (typeof value !== 'string') return null;
    const path = value.replace(/^site\//,'');
    return path.startsWith('data/') && /^[\p{L}\p{N}_./-]+$/u.test(path) &&
      !path.split('/').includes('..') && path.endsWith('.'+extension) ? path : null;
  }
  function safeURL(value) {
    if (typeof value !== 'string') return null;
    try { const u = new URL(value); return ['https:','http:'].includes(u.protocol) ? u.href : null; }
    catch (_) { return null; }
  }
  function ensureCatalog(catalog) {
    if (!catalog || !Array.isArray(catalog.zones) || catalog.production_use !== false ||
        catalog.production_ready !== false || catalog.deployment_status !== 'RESEARCH_ONLY') {
      throw new Error('Catálogo Phase-2 ausente o incompatible con la vista informativa');
    }
    const ids = catalog.zones.map(z => z.candidate_id);
    if (ids.some(id => typeof id !== 'string' || !id) || new Set(ids).size !== ids.length) {
      throw new Error('Identificadores de catálogo ausentes o duplicados');
    }
  }
  function buildPlan(catalog, spatial = {}, maps = {}, remaining = {}) {
    ensureCatalog(catalog);
    const mapsOK = maps.production_use === false && maps.production_ready === false &&
      maps.operational_alerting_enabled === false && Array.isArray(maps.research_zones) &&
      Array.isArray(maps.technical_layers) && Array.isArray(maps.research_discovery_units);
    const spatialOK = spatial.production_use === false && spatial.production_ready === false &&
      spatial.operational_alerting_enabled === false && spatial.activation_gate === 'BLOCKED';
    const sourceById = new Map((mapsOK ? maps.research_zones : []).map(z => [z.candidate_id,z]));
    const extraById = new Map(list(remaining.layers).map(z => [z.candidate_id,z]));
    const blockedById = new Map(list(remaining.blocked).map(z => [z.candidate_id,z]));
    const groupId = (catalog.count_contract || {}).legacy_candidate_id;
    const candidates = catalog.zones.map(z => {
      const source = sourceById.get(z.candidate_id) || {};
      const extra = extraById.get(z.candidate_id) || {};
      const blocked = blockedById.get(z.candidate_id) || {};
      return {key:'candidate:'+z.candidate_id, kind:'candidate', candidateId:z.candidate_id,
        title:z.system_name || z.candidate_id, territory:[z.department,z.province_or_corridor].filter(Boolean).join(' · '),
        status:z.deployment_status, gate:z.activation_gate, contractStatus:z.contract_status,
        assets:z.asset_status || {}, blockers:list(z.blocking_items),
        sources:list((source.sources || {}).official_source_ids),
        contractPath:(source.sources || {}).contract_path || null,
        historicalGrouper:z.candidate_id === groupId,
        reason: extra.map_eligible_research_only === false ? extra.disclaimer || 'Geometría retenida para revisión; no habilitada para el mapa general.' : blocked.reason || '',
        layerKeys:[]};
    });
    const registeredCandidateCount=candidates.length;
    const discoveries=[];
    for (const d of mapsOK ? list(maps.research_discovery_units) : []) {
      const g=d.geometry||{};
      discoveries.push({key:'discovery:'+d.discovery_id,kind:'discovery',candidateId:d.discovery_id,
        title:d.system_name||d.discovery_id,territory:[d.department,d.territorial_reference].filter(Boolean).join(' · '),
        status:d.deployment_status,gate:d.activation_gate,contractStatus:d.contract_status,
        assets:{geometry:g.status},blockers:g.map_eligible?[]:['Geometría reproducible pendiente; no se dibuja aproximación'],
        sources:list(g.source_ids),contractPath:d.contract_path||null,historicalGrouper:/GROUPER/.test(String(d.entity_role||'')),
        reason:g.map_eligible?'':'Discovery registrada sin geometría reproducible; permanece en inventario sin contorno.',
        disclaimer:'Unidad discovery RESEARCH_ONLY; no altera los 18 candidatos Phase-2 ni habilita alertas.',layerKeys:[]});
    }
    const byId = new Map([...candidates,...discoveries].map(c => [c.candidateId,c]));
    const requests = [];
    const keys = new Set();
    const add = request => {
      if (keys.has(request.key)) throw new Error('Capa duplicada: '+request.key);
      keys.add(request.key); requests.push(request);
      if (byId.has(request.candidateId)) byId.get(request.candidateId).layerKeys.push(request.key);
    };
    for (const parent of spatialOK ? list(spatial.candidate_records) : []) {
      if (!byId.has(parent.candidate_id)) continue;
      for (const c of list(parent.subunit_contracts)) {
        if (c.contract_status !== 'RESEARCH_SAMPLING_ELIGIBLE' || c.candidate_id !== parent.candidate_id ||
            c.production_use !== false || c.production_ready !== false || c.operational_alerting_enabled !== false ||
            c.activation_gate !== 'BLOCKED' || c.counts_as_candidate_wide_geometry !== false) continue;
        const ref = c.geometry_ref || {};
        add({key:'phase2_subunit:'+parent.candidate_id+':'+c.subunit_id, kind:'monitored',
          candidateId:parent.candidate_id, title:label(c.subunit_id), path:dataPath(ref.path),
          selector:ref.feature_selector, expectedType:ref.geometry_type,
          status:c.deployment_status, representation:c.contract_scope,
          sources:[], confidence:ref.confidence || '', area:ref.declared_area_km2,
          disclaimer:'Contrato de muestreo de investigación. No completa la geometría del candidato padre ni habilita alertas.',
          sourceRef:PATHS.spatial, layerKeys:[]});
      }
    }
    if (mapsOK) {
      for (const t of maps.technical_layers) {
        if (t.map_eligible !== true || t.deployment_status !== 'TEST_ONLY' ||
            t.loaded_into_operational_calculation !== false || t.carries_alert_values !== false ||
            t.carries_risk_classification !== false) continue;
        add({key:'technical:'+t.layer_id,kind:'technical',title:t.title,path:dataPath(t.source_path),
          status:t.deployment_status,representation:t.representation,confidence:t.confidence,
          sources:list(t.source_ids),disclaimer:t.map_disclaimer || '',sourceRef:PATHS.layers, layerKeys:[]});
      }
      for (const r of maps.research_zones) {
        const g = r.geometry || {};
        if (!byId.has(r.candidate_id) || r.candidate_id === groupId || g.map_eligible !== true ||
            r.deployment_status !== 'RESEARCH_ONLY' || r.production_use !== false || r.alerting_enabled !== false) continue;
        const path = dataPath(g.source_path || g.path);
        const excludes = requests.filter(q => q.kind === 'monitored' && q.path === path).map(q => q.selector);
        add({key:'context:'+r.candidate_id,kind:'context',candidateId:r.candidate_id,
          title:r.system_name+' · geometrías documentadas',path,excludes,
          status:r.deployment_status,representation:g.representation,
          confidence:(r.confidence || {}).geometry,sources:list(g.source_ids),
          disclaimer:g.map_disclaimer || 'Geometría informativa: no es una delimitación de riesgo.',
          sourceRef:PATHS.layers,layerKeys:[]});
      }
    }
    if (mapsOK) {
      for (const c of list(maps.research_component_layers)) {
        if (!byId.has(c.candidate_id) || c.map_eligible !== true || c.deployment_status !== 'RESEARCH_ONLY' ||
            c.production_use !== false || c.production_ready !== false || c.operational_alerting_enabled !== false ||
            c.loaded_into_operational_calculation !== false || c.carries_alert_values !== false ||
            c.carries_risk_classification !== false || c.counts_as_complete_candidate_geometry !== false ||
            c.candidate_wide_sampling_ready !== false) continue;
        add({key:'context_component:'+c.layer_id,kind:'context',candidateId:c.candidate_id,
          title:c.title,path:dataPath(c.source_path || c.path),status:c.deployment_status,
          representation:c.representation,confidence:c.confidence,sources:list(c.source_ids),
          disclaimer:c.map_disclaimer || 'Capa componente RESEARCH_ONLY; no es una delimitación de riesgo.',
          sourceRef:PATHS.layers,layerKeys:[]});
      }
    }
    if (mapsOK) {
      for (const d of list(maps.research_discovery_units)) {
        const g=d.geometry||{};
        if (!byId.has(d.discovery_id) || g.map_eligible!==true || d.deployment_status!=='RESEARCH_ONLY' ||
            d.production_use!==false || d.production_ready!==false || d.operational_alerting_enabled!==false ||
            d.activation_gate!=='BLOCKED' || d.decision_thresholds!==null || d.hydraulic_factors!==null) continue;
        add({key:'discovery_context:'+d.discovery_id,kind:'context',candidateId:d.discovery_id,recordKey:'discovery:'+d.discovery_id,
          title:d.system_name+' · discovery',path:dataPath(g.source_path||g.path),status:d.deployment_status,
          representation:g.representation,confidence:'OFFICIAL_CONTEXT_ONLY',sources:list(g.source_ids),
          disclaimer:g.map_disclaimer||'Discovery RESEARCH_ONLY; no es riesgo ni alerta.',sourceRef:PATHS.layers,layerKeys:[]});
      }
    }
    for (const r of requests) r.layerKeys = [r.key];
    return {candidates,discoveries,requests,mapsOK,spatialOK,
      pilotIds:list((catalog.relationship_to_v08 || {}).operational_pilots),
      summary:{registeredCandidates:registeredCandidateCount,
        discoveryUnits:discoveries.length,
        discoveryWithGeometry:discoveries.filter(c=>c.layerKeys.length).length,
        monitoredSubunits:requests.filter(r => r.kind === 'monitored').length,
        technicalLayers:requests.filter(r => r.kind === 'technical').length,
        candidatesWithRelatedGeometry:candidates.filter(c => c.layerKeys.length).length,
        candidatesWithoutRelatedGeometry:candidates.filter(c => !c.layerKeys.length).length}};
  }
  function selectFeatures(documentJSON, request) {
    const features = documentJSON && documentJSON.type === 'FeatureCollection' ? list(documentJSON.features) : [documentJSON];
    let selected = features;
    if (request.kind === 'monitored') {
      const s = request.selector;
      if (!s || typeof s.property !== 'string' || s.value == null) throw new Error('Selector espacial ausente');
      selected = features.filter(f => f && f.properties && f.properties[s.property] === s.value);
      if (selected.length !== 1) throw new Error('El selector no resuelve una única unidad');
    } else if (request.excludes) {
      selected = features.filter(f => !request.excludes.some(s => s && f && f.properties && f.properties[s.property] === s.value));
    }
    if (!selected.length) throw new Error('No hay geometrías representables en este archivo');
    for (const f of selected) {
      if (!f || f.type !== 'Feature' || !f.geometry ||
          !['Polygon','MultiPolygon','LineString','MultiLineString','Point','MultiPoint'].includes(f.geometry.type) ||
          !Array.isArray(f.geometry.coordinates)) throw new Error('Geometría ausente o de tipo no admitido');
      if (request.kind === 'monitored' && !['Polygon','MultiPolygon'].includes(f.geometry.type)) throw new Error('El contrato de muestreo no contiene un área');
      if (request.expectedType && f.geometry.type !== request.expectedType) throw new Error('Tipo geométrico distinto al contrato');
      const p=f.properties || {};
      if (p.production_use === true || p.production_ready === true || p.loaded_into_operational_calculation === true ||
          p.carries_alert_values === true || p.carries_risk_classification === true) throw new Error('Flags incompatibles con la vista informativa');
    }
    return selected;
  }
  function featureName(feature, request) {
    const p = feature.properties || {};
    return p.name || p.title || p.unit_id || (p.sector ? p.sector + ' · ' + (p.ftr_key || '') : null) || p.feature_role || p.id || request.title;
  }
  function semanticLabel(feature, request) {
    const p = feature.properties || {};
    if (p.context_only === true || request.representation === 'DOCUMENT_VIEWER_EXTENTS') return 'Ámbito documental; NO es cuenca ni mancha de inundación';
    const role = String(p.hydrologic_role || p.feature_role || request.representation || '');
    if (/faja|margin|regulatory/i.test(role)) return 'Faja marginal / margen / corredor regulatorio; NO es cuenca';
    if (['LineString','MultiLineString'].includes(feature.geometry.type)) return 'Tramo o referencia lineal; NO delimita un área inundable';
    if (p.candidate_status === 'REVIEW_ONLY' || request.representation === 'MULTIPLE_DEM_CANDIDATE_POLYGONS') return 'Geometría candidata REVIEW_ONLY; no es una delimitación oficial definitiva';
    return 'Geometría informativa; no clasifica riesgo ni valida activación';
  }
  function sourceLink(path, text) {
    const p=dataPath(path,'json') || dataPath(path,'geojson');
    return p ? '<a href="'+esc(p)+'" target="_blank" rel="noopener noreferrer">'+esc(text)+'</a>' : '';
  }
  async function fetchJSON(path) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(),20000);
    try { const r=await fetch(path+'?t='+Date.now(),{cache:'no-store',signal:controller.signal});
      if (!r.ok) throw new Error(path+' HTTP '+r.status); return await r.json(); }
    finally {clearTimeout(timeout);}
  }
  const state = {map:null,group:null,layers:new Map(),features:new Map(),plan:null,
    records:[],selected:null,mode:'all',query:'',fitted:false,loading:false,errors:[],checkedAt:null};
  function styles() {
    const s=document.createElement('style'); s.textContent=`
      .ti-shell{display:grid;gap:12px}.ti-banner{background:#eef5f9;border-left:5px solid #164e73;padding:14px;line-height:1.5}
      .ti-grid{display:grid;grid-template-columns:340px 1fr;gap:14px}.ti-panel{background:white;border:1px solid var(--line,#d9e2ea);border-radius:12px;overflow:hidden}
      .ti-header{padding:12px 14px;border-bottom:1px solid var(--line,#d9e2ea)}.ti-header h2,.ti-header h3{margin:0 0 6px}
      .ti-tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.ti-tools input,.ti-tools select{max-width:100%;min-height:36px}
      #ti-list{max-height:700px;overflow:auto}.ti-row{display:block;width:100%;border:0;border-bottom:1px solid #e2e8ed;background:white;text-align:left;padding:12px;cursor:pointer;white-space:normal}
      .ti-row:hover,.ti-row[aria-current=true]{background:#edf6fc}.ti-row b{display:block;font-size:13px}.ti-row small{display:block;font-size:11px;color:#536776;line-height:1.4;margin-top:4px}
      #ti-map{height:520px}.ti-note{font-size:12px;line-height:1.5;color:#486173}.ti-status{background:#f3f6f8;padding:10px;font-size:12px;line-height:1.6}
      .ti-badge{display:inline-block;background:#edf1f4;color:#354c5d;border-radius:5px;padding:3px 6px;font-size:11px;margin:3px 4px 3px 0}
      .ti-detail{padding:14px;line-height:1.5}.ti-detail h3{margin:0 0 6px}.ti-detail dl{display:grid;grid-template-columns:130px 1fr;gap:6px;font-size:12px}.ti-detail dt{font-weight:bold}.ti-detail dd{margin:0;overflow-wrap:anywhere}
      .ti-feature-list{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.ti-feature-list button{font-size:11px;padding:5px 7px}
      .ti-error{color:#783f00;background:#fff1d8;padding:9px}.ti-legend{padding:10px;font-size:12px;line-height:1.5}.ti-legend span{margin-right:16px}
      .ti-popup{font-size:12px;line-height:1.45;max-width:290px}.ti-label{font-size:11px;font-weight:bold}
      @media(max-width:1000px){.ti-grid{grid-template-columns:1fr}#ti-list{max-height:300px}#ti-map{height:420px}}
    `;document.head.appendChild(s);
  }
  function setup() {
    const tabs=document.querySelector('.tabs'), first=document.querySelector('.section');
    if (!tabs || !first || document.getElementById('territorial-inventory')) return false;
    styles();
    const tab=document.createElement('div');tab.className='tab';tab.dataset.tab='territorial-inventory';tab.textContent='Mapa e inventario';tabs.prepend(tab);
    const section=document.createElement('section');section.id='territorial-inventory';section.className='section';
    section.innerHTML=`<div class="ti-shell"><div class="ti-banner"><b>Inventario territorial completo · IRFEN v0.8</b><br>
      Aquí aparecen los candidatos definidos, las subunidades de muestreo y las capas de los pilotos. Mostrar una geometría no exige que esté habilitada para NASA, pero sí una fuente cartográfica admisible.
      <br><b>RESEARCH / TEST MODE.</b> Las fajas, los tramos, los ámbitos documentales y las alternativas de cuenca se identifican por separado. No son mapas de riesgo ni alertas.</div>
      <div class="ti-tools"><button id="ti-refresh">Actualizar inventario</button><button id="ti-all">Encuadrar capas visibles</button><button id="ti-monitor">Ir al monitoreo NASA</button><span class="ti-note" id="ti-time"></span></div>
      <div id="ti-summary" class="ti-status" role="status">Cargando catálogos…</div>
      <div class="ti-grid"><div class="ti-panel"><div class="ti-header"><h3>Buscar zona o capa</h3><div class="ti-tools"><input id="ti-search" type="search" aria-label="Buscar candidato o capa" placeholder="Malanche, Huaycoloro, Catacaos…"><select id="ti-filter" aria-label="Filtrar inventario"><option value="all">Todo el inventario</option><option value="candidate">18 candidatos Phase-2</option><option value="discovery">Discovery norte-costera</option><option value="monitored">Subunidades de muestreo</option><option value="technical">Capas de los pilotos v0.8</option><option value="pending">Sin geometría representable</option></select></div><p class="ti-note">Seleccionar una ficha muestra sus fuentes y pendientes, aunque aún no tenga contorno.</p></div><div id="ti-list"></div></div>
      <div class="ti-panel"><div class="ti-header"><h3>Geometrías documentadas</h3><div class="ti-tools"><label><input type="checkbox" data-ti-layer="monitored" checked> Muestreo NASA</label><label><input type="checkbox" data-ti-layer="technical" checked> Capas de pilotos</label><label><input type="checkbox" data-ti-layer="context" checked> Investigación y contexto</label></div></div><div id="ti-map"></div>
      <div class="ti-legend"><span>Azul: capas de pilotos</span><span>Verde azulado: muestreo de investigación</span><span>Gris / violeta: contexto y alternativas</span><br>Los colores identifican tipos de capa, NO niveles de riesgo. No se crean marcadores para suplir geometrías faltantes.</div><div id="ti-map-status" class="ti-status"></div><div id="ti-detail" class="ti-detail">Selecciona una zona para ver sus características, fuentes y motivo de los pendientes.</div></div></div></div>`;
    first.before(section);
    function activate() {
      document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t===tab));
      document.querySelectorAll('.section').forEach(s=>s.classList.toggle('active',s===section));
      document.body.classList.add('v08-active');
      setTimeout(()=>{if(state.map)state.map.invalidateSize();},50);
    }
    tab.addEventListener('click',activate);activate();
    document.getElementById('ti-search').addEventListener('input',e=>{state.query=e.target.value;renderList();});
    document.getElementById('ti-filter').addEventListener('change',e=>{state.mode=e.target.value;renderList();});
    document.getElementById('ti-refresh').onclick=load;
    document.getElementById('ti-all').onclick=fitVisible;
    document.getElementById('ti-monitor').onclick=()=>{const t=document.querySelector('.tab[data-tab="v08monitor"]');if(t)t.click();};
    document.getElementById('ti-list').addEventListener('click',e=>{const b=e.target.closest('[data-ti-record]');if(b)selectRecord(b.dataset.tiRecord,true);});
    document.getElementById('ti-detail').addEventListener('click',e=>{const b=e.target.closest('[data-ti-feature]');if(b){const f=state.features.get(b.dataset.tiFeature);if(f&&state.map){state.map.fitBounds(f.layer.getBounds().pad(.12),{maxZoom:16});f.layer.openPopup();}}});
    const selectedSection = section;
    selectedSection.querySelectorAll('[data-ti-layer]').forEach(input=>input.addEventListener('change',applyVisibility));
    return true;
  }
  function categoryOn(kind) {const el=document.querySelector('[data-ti-layer="'+kind+'"]');return !!el&&el.checked;}
  function recordLayers(record) {return record.layerKeys.map(k=>state.layers.get(k)).filter(Boolean);}
  function renderList() {
    if (!state.plan) return;
    const q=state.query.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const rows=state.records.filter(r=>{
      if(state.mode==='pending' && (!['candidate','discovery'].includes(r.kind)||r.layerKeys.length))return false;
      if(!['all','pending'].includes(state.mode)&&r.kind!==state.mode)return false;
      return !q||[r.title,r.territory,r.candidateId,...list(r.sources)].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(q);
    });
    document.getElementById('ti-list').innerHTML=rows.map(r=>{
      const count=recordLayers(r).length;
      const status=count ? (r.kind==='candidate'?'Capas relacionadas disponibles; no implica cuenca completa':r.kind==='discovery'?'Geometría discovery oficial/contextual disponible; no es operativa':'Geometría disponible') : r.layerKeys.length?'Error al cargar geometría':'Sin delimitación representable';
      return '<button class="ti-row" data-ti-record="'+esc(r.key)+'" aria-current="'+String(state.selected===r.key)+'"><b>'+esc(r.title)+'</b><small>'+esc(r.territory||r.status||'')+'</small><small>'+esc(status)+'</small></button>';
    }).join('')||'<p class="ti-detail">Sin coincidencias. El filtro no elimina registros del catálogo.</p>';
  }
  function selectRecord(key,focus) {
    const r=state.records.find(r=>r.key===key);if(!r)return;
    state.selected=key;renderList();
    const layers=recordLayers(r);
    const featureEntries=[...state.features.entries()].filter(([,f])=>r.layerKeys.includes(f.requestKey));
    const status=layers.length?'Geometrías disponibles como información; no constituye validación operacional':r.layerKeys.length?'No se pudo cargar la geometría. Consulta el estado de las capas.':'Candidato definido, pero sin delimitación cartográfica representable. No se inventa un contorno ni una ubicación puntual.';
    const dl=(k,v)=>'<dt>'+esc(k)+'</dt><dd>'+esc(v??'No consta')+'</dd>';
    const assets=Object.entries(r.assets||{}).map(([k,v])=>k+': '+v).join(' · ');
    document.getElementById('ti-detail').innerHTML='<h3>'+esc(r.title)+'</h3><span class="ti-badge">'+esc(r.status||'TEST_ONLY')+'</span><p>'+esc(status)+'</p>'+
      (r.historicalGrouper?'<p><b>Agrupador histórico no activable.</b> Se visualizan sus unidades hijas por separado. No se dibuja una cuenca compuesta.</p>':'')+
      '<dl>'+dl('Territorio',r.territory)+dl('Estado / contrato',r.contractStatus||r.representation)+dl('Activation gate',r.gate||'No aplicable: capa informativa')+dl('Activos',assets||null)+dl('Fuentes',list(r.sources).join(' · ')||null)+dl('Confianza',r.confidence)+dl('Pendientes',list(r.blockers).join(' · ')||null)+'</dl>'+
      (r.reason?'<p class="ti-error">'+esc(r.reason)+'</p>':'')+(r.disclaimer?'<p class="ti-note">'+esc(r.disclaimer)+'</p>':'')+
      '<div>'+sourceLink(r.contractPath,'Ver contrato científico')+' '+sourceLink(r.path,'Ver GeoJSON fuente')+' '+sourceLink(r.sourceRef,'Ver catálogo de procedencia')+'</div>'+
      (featureEntries.length?'<p class="ti-note">Elementos cartográficos (pueden ser alternativas o contextos, no nuevas quebradas):</p><div class="ti-feature-list">'+featureEntries.map(([id,f])=>'<button data-ti-feature="'+esc(id)+'">'+esc(f.name)+'</button>').join('')+'</div>':'');
    if(focus&&layers.length&&state.map){
      for(const request of state.plan.requests.filter(x=>r.layerKeys.includes(x.key))){const input=document.querySelector('[data-ti-layer="'+request.kind+'"]');if(input)input.checked=true;}
      applyVisibility();state.map.invalidateSize();
      // Bounds only control the camera. This does NOT construct a composite polygon.
      const group=L.featureGroup(layers);state.map.fitBounds(group.getBounds().pad(.12),{maxZoom:15});
      if(layers.length===1)layers[0].openPopup();
    }
  }
  function applyVisibility(){
    if(!state.map||!state.group||!state.plan)return;
    for(const r of state.plan.requests){const layer=state.layers.get(r.key);if(!layer)continue;
      if(categoryOn(r.kind))state.group.addLayer(layer);else state.group.removeLayer(layer);}
  }
  function fitVisible(){
    if(!state.map||!state.plan)return;
    const visible=state.plan.requests.filter(r=>categoryOn(r.kind)).map(r=>state.layers.get(r.key)).filter(Boolean);
    if(visible.length){state.map.invalidateSize();state.map.fitBounds(L.featureGroup(visible).getBounds().pad(.1),{maxZoom:9});state.fitted=true;}
  }
  async function renderMap(){
    const p=state.plan; const docs=new Map(); const layers=new Map();const features=new Map();const errors=[];
    if(typeof L!=='undefined'&&!state.map){state.map=L.map('ti-map').setView([-9.3,-76.5],5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; OpenStreetMap contributors'}).addTo(state.map);}
    await Promise.all(p.requests.map(async request=>{
      try{
        if(typeof L==='undefined')throw new Error('Biblioteca cartográfica no disponible');
        if(!request.path)throw new Error('Ruta cartográfica ausente o no segura');
        if(!docs.has(request.path))docs.set(request.path,fetchJSON(request.path));
        const doc=await docs.get(request.path);const selected=selectFeatures(doc,request);
        const group=L.featureGroup();
        selected.forEach((feature,index)=>{
          const name=featureName(feature,request),semantic=semanticLabel(feature,request);
          const context=/documental|Faja|Tramo/.test(semantic),alternative=/REVIEW_ONLY/.test(semantic);
          const color=context?'#64748b':alternative?'#7c3aed':request.kind==='monitored'?'#0f766e':'#2563eb';
          const layer=L.geoJSON(feature,{style:{color,weight:2,fillColor:color,fillOpacity:context?0:.045,dashArray:'5 5'},
            pointToLayer:(_,latlng)=>L.circleMarker(latlng,{radius:4,color,fillOpacity:.1})});
          if(!layer.getBounds().isValid())throw new Error('Límites geográficos no válidos');
          const prop=feature.properties||{};
          const area=finite(prop.delineated_area_km2)?prop.delineated_area_km2:finite((prop.coverage||{}).delineated_area_km2)?prop.coverage.delineated_area_km2:request.area;
          const url=safeURL(prop.source_url || prop.source_page);
          layer.bindTooltip(esc(name),{permanent:request.kind==='monitored',className:'ti-label',direction:'auto'});
          layer.bindPopup('<div class="ti-popup"><b>'+esc(name)+'</b><p><b>'+esc(semantic)+'</b></p>'+esc(request.status)+'<br>'+esc(request.confidence||'')+
            (finite(area)?'<br>Área declarada: '+esc(area)+' km²':'')+'<p>'+esc(request.disclaimer)+'</p>'+sourceLink(request.path,'Geometría fuente')+
            (url?' · <a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Documento fuente</a>':'')+'<br>No genera puntuaciones ni alertas.</div>');
          layer.on('click',()=>selectRecord(request.recordKey||(request.candidateId?'candidate:'+request.candidateId:request.key),false));
          group.addLayer(layer);features.set(request.key+'#'+index,{layer,name,requestKey:request.key});
        });
        layers.set(request.key,group);
      }catch(error){errors.push(request.title+': '+String(error.message||error));
        for(const [id,f]of features)if(f.requestKey===request.key)features.delete(id);}
    }));
    const replacement=typeof L!=='undefined'?L.layerGroup():null;
    if(state.map&&replacement){replacement.addTo(state.map);if(state.group)state.map.removeLayer(state.group);state.group=replacement;}
    state.layers=layers;state.features=features;state.errors=errors;applyVisibility();
    document.getElementById('ti-map-status').innerHTML='<b>Grupos de capas esperados:</b> '+p.requests.length+' · <b>Cargados:</b> '+layers.size+' · <b>Elementos geométricos:</b> '+features.size+' · <b>Errores:</b> '+errors.length+
      (errors.length?'<details open><summary>Ver errores de carga</summary>'+errors.map(esc).join('<br>')+'</details>':'')+'<br>Los elementos geométricos no se cuentan como nuevas quebradas ni nuevos candidatos.';
    if(!state.fitted)fitVisible();
  }
  async function load(){
    if(state.loading)return;state.loading=true;const button=document.getElementById('ti-refresh');button.disabled=true;
    const time=document.getElementById('ti-time');time.textContent='Consultando catálogos…';
    try{
      const catalog=await fetchJSON(PATHS.catalog);
      const keys=['spatial','layers','remaining'];const results=await Promise.allSettled(keys.map(k=>fetchJSON(PATHS[k])));
      const data={};const failures=[];
      results.forEach((r,i)=>{data[keys[i]]=r.status==='fulfilled'?r.value:{};if(r.status!=='fulfilled')failures.push(PATHS[keys[i]]);});
      const plan=buildPlan(catalog,data.spatial,data.layers,data.remaining);
      if(!plan.mapsOK && !failures.includes(PATHS.layers))failures.push(PATHS.layers+' (contrato no válido)');
      if(!plan.spatialOK && !failures.includes(PATHS.spatial))failures.push(PATHS.spatial+' (contrato no válido)');
      state.plan=plan;state.records=[...plan.candidates,...plan.discoveries,...plan.requests.filter(r=>r.kind!=='context')];
      const s=plan.summary;
      document.getElementById('ti-summary').innerHTML='<b>'+s.registeredCandidates+' candidatos Phase-2 definidos</b> · '+s.discoveryUnits+' unidades discovery norte-costera ('+s.discoveryWithGeometry+' con geometría representable) · '+s.monitoredSubunits+' subunidades con contrato de muestreo · '+s.technicalLayers+' capas técnicas de '+plan.pilotIds.length+' pilotos v0.8.<br>'+
        s.candidatesWithRelatedGeometry+' candidatos tienen geometrías relacionadas representables; <b>'+s.candidatesWithoutRelatedGeometry+' permanecen en el listado sin contorno representable</b>. Las subdivisiones no aumentan el total de candidatos.'+
        '<br>El catálogo no autoriza sustituir geometrías faltantes por puntos aproximados. Una geometría parcial tampoco equivale a cuenca completa.'+
        (failures.length?'<p class="ti-error">Catálogos complementarios no cargados: '+failures.map(esc).join(', ')+'. Los conteos de capas pueden estar incompletos.</p>':'');
      await renderMap();renderList();if(state.selected)selectRecord(state.selected,false);
      state.checkedAt=new Date().toISOString();time.textContent='Consulta de pantalla: '+state.checkedAt+' · Catálogo: '+(catalog.generated_at||'sin fecha');
    }catch(error){time.textContent='No se pudo actualizar: '+String(error.message||error)+(state.checkedAt?'. Se conserva la vista anterior consultada '+state.checkedAt:'');}
    finally{state.loading=false;button.disabled=false;}
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={buildPlan,selectFeatures,semanticLabel,dataPath,safeURL,featureName};
  if(typeof document!=='undefined'&&setup()){load();setInterval(load,5*60*1000);}
})();