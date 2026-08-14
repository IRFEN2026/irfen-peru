(() => {
  const fmt = value => value == null ? '—' : `${Number(value).toFixed(2)} mm`;
  const signed = value => {
    if (value == null) return '—';
    const n = Number(value);
    return `${n >= 0 ? '+' : ''}${n.toFixed(2)} mm`;
  };

  const safeJson = async url => {
    try {
      const r = await fetch(`${url}?t=${Date.now()}`);
      return r.ok ? await r.json() : null;
    } catch (_) {
      return null;
    }
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

  function comparisonTable(title, legacy, polygon, delta, legacyLabel='Caja / operativo') {
    if (!polygon) return '<div class="small" style="margin-top:12px">Comparación poligonal pendiente.</div>';
    return `
      <h4 style="margin:16px 0 6px">${title}</h4>
      <div class="tablepanel" style="margin:0;overflow:auto">
        <table>
          <thead><tr><th>Acumulado</th><th>${legacyLabel}</th><th>Polígono DEM</th><th>Diferencia</th></tr></thead>
          <tbody>
            ${row('24h', legacy && legacy.rain24, polygon.rain24, delta && delta.rain24)}
            ${row('72h', legacy && legacy.rain72, polygon.rain72, delta && delta.rain72)}
            ${row('7 días', legacy && legacy.rain7d, polygon.rain7d, delta && delta.rain7d)}
          </tbody>
        </table>
      </div>`;
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

  function geometrySummary(v) {
    if (!v) return '<div class="small">Geometría candidata pendiente.</div>';
    const spatial = v.external_spatial_check || {};
    const topology = v.topology_check || {};
    return `
      <div class="small" style="line-height:1.65">
        <b>Área de referencia:</b> ${v.reference_area_km2 ?? '—'} km² ·
        <b>DEM:</b> ${v.delineated_area_km2 ?? '—'} km² ·
        <b>error:</b> ${v.relative_area_error_pct ?? '—'}% ·
        <b>control geométrico:</b> ${v.status || '—'}.
        <br>
        <b>Control espacial:</b> ${spatial.spatial_context_status || 'pendiente'}
        ${topology.status ? ` · <b>topología:</b> ${topology.status}` : ''}.
        <br>
        <b>Decisión científica:</b> ${v.decision || 'pendiente'} ·
        <b>Producción:</b> ${v.production_ready ? 'habilitada' : 'NO habilitada'}.
      </div>`;
  }

  function header(title, subtitle, tag='NO OPERATIVO') {
    return `
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">
        <div>
          <h3 style="margin:0 0 4px">${title}</h3>
          <div class="small">${subtitle}</div>
        </div>
        <span class="sourcechip" style="background:#e9f2ff;color:#194f82">${tag}</span>
      </div>`;
  }

  function sanPanel(history, latest, validation) {
    const event = (history.events || []).find(x => x.id === 'SI-2017-03-15');
    const current = (latest.zones || []).find(x => x.id === 'san_ildefonso');
    const hp = event && event.experimental_polygon;
    const cp = current && current.experimental_polygon;

    return `
      ${header('IRFEN v0.8 · San Ildefonso', 'Microcuenca DEM + validación IMERG en paralelo')}
      <div class="histnote" style="margin:12px 0">
        La amenaza y la prioridad siguen usando la configuración operativa v0.7.1. La v0.8 se mantiene como carril científico paralelo.
      </div>
      ${geometrySummary(validation)}
      ${comparisonTable('Evento 15/03/2017 · IMERG Final', event, hp, hp && hp.delta_vs_legacy_bbox_mm, 'Caja antigua')}
      ${comparisonTable('Comparación diaria actual', current, cp, cp && cp.delta_vs_operational_bbox_mm, 'Operativo actual')}
      <div class="small" style="margin-top:12px;line-height:1.55">
        <b>Puerta pendiente:</b> representar el sistema hidráulico 2026 (diques, captación, túnel/canales y descarga al río Moche) antes de cambiar la lógica de producción.
      </div>`;
  }

  function huayPanel(history, latest, validation) {
    const event = (history.events || []).find(x => x.id === 'CH-2015-03-23');
    const current = (latest.zones || []).find(x => x.id === 'chosica');
    const hp = event && event.experimental_polygon;
    const cp = current && current.experimental_polygon;

    return `
      ${header('IRFEN v0.8 · Huaycoloro / Chosica', 'Subcuenca DEM + comparación histórica y diaria en paralelo')}
      <div class="histnote" style="margin:12px 0">
        La subcuenca DEM de Huaycoloro se mantiene separada de la lógica operativa. La canalización de 10.5 km inaugurada en 2025 obliga a distinguir <b>amenaza meteorológica</b>, <b>respuesta hidrológica</b> y <b>capacidad hidráulica urbana</b>.
      </div>
      ${geometrySummary(validation)}
      ${comparisonTable('Evento 23/03/2015 · IMERG Final', event, hp, hp && hp.delta_vs_legacy_bbox_mm, 'Caja antigua')}
      ${comparisonTable('Comparación diaria actual', current, cp, cp && cp.delta_vs_operational_bbox_mm, 'Operativo actual')}
      <div class="small" style="margin-top:12px;line-height:1.55">
        <b>Puerta pendiente:</b> incorporar explícitamente la canalización Huaycoloro y validar la relación lluvia–caudal–impacto con eventos y días lluviosos sin activación antes de producción.
      </div>`;
  }

  function catacaosPanel(status) {
    return `
      ${header('IRFEN v0.8 · Catacaos / Bajo Piura', 'Modelo río–cuenca–llanura de inundación', 'DISEÑO')}
      <div class="histnote" style="margin:12px 0">
        Catacaos no se modelará forzándolo a una microcuenca simple. El riesgo depende del río Piura, aportes aguas arriba, la intercuenca Bajo Piura, defensas, drenaje urbano y llanura de inundación.
      </div>
      <div class="small" style="line-height:1.65">
        <b>Arquitectura:</b> lluvia de cuenca → estado del río → capacidad hidráulica/drenaje → exposición de llanura → prioridad territorial.
        <br>
        ${status && status.next_step ? `<b>Siguiente paso:</b> ${status.next_step}` : 'Se están identificando series hidrológicas y fuentes reutilizables.'}
      </div>`;
  }

  async function renderForSelected() {
    const panel = createPanel();
    const selector = document.getElementById('histZone');
    if (!panel || !selector) return;

    panel.style.display = 'block';
    panel.innerHTML = '<div class="small">Cargando validación científica v0.8…</div>';

    const [history, latest, sanValidation, huayValidation, status] = await Promise.all([
      safeJson('data/history.json'),
      safeJson('data/latest.json'),
      safeJson('data/watersheds/san_ildefonso_validation.json'),
      safeJson('data/watersheds/huaycoloro_validation.json'),
      safeJson('data/scientific_status.json')
    ]);

    const zid = selector.value;
    const zoneStatus = status && (status.zones || []).find(z => z.id === zid);

    if (zid === 'san_ildefonso') {
      panel.innerHTML = sanPanel(history || {events: []}, latest || {zones: []}, sanValidation);
    } else if (zid === 'chosica') {
      panel.innerHTML = huayPanel(history || {events: []}, latest || {zones: []}, huayValidation);
    } else if (zid === 'catacaos') {
      panel.innerHTML = catacaosPanel(zoneStatus);
    } else {
      panel.style.display = 'none';
    }
  }

  async function addWatershedOverlays() {
    if (typeof L === 'undefined' || typeof map === 'undefined') return;
    const specs = [
      ['San Ildefonso · microcuenca v0.8', 'data/watersheds/san_ildefonso_watershed.geojson'],
      ['Huaycoloro · subcuenca v0.8', 'data/watersheds/huaycoloro_watershed.geojson']
    ];
    const overlays = {};

    for (const [label, url] of specs) {
      const geo = await safeJson(url);
      if (!geo) continue;
      const lyr = L.geoJSON(geo, {
        style: {weight: 2, fillOpacity: 0.08, dashArray: '6 5'}
      });
      const p = geo.properties || {};
      lyr.bindPopup(`<b>${p.name || label}</b><br>Área DEM: ${p.delineated_area_km2 ?? '—'} km²<br>Estado: ${p.validation_status || 'experimental'}<br><b>No operativo</b>`);
      overlays[label] = lyr;
      lyr.addTo(map);
    }

    if (Object.keys(overlays).length) {
      L.control.layers(null, overlays, {collapsed: true, position: 'topright'}).addTo(map);
    }
  }

  async function init() {
    const selector = document.getElementById('histZone');
    if (selector) {
      selector.addEventListener('change', renderForSelected);
      await renderForSelected();
    }
    await addWatershedOverlays();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 500));
  } else {
    setTimeout(init, 500);
  }
})();
