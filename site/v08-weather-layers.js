(function(){
  'use strict';

  const NASA_WMS='https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi';
  const SOURCE_NOTE='Contexto visual externo. No modifica el cálculo, estado, umbrales ni alertas IRFEN.';
  const attached=new WeakSet();

  function isoDay(offset){
    const d=new Date();
    d.setUTCDate(d.getUTCDate()+offset);
    return d.toISOString().slice(0,10);
  }

  function makeWms(layerName,date,opacity){
    return L.tileLayer.wms(NASA_WMS,{
      layers:layerName,
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
    let date=isoDay(0);
    let opacity=.62;

    const Control=L.Control.extend({
      options:{position:'topright'},
      onAdd:function(){
        const box=L.DomUtil.create('div','irfen-weather-control leaflet-bar');
        box.innerHTML=
          '<div class="iw-head"><b>Capas meteorológicas</b><span>'+label+'</span></div>'+
          '<label><input type="checkbox" data-iw="rain"> NASA · lluvia IMERG NRT</label>'+
          '<label><input type="checkbox" data-iw="clouds"> NASA · nubes / imagen visible</label>'+
          '<label class="iw-row">Fecha <select data-iw="day">'+
            '<option value="0">Hoy UTC</option><option value="-1">Ayer UTC</option><option value="-2">Hace 2 días</option>'+
          '</select></label>'+
          '<label class="iw-row">Opacidad <input data-iw="opacity" type="range" min="20" max="90" value="62"></label>'+
          '<div class="iw-senamhi"><b>SENAMHI</b> · conector WMS preparado; se habilitará cuando quede fijado un endpoint/capa institucional estable.</div>'+
          '<div class="iw-note">'+SOURCE_NOTE+'</div>';

        L.DomEvent.disableClickPropagation(box);
        L.DomEvent.disableScrollPropagation(box);

        const rainInput=box.querySelector('[data-iw="rain"]');
        const cloudInput=box.querySelector('[data-iw="clouds"]');
        const dayInput=box.querySelector('[data-iw="day"]');
        const opacityInput=box.querySelector('[data-iw="opacity"]');

        function rebuild(){
          if(rain){targetMap.removeLayer(rain);rain=null;}
          if(clouds){targetMap.removeLayer(clouds);clouds=null;}

          if(rainInput.checked){
            rain=makeWms('IMERG_Precipitation_Rate_30min_v7_NRT',date,opacity);
            rain.addTo(targetMap);
          }
          if(cloudInput.checked){
            clouds=makeWms('VIIRS_SNPP_CorrectedReflectance_TrueColor',date,Math.min(opacity,.78));
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
      '.irfen-weather-control{background:#fff;width:260px;padding:10px 11px;border:1px solid #cfdbe4;border-radius:10px;box-shadow:0 2px 12px rgba(12,45,65,.16);font:12px/1.35 Arial,sans-serif;color:#213442}'+
      '.irfen-weather-control label{display:block;margin:7px 0;cursor:pointer}'+
      '.irfen-weather-control input[type=checkbox]{margin-right:6px}'+
      '.iw-head{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid #e2e9ee;padding-bottom:7px;margin-bottom:5px}'+
      '.iw-head span{font-size:10px;color:#6d7f8c}.iw-row{display:flex!important;justify-content:space-between;align-items:center;gap:8px}'+
      '.iw-row select{max-width:120px;padding:4px}.iw-row input[type=range]{width:120px}'+
      '.iw-note,.iw-senamhi{margin-top:8px;padding-top:7px;border-top:1px solid #e2e9ee;color:#5c6f7d;font-size:10px}'+
      '.iw-senamhi{background:#f5f8fa;padding:7px;border-radius:6px}'+
      '@media(max-width:700px){.irfen-weather-control{width:220px}}';
    document.head.appendChild(s);
  }

  installStyles();

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