(() => {
  const safeJson = async url => {
    try {
      const r = await fetch(`${url}?t=${Date.now()}`);
      return r.ok ? await r.json() : null;
    } catch (_) { return null; }
  };

  const pct = v => v == null ? '—' : `${(Number(v) * 100).toFixed(0)}%`;
  const mm = v => v == null ? '—' : `${Number(v).toFixed(2)} mm`;

  function badge(text, kind='exp') {
    const m = {
      exp:['#e9f2ff','#194f82'],
      ok:['#e8f5ed','#246b3b'],
      warn:['#fff4dd','#795000'],
      bad:['#fdeaea','#8a2530']
    }[kind] || ['#eee','#333'];
    return `<span style="display:inline-block;padding:4px 8px;border-radius:999px;background:${m[0]};color:${m[1]};font-size:11px;font-weight:700">${text}</span>`;
  }

  function ensureUI() {
    if (document.getElementById('readiness')) return;
    const tabs = document.querySelector('.tabs');
    const last = document.querySelector('.section:last-of-type');
    if (!tabs || !last) return;
    const tab = document.createElement('div');
    tab.className='tab'; tab.dataset.tab='readiness'; tab.textContent='Pruebas v0.8';
    tabs.appendChild(tab);
    const sec=document.createElement('section');
    sec.id='readiness'; sec.className='section';
    sec.innerHTML='<div class="method"><h2>Preparación para pruebas IRFEN v0.8</h2><div id="readinessBody" class="small">Cargando…</div></div>';
    last.parentNode.insertBefore(sec,last.nextSibling);
    tab.onclick=()=>{
      document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));
      tab.classList.add('active'); sec.classList.add('active'); render();
    };
  }

  function signalTable(z) {
    const o=z.observation||{}; const or=z.observed_threshold_ratios||{};
    const f=z.forecast||{}; const fr=f.threshold_ratios||{};
    return `<div class="tablepanel" style="margin:10px 0 0;overflow:auto">
      <table>
        <thead><tr><th>Señal</th><th>Valor</th><th>% umbral provisional</th></tr></thead>
        <tbody>
          <tr><td>Observado 24h</td><td>${mm(o.rain24)}</td><td>${pct(or.rain24)}</td></tr>
          <tr><td>Observado 72h</td><td>${mm(o.rain72)}</td><td>${pct(or.rain72)}</td></tr>
          <tr><td>Observado 7d</td><td>${mm(o.rain7d)}</td><td>${pct(or.rain7d)}</td></tr>
          <tr><td>Forecast 24h</td><td>${mm(f.forecast24_mm)}</td><td>${pct(fr.forecast24)}</td></tr>
          <tr><td>Forecast 72h</td><td>${mm(f.forecast72_mm)}</td><td>${pct(fr.forecast72)}</td></tr>
        </tbody>
      </table>
    </div>`;
  }

  function zoneCard(z) {
    const obsCross=(z.observed_threshold_crossings||[]).length;
    const fcCross=((z.forecast||{}).threshold_crossings||[]).length;
    const blocked=(z.blockers||[]).length>0;
    const gate=z.hydraulic_gate||{};
    return `<div class="card" style="margin:0">
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start;flex-wrap:wrap">
        <div><div class="small">${z.zone_id}</div><h3 style="margin:3px 0">${z.name||z.zone_id}</h3></div>
        ${badge(blocked?'PRUEBA PARCIAL':'LISTO INVESTIGACIÓN',blocked?'warn':'ok')}
      </div>
      <div class="small" style="line-height:1.55;margin-top:8px">
        <b>Estado:</b> ${z.readiness||'—'}<br>
        <b>Observación:</b> ${z.observation?.method||'—'}<br>
        <b>Cruces observados:</b> ${obsCross} · <b>cruces forecast:</b> ${fcCross}<br>
        <b>Puerta hidráulica:</b> ${gate.status||'sin puerta registrada'}
        ${z.river_state_available===false?'<br><b>Río:</b> falta señal numérica reutilizable':''}
      </div>
      ${signalTable(z)}
      <div class="small" style="margin-top:10px;line-height:1.55">
        <b>Bloqueos:</b> ${(z.blockers||[]).length ? z.blockers.join(' · ') : 'ninguno para investigación'}
        <br><span style="opacity:.85">${z.interpretation||''}</span>
      </div>
    </div>`;
  }

  async function render(){
    const body=document.getElementById('readinessBody'); if(!body)return;
    const state=await safeJson('data/experimental_state.json');
    if(!state || state.production_use!==false){
      body.innerHTML='<div class="histnote">El estado experimental todavía no ha sido generado por el pipeline.</div>';
      return;
    }
    body.innerHTML=`
      <div class="histnote" style="margin:0 0 14px">
        Esta pantalla sirve para <b>ensayar la lógica futura</b>. Los porcentajes comparan señales con umbrales provisionales, pero <b>no son alertas</b> y no alteran la v0.7.1.
      </div>
      <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
        ${(state.zones||[]).map(zoneCard).join('')}
      </div>
      <div class="small" style="margin-top:14px;line-height:1.6">
        <b>Regla científica:</b> no existe todavía un score compuesto lluvia+forecast+infraestructura. IRFEN mantiene las señales separadas hasta contar con calibración hidráulica y, en Catacaos, estado numérico del río Piura.
      </div>`;
  }

  async function init(){ensureUI(); await render();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,1000));
  else setTimeout(init,1000);
})();
