(() => {
  const fmt = value => value == null ? '—' : `${Number(value).toFixed(2)} mm`;
  const signed = value => {
    if (value == null) return '—';
    const n = Number(value);
    return `${n >= 0 ? '+' : ''}${n.toFixed(2)} mm`;
  };

  function row(label, legacy, polygon, delta) {
    return `
      <tr>
        <td><b>${label}</b></td>
        <td>${fmt(legacy)}</td>
        <td>${fmt(polygon)}</td>
        <td><b>${signed(delta)}</b></td>
      </tr>`;
  }

  function createPanel() {
    let panel = document.getElementById('irfenV08Experimental');
    if (panel) return panel;
    const hist = document.getElementById('hist');
    if (!hist) return null;
    panel = document.createElement('div');
    panel.id = 'irfenV08Experimental';
    panel.className = 'histcard';
    panel.style.marginTop = '16px';
    panel.style.border = '2px solid #b8c9dc';
    panel.style.background = '#f8fbff';
    const table = hist.querySelector('.tablepanel');
    hist.insertBefore(panel, table || null);
    return panel;
  }

  async function render() {
    const panel = createPanel();
    if (!panel) return;

    try {
      const [historyResponse, latestResponse, validationResponse] = await Promise.all([
        fetch(`data/history.json?t=${Date.now()}`),
        fetch(`data/latest.json?t=${Date.now()}`),
        fetch(`data/watersheds/san_ildefonso_validation.json?t=${Date.now()}`)
      ]);

      const history = historyResponse.ok ? await historyResponse.json() : {events: []};
      const latest = latestResponse.ok ? await latestResponse.json() : {zones: []};
      const validation = validationResponse.ok ? await validationResponse.json() : null;

      const event = (history.events || []).find(x => x.id === 'SI-2017-03-15');
      const current = (latest.zones || []).find(x => x.id === 'san_ildefonso');
      const historicalPolygon = event && event.experimental_polygon;
      const currentPolygon = current && current.experimental_polygon;

      if (!historicalPolygon) {
        panel.innerHTML = `
          <h3 style="margin-top:0">v0.8 · Validación por microcuenca</h3>
          <div class="small">La comparación histórica experimental todavía no está disponible.</div>`;
        return;
      }

      const hDelta = historicalPolygon.delta_vs_legacy_bbox_mm || {};
      const cDelta = currentPolygon ? (currentPolygon.delta_vs_operational_bbox_mm || {}) : {};
      const spatial = validation && validation.external_spatial_check;

      panel.innerHTML = `
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">
          <div>
            <h3 style="margin:0 0 4px">IRFEN v0.8 · Comparación experimental de microcuenca</h3>
            <div class="small">Quebrada San Ildefonso · Copernicus DEM GLO-30 + NASA GPM IMERG</div>
          </div>
          <span class="sourcechip" style="background:#e9f2ff;color:#194f82">NO OPERATIVO</span>
        </div>

        <div class="histnote" style="margin:12px 0">
          El cálculo de amenaza y prioridad <b>sigue usando la configuración operativa anterior</b>.
          Esta sección compara ambos métodos para validar científicamente el cambio antes de adoptarlo.
        </div>

        <h4 style="margin:12px 0 6px">Evento 15/03/2017 · IMERG Final</h4>
        <div class="tablepanel" style="margin:0;overflow:auto">
          <table>
            <thead>
              <tr><th>Acumulado</th><th>Caja antigua</th><th>Microcuenca DEM</th><th>Diferencia</th></tr>
            </thead>
            <tbody>
              ${row('24h', event.rain24, historicalPolygon.rain24, hDelta.rain24)}
              ${row('72h', event.rain72, historicalPolygon.rain72, hDelta.rain72)}
              ${row('7 días', event.rain7d, historicalPolygon.rain7d, hDelta.rain7d)}
            </tbody>
          </table>
        </div>

        ${currentPolygon ? `
          <h4 style="margin:16px 0 6px">Comparación diaria actual</h4>
          <div class="tablepanel" style="margin:0;overflow:auto">
            <table>
              <thead>
                <tr><th>Acumulado</th><th>Operativo actual</th><th>Microcuenca DEM</th><th>Diferencia</th></tr>
              </thead>
              <tbody>
                ${row('24h', current.rain24, currentPolygon.rain24, cDelta.rain24)}
                ${row('72h', current.rain72, currentPolygon.rain72, cDelta.rain72)}
                ${row('7 días', current.rain7d, currentPolygon.rain7d, cDelta.rain7d)}
              </tbody>
            </table>
          </div>` : ''}

        <div class="small" style="margin-top:12px;line-height:1.55">
          <b>Geometría candidata:</b>
          ${validation ? `${validation.delineated_area_km2} km² frente a ${validation.reference_area_km2} km² de referencia · error ${validation.relative_area_error_pct}%` : '—'}.
          ${spatial ? `Control ANA/SIGRID: <b>${spatial.spatial_context_status}</b> · intersección con ámbito cartográfico oficial: ${spatial.official_extent_overlap_pct}%.` : ''}
          <br>
          <b>Siguiente condición:</b> validación hidráulica e incorporación de las obras de control 2026 antes de cualquier cambio de producción.
        </div>`;
    } catch (error) {
      panel.innerHTML = `<h3>IRFEN v0.8 · Validación por microcuenca</h3><div class="small">No se pudo cargar la comparación experimental: ${error}</div>`;
    }
  }

  function syncVisibility() {
    const panel = document.getElementById('irfenV08Experimental');
    const selector = document.getElementById('histZone');
    if (!panel || !selector) return;
    panel.style.display = selector.value === 'san_ildefonso' ? 'block' : 'none';
  }

  async function init() {
    await render();
    const selector = document.getElementById('histZone');
    if (selector) {
      selector.addEventListener('change', syncVisibility);
      syncVisibility();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 400));
  } else {
    setTimeout(init, 400);
  }
})();
