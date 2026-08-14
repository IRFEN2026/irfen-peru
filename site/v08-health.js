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
      ok:['#e8f5ed','#246b3b'],
      warn:['#fff4dd','#795000'],
      bad:['#fdeaea','#8a2530'],
      exp:['#e9f2ff','#194f82']
    }[level] || ['#eee','#333'];
    return `<span style="display:inline-block;padding:4px 8px;border-radius:999px;background:${cfg[0]};color:${cfg[1]};font-size:11px;font-weight:700">${text}</span>`;
  }

  function tile(title, status, detail, level) {
    return `<div class="card" style="margin:0">
      <div class="small">${title}</div>
      <div style="margin:5px 0 7px">${badge(status, level)}</div>
      <div class="small" style="line-height:1.55">${detail}</div>
    </div>`;
  }

  function ensureUI() {
    if (document.getElementById('health')) return;
    const tabs = document.querySelector('.tabs');
    const last = document.querySelector('.section:last-of-type');
    if (!tabs || !last) return;
    const tab = document.createElement('div');
    tab.className='tab'; tab.dataset.tab='health'; tab.textContent='Estado del sistema';
    tabs.appendChild(tab);
    const sec=document.createElement('section');
    sec.id='health'; sec.className='section';
    sec.innerHTML='<div class="method"><h2>Estado técnico IRFEN</h2><div id="healthBody" class="small">Cargando…</div></div>';
    last.parentNode.insertBefore(sec,last.nextSibling);
    tab.onclick=()=>{
      document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.section').forEach(x=>x.classList.remove('active'));
      tab.classList.add('active'); sec.classList.add('active'); render();
    };
  }

  async function render(){
    const body=document.getElementById('healthBody'); if(!body)return;
    const [latest, forecast, sci, san, huay, gore, probe, sen] = await Promise.all([
      safeJson('data/latest.json'),
      safeJson('data/forecast/latest.json'),
      safeJson('data/scientific_status.json'),
      safeJson('data/watersheds/san_ildefonso_validation.json'),
      safeJson('data/watersheds/huaycoloro_validation.json'),
      safeJson('data/hydrology/gore_piura_discovery.json'),
      safeJson('data/hydrology/gore_piura_probe.json'),
      safeJson('data/hydrology/senamhi_piura_discovery.json')
    ]);

    const op = latest && latest.operational_status || 'sin datos';
    const opLevel = op==='updated'?'ok':op==='stale'?'warn':'bad';
    const opAge=latest ? ageHours(latest.generated_at) : null;
    const fAge=forecast ? ageHours(forecast.generated_at):null;
    const fOk=forecast && forecast.production_use===false;
    const piuraDaily = probe && probe.latest_item;
    const goreOk = gore && (gore.sources||[]).some(x=>x.http_status===200);
    const senOk = sen && sen.status !== 'access_failed';

    body.innerHTML=`
      <div class="histnote" style="margin:0 0 14px">
        Este panel distingue el <b>núcleo operativo</b> de los componentes <b>experimentales v0.8</b>. Un componente experimental disponible no implica que esté autorizado para generar alertas.
      </div>
      <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(230px,1fr))">
        ${tile('NASA IMERG · operación',op.toUpperCase(),`${latest && latest.status_message || 'Sin mensaje'}${opAge!=null?`<br>Antigüedad dataset: ${opAge.toFixed(1)} h`:''}`,opLevel)}
        ${tile('NASA GEOS · forecast',fOk?'EXPERIMENTAL DISPONIBLE':'NO DISPONIBLE',fOk?`Última ejecución: ${fAge!=null?fAge.toFixed(1)+' h':'—'} · ${forecast.zones?.[0]?.available_future_hours ?? '—'} h futuras.<br>No alimenta alertas.`:'No se encontró forecast.',fOk?'exp':'warn')}
        ${tile('San Ildefonso · cuenca',san?.status || 'PENDIENTE',san?`${san.delineated_area_km2} km² · error ${san.relative_area_error_pct}% · ${san.decision}.`:'Sin validación.',san?.status==='PASS'?'exp':'warn')}
        ${tile('Huaycoloro · cuenca',huay?.status || 'PENDIENTE',huay?`${huay.delineated_area_km2} km² · error ${huay.relative_area_error_pct}% · topología ${huay.topology_check?.status || '—'}.`:'Sin validación.',huay?.status==='PASS'?'exp':'warn')}
        ${tile('Catacaos · hidrología regional',goreOk?'FUENTE DIARIA LOCALIZADA':'EN EXPLORACIÓN',piuraDaily?`GORE Piura lista datos hasta ${piuraDaily.fecha || piuraDaily.fkey}. La extracción de valores sigue en validación.`:'Portal regional '+(goreOk?'accesible':'no accesible')+'.',goreOk?'exp':'warn')}
        ${tile('SENAMHI · acceso automático',senOk?'ACCESIBLE':'BLOQUEADO DESDE CI',senOk?'Interfaz automática disponible.':'El portal oficial existe, pero las consultas desde GitHub Actions agotaron tiempo. Se mantiene como fuente oficial de referencia y se busca canal reutilizable.',senOk?'exp':'warn')}
      </div>
      <div class="small" style="margin-top:14px;line-height:1.6">
        <b>Contrato de seguridad:</b> v0.8 conserva <code>production_ready=false</code> / <code>production_use=false</code> y pasa validaciones automáticas antes del despliegue. La función operativa v0.7.1 permanece aislada de forecast y polígonos experimentales.
        ${sci?`<br><b>Versión científica:</b> ${sci.version || '—'} · actualizada ${sci.updated_at || '—'}.`:''}
      </div>`;
  }

  async function init(){ensureUI(); await render();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,900));
  else setTimeout(init,900);
})();
