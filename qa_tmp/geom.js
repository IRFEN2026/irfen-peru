() => { const m=document.getElementById('map').getBoundingClientRect();
  const levels=[...document.querySelectorAll('#map .leaflet-tile-container')];
  const top=levels.reduce((a,c)=>(+c.style.zIndex>+(a?a.style.zIndex:-1e9)?c:a),null);
  const all=[...document.querySelectorAll('#map img.leaflet-tile')];
  const tiles=(top?[...top.querySelectorAll('img.leaflet-tile.leaflet-tile-loaded')]:[]).length?[...top.querySelectorAll('img.leaflet-tile.leaflet-tile-loaded')]:all.filter(t=>t.classList.contains('leaflet-tile-loaded'));
  const r=tiles.map(t=>t.getBoundingClientRect());
  let overlap=0; for(let i=0;i<r.length;i++)for(let j=i+1;j<r.length;j++){const a=r[i],b=r[j];if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)overlap++;}
  let uncovered=0; for(let i=0;i<=8;i++)for(let j=0;j<=8;j++){const x=m.left+2+(m.width-4)*i/8,y=m.top+2+(m.height-4)*j/8;if(!r.some(b=>x>=b.left&&x<=b.right&&y>=b.top&&y<=b.bottom))uncovered++;}
  let leaked=0; for(const [x,y] of [[m.left-4,m.top+m.height/2],[m.right+4,m.top+m.height/2],[m.left+m.width/2,m.top-4],[m.left+m.width/2,m.bottom+4]]){const e=document.elementFromPoint(x,y);if(e&&e.classList&&e.classList.contains('leaflet-tile'))leaked++;}
  const fully_outside=r.filter(b=>b.right<=m.left||b.left>=m.right||b.bottom<=m.top||b.top>=m.bottom).length;
  const sheet=[...document.styleSheets].find(s=>(s.href||'').includes('leaflet.css')); let rules=null; try{rules=sheet?sheet.cssRules.length:null}catch(e){rules='err'}
  return {leaflet_css_rules:rules, pane:getComputedStyle(document.querySelector('#map .leaflet-tile-pane')).position, loaded_tiles:r.length,
    tile_hosts:[...new Set(tiles.map(t=>new URL(t.src).host))], overlap, uncovered_of_81:uncovered, leaked_outside:leaked, fully_outside_hidden:fully_outside,
    map_overflow:getComputedStyle(document.getElementById('map')).overflow, css_flag:document.getElementById('map').dataset.leafletCss||null}; }
