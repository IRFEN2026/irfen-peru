(() => {
  const fmt = value => value == null ? '—' : `${Number(value).toFixed(2)} mm`;
  const safeJson = async url => {
    try {
      const r = await fetch(`${url}?t=${Date.now()}`);
      return r.ok ? await r.json() : null;
    } catch (_) {
      return null;
    }
  };

  function createPanel() {
    let panel = document.getElementById('irfenForecastExperimental');
    if (panel) return panel;
    const op = document.getElementById('op');
    if (!op) return null;
    panel = document.createElement('div');
    panel.id = 'irfenForecastExperimental';
    panel.className = 'panel';
    panel.style.marginTop = '16px';
    panel.style.border = '2px solid #b8c9dc';
    panel.style.background = '#f8fbff';
    const table = op.querySelector('.tablepanel');
    op.insertBefore(panel, table || null);
    return panel;
  }

  function zoneCard(forecast, observed) {
    const combined = observed && observed.rain72 != null && forecast.forecast24_mm != null
      ? Number(observed.rain72) + Number(forecast.forecast24_mm)
      : null;
    const provisional = forecast.sampling_method === 'provisional_weighted_operational_sampling_areas';
    return `
      <div class="card" style="margin:0">
        <div class="small">${forecast.zone_id === 'catacaos' ? 'PIURA · MODELO FLUVIAL EN DISEÑO' : 'PRONÓSTICO DE LLUVIA · V0.8'}</div>
        <h3 style="margin:4px 0 8px">${forecast.name}</h3>
        <div class="metrics">
          <div class="metric"><span class="small">Próx. 24h</span><b>${fmt(forecast.forecast24_mm)}</b></div>
          <div class="metric"><span class="small">Próx. 72h</span><b>${fmt(forecast.forecast72_mm)}</b></div>
          <div class="metric"><span class="small">Hasta 120h</span><b>${fmt(forecast.forecast120_mm)}</b></div>
        </div>
        <div class="small" style="margin-top:10px;line-height:1.55">
          <b>Antecedente observado 72h:</b> ${observed ? fmt(observed.rain72) : '—'}
          <br>
          <b>Contexto combinado 72h observadas + 24h previstas:</b> ${fmt(combined)}
          <br>
          <span style="opacity:.85">Este valor combinado es descriptivo y <b>NO es un umbral de activación</b>.</span>
          ${provisional ? '<br><b>Catacaos:</b> forecast espacial provisional; todavía no incorpora caudal del río Piura.' : ''}
        </div>
      </div>`;
  }

  async function render() {
    const panel = createPanel();
    if (!panel) return;
    const [forecast, latest] = await Promise.all([
      safeJson('data/forecast/latest.json'),
      safeJson('data/latest.json')
    ]);
    if (!forecast || forecast.production_use !== false || !Array.isArray(forecast.zones)) {
      panel.style.display = 'none';
      return;
    }
    panel.style.display = 'block';
    const observed = Object.fromEntries(((latest && latest.zones) || []).map(z => [z.id, z]));
    const available = forecast.zones.filter(z => z.forecast24_mm != null || z.forecast72_mm != null);
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">
        <div>
          <h2 style="margin:0 0 4px">Previsión de precipitación · carril experimental</h2>
          <div class="small">${forecast.source || 'NASA GMAO GEOS-CF v2'} · resolución ${Array.isArray(forecast.grid_resolution_deg) ? forecast.grid_resolution_deg.join('° × ') + '°' : '—'}</div>
        </div>
        <span class="sourcechip" style="background:#e9f2ff;color:#194f82">NO OPERATIVO</span>
      </div>
      <div class="histnote" style="margin:12px 0">
        Primer prototipo de la lógica <b>lluvia observada + lluvia prevista</b>. Se muestra para pruebas, pero no interviene en Amenaza, Impacto, Prioridad ni alertas.
      </div>
      <div class="cards" style="grid-template-columns:repeat(auto-fit,minmax(270px,1fr))">
        ${available.map(z => zoneCard(z, observed[z.zone_id])).join('')}
      </div>
      <div class="small" style="margin-top:12px;line-height:1.55">
        <b>Ventana del modelo:</b> ${forecast.dataset_time_start || '—'} → ${forecast.dataset_time_end || '—'} ·
        <b>actualizado:</b> ${forecast.generated_at ? new Date(forecast.generated_at).toLocaleString() : '—'}.
        <br>${forecast.warning || ''}
      </div>`;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(render, 700));
  } else {
    setTimeout(render, 700);
  }
})();
