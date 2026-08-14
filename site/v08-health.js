(() => {
  const safeJson = async url => {
    try {
      const r = await fetch(`${url}?t=${Date.now()}`);
      return r.ok ? await r.json() : null;
    } catch (_) { return null; }
  };

  const ageHours = value => {
    if (!value) return null;
    const ms = Date.now() - new Date(value).getTime();
    return Number.isFinite(ms) ? ms / 3600000 : null;
  };

  function badge(text, level='ok') {
    const cfg = {
      ok:['#e8f5ed','#246b3b'], warn:['#fff4dd','#795000'],
      bad:['#fdeaea','#8a2530'], exp:['#e9f2ff','#194f82']
    }[level] || ['#eee','#333'];
    return `<span style="display:inline-block;padding:4px 8px;border-radius:999px;background:${cfg[0]};color:${cfg[1]};font-size:11px;font-weight:700">${text}</span>`;
  }

  function tile(title, status, detail, level) {
    return `<div class="card" style="margin:0">
      <div class="small">${title}</div><div style="margin:5px 0 7px">${badge(status, level)}</div>
      <div class="small" style="line-height:1.55">${detail}</div>
    </div>`;
  }

  function ensureUI() {
    if (document.getElementById('health')) return;
    const tabs = document.querySelector('.tabs'); const last = document.querySelector('.section:last-of-type');
    if (!tabs || !last) return;
    const tab = document.createElement('div'); tab.className='tab'; tab.dataset.tab='health'; tab.textContent='Estado del sistema'; tabs.appendChild(tab);
    const sec=document.createElement('section'); sec.id='health'; sec.className='section';
    sec.innerHTML='<div class="method"><h2>Estado técnico IRFEN</h2><div id="healthBody" class="small">Cargando…</div></div>';
    last.parentNode.insertBefore(sec,last.nextSibling);
    tab.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));tab.classList.add('active');sec.classList.add('active');render();};
  }

  async function render(){
    const body=document.getElementById('healthBody'); if(!body)return;
    const [latest, forecast, sci, san, huay, piura, hydraulics, tests] = await Promise.all([
      safeJson('data/latest.json'), safeJson('data/forecast/latest.json'), safeJson('data/scientific_status.json'),
      safeJson('data/watersheds/san_ildefonso_validation.json'), safeJson('data/watersheds/huaycoloro_validation.json'),
      safeJson('data/hydrology/piura_source_status.json'), safeJson('data/hydraulics/current_infrastructure.json'),
      safeJson('data/test_report.json')
    ]);

    const op=latest?.operational_status||'sin datos'; const opLevel=op==='updated'?'ok':op==='stale'?'warn':'bad';
    const opAge=latest?ageHours(latest.generated_at):null; const fAge=forecast?ageHours(forecast.generated_at):null;
    const fOk=forecast?.production_use===false; const hydZones=hydraulics?.zones||[];
    const hydSan=hydZones.find(x=>x.zone_id==='san_ildefonso'), hydHuay=hydZones.find(x=>x.zone_id==='chosica'), hydPiura=hydZones.find(x=>x.zone_id==='catacaos');
    const gore=piura?.gore_piura||{}; const sen=piura?.senamhi||{};
    const testOk=tests?.status==='PASS';

    body.innerHTML=`
      <div class="histnote" style="margin:0 0 14px">Este panel distingue el <b>núcleo operativo</b> de los componentes <b>experimentales v0.8</b>. Un componente experimental disponible no implica autorización para generar alertas.</div>
      <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(230px,1fr))">
        ${tile('NASA IMERG · operación',op.toUpperCase(),`${latest?.status_message||'Sin mensaje'}${opAge!=null?`<br>Antigüedad dataset: ${opAge.toFixed(1)} h`:''}`,opLevel)}
        ${tile('NASA GEOS · forecast',fOk?'EXPERIMENTAL DISPONIBLE':'NO DISPONIBLE',fOk?`Última ejecución: ${fAge!=null?fAge.toFixed(1)+' h':'—'} · ${forecast.zones?.[0]?.available_future_hours??'—'} h futuras.<br>No alimenta alertas.`:'No se encontró forecast.',fOk?'exp':'warn')}
        ${tile('Regresión v0.8',tests?(testOk?'PASS':'FAIL'):'PENDIENTE',tests?`${tests.passed||0} pruebas OK · ${tests.failed||0} fallidas.<br>Integridad arquitectónica, no calibración científica.`:'El pipeline todavía no publicó el reporte.',testOk?'ok':tests?'bad':'warn')}
        ${tile('San Ildefonso · cuenca',san?.status||'PENDIENTE',san?`${san.delineated_area_km2} km² · error ${san.relative_area_error_pct}% · ${san.decision}.`:'Sin validación.',san?.status==='PASS'?'exp':'warn')}
        ${tile('San Ildefonso · hidráulica',hydSan?.scientific_gate?.status||'PENDIENTE',hydSan?`Sistema: ${hydSan.system_status}.<br>Diques + túnel 1.51 km + captación/derivación. Sin atenuación numérica sin calibración.`:'Inventario no disponible.',hydSan?'warn':'bad')}
        ${tile('Huaycoloro · cuenca',huay?.status||'PENDIENTE',huay?`${huay.delineated_area_km2} km² · error ${huay.relative_area_error_pct}% · topología ${huay.topology_check?.status||'—'}.`:'Sin validación.',huay?.status==='PASS'?'exp':'warn')}
        ${tile('Huaycoloro · hidráulica',hydHuay?.scientific_gate?.status||'PENDIENTE',hydHuay?`Canal 10.5 km + 2 acueductos + control de sedimentos. Capacidad cuantitativa todavía pendiente.`:'Inventario no disponible.',hydHuay?'warn':'bad')}
        ${tile('Catacaos · GORE Piura',gore.catalog_status==='available'?'FUENTE DIARIA DISPONIBLE':'EN EXPLORACIÓN',gore.latest_report_date?`Informe más reciente: ${gore.latest_report_date} · antigüedad ${gore.report_age_days??'—'} días.<br>Los enlaces numéricos siguen sin integrarse.`:'Sin informe regional reciente.',gore.catalog_status==='available'?'exp':'warn')}
        ${tile('Catacaos · puerta fluvial',hydPiura?.scientific_gate?.status||'PENDIENTE',hydPiura?`IRFEN exige nivel/caudal real antes de habilitar lógica fluvial. Referencia SENAMHI Puente Ñácara: rojo ${sen.reference_red_threshold_m3s??'—'} m³/s.`:'Inventario no disponible.',hydPiura?'warn':'bad')}
        ${tile('SENAMHI Puente Ñácara',sen.numeric_river_state_available?'DATO NUMÉRICO DISPONIBLE':'SIN DATO AUTOMÁTICO',sen.numeric_river_state_available?'Señal numérica localizada; aún requiere validación.':`GitHub Actions no logra acceder de forma estable al portal numérico. Último estado: ${sen.automatic_numeric_access_status||'—'}.`,sen.numeric_river_state_available?'exp':'warn')}
      </div>
      <div class="small" style="margin-top:14px;line-height:1.6"><b>Contrato de seguridad:</b> v0.8 conserva <code>production_ready=false</code> / <code>production_use=false</code>, mantiene <code>production_modifier=null</code> para infraestructura no calibrada y ejecuta puertas + regresión antes del despliegue. La función operativa v0.7.1 permanece aislada de forecast, polígonos, río e hidráulica experimental.${sci?`<br><b>Versión científica:</b> ${sci.version||'—'} · actualizada ${sci.updated_at||'—'}.`:''}</div>`;
  }

  async function init(){ensureUI(); await render();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,900)); else setTimeout(init,900);
})();
