"use strict";
/* IRFEN v0.9 · navegación común (RESEARCH_ONLY / TEST_ONLY).
   Secciones sobre las páginas existentes, sin cambiar sus URL:
     Resumen               -> resumen.html
     Radar nacional        -> vigilancia_nacional.html (sin predicción de riesgo)
     Mapa                  -> territorio.html
     Quebradas e inventario-> inventario.html (inventario documental nacional; el visor conserva su listado regional)
     Lluvia y avisos       -> index.html
     Evidencia y avances   -> resumen.html#avances
   Solo enlaces: no lee datos, no calcula estados. Un enlace cuya página no está disponible (p. ej. la puerta de
   publicación retiró el visor) se oculta en lugar de llevar a un 404. */
(function () {
  const SECTIONS = [
    {id: "resumen", label: "Resumen", href: "resumen.html"},
    {id: "nacional", label: "Vigilancia nacional", href: "vigilancia_nacional.html"},
    {id: "mapa", label: "Mapa", href: "territorio.html"},
    {id: "inventario", label: "Quebradas e inventario", href: "inventario.html"},
    {id: "lluvia", label: "Lluvia y avisos", href: "index.html"},
    {id: "avances", label: "Evidencia y avances", href: "resumen.html#avances"},
  ];
  function current() {
    const page = (location.pathname.split("/").pop() || "index.html").toLowerCase();
    const hash = location.hash.replace("#", "").toLowerCase();
    if (page === "vigilancia_nacional.html") return "nacional";
    if (page === "territorio.html") return "mapa";
    if (page === "inventario.html") return "inventario";
    if (page === "resumen.html") return hash === "avances" ? "avances" : "resumen";
    return "lluvia";
  }
  function render() {
    let host = document.getElementById("irfen-nav");
    if (!host) { host = document.createElement("div"); host.id = "irfen-nav"; document.body.insertBefore(host, document.body.firstChild); }
    const cur = current();
    host.innerHTML = `<nav class="irfen-nav" aria-label="Secciones de IRFEN v0.9">
      <a class="irfen-brand" href="resumen.html">IRFEN <span>v0.9</span></a>
      <div class="irfen-links">${SECTIONS.map(s =>
        `<a href="${s.href}" data-section="${s.id}"${s.id === cur ? ' aria-current="page"' : ""}>${s.label}</a>`).join("")}</div>
      <span class="irfen-tag" title="Versión experimental de investigación. No emite alertas.">Experimental · no es alerta</span>
    </nav>`;
    // on narrow screens the links scroll sideways: keep the current section in view
    const links = host.querySelector(".irfen-links"), here = links.querySelector("[aria-current]");
    if (here && links.scrollWidth > links.clientWidth) links.scrollLeft = Math.max(0, here.offsetLeft - links.offsetLeft - (links.clientWidth - here.offsetWidth) / 2);
    // hide links whose page is not served (never send the reader to a 404)
    const seen = {};
    host.querySelectorAll("a[data-section]").forEach(a => {
      const file = a.getAttribute("href").split("#")[0];
      if (!(file in seen)) seen[file] = fetch(file, {method: "HEAD", cache: "no-store"}).then(r => r.ok).catch(() => false);
      seen[file].then(ok => { if (!ok) a.hidden = true; });
    });
  }
  const css = `.irfen-nav{position:static;z-index:auto;display:flex;flex-wrap:nowrap;align-items:center;gap:12px;padding:8px 16px;
    background:var(--surface,#fcfcfb);border-bottom:1px solid var(--border,#dcdbd6);font:14px/1.3 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
  .irfen-brand{font-weight:700;color:var(--ink,#0b0b0b);text-decoration:none;white-space:nowrap}.irfen-brand span{font-weight:500;color:var(--ink-2,#52514e)}
  .irfen-links{display:flex;gap:4px;overflow-x:auto;scrollbar-width:thin;flex:1 1 auto;min-width:0}
  .irfen-links a{white-space:nowrap;padding:6px 10px;border-radius:999px;color:var(--ink-2,#52514e);text-decoration:none}
  .irfen-links a:hover,.irfen-links a:focus-visible{background:var(--surface-2,#f2f1ee);color:var(--ink,#0b0b0b)}
  .irfen-links a[aria-current="page"]{background:var(--ink,#0b0b0b);color:var(--surface,#fcfcfb)}
  .irfen-tag{white-space:nowrap;font-size:12px;padding:3px 8px;border-radius:999px;background:var(--warn-bg,#fff4d6);color:var(--warn-ink,#6b4e00)}
  @media (max-width:720px){.irfen-nav{flex-wrap:wrap;gap:6px 10px;padding:8px 12px}.irfen-links{order:3;flex-basis:100%}}`;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render); else render();
  window.addEventListener("hashchange", () => {
    const cur = current();
    document.querySelectorAll("#irfen-nav a[data-section]").forEach(a => a.toggleAttribute("aria-current", a.dataset.section === cur));
    document.querySelectorAll("#irfen-nav a[aria-current]").forEach(a => a.setAttribute("aria-current", "page"));
  });
})();
