(() => {
  const safeJson=async url=>{try{const r=await fetch(`${url}?t=${Date.now()}`);return r.ok?await r.json():null;}catch(_){return null;}};
  const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={geometry:'Geometría',exposure:'Exposición',historical_events:'Eventos',observations:'Observación',forecast:'Forecast',hydraulic_context:'Contexto hidráulico'};
  const badge=(text,kind='exp')=>{const m={exp:['#e9f2ff','#194f82'],ok:['#e8f5ed','#246b3b'],warn:['#fff4dd','#795000'],bad:['#fdeaea','#8a2530']}[kind]||['#eee','#333'];return `<span style="display:inline-block;padding:4px 8px;border-radius:999px;background:${m[0]};color:${m[1]};font-size:11px;font-weight:700">${esc(text)}</span>`;};

  function ensureUI(){
    if(document.getElementById('expansion'))return;
    const tabs=document.querySelector('.tabs'),last=document.querySelector('.section:last-of-type');if(!tabs||!last)return;
    const tab=document.createElement('div');tab.className='tab';tab.dataset.tab='expansion';tab.textContent='Expansión';tabs.appendChild(tab);
    const sec=document.createElement('section');sec.id='expansion';sec.className='section';sec.innerHTML='<div class="method"><h2>Preparación territorial IRFEN</h2><div id="expansionBody" class="small">Cargando…</div></div>';last.parentNode.insertBefore(sec,last.nextSibling);
    tab.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));tab.classList.add('active');sec.classList.add('active');render();};
  }

  function gate(g){
    const kind=g.status==='READY'?'ok':g.status==='PARTIAL'?'warn':'exp';
    return `<span title="${esc(g.path||'Evidencia pendiente')}" style="display:inline-flex;gap:4px;align-items:center;margin:3px 4px 3px 0">${badge(labels[g.id]||g.id,kind)}<span style="font-size:10px">${esc(g.status)}</span></span>`;
  }

  function zoneCard(z,trace){
    const sources=(z.official_sources||[]).filter(s=>s.url).map(s=>`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.id)}</a>`).join(' · ')||'pendientes';
    const priority=trace&&trace.development_priority||{};
    const geometry=trace&&trace.geometry||{};
    const coverage=trace&&trace.coverage||{};
    const confidence=trace&&trace.confidence||{};
    const variables=(trace&&trace.variables_available||[]).map(v=>`${esc(labels[v.variable]||v.variable)}: ${esc(v.status)}`).join(' · ')||'ninguna variable reproducible disponible';
    return `<div class="card" style="margin:0">
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start;flex-wrap:wrap">
        <div><div class="small">${esc(z.department)} · ${esc(z.province_or_corridor)}</div><h3 style="margin:3px 0">${esc(z.system_name)}</h3></div>
        ${badge('RESEARCH_ONLY','exp')}
      </div>
      <div class="small" style="line-height:1.55;margin-top:8px"><b>Contrato:</b> ${esc(z.contract_status)} · <b>activación:</b> BLOQUEADA<br><b>Mecanismo:</b> ${esc(z.mechanism_status)}</div>
      <div class="small" style="line-height:1.55;margin-top:8px"><b>Orden de desarrollo:</b> ${esc(priority.development_order)} · ${esc(priority.wave_label)} <b>(no es prioridad de riesgo)</b><br><b>Geometría:</b> ${esc(geometry.status)} · ${geometry.map_eligible?'archivo reproducible disponible':'retenida: no hay archivo reproducible'}<br><b>Confianza geométrica:</b> ${esc(confidence.geometry)} · <b>cobertura:</b> ${esc(coverage.geometry_coverage)}<br><b>Variables:</b> ${variables}</div>
      <div style="margin-top:9px">${Object.entries(z.asset_status||{}).map(([id,status])=>gate({id,status})).join('')}</div>
      <div class="small" style="line-height:1.55;margin-top:8px"><b>Fuentes oficiales:</b> ${sources}<br><b>Criterio territorial:</b> ${esc(z.equity_reason)}<br><b>Regla de dato ausente:</b> riesgo desconocido, nunca riesgo bajo.</div>
    </div>`;
  }

  async function render(){
    const body=document.getElementById('expansionBody');if(!body)return;
    const [d,mapCatalog]=await Promise.all([safeJson('data/phase2/catalog.json'),safeJson('data/map_layers.json')]);
    if(!d||d.production_use!==false||!mapCatalog||mapCatalog.production_use!==false){body.innerHTML='<div class="histnote">El catálogo de expansión todavía no ha sido generado.</div>';return;}
    const s=d.summary||{};
    const mapSummary=mapCatalog.summary||{};
    const traceById=Object.fromEntries((mapCatalog.research_zones||[]).map(z=>[z.candidate_id,z]));
    body.innerHTML=`<div class="card" style="margin:0 0 14px;border:2px solid #e4c06b;background:#fffaf0">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap"><div><div class="small">FASE SIGUIENTE · PREPARACIÓN ACELERADA</div><h3 style="margin:4px 0 6px">${esc(s.registered_candidates)} sistemas ya tienen contrato común</h3></div>${badge('SIN ALERTAS ACTIVAS','warn')}</div>
      <div style="line-height:1.55">La plataforma ya puede recibir geometría, exposición, eventos, observaciones, forecast y contexto hidráulico mediante el mismo paquete para cada zona.</div>
      <div class="small" style="margin-top:8px"><b>Contratos:</b> ${esc(s.contracts_present)} · <b>fuera de Lima Metropolitana:</b> ${esc(s.outside_lima_metropolitana)} · <b>geometrías reproducibles aptas para mapa:</b> ${esc(mapSummary.research_candidates_map_eligible)}/${esc(mapSummary.research_candidates_registered)} · <b>zonas operativas nuevas:</b> 0.</div>
    </div>
    <div class="histnote" style="margin:0 0 14px"><b>Separación de seguridad:</b> esta cola no cambia los tres pilotos de v0.8, no copia umbrales y no interpreta la falta de datos como riesgo bajo. Cada zona exige validación propia antes de cualquier futura promoción.</div>
    <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(310px,1fr))">${(d.zones||[]).map(z=>zoneCard(z,traceById[z.candidate_id])).join('')}</div>`;
  }

  async function init(){ensureUI();await render();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,1100));else setTimeout(init,1100);
})();
