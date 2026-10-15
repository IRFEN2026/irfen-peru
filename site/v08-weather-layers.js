(function(){
  'use strict';

  const NASA_WMS_BEST='https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi';
  const NASA_WMS_NRT='https://gibs.earthdata.nasa.gov/wms/epsg3857/nrt/wms.cgi';
  const SOURCE_NOTE='Contexto visual externo. No modifica el cálculo, estado, umbrales ni alertas IRFEN.';
  const attached=new WeakSet();
  // Estados visibles del mosaico IMERG (solo conexión con NASA GIBS; no es un estado del modelo).
  const RAIN_STATE={off:['APAGADA',''],loading:['CARGANDO','wait'],on:['ACTIVA','on'],error:['SIN MOSAICOS','err']};

  function isoDay(offset){
    const d=new Date();
    d.setUTCDate(d.getUTCDate()+offset);
    return d.toISOString().slice(0,10);
  }

  function makeWms(baseUrl,layerName,date,opacity){
    return L.tileLayer.wms(baseUrl,{
      layers:layerName,
      styles:'',
      format:'image/png',
      transparent:true,
      version:'1.3.0',
      time:date,
      opacity:opacity,
      attribution:'NASA Earthdata GIBS'
    });
  }

  function addControl(targetMap,label){
    if(!targetMap || typeof L==='undefined' || attached.has(targetMap)) return;
    attached.add(targetMap);

    let rain=null;
    let clouds=null;
    let date=isoDay(-1);
    let opacity=.62;

    const Control=L.Control.extend({
      options:{position:'topright'},
      onAdd:function(){
        const box=L.DomUtil.create('div','irfen-weather-control');
        // Cerrado por defecto: el mapa es el protagonista. El botón muestra el estado aunque el panel esté plegado.
        box.innerHTML=
          '<button type="button" class="iw-toggle" data-iw="toggle" aria-expanded="false" title="Capas meteorológicas · '+label+'">'+
            '<span class="iw-toggle-label">Meteorología</span><span class="iw-active-pill" data-iw="rain-pill">APAGADA</span><span class="iw-vis-tag" data-iw="vis-tag" hidden>Visible</span>'+
          '</button>'+
          '<div class="iw-panel" data-iw="panel" role="dialog" aria-label="Capas meteorológicas" hidden>'+
          '<div class="iw-head"><b>Capas meteorológicas</b><span>'+label+'</span><button type="button" class="iw-close" data-iw="close" aria-label="Cerrar">×</button></div>'+
          '<label class="iw-rain-label"><input type="checkbox" data-iw="rain"> NASA · lluvia IMERG NRT</label>'+
          '<label class="iw-check"><input type="checkbox" data-iw="clouds"> NASA · imagen satelital visible</label>'+
          '<label class="iw-row">Fecha <select data-iw="day">'+
            '<option value="-1" selected>Ayer UTC (predeterminado)</option><option value="0">Hoy UTC (si está disponible)</option><option value="-2">Hace 2 días</option>'+
          '</select></label>'+
          '<label class="iw-row">Opacidad <input data-iw="opacity" type="range" min="20" max="90" value="62" aria-label="Opacidad de las capas meteorológicas"></label>'+
          '<div class="iw-status" data-iw="status"><b>Conexión IMERG:</b> inactiva.</div><div class="iw-rain-legend" data-iw="rain-legend" hidden><div><b>Precipitación IMERG</b> · contexto visual</div><div class="iw-empty">Los colores son los del mosaico publicado por NASA GIBS. Aquí no se muestra una escala cuantitativa. Sin color = sin precipitación representada en el mosaico visible.</div></div>'+
          '<details class="iw-more"><summary>Notas metodológicas</summary>'+
            '<p>Por defecto se usa ayer UTC para reducir falsos vacíos por latencia NRT.</p>'+
            '<div class="iw-senamhi"><b>SENAMHI</b> · conector WMS preparado; se habilitará cuando quede fijado un endpoint/capa institucional estable.</div>'+
            '<div class="iw-note">'+SOURCE_NOTE+'</div>'+
          '</details>'+
          '</div>';

        L.DomEvent.disableClickPropagation(box);
        L.DomEvent.disableScrollPropagation(box);

        const toggle=box.querySelector('[data-iw="toggle"]');
        const panel=box.querySelector('[data-iw="panel"]');
        const closeBtn=box.querySelector('[data-iw="close"]');
        const rainInput=box.querySelector('[data-iw="rain"]');
        const cloudInput=box.querySelector('[data-iw="clouds"]');
        const dayInput=box.querySelector('[data-iw="day"]');
        const opacityInput=box.querySelector('[data-iw="opacity"]');
        const statusEl=box.querySelector('[data-iw="status"]');
        const rainPill=box.querySelector('[data-iw="rain-pill"]');
        const visTag=box.querySelector('[data-iw="vis-tag"]');
        const rainLegend=box.querySelector('[data-iw="rain-legend"]');

        function setOpen(open){
          panel.hidden=!open;
          toggle.setAttribute('aria-expanded',String(open));
          box.classList.toggle('is-open',open);
          if(open){
            rainInput.focus({preventScroll:true});
            // Un solo panel abierto sobre el mapa: avisa a los demás paneles para que se plieguen.
            box.dispatchEvent(new CustomEvent('irfen:map-panel-open',{bubbles:true}));
          }
        }
        document.addEventListener('irfen:map-panel-open',function(ev){if(!box.contains(ev.target)&&!panel.hidden)setOpen(false);});
        toggle.addEventListener('click',function(){setOpen(panel.hidden);});
        closeBtn.addEventListener('click',function(){setOpen(false);toggle.focus({preventScroll:true});});
        box.addEventListener('keydown',function(ev){if(ev.key==='Escape'&&!panel.hidden){setOpen(false);toggle.focus({preventScroll:true});}});

        function setRainState(key){
          const s=RAIN_STATE[key]||RAIN_STATE.off;
          rainPill.textContent=s[0];
          rainPill.className='iw-active-pill'+(s[1]?' '+s[1]:'');
          rainPill.dataset.state=key;
        }

        function rebuild(){
          if(rainLegend) rainLegend.hidden=!rainInput.checked;
          if(visTag) visTag.hidden=!cloudInput.checked;
          if(rain){targetMap.removeLayer(rain);rain=null;}
          if(clouds){targetMap.removeLayer(clouds);clouds=null;}

          if(rainInput.checked){
            setRainState('loading');
            if(statusEl) statusEl.innerHTML='<b>Conexión IMERG:</b> cargando '+date+'…';
            rain=makeWms(NASA_WMS_NRT,'IMERG_Precipitation_Rate_30min_v7_NRT',date,opacity);
            rain.on('load',function(){
              setRainState('on');
              if(statusEl) statusEl.innerHTML='<b>Conexión IMERG:</b> cargada · '+date+'. Si no aparece color, no hay precipitación representada en los mosaicos visibles.';
            });
            rain.on('tileerror',function(){
              setRainState('error');
              if(statusEl) statusEl.innerHTML='<b>Conexión IMERG:</b> error recuperando mosaicos NASA GIBS para '+date+'.';
            });
            rain.addTo(targetMap);
          } else {
            setRainState('off');
            if(statusEl) statusEl.innerHTML='<b>Conexión IMERG:</b> inactiva.';
          }
          if(cloudInput.checked){
            clouds=makeWms(NASA_WMS_BEST,'VIIRS_SNPP_CorrectedReflectance_TrueColor',date,Math.min(opacity,.78));
            clouds.addTo(targetMap);
          }
        }

        rainInput.addEventListener('change',rebuild);
        cloudInput.addEventListener('change',rebuild);
        dayInput.addEventListener('change',function(){
          date=isoDay(Number(dayInput.value)||0);
          rebuild();
        });
        opacityInput.addEventListener('input',function(){
          opacity=(Number(opacityInput.value)||62)/100;
          if(rain) rain.setOpacity(opacity);
          if(clouds) clouds.setOpacity(Math.min(opacity,.78));
        });

        return box;
      }
    });

    new Control().addTo(targetMap);
  }

  function installStyles(){
    if(document.getElementById('irfen-weather-style')) return;
    const s=document.createElement('style');
    s.id='irfen-weather-style';
    s.textContent=
      '.irfen-weather-control{font:12px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#1d2f3c}'+
      '.iw-toggle{display:inline-flex;align-items:center;gap:7px;height:32px;padding:0 10px;background:#fff;color:#1d2f3c;border:1px solid #c9d5de;border-radius:8px;box-shadow:0 1px 4px rgba(12,45,65,.18);font:600 12px/1 inherit;cursor:pointer}'+
      '.iw-toggle:hover,.irfen-weather-control.is-open .iw-toggle{background:#f1f6f9;border-color:#9fb4c3}'+
      '.iw-toggle:focus-visible,.iw-close:focus-visible{outline:2px solid #1f63b8;outline-offset:2px}'+
      '.iw-panel{margin-top:6px;width:272px;max-height:70vh;overflow:auto;background:#fff;padding:10px 12px;border:1px solid #c9d5de;border-radius:10px;box-shadow:0 6px 20px rgba(12,45,65,.18)}'+
      '.iw-panel[hidden]{display:none}'+
      '.irfen-weather-control label{display:block;margin:7px 0;cursor:pointer}'+
      '.irfen-weather-control input[type=checkbox]{margin:0 6px 0 0;vertical-align:-2px}'+
      '.iw-head{display:flex;flex-wrap:wrap;align-items:center;gap:0 8px;border-bottom:1px solid #e2e9ee;padding-bottom:7px;margin-bottom:4px}'+
      '.iw-head span{order:3;flex-basis:100%;font-size:10px;color:#6d7f8c}.iw-head .iw-close{margin-left:auto}'+
      '.iw-close{border:0;background:transparent;font-size:18px;line-height:1;color:#53687a;cursor:pointer;padding:0 2px}'+
      '.iw-row{display:flex!important;justify-content:space-between;align-items:center;gap:8px}'+
      '.iw-row select{max-width:150px;padding:3px 4px;font:inherit}.iw-row input[type=range]{width:130px}'+
      '.iw-status{margin-top:8px;padding:6px 8px;background:#eef6fb;border-radius:6px;color:#36586f;font-size:11px}'+
      '.iw-active-pill{padding:2px 7px;border-radius:999px;background:#eef1f3;color:#5f707b;font-size:10px;font-weight:700;letter-spacing:.02em}'+
      '.iw-active-pill.on{background:#dff3e5;color:#1d6539}.iw-active-pill.wait{background:#fff4d6;color:#6b4e00}.iw-active-pill.err{background:#fde8e8;color:#8a1c1c}'+
      '.iw-vis-tag{padding:2px 6px;border-radius:999px;background:#e8eef9;color:#28477a;font-size:10px;font-weight:700}'+
      '.iw-rain-legend{margin-top:8px;padding:7px 8px;background:#f7fafc;border:1px solid #dfe8ee;border-radius:7px;color:#42596a;font-size:11px}.iw-empty{margin-top:4px;color:#687b8c}'+
      '.iw-more{margin-top:8px;border-top:1px solid #e2e9ee;padding-top:6px;color:#5c6f7d;font-size:11px}'+
      '.iw-more summary{cursor:pointer;color:#36586f;font-weight:600}.iw-more p{margin:6px 0}'+
      '.iw-senamhi{background:#f5f8fa;padding:6px 7px;border-radius:6px;margin:6px 0}.iw-note{margin-top:6px}'+
      '@media(max-width:700px){.iw-panel{width:260px;max-width:78vw;max-height:60vh}.iw-toggle-label{font-size:11px}}';
    document.head.appendChild(s);
  }

  installStyles();

  // API estable para que cualquier mapa Leaflet de IRFEN pueda adjuntar
  // explícitamente las capas meteorológicas sin depender del orden de eventos.
  window.IRFENWeatherLayers = {
    attach:function(targetMap,label){
      addControl(targetMap,label||'Vista experta');
    }
  };

  // Mapa operativo principal, definido en index.html.
  try{
    if(typeof map!=='undefined' && map) addControl(map,'Vista operativa');
  }catch(_){}

  // Otros mapas de la plataforma pueden anunciarse sin acoplar este módulo a su implementación.
  window.addEventListener('irfen:map-ready',function(ev){
    const d=ev.detail||{};
    addControl(d.map,d.label||'Vista experta');
  });
})();
