(() => {
  const fmt = value => value == null ? '—' : `${Number(value).toFixed(2)} mm`;
  const signed = value => value == null ? '—' : `${Number(value) >= 0 ? '+' : ''}${Number(value).toFixed(2)} mm`;
  const safeJson = async url => { try { const r=await fetch(`${url}?t=${Date.now()}`); return r.ok?await r.json():null; } catch(_){return null;} };
  const esc = value => String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  function row(label, legacy, polygon, delta) { return `<tr><td><b>${label}</b></td><td>${fmt(legacy)}</td><td>${fmt(polygon)}</td><td><b>${signed(delta)}</b></td></tr>`; }
  function comparisonTable(title, legacy, polygon, delta, legacyLabel='Caja / operativo') {
    if (!polygon) return '<div class="small" style="margin-top:12px">Comparación poligonal pendiente.</div>';
    return `<h4 style="margin:16px 0 6px">${title}</h4><div class="tablepanel" style="margin:0;overflow:auto"><table><thead><tr><th>Acumulado</th><th>${legacyLabel}</th><th>Polígono DEM</th><th>Diferencia</th></tr></thead><tbody>${row('24h',legacy&&legacy.rain24,polygon.rain24,delta&&delta.rain24)}${row('72h',legacy&&legacy.rain72,polygon.rain72,delta&&delta.rain72)}${row('7 días',legacy&&legacy.rain7d,polygon.rain7d,delta&&delta.rain7d)}</tbody></table></div>`;
  }
  function createPanel(){let p=document.getElementById('irfenV08Experimental');if(p)return p;const h=document.getElementById('hist');if(!h)return null;p=document.createElement('div');p.id='irfenV08Experimental';p.className='histcard';p.style.marginTop='16px';p.style.border='2px solid #b8c9dc';p.style.background='#f8fbff';const t=h.querySelector('.tablepanel');h.insertBefore(p,t||null);return p;}
  function geometrySummary(v){if(!v)return'<div class="small">Geometría candidata pendiente.</div>';const s=v.external_spatial_check||{},top=v.topology_check||{};return `<div class="small" style="line-height:1.65"><b>Área de referencia:</b> ${v.reference_area_km2??'—'} km² · <b>DEM:</b> ${v.delineated_area_km2??'—'} km² · <b>error:</b> ${v.relative_area_error_pct??'—'}% · <b>control geométrico:</b> ${v.status||'—'}.<br><b>Control espacial:</b> ${s.spatial_context_status||'pendiente'}${top.status?` · <b>topología:</b> ${top.status}`:''}.<br><b>Decisión científica:</b> ${v.decision||'pendiente'} · <b>Producción:</b> ${v.production_ready?'habilitada':'NO habilitada'}.</div>`;}
  function header(title,subtitle,tag='NO OPERATIVO'){return `<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap"><div><h3 style="margin:0 0 4px">${title}</h3><div class="small">${subtitle}</div></div><span class="sourcechip" style="background:#e9f2ff;color:#194f82">${tag}</span></div>`;}

  function sanPanel(history,latest,validation){const e=(history.events||[]).find(x=>x.id==='SI-2017-03-15'),c=(latest.zones||[]).find(x=>x.id==='san_ildefonso'),hp=e&&e.experimental_polygon,cp=c&&c.experimental_polygon;return `${header('IRFEN v0.8 · San Ildefonso','Microcuenca DEM + validación IMERG en paralelo')}<div class="histnote" style="margin:12px 0">La amenaza y la prioridad siguen usando la configuración operativa v0.7.1. La v0.8 se mantiene como carril científico paralelo.</div>${geometrySummary(validation)}${comparisonTable('Evento 15/03/2017 · IMERG Final',e,hp,hp&&hp.delta_vs_legacy_bbox_mm,'Caja antigua')}${comparisonTable('Comparación diaria actual',c,cp,cp&&cp.delta_vs_operational_bbox_mm,'Operativo actual')}<div class="small" style="margin-top:12px;line-height:1.55"><b>Puerta pendiente:</b> calibrar explícitamente el sistema hidráulico 2026 (diques, captación, túnel/canales y descarga al río Moche) antes de cambiar la lógica de producción.</div>`;}
  function huayPanel(history,latest,validation){const e=(history.events||[]).find(x=>x.id==='CH-2015-03-23'),c=(latest.zones||[]).find(x=>x.id==='chosica'),hp=e&&e.experimental_polygon,cp=c&&c.experimental_polygon;return `${header('IRFEN v0.8 · Huaycoloro / Chosica','Subcuenca DEM + comparación histórica y diaria en paralelo')}<div class="histnote" style="margin:12px 0">La subcuenca DEM se mantiene separada de la lógica operativa. La canalización de 10.5 km inaugurada en 2025 obliga a distinguir <b>amenaza meteorológica</b>, <b>respuesta hidrológica</b> y <b>capacidad hidráulica urbana</b>.</div>${geometrySummary(validation)}${comparisonTable('Evento 23/03/2015 · IMERG Final',e,hp,hp&&hp.delta_vs_legacy_bbox_mm,'Caja antigua')}${comparisonTable('Comparación diaria actual',c,cp,cp&&cp.delta_vs_operational_bbox_mm,'Operativo actual')}<div class="small" style="margin-top:12px;line-height:1.55"><b>Puerta pendiente:</b> validar la relación lluvia–caudal–impacto con la canalización actual y eventos posteriores a 2025.</div>`;}

  function catacaosPanel(status,ref,source){
    const hist=(ref&&ref.historical_event_flows)||[],design=(ref&&ref.design_references)||[],sen=(source&&source.senamhi)||{},gore=(source&&source.gore_piura)||{};
    const histRows=hist.map(x=>`<tr><td>${x.date||x.year||'—'}</td><td>${x.event||x.event_id}</td><td><b>${Number(x.flow_m3s).toFixed(0)} m³/s</b></td><td>${x.location_status==='not_harmonized_to_puente_nacara'?'Ubicación no homologada con Ñácara':'—'}</td></tr>`).join('');
    const designRows=design.map(x=>`<tr><td>${x.component_type}</td><td><b>${Number(x.design_flow_m3s).toFixed(0)} m³/s</b></td><td>${x.status||'—'}</td></tr>`).join('');
    return `${header('IRFEN v0.8 · Catacaos / Bajo Piura','Modelo río–cuenca–llanura de inundación','DISEÑO')}<div class="histnote" style="margin:12px 0">Catacaos no se modelará forzándolo a una microcuenca simple. El riesgo depende del río Piura, aportes aguas arriba, defensas, drenaje urbano y llanura de inundación.</div><div class="small" style="line-height:1.65"><b>Arquitectura:</b> lluvia de cuenca → estado del río → capacidad hidráulica/drenaje → exposición de llanura → prioridad territorial.<br>${status&&status.next_step?`<b>Siguiente paso:</b> ${status.next_step}`:'Se están identificando series hidrológicas y fuentes reutilizables.'}<br><b>Mapa:</b> el selector de capas incluye ámbitos documentales 2011/2017/2026 y tramos críticos ANA 2026, apagados por defecto. Los ámbitos <b>no son polígonos de peligro</b>; los tramos ANA son referencias lineales de puntos críticos/intervención.</div><h4 style="margin:16px 0 6px">Estado de fuentes oficiales</h4><div class="small" style="line-height:1.65"><b>GORE Piura:</b> ${gore.catalog_status||'—'} · último informe ${gore.latest_report_date||'—'}${gore.report_age_days!=null?` (${gore.report_age_days} días)`:''}.<br><b>SENAMHI Puente Ñácara:</b> dato numérico automático ${sen.numeric_river_state_available?'disponible':'pendiente'} · umbral rojo histórico de referencia ${sen.reference_red_threshold_m3s??'—'} m³/s. <b>Ese umbral no equivale a un umbral de desborde en Catacaos.</b></div>${hist.length?`<h4 style="margin:16px 0 6px">Caudales históricos de referencia</h4><div class="tablepanel" style="margin:0;overflow:auto"><table><thead><tr><th>Fecha</th><th>Evento</th><th>Caudal publicado</th><th>Control espacial</th></tr></thead><tbody>${histRows}</tbody></table></div>`:''}${design.length?`<h4 style="margin:16px 0 6px">Referencias de diseño</h4><div class="tablepanel" style="margin:0;overflow:auto"><table><thead><tr><th>Componente</th><th>Caudal</th><th>Uso</th></tr></thead><tbody>${designRows}</tbody></table></div>`:''}<div class="histnote" style="margin-top:12px"><b>Regla v0.8:</b> estos caudales no se compararán entre sí como si pertenecieran al mismo punto de control hasta homologar ubicación, tiempo de tránsito, aportes intermedios y capacidad hidráulica actual.</div>`;
  }

  async function renderForSelected(){const p=createPanel(),s=document.getElementById('histZone');if(!p||!s)return;p.style.display='block';p.innerHTML='<div class="small">Cargando validación científica v0.8…</div>';const [history,latest,sanV,huayV,status,piuraRef,piuraSource]=await Promise.all([safeJson('data/history.json'),safeJson('data/latest.json'),safeJson('data/watersheds/san_ildefonso_validation.json'),safeJson('data/watersheds/huaycoloro_validation.json'),safeJson('data/scientific_status.json'),safeJson('data/hydrology/piura_reference_model.json'),safeJson('data/hydrology/piura_source_status.json')]);const zid=s.value,zoneStatus=status&&(status.zones||[]).find(z=>z.id===zid);if(zid==='san_ildefonso')p.innerHTML=sanPanel(history||{events:[]},latest||{zones:[]},sanV);else if(zid==='chosica')p.innerHTML=huayPanel(history||{events:[]},latest||{zones:[]},huayV);else if(zid==='catacaos')p.innerHTML=catacaosPanel(zoneStatus,piuraRef,piuraSource);else p.style.display='none';}

  async function addMapOverlays(){
    if(typeof L==='undefined'||typeof map==='undefined')return;
    const catalog=await safeJson('data/map_layers.json');
    if(!catalog||catalog.production_use!==false||catalog.operational_alerting_enabled!==false)return;
    const overlays={};
    for(const entry of catalog.technical_layers||[]){
      if(!['TEST_ONLY','RESEARCH_ONLY'].includes(entry.deployment_status)||entry.map_eligible!==true||!entry.source_path)continue;
      const geo=await safeJson(entry.source_path);if(!geo)continue;
      const style=entry.style||{color:'#475569',weight:2,fillOpacity:0,dashArray:'5 5'};
      const layerName=`${entry.title} · ${entry.deployment_status}`;
      const technicalLayer=L.geoJSON(geo,{
        style,
        pointToLayer:(_feature,latlng)=>L.circleMarker(latlng,{radius:6,...style}),
        onEachFeature:(feature,featureLayer)=>{
          const p=feature.properties||{};
          const featureName=p.name||p.sector||p.quebrada_search_name||entry.title;
          featureLayer.bindPopup(`<b>${esc(featureName)}</b><br>${esc(entry.title)}<br><b>${esc(entry.deployment_status)} · sin alerta · sin puntuación de riesgo</b><br>${esc(entry.map_disclaimer)}<br><span style="font-size:11px">Fuente geométrica: ${esc(entry.source_path)} · confianza: ${esc(entry.confidence)}</span>`);
        }
      });
      overlays[layerName]=technicalLayer;
      if(entry.default_visibility===true)technicalLayer.addTo(map);
    }
    if(Object.keys(overlays).length)L.control.layers(null,overlays,{collapsed:true,position:'topright'}).addTo(map);
    const mapNode=document.getElementById('map'),summary=catalog.summary||{};
    if(mapNode&&!document.getElementById('mapLayerTrace')){
      const note=document.createElement('div');note.id='mapLayerTrace';note.className='histnote';note.style.margin='0';note.style.borderRadius='0';
      note.innerHTML=`<b>Capas técnicas no operativas:</b> ${esc(summary.technical_layers_registered)} registradas; ${esc(summary.technical_layers_visible_by_default)} visibles por defecto. <b>Expansión:</b> ${esc(summary.research_candidates_map_eligible)}/${esc(summary.research_candidates_registered)} zonas tienen geometría reproducible apta para mostrarse. Las restantes se retienen; no se sustituyen por puntos aproximados.`;
      mapNode.insertAdjacentElement('afterend',note);
    }
  }
  async function init(){const s=document.getElementById('histZone');if(s){s.addEventListener('change',renderForSelected);await renderForSelected();}await addMapOverlays();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,500));else setTimeout(init,500);
})();
