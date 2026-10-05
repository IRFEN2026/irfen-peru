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
  // Categorías semánticas: A cuencas · B quebradas/cauces · C colectores · D nodos + contextos.
  const CATEGORY_KIND = {CATCHMENT:'catchment', LOCAL_CHANNEL:'local_channel', COLLECTOR:'collector', NODE:'node',
    REGULATORY_FAJA_MARGINAL:'faja', ENGINEERED_OR_CRITICAL_REACH_CONTEXT:'works', DOCUMENT_CONTEXT:'document'};
  const FORBIDDEN_TRUE = ['loaded_into_operational_calculation','carries_alert_values','carries_risk_classification'];
  const INVENTORY_KINDS = new Set(['REGISTERED_LOCAL_UNIT','COLLECTOR','NODE','REPOSITORY_GEOMETRY_WITHHELD']);
  // Display-only shortcuts to exact, already map-eligible official parent-basin
  // geometries. They never create geometry or change scientific state.
  const RECENT_ADVANCES = Object.freeze({
    ica_pisco_san_andres: Object.freeze({
      title:'Pisco · Cuenca oficial ANA · UH 13752',
      path:'data/phase2/geometries/ica_pisco_san_andres_pisco_basin_context.geojson',
      note:'Cuenca Pisco disponible como contexto oficial. Quitasol y Paracas siguen sin geometría ni outlet resueltos.'
    }),
    arequipa_acari_san_agustin: Object.freeze({
      title:'Acarí · Cuenca oficial ANA · UH 13718',
      path:'data/phase2/geometries/arequipa_acari_san_agustin_acari_basin_context.geojson',
      note:'Cuenca Acarí disponible como contexto oficial. San Agustín sigue como componente local con identidad hidrológica no resuelta y sin routing al Río Acarí.'
    }),
    ica_palpa_changuillo: Object.freeze({
      title:'Grande · Cuenca oficial ANA · UH 1372',
      path:'data/phase2/geometries/ica_palpa_changuillo_grande_basin_context.geojson',
      note:'Cuenca Grande disponible como contexto oficial para Palpa-Changuillo. Yauca del Rosario, Curis y Macchanga permanecen fuera de este binding y sin padre hidrográfico asignado.'
    })
  });
  function semanticsOf(maps) {
    const s = maps && maps.map_semantics;
    if (!s || typeof s.version !== 'string' || !s.version.startsWith('irfen-map-semantic-layers-') ||
        !Array.isArray(s.features) || !Array.isArray(s.entities) || !s.categories || !s.node_semantics) return null;
    const g = s.guardrails || {};
    if (g.risk_colors_forbidden !== true || g.categories_never_mixed_in_one_map_layer !== true ||
        g.unresolved_nodes_not_drawn !== true || g.approximate_points_forbidden !== true ||
        g.parent_geometry_by_child_union_forbidden !== true) return null;
    if ((s.node_semantics.UNRESOLVED || {}).drawable !== false) return null;
    return s;
  }
  const guardedLayer = t => t && t.loaded_into_operational_calculation === false &&
    t.carries_alert_values === false && t.carries_risk_classification === false;
  function ownerEligibility(maps, byId) {
    const find = (rows, key, id) => list(rows).find(r => r && r[key] === id);
    return f => {
      if (f.owner_collection === 'technical_layers') {
        const t = find(maps.technical_layers, 'layer_id', f.owner_id);
        return !!t && t.map_eligible === true && ['TEST_ONLY','RESEARCH_ONLY'].includes(t.deployment_status) && guardedLayer(t);
      }
      if (f.owner_collection === 'research_zones') {
        const z = find(maps.research_zones, 'candidate_id', f.owner_id); const g = (z || {}).geometry || {};
        if (!z || !byId.has(z.candidate_id) || g.map_eligible !== true) return false;
        return z.deployment_status === 'RESEARCH_ONLY' && z.production_use === false && z.alerting_enabled === false;
      }
      if (f.owner_collection === 'research_component_layers') {
        const c = find(maps.research_component_layers, 'layer_id', f.owner_id);
        return !!c && byId.has(c.candidate_id) && c.map_eligible === true && c.deployment_status === 'RESEARCH_ONLY' &&
          guardedLayer(c) && c.counts_as_complete_candidate_geometry === false && c.candidate_wide_sampling_ready === false;
      }
      if (f.owner_collection === 'research_discovery_units') {
        const d = find(maps.research_discovery_units, 'discovery_id', f.owner_id); const g = (d || {}).geometry || {};
        if (!d || !byId.has(d.discovery_id) || g.map_eligible !== true) return false;
        return d.deployment_status === 'RESEARCH_ONLY' && d.production_use === false && d.production_ready === false &&
          d.operational_alerting_enabled === false && d.activation_gate === 'BLOCKED' && d.decision_thresholds === null && d.hydraulic_factors === null;
      }
      if (f.owner_collection === 'spatial_sampling_subunits') return byId.has(f.parent_id);
      return false;
    };
  }
  function ownerTitle(maps, f) {
    const pick = (rows, key, field) => ((list(rows).find(r => r && r[key] === f.owner_id)) || {})[field];
    return ({technical_layers: () => pick(maps.technical_layers,'layer_id','title'),
      research_zones: () => pick(maps.research_zones,'candidate_id','system_name'),
      research_component_layers: () => pick(maps.research_component_layers,'layer_id','title'),
      research_discovery_units: () => pick(maps.research_discovery_units,'discovery_id','system_name'),
      spatial_sampling_subunits: () => label(f.owner_id)}[f.owner_collection] || (() => f.owner_id))() || f.owner_id;
  }
  const categoryLabel = (sem, category) => ((sem.categories || {})[category] || {}).label || category;
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
          category:'CATCHMENT', listKind:'monitored', status:c.deployment_status, representation:c.contract_scope,
          sources:[], confidence:ref.confidence || '', area:ref.declared_area_km2,
          disclaimer:'Contrato de muestreo de investigación. No completa la geometría del candidato padre ni habilita alertas.',
          sourceRef:PATHS.spatial, layerKeys:[]});
      }
    }
    const sem = mapsOK ? semanticsOf(maps) : null;
    const inventory = [];
    if (sem) {
      const ownerOK = ownerEligibility(maps, byId);
      const monitoredKeys = new Set(requests.filter(q => q.kind === 'monitored')
        .map(q => q.path + '|' + (q.selector || {}).value));
      const groups = new Map();
      for (const f of sem.features) {
        if (!ownerOK(f) || f.map_eligible !== true || !CATEGORY_KIND[f.map_category] ||
            FORBIDDEN_TRUE.some(k => f[k] === true) || f.production_use !== false ||
            f.production_ready !== false || f.operational_alerting_enabled !== false ||
            f.activation_gate !== 'BLOCKED' || f.decision_thresholds !== null || f.hydraulic_factors !== null) continue;
        if (f.map_category === 'NODE') {
          const ns = (sem.node_semantics || {})[f.node_semantics];
          if (!ns || ns.drawable !== true || f.node_semantics === 'UNRESOLVED') continue;
        }
        const sel = f.selector || {};
        // Una subunidad ya dibujada como muestreo NASA no se duplica como contexto.
        if (f.sampling_contract && (monitoredKeys.has(f.path + '|' + sel.unit_id) || monitoredKeys.has(f.path + '|' + sel.value))) continue;
        const kind = CATEGORY_KIND[f.map_category];
        const gkey = kind + ':' + f.owner_collection + ':' + f.owner_id;
        if (!groups.has(gkey)) {
          const recordId = ['research_zones','research_component_layers','spatial_sampling_subunits'].includes(f.owner_collection) ?
            f.parent_id : f.owner_collection === 'research_discovery_units' ? f.owner_id : null;
          groups.set(gkey, {key:gkey, kind, category:f.map_category,
            listKind: f.owner_collection === 'technical_layers' ? 'technical' : 'context',
            candidateId: recordId && byId.has(recordId) ? recordId : undefined,
            recordKey: recordId && byId.has(recordId) ? byId.get(recordId).key : undefined,
            title: ownerTitle(maps, f) + ' · ' + categoryLabel(sem, f.map_category),
            path: dataPath(f.path), allFeatures: false, featureIndices: [], featureMeta: [],
            allowedTypes: list((sem.categories[f.map_category] || {}).allowed_geometry_types),
            status: f.deployment_status, representation: f.semantic_role, confidence: f.confidence,
            sources: list(f.source_ids), disclaimer: f.map_disclaimer, sourceRef: PATHS.layers, layerKeys: []});
        }
        const g = groups.get(gkey);
        if (sel.all_features === true) g.allFeatures = true;
        else if (Number.isInteger(sel.feature_index)) g.featureIndices.push(sel.feature_index);
        else continue;
        g.featureMeta.push({entityId:f.entity_id, parentId:f.parent_id, semanticRole:f.semantic_role,
          nodeSemantics:f.node_semantics, exactConfluence:f.may_be_labeled_exact_confluence === true,
          confidence:f.confidence, name:f.name, sources:list(f.source_ids), sourceAttribution:f.source_attribution});
        g.sources = [...new Set([...g.sources, ...list(f.source_ids)])];
      }
      for (const g of groups.values()) add(g);
      for (const e of sem.entities) {
        if (e.map_eligible !== false || !INVENTORY_KINDS.has(e.record_kind)) continue;
        inventory.push({key:'withheld:'+e.entity, kind:'withheld', candidateId:e.entity,
          title:e.entity, territory:[e.type, e.parent ? 'padre: ' + e.parent : null].filter(Boolean).join(' · '),
          status:'RESEARCH_ONLY', gate:'BLOCKED', contractStatus:e.record_kind, assets:{tipo:e.type},
          blockers:[e.reason_if_withheld], sources:[e.source].filter(Boolean), contractPath:null,
          confidence:e.confidence, nodeSemantics:e.node_semantics,
          reason:'Registrado en inventario sin dibujo: ' + e.reason_if_withheld,
          disclaimer:'No se crea contorno, línea ni punto aproximado para esta entidad.', layerKeys:[]});
      }
    }
    for (const r of requests) r.layerKeys = [r.key];
    // Only surface a recent advance when the exact approved parent-basin file
    // exists in the guarded semantic catalog as a CATCHMENT request.
    for (const c of candidates) {
      const meta=RECENT_ADVANCES[c.candidateId];
      if (!meta) continue;
      const request=requests.find(r=>r.candidateId===c.candidateId && r.category==='CATCHMENT' && r.path===meta.path);
      if (request) c.recentAdvance={...meta,layerKey:request.key};
    }
    const ss = sem ? sem.summary : {};
    return {candidates,discoveries,inventory,requests,mapsOK,spatialOK,semanticsOK:!!sem,
      categories: sem ? sem.categories : {}, nodeSemantics: sem ? sem.node_semantics : {},
      pilotIds:list((catalog.relationship_to_v08 || {}).operational_pilots),
      summary:{registeredCandidates:registeredCandidateCount,
        discoveryUnits:discoveries.length,
        discoveryWithGeometry:discoveries.filter(c=>c.layerKeys.length).length,
        monitoredSubunits:requests.filter(r => r.kind === 'monitored').length,
        technicalLayers:new Set(requests.filter(r => r.listKind === 'technical').map(r => r.key.split(':').slice(1).join(':'))).size,
        candidatesWithRelatedGeometry:candidates.filter(c => c.layerKeys.length).length,
        candidatesWithoutRelatedGeometry:candidates.filter(c => !c.layerKeys.length).length,
        inventoryWithheld:inventory.length,
        recentIntegrated:candidates.filter(c=>c.recentAdvance).length,
        semantic:ss}};
  }
  function selectFeatures(documentJSON, request) {
    const features = documentJSON && documentJSON.type === 'FeatureCollection' ? list(documentJSON.features) : [documentJSON];
    let selected = features;
    if (request.kind === 'monitored') {
      const s = request.selector;
      if (!s || typeof s.property !== 'string' || s.value == null) throw new Error('Selector espacial ausente');
      selected = features.filter(f => f && f.properties && f.properties[s.property] === s.value);
      if (selected.length !== 1) throw new Error('El selector no resuelve una única unidad');
    } else if (Array.isArray(request.featureIndices) && !request.allFeatures) {
      // Selección por índice sobre un archivo fijado por SHA-256 en el catálogo.
      selected = request.featureIndices.map(i => {
        if (!Number.isInteger(i) || i < 0 || i >= features.length) throw new Error('Índice de feature fuera del archivo');
        return features[i];
      });
    }
    if (!selected.length) throw new Error('No hay geometrías representables en este archivo');
    for (const f of selected) {
      if (!f || f.type !== 'Feature' || !f.geometry ||
          !['Polygon','MultiPolygon','LineString','MultiLineString','Point','MultiPoint'].includes(f.geometry.type) ||
          !Array.isArray(f.geometry.coordinates)) throw new Error('Geometría ausente o de tipo no admitido');
      if (request.kind === 'monitored' && !['Polygon','MultiPolygon'].includes(f.geometry.type)) throw new Error('El contrato de muestreo no contiene un área');
      if (request.expectedType && f.geometry.type !== request.expectedType) throw new Error('Tipo geométrico distinto al contrato');
      if (Array.isArray(request.allowedTypes) && request.allowedTypes.length && !request.allowedTypes.includes(f.geometry.type))
        throw new Error('Tipo geométrico incompatible con la categoría '+request.category);
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
  const NODE_LABEL = {
    EXACT_OFFICIAL:'Confluencia oficial exacta',
    REPRODUCIBLE_DERIVED:'Nodo derivado reproducible; NO es confluencia oficial confirmada',
    MONITORING_ANCHOR:'Ancla de monitoreo; NO es outlet ni confluencia',
    NEAR_CONFLUENCE:'Próximo a confluencia; NO es la confluencia',
    UNRESOLVED:'Confluencia/outlet no resuelto; no se dibuja'};
  function semanticLabel(feature, request, meta = {}) {
    const p = feature.properties || {};
    switch (request.category) {
      case 'CATCHMENT':
        if (request.kind === 'monitored') return 'Cuenca / subunidad de muestreo de investigación; no completa el candidato padre ni es mancha de inundación';
        if (/CANDIDATE/.test(String(meta.semanticRole || '')) || p.candidate_status === 'REVIEW_ONLY')
          return 'Cuenca candidata REVIEW_ONLY; no es una delimitación oficial definitiva ni mancha de inundación';
        return 'Cuenca / subcuenca (contexto hidrológico); no es mancha de inundación, riesgo ni alerta';
      case 'LOCAL_CHANNEL': return 'Quebrada / cauce local; NO es cuenca, outlet, confluencia ni colector';
      case 'COLLECTOR': return 'Río colector; la activación de un tributario NO implica respuesta del colector';
      case 'NODE': return NODE_LABEL[meta.nodeSemantics] || 'Nodo sin semántica declarada';
      case 'REGULATORY_FAJA_MARGINAL': return 'Faja marginal / margen / corredor regulatorio; NO es cuenca, cauce, footprint ni extensión de inundación';
      case 'ENGINEERED_OR_CRITICAL_REACH_CONTEXT': return 'Obra / tramo crítico; NO es capacidad hidráulica histórica ni evento; NO delimita un área inundable';
      case 'DOCUMENT_CONTEXT': return 'Ámbito documental; NO es cuenca ni mancha de inundación';
      default: return 'Geometría sin categoría semántica; no se interpreta';
    }
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
      .ti-recent{background:#f7fafc;border:1px solid #d9e2ea;border-radius:10px;padding:11px 12px;display:grid;gap:8px}.ti-recent-actions{display:flex;gap:7px;flex-wrap:wrap}.ti-recent-actions button{font-size:12px;padding:7px 9px;background:#fff}.ti-recent-note{font-size:11px;color:#536776;line-height:1.45}
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
      <br><b>RESEARCH / TEST MODE.</b> Cuencas, quebradas/cauces locales, ríos colectores y nodos se dibujan en capas separadas; las fajas marginales, obras/tramos críticos y ámbitos documentales se identifican aparte. No son mapas de riesgo ni alertas.</div>
      <div class="ti-tools"><button id="ti-refresh">Actualizar inventario</button><button id="ti-all">Encuadrar capas visibles</button><button id="ti-monitor">Ir al monitoreo NASA</button><span class="ti-note" id="ti-time"></span></div>
      <div id="ti-summary" class="ti-status" role="status">Cargando catálogos…</div>
      <div class="ti-recent" id="ti-recent"><div><b>Avances recientes integrados</b> · geometrías oficiales ANA ya disponibles como contexto de investigación.</div><div class="ti-recent-actions"><button type="button" data-ti-recent="ica_pisco_san_andres">Pisco · UH 13752</button><button type="button" data-ti-recent="arequipa_acari_san_agustin">Acarí · UH 13718</button><button type="button" data-ti-recent="ica_palpa_changuillo">Grande · UH 1372</button></div><div class="ti-recent-note">Seleccionar una cuenca enfoca únicamente su geometría oficial integrada. No representa riesgo, inundación, activación ni alerta.</div></div>
      <div class="ti-grid"><div class="ti-panel"><div class="ti-header"><h3>Buscar zona o capa</h3><div class="ti-tools"><input id="ti-search" type="search" aria-label="Buscar candidato o capa" placeholder="Malanche, Huaycoloro, Catacaos…"><select id="ti-filter" aria-label="Filtrar inventario"><option value="all">Todo el inventario</option><option value="recent">Avances recientes</option><option value="candidate">Candidatos Phase-2</option><option value="discovery">Discovery norte-costera</option><option value="monitored">Subunidades de muestreo</option><option value="technical">Capas de los pilotos v0.8</option><option value="withheld">Retenidas: colectores, nodos y unidades sin geometría</option><option value="pending">Sin geometría representable</option></select></div><p class="ti-note">Seleccionar una ficha muestra sus fuentes y pendientes, aunque aún no tenga contorno.</p></div><div id="ti-list"></div></div>
      <div class="ti-panel"><div class="ti-header"><h3>Geometrías documentadas</h3><div class="ti-tools" id="ti-layer-toggles"><label><input type="checkbox" data-ti-layer="monitored" checked> Muestreo NASA</label><label><input type="checkbox" data-ti-layer="catchment" checked> A · Cuencas / subcuencas</label><label><input type="checkbox" data-ti-layer="local_channel" checked> B · Quebradas / cauces locales</label><label><input type="checkbox" data-ti-layer="collector" checked> C · Ríos colectores</label><label><input type="checkbox" data-ti-layer="node" checked> D · Outlets / confluencias / nodos</label><label><input type="checkbox" data-ti-layer="faja" checked> Fajas marginales</label><label><input type="checkbox" data-ti-layer="works" checked> Obras / tramos críticos</label><label><input type="checkbox" data-ti-layer="document" checked> Ámbitos documentales</label></div></div><div id="ti-map"></div>
      <div class="ti-legend" id="ti-legend">Los colores identifican tipos de entidad, NO niveles de riesgo. No se crean marcadores para suplir geometrías faltantes.</div><div id="ti-map-status" class="ti-status"></div><div id="ti-detail" class="ti-detail">Selecciona una zona para ver sus características, fuentes y motivo de los pendientes.</div></div></div></div>`;
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
    document.getElementById('ti-recent').addEventListener('click',e=>{const b=e.target.closest('[data-ti-recent]');if(b)focusRecentAdvance(b.dataset.tiRecent);});
    document.getElementById('ti-detail').addEventListener('click',e=>{const b=e.target.closest('[data-ti-feature]');if(b){const f=state.features.get(b.dataset.tiFeature);if(f&&state.map){state.map.fitBounds(f.layer.getBounds().pad(.12),{maxZoom:16});f.layer.openPopup();}}});
    const selectedSection = section;
    selectedSection.querySelectorAll('[data-ti-layer]').forEach(input=>input.addEventListener('change',applyVisibility));
    return true;
  }
  function categoryOn(kind) {const el=document.querySelector('[data-ti-layer="'+kind+'"]');return !!el&&el.checked;}
  function recordLayers(record) {return record.layerKeys.map(k=>state.layers.get(k)).filter(Boolean);}
  function focusRecentAdvance(candidateId) {
    const r=state.records.find(x=>x.candidateId===candidateId && x.recentAdvance);
    if(!r)return;
    selectRecord(r.key,false);
    const request=state.plan.requests.find(x=>x.key===r.recentAdvance.layerKey);
    const layer=state.layers.get(r.recentAdvance.layerKey);
    if(!request||!layer||!state.map)return;
    const input=document.querySelector('[data-ti-layer="'+request.kind+'"]');if(input)input.checked=true;
    applyVisibility();state.map.invalidateSize();
    state.map.fitBounds(layer.getBounds().pad(.12),{maxZoom:10});
    layer.eachLayer(x=>{if(typeof x.openPopup==='function')x.openPopup();});
  }
  function renderList() {
    if (!state.plan) return;
    const q=state.query.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
    const rows=state.records.filter(r=>{
      if(state.mode==='pending' && (!['candidate','discovery'].includes(r.kind)||r.layerKeys.length))return false;
      if(state.mode==='recent' && !r.recentAdvance)return false;
      if(!['all','pending','recent'].includes(state.mode)&&(r.listKind||r.kind)!==state.mode)return false;
      return !q||[r.title,r.territory,r.candidateId,...list(r.sources)].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(q);
    });
    document.getElementById('ti-list').innerHTML=rows.map(r=>{
      const count=recordLayers(r).length;
      const status=r.kind==='withheld'?'Retenida: inventario sin dibujo':count ? (r.kind==='candidate'?'Capas relacionadas disponibles; no implica cuenca completa':r.kind==='discovery'?'Geometría discovery oficial/contextual disponible; no es operativa':'Geometría disponible') : r.layerKeys.length?'Error al cargar geometría':'Sin delimitación representable';
      return '<button class="ti-row" data-ti-record="'+esc(r.key)+'" aria-current="'+String(state.selected===r.key)+'"><b>'+esc(r.title)+'</b><small>'+esc(r.territory||r.status||'')+'</small>'+(r.recentAdvance?'<small><b>Avance integrado · cuenca oficial ANA</b></small>':'')+'<small>'+esc(status)+'</small></button>';
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
      (r.recentAdvance?'<p class="ti-note"><b>'+esc(r.recentAdvance.title)+'</b><br>'+esc(r.recentAdvance.note)+'<br><b>Estado:</b> RESEARCH_ONLY / BLOCKED. No representa riesgo, inundación ni alerta.</p>':'')+
      (r.historicalGrouper?'<p><b>Agrupador histórico no activable.</b> Se visualizan sus unidades hijas por separado. No se dibuja una cuenca compuesta.</p>':'')+
      '<dl>'+dl('Territorio',r.territory)+dl('Estado / contrato',r.contractStatus||r.representation)+dl('Activation gate',r.gate||'No aplicable: capa informativa')+dl('Activos',assets||null)+dl('Fuentes',list(r.sources).join(' · ')||null)+dl('Confianza',r.confidence)+(r.nodeSemantics?dl('Semántica de nodo',r.nodeSemantics):'')+dl('Pendientes',list(r.blockers).join(' · ')||null)+'</dl>'+
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
  const HEX=/^#[0-9a-f]{6}$/i;
  function categoryStyle(categories,request){
    if(request.kind==='monitored')return {color:'#0f766e',weight:2.5,fillColor:'#5eead4',fillOpacity:.06};
    const s=((categories||{})[request.category]||{}).style||{};
    const color=HEX.test(s.color||'')?s.color:'#64748b';
    return {color,weight:finite(s.weight)?s.weight:2,fillColor:HEX.test(s.fillColor||'')?s.fillColor:color,
      fillOpacity:finite(s.fillOpacity)?s.fillOpacity:0,dashArray:typeof s.dashArray==='string'?s.dashArray:null,radius:finite(s.radius)?s.radius:undefined};
  }
  function renderLegend(plan){
    const el=document.getElementById('ti-legend');if(!el)return;
    const items=Object.entries(plan.categories||{}).map(([id,c])=>{const s=categoryStyle(plan.categories,{category:id});
      return '<span><svg width="22" height="10" aria-hidden="true"><line x1="1" y1="5" x2="21" y2="5" stroke="'+esc(s.color)+'" stroke-width="3"'+(s.dashArray?' stroke-dasharray="'+esc(s.dashArray)+'"':'')+'/></svg> '+esc((c.group&&c.group!=='CONTEXT'?c.group+' · ':'')+c.label)+'</span>';});
    el.innerHTML=items.join('')+'<br>Los colores identifican tipos de entidad, NO niveles de riesgo. No se crean marcadores para suplir geometrías faltantes. Un nodo UNRESOLVED no se dibuja; sólo un nodo EXACT_OFFICIAL se rotula como confluencia exacta.';
  }
  async function renderMap(){
    const p=state.plan; const docs=new Map(); const layers=new Map();const features=new Map();const errors=[];
    if(typeof L!=='undefined'&&!state.map){state.map=L.map('ti-map').setView([-9.3,-76.5],5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; OpenStreetMap contributors'}).addTo(state.map);
      if(window.IRFENWeatherLayers && typeof window.IRFENWeatherLayers.attach==='function') window.IRFENWeatherLayers.attach(state.map,'Mapa e inventario'); else window.dispatchEvent(new CustomEvent('irfen:map-ready',{detail:{map:state.map,label:'Mapa e inventario'}}));}
    await Promise.all(p.requests.map(async request=>{
      try{
        if(typeof L==='undefined')throw new Error('Biblioteca cartográfica no disponible');
        if(!request.path)throw new Error('Ruta cartográfica ausente o no segura');
        if(!docs.has(request.path))docs.set(request.path,fetchJSON(request.path));
        const doc=await docs.get(request.path);const selected=selectFeatures(doc,request);
        const group=L.featureGroup();
        const style=categoryStyle(p.categories,request);
        selected.forEach((feature,index)=>{
          const meta=(request.featureMeta||[])[index]||{};
          const name=meta.name||featureName(feature,request),semantic=semanticLabel(feature,request,meta);
          const layer=L.geoJSON(feature,{style,
            pointToLayer:(_,latlng)=>L.circleMarker(latlng,{radius:style.radius||5,color:style.color,weight:style.weight,
              fillColor:style.fillColor||style.color,fillOpacity:style.fillOpacity??.9})});
          if(!layer.getBounds().isValid())throw new Error('Límites geográficos no válidos');
          const prop=feature.properties||{};
          const area=finite(prop.delineated_area_km2)?prop.delineated_area_km2:finite((prop.coverage||{}).delineated_area_km2)?prop.coverage.delineated_area_km2:request.area;
          const url=safeURL(prop.source_url || prop.source_page);
          layer.bindTooltip(esc(name)+(request.category==='NODE'?' · '+esc(meta.nodeSemantics||''):''),{permanent:request.kind==='monitored',className:'ti-label',direction:'auto'});
          // Confianza y fuentes de ESTA geometría; las del grupo no se transfieren.
          const ownConfidence=meta.confidence||request.confidence||'';
          const ownSources=Array.isArray(meta.sources)?meta.sources:[];
          layer.bindPopup('<div class="ti-popup"><b>'+esc(name)+'</b><p><b>'+esc(semantic)+'</b></p>'+esc(request.status)+'<br>'+esc(ownConfidence)+
            (ownSources.length?'<br>Fuentes: '+esc(ownSources.join(' · '))+(meta.sourceAttribution==='LAYER_LEVEL_NOT_ATTRIBUTABLE_TO_FEATURE'?' (nivel capa; no atribuibles a esta geometría)':''):'')+
            (finite(area)?'<br>Área declarada: '+esc(area)+' km²':'')+'<p>'+esc(request.disclaimer)+'</p>'+sourceLink(request.path,'Geometría fuente')+
            (url?' · <a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Documento fuente</a>':'')+'<br>No genera puntuaciones ni alertas.</div>');
          layer.on('click',()=>selectRecord(request.recordKey||(request.candidateId&&state.records.some(r=>r.key==='candidate:'+request.candidateId)?'candidate:'+request.candidateId:request.key),false));
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
  function semanticSummary(ss,ok){
    if(!ok)return '<p class="ti-error">Bloque semántico del catálogo ausente o no válido: no se dibujan capas de investigación.</p>';
    const n=k=>esc(ss[k]??0);
    return '<br><b>Capas semánticas:</b> '+n('features_catchment_map_eligible')+' cuencas/subcuencas · '+n('features_local_channel_map_eligible')+' tramos de quebrada/cauce local · '+
      n('features_collector_map_eligible')+' ejes de colector ('+n('collectors_registered')+' colectores registrados, '+n('collectors_map_eligible')+' con eje reproducible) · '+
      n('features_node_map_eligible')+' nodos dibujables ('+n('nodes_unresolved')+' UNRESOLVED sin dibujo) · '+n('features_regulatory_faja_marginal_map_eligible')+' elementos de faja marginal · '+
      n('features_engineered_or_critical_reach_context_map_eligible')+' obras/tramos críticos · '+n('features_document_context_map_eligible')+' ámbitos documentales.<br>'+
      '<b>'+n('entities_withheld')+' entidades</b> permanecen en inventario sin dibujo por falta de geometría reproducible admisible. Conectividad hidrológica ≠ activación del tributario ≠ respuesta del colector.';
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
      state.plan=plan;state.records=[...plan.candidates,...plan.discoveries,...plan.inventory,...plan.requests.filter(r=>['technical','monitored'].includes(r.listKind))];
      renderLegend(plan);
      const s=plan.summary;
      document.getElementById('ti-summary').innerHTML='<b>'+s.registeredCandidates+' candidatos Phase-2 definidos</b> · '+s.discoveryUnits+' unidades discovery norte-costera ('+s.discoveryWithGeometry+' con geometría representable) · '+s.monitoredSubunits+' subunidades con contrato de muestreo · '+s.technicalLayers+' capas técnicas de '+plan.pilotIds.length+' pilotos v0.8.<br>'+
        '<b>'+s.recentIntegrated+' avances recientes</b> tienen una cuenca oficial ANA integrada y representable como contexto de investigación.<br>'+
        s.candidatesWithRelatedGeometry+' candidatos tienen geometrías relacionadas representables; <b>'+s.candidatesWithoutRelatedGeometry+' permanecen en el listado sin contorno representable</b>. Las subdivisiones no aumentan el total de candidatos.'+
        '<br>El catálogo no autoriza sustituir geometrías faltantes por puntos aproximados. Una geometría parcial tampoco equivale a cuenca completa.'+
        semanticSummary(s.semantic,plan.semanticsOK)+
        (failures.length?'<p class="ti-error">Catálogos complementarios no cargados: '+failures.map(esc).join(', ')+'. Los conteos de capas pueden estar incompletos.</p>':'');
      await renderMap();renderList();if(state.selected)selectRecord(state.selected,false);
      state.checkedAt=new Date().toISOString();time.textContent='Consulta de pantalla: '+state.checkedAt+' · Catálogo: '+(catalog.generated_at||'sin fecha');
    }catch(error){time.textContent='No se pudo actualizar: '+String(error.message||error)+(state.checkedAt?'. Se conserva la vista anterior consultada '+state.checkedAt:'');}
    finally{state.loading=false;button.disabled=false;}
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={buildPlan,selectFeatures,semanticLabel,dataPath,safeURL,featureName};
  if(typeof document!=='undefined'&&setup()){load();setInterval(load,5*60*1000);}
})();
