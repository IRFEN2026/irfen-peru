(() => {
  let latest = null;
  let forecast = null;
  let history = null;
  let scenarioLabel = 'observado actual';

  const clamp = x => Math.max(0, Math.min(1.35, Number(x) || 0));
  const cls = v => v >= 80 ? 'Crítica' : v >= 60 ? 'Muy alta' : v >= 40 ? 'Alta' : v >= 20 ? 'Vigilancia' : 'Baja';
  const fmt = v => Number.isFinite(Number(v)) ? Number(v).toFixed(1) : '—';

  async function safeJson(url) {
    try { const r = await fetch(`${url}?t=${Date.now()}`); return r.ok ? await r.json() : null; }
    catch (_) { return null; }
  }

  function ensureUI() {
    if (document.getElementById('sim')) return;
    const tabs = document.querySelector('.tabs');
    const met = document.getElementById('met');
    if (!tabs || !met) return;
    const tab = document.createElement('div');
    tab.className='tab'; tab.dataset.tab='sim'; tab.textContent='Simulador v0.8'; tabs.appendChild(tab);
    const section=document.createElement('section'); section.id='sim'; section.className='section';
    section.innerHTML=`
      <div class="method">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">
          <div><h2 style="margin:0 0 4px">Simulador de escenarios IRFEN v0.8</h2><div class="small">Prueba local en el navegador · no escribe datos · no envía alertas</div></div>
          <span class="sourcechip" style="background:#fff4dd;color:#795000">SOLO PRUEBAS</span>
        </div>
        <div class="histnote" style="margin:12px 0">Permite ensayar la fórmula operativa actual con valores hipotéticos o eventos históricos IMERG. La previsión se muestra como contexto separado y <b>no se suma al índice de amenaza</b>.</div>
        <div class="histtoolbar" style="margin-bottom:12px">
          <label><b>Zona:</b></label><select id="simZone"></select>
          <button id="simLive">Observado actual</button><button id="simHistory">Evento histórico</button>
          <button id="simHalf">50% umbrales</button><button id="simThreshold">100% umbrales</button>
        </div>
        <div id="simHistoricalInfo" class="small" style="margin-bottom:10px"></div>
        <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin-bottom:14px">
          <label class="metric">24h observadas<input id="sim24" type="number" min="0" step="0.1" style="width:100%;margin-top:6px"></label>
          <label class="metric">72h observadas<input id="sim72" type="number" min="0" step="0.1" style="width:100%;margin-top:6px"></label>
          <label class="metric">7 días observados<input id="sim7d" type="number" min="0" step="0.1" style="width:100%;margin-top:6px"></label>
          <label class="metric">Previsión 24h<input id="simF24" type="number" min="0" step="0.1" style="width:100%;margin-top:6px"></label>
        </div>
        <div id="simResult"></div>
      </div>`;
    met.parentNode.insertBefore(section,met.nextSibling);
    tab.addEventListener('click',()=>{
      document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));
      tab.classList.add('active'); section.classList.add('active'); render();
    });
  }

  function zone(){const id=document.getElementById('simZone')?.value;return latest&&(latest.zones||[]).find(z=>z.id===id);}
  function forecastZone(id){return forecast&&(forecast.zones||[]).find(z=>z.zone_id===id);}
  function historicalEvent(id){
    const ev=(history&&history.events)||[];
    return ev.filter(e=>e.zone_id===id&&e.imerg!==false&&e.rain24!=null&&e.rain72!=null&&e.rain7d!=null)
      .sort((a,b)=>(b.year||0)-(a.year||0))[0]||null;
  }

  function applyValues(a,b,c,label,forecastValue=null){
    document.getElementById('sim24').value=Number(a||0).toFixed(1);
    document.getElementById('sim72').value=Number(b||0).toFixed(1);
    document.getElementById('sim7d').value=Number(c||0).toFixed(1);
    const z=zone(); const f=z&&forecastZone(z.id);
    const fv=forecastValue!=null?forecastValue:(f&&f.forecast24_mm!=null?f.forecast24_mm:0);
    document.getElementById('simF24').value=Number(fv||0).toFixed(1);
    scenarioLabel=label;
    render();
  }

  function setInputs(mode){
    const z=zone(); if(!z)return; const t=z.thresholds_provisional||{};
    const info=document.getElementById('simHistoricalInfo'); if(info)info.textContent='';
    if(mode==='live') return applyValues(z.rain24,z.rain72,z.rain7d,'observado actual');
    if(mode==='history'){
      const e=historicalEvent(z.id);
      if(!e){if(info)info.textContent='No hay un evento IMERG completo disponible para esta zona.';return;}
      if(info)info.innerHTML=`Preset: <b>${e.year||''} · ${e.event||e.id}</b> (${e.date||'fecha no disponible'}) · fuente ${e.source||'—'}.`;
      return applyValues(e.rain24,e.rain72,e.rain7d,`evento histórico ${e.date||e.year}`,0);
    }
    const factor=mode==='half'?0.5:1;
    applyValues((t.rain24||0)*factor,(t.rain72||0)*factor,(t.rain7d||0)*factor,`${factor*100}% de umbrales provisionales`);
  }

  function render(){
    const z=zone(),out=document.getElementById('simResult'); if(!z||!out)return;
    const t=z.thresholds_provisional||{};
    const r24=Number(document.getElementById('sim24').value||0),r72=Number(document.getElementById('sim72').value||0),r7d=Number(document.getElementById('sim7d').value||0),f24=Number(document.getElementById('simF24').value||0);
    const raw=100*(.38*clamp(r24/t.rain24)+.30*clamp(r72/t.rain72)+.32*clamp(r7d/t.rain7d))/1.35;
    const threat=Math.round(raw),impact=Number(z.impact_score||0),priority=Math.round(threat*impact/100),context=r72+f24;
    out.innerHTML=`
      <div class="kpis" style="margin:0 0 14px">
        <div class="kpi"><span class="small">Amenaza simulada</span><b>${threat}/100</b><span class="small">${cls(threat)}</span></div>
        <div class="kpi"><span class="small">Impacto configurado</span><b>${impact}/100</b><span class="small">sin modificar</span></div>
        <div class="kpi"><span class="small">Prioridad simulada</span><b>${priority}/100</b><span class="small">${cls(priority)}</span></div>
        <div class="kpi"><span class="small">72h + previsión 24h</span><b>${fmt(context)} mm</b><span class="small">contexto, no índice</span></div>
      </div>
      <div class="small" style="line-height:1.65">
        <b>Escenario:</b> ${scenarioLabel}.<br>
        <b>Umbrales provisionales:</b> 24h ${t.rain24} mm · 72h ${t.rain72} mm · 7d ${t.rain7d} mm.<br>
        <b>Entrada:</b> ${fmt(r24)} / ${fmt(r72)} / ${fmt(r7d)} mm + forecast24 ${fmt(f24)} mm.<br>
        <b>Importante:</b> el resultado reproduce matemáticamente el índice actual para pruebas de interfaz; un evento histórico no convierte estos valores en umbrales de activación validados.
      </div>`;
  }

  async function init(){
    ensureUI(); [latest,forecast,history]=await Promise.all([safeJson('data/latest.json'),safeJson('data/forecast/latest.json'),safeJson('data/history.json')]);
    const selector=document.getElementById('simZone'); if(!selector||!latest)return;
    selector.innerHTML=(latest.zones||[]).map(z=>`<option value="${z.id}">${z.name}</option>`).join('');
    selector.addEventListener('change',()=>setInputs('live'));
    ['sim24','sim72','sim7d','simF24'].forEach(id=>document.getElementById(id)?.addEventListener('input',()=>{scenarioLabel='entrada manual';render();}));
    document.getElementById('simLive').onclick=()=>setInputs('live'); document.getElementById('simHistory').onclick=()=>setInputs('history');
    document.getElementById('simHalf').onclick=()=>setInputs('half'); document.getElementById('simThreshold').onclick=()=>setInputs('threshold'); setInputs('live');
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,800)); else setTimeout(init,800);
})();
