(() => {
  const DATA_URL = 'data/independent_validation/basins.json';
  const LAYER_NAME = 'Investigación independiente · RESEARCH_ONLY';
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const stageStyle = stage => {
    const styles = {
      A0_A1_INTAKE: {color:'#596773', fillColor:'#dce3e8'},
      A1_2_A1_3: {color:'#315d86', fillColor:'#cfe0f0'},
      FEATURE_VECTOR_READY: {color:'#4d5f75', fillColor:'#dfe7ef'},
      BLOCKED: {color:'#6c5963', fillColor:'#eadfe4'}
    };
    return styles[stage] || {color:'#596773', fillColor:'#e5eaee'};
  };

  const popupHtml = basin => {
    const indicators = (basin.public_indicators || [])
      .slice(0, 6)
      .map(i => `<div style="display:flex;justify-content:space-between;gap:12px;margin:4px 0"><span>${esc(i.label)}</span><b>${esc(i.value)}</b></div>`)
      .join('');
    return `
      <div style="min-width:255px;line-height:1.4">
        <div style="font-size:11px;font-weight:800;letter-spacing:.03em">RESEARCH_ONLY · TEST_ONLY</div>
        <h3 style="margin:5px 0 8px">${esc(basin.basin_name)}</h3>
        ${indicators}
        <hr style="border:0;border-top:1px solid #d9e2ea;margin:9px 0">
        <div style="font-size:11px;color:#687b8c">Estado cartográfico científico; no representa riesgo, alerta ni decisión operativa.</div>
      </div>`;
  };

  const fetchJson = async url => {
    const response = await fetch(`${url}?t=${Date.now()}`);
    if (!response.ok) throw new Error(`${url} HTTP ${response.status}`);
    return response.json();
  };

  const validateEnvelope = data => {
    if (!data || data.deployment_status !== 'RESEARCH_ONLY' || data.test_status !== 'TEST_ONLY') return false;
    if (data.production_use !== false || data.production_ready !== false || data.operational_alerting_enabled !== false) return false;
    if (data.operational_labels_allowed !== false || data.blind_outcome_evidence !== 'SEALED') return false;
    return (data.basins || []).every(b => b.production_use === false && b.production_ready === false && b.operational_alerting_enabled === false);
  };

  async function buildLayer() {
    if (typeof map === 'undefined' || typeof L === 'undefined') return;
    const data = await fetchJson(DATA_URL);
    if (!validateEnvelope(data)) throw new Error('Independent basin map safety contract failed');

    const researchLayer = L.layerGroup();
    const bySource = new Map();
    for (const basin of data.basins || []) {
      const source = basin.geometry && basin.geometry.source_path;
      if (!source) continue;
      if (!bySource.has(source)) bySource.set(source, []);
      bySource.get(source).push(basin);
    }

    for (const [source, basins] of bySource.entries()) {
      const geojson = await fetchJson(source);
      for (const basin of basins) {
        const g = basin.geometry || {};
        const feature = (geojson.features || []).find(f => f.properties && f.properties[g.feature_property] === g.feature_value);
        if (!feature) continue;
        const style = stageStyle(basin.research_stage);
        L.geoJSON(feature, {
          style: {
            color: style.color,
            fillColor: style.fillColor,
            weight: 2,
            opacity: .9,
            fillOpacity: .22,
            dashArray: '6 4'
          },
          onEachFeature: (_feature, leafletLayer) => leafletLayer.bindPopup(popupHtml(basin))
        }).addTo(researchLayer);
      }
    }

    L.control.layers(null, {[LAYER_NAME]: researchLayer}, {collapsed:true, position:'topright'}).addTo(map);
  }

  const init = () => buildLayer().catch(err => console.warn('Independent basin research layer unavailable:', err));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 400));
  else setTimeout(init, 400);
})();
