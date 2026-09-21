(() => {
  "use strict";

  const DATA = {
    rainfall: "data/phase2/subunit_rainfall_evidence_v0_1.json",
    spatial: "data/phase2/spatial_observation_contracts_v0_1.json",
    catalog: "data/phase2/catalog.json",
    scientific: "data/scientific_status.json",
    climate: "data/phase2/climate_evidence_normalized_v0_1.json",
    probe: "data/calibration/imerg_early_live_probe.json",
    daily: "data/phase2/subunit_imerg_late_v0_1.json",
    archive: "data/calibration/imerg_early_live_archive.json"
  };

  const state = {
    map: null,
    layer: null,
    last: null,
    timer: null,
    loading: false,
    mapFitted: false,
    selectedTarget: "",
    mapLayers: new Map(),
    refreshedAt: null
  };

  const labels = {
    cashahuacra: "Cashahuacra",
    shingolay: "Shingolay",
    lambayeque_chancay_lambayeque_chongoyape: "Chancay–Lambayeque / Chongoyape",
    lambayeque_zana_oyotun: "Zaña / Oyotún"
  };

  const assetLabels = {
    geometry: "Geometría",
    exposure: "Exposición",
    historical_events: "Histórico",
    observations: "Observación",
    forecast: "Forecast",
    hydraulic_context: "Hidráulica"
  };

  const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, ch => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  }[ch]));

  const human = id => labels[id] || String(id || "—")
    .replace(/^lambayeque_/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());

  const fmt = (value, digits = 3) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return "—";
    const text = value.toFixed(digits);
    return text.includes(".") ? text.replace(/\.?0+$/, "") : text;
  };

  const fmtDate = value => {
    if (!value) return "—";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleString("es-PE", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC"
    }) + " UTC";
  };

  const fetchJson = async path => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path + "?t=" + Date.now(), {
        cache: "no-store", signal: controller.signal
      });
      if (!response.ok) throw new Error(path + " HTTP " + response.status);
      return await response.json();
    } finally { clearTimeout(timer); }
  };

  const statusClass = status => {
    const s = String(status || "").toUpperCase();
    // Negative states MUST precede AVAILABLE/READY substring checks.
    if (/UNAVAILABLE|NOT_AVAILABLE|NOT_READY|NOT_YET|INCOMPLETE|MISSING|BLOCKED|INSUFFICIENT|UNKNOWN|ERROR|UNREACHABLE|STALE/.test(s)) return "v08-bad";
    if (/PARTIAL|CANDIDATE|REVIEW|TEST|RESEARCH/.test(s)) return "v08-warn";
    if (/READY|AVAILABLE|PRESENT|ELIGIBLE|COMPLETE/.test(s)) return "v08-ok";
    return "v08-neutral";
  };

  const usableWindow = w => !!w && w.available === true &&
    typeof w.accum_mm === "number" && Number.isFinite(w.accum_mm) && w.accum_mm >= 0;
  const targetKey = (candidate, contract) =>
    "phase2_subunit:" + candidate.candidate_id + ":" + contract.subunit_id;
  const geometryPath = ref => {
    const path = typeof ref.path === "string" ? ref.path.replace(/^site\//, "") : "";
    if (!/^data\/[A-Za-z0-9_./-]+\.geojson$/.test(path) || path.split("/").includes("..")) {
      throw new Error("Ruta geométrica no válida");
    }
    return path;
  };
  const ageText = (value, now = Date.now()) => {
    const ms = value ? Date.parse(value) : NaN;
    return Number.isFinite(ms) && ms <= now ? fmt((now - ms) / 3600000, 1) + " h" : "no calculable";
  };

  function continuityForTarget(archive, targetId, n = 48, anchorUtc = null) {
    if (!Number.isInteger(n) || n < 1 || n > 48) throw new Error("Ventana de diagnóstico no válida");
    const step = 30 * 60 * 1000;
    const observed = new Map();
    const allTimes = [];
    for (const granule of (archive.granules || [])) {
      const t = Date.parse(granule.time_utc);
      if (!Number.isFinite(t) || t % step !== 0) continue;
      allTimes.push(t);
      const rows = (granule.targets || []).filter(r => r.target_id === targetId);
      for (const row of rows) {
        const v = row.accum_30min_mm;
        if (typeof v !== "number" || !Number.isFinite(v) || v < 0) continue;
        if (observed.has(t) && observed.get(t) !== v) observed.set(t, null);
        else if (!observed.has(t)) observed.set(t, v);
      }
    }
    let anchor = anchorUtc ? Date.parse(anchorUtc) : NaN;
    if (!Number.isFinite(anchor) || anchor % step !== 0) {
      anchor = allTimes.length ? Math.max(...allTimes) : NaN;
    }
    if (!Number.isFinite(anchor)) return {expected: n, present: null, missing: null, anchor: null};
    const missing = [];
    for (let i = n - 1; i >= 0; i -= 1) {
      const t = anchor - i * step;
      if (!observed.has(t) || observed.get(t) === null) missing.push(new Date(t).toISOString());
    }
    return {expected: n, present: n - missing.length, missing, anchor: new Date(anchor).toISOString()};
  }

  const chip = (text, kind) => "<span class=\"v08-chip " + (kind || statusClass(text)) + "\">" + esc(text || "—") + "</span>";

  const windowValue = w => {
    if (!usableWindow(w)) return "<span class=\"v08-missing\">Datos insuficientes</span>";
    return "<b>" + fmt(w.accum_mm) + " mm</b>";
  };

  const windowDetail = w => {
    if (!w) return "Sin evidencia";
    if (usableWindow(w)) {
      return esc((w.start_utc || w.start_date || "") + (w.end_utc || w.end_date ? " → " + (w.end_utc || w.end_date) : ""));
    }
    const available = w.available_samples != null ? w.available_samples : w.days_available;
    const required = w.required_samples != null ? w.required_samples : w.days_required;
    if (available != null && required != null) return esc(available + "/" + required + " muestras; continuidad insuficiente");
    return esc(w.evidence_status || "INSUFFICIENT_EVIDENCE");
  };

  function injectStyles() {
    if (document.getElementById("v08-monitor-style")) return;
    const style = document.createElement("style");
    style.id = "v08-monitor-style";
    style.textContent = [
      "body.v08-active .legacy-global{display:none!important}",
      ".v08-map-tools{padding:10px 14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--line)}",
      ".v08-map-tools select{max-width:100%;flex:1;min-width:180px}",
      ".v08-map-status{padding:8px 14px;font-size:12px;background:#f5f8fa;line-height:1.5}",
      ".v08-map-label{font-size:11px;font-weight:700;background:#fff;color:#163b4e;border:1px solid #819cac;padding:3px 5px;white-space:normal;max-width:180px;box-shadow:none}",
      ".v08-target button{margin-top:8px;font-weight:700;font-size:12px}",
      ".v08-time{margin-top:8px;padding-top:7px;border-top:1px solid var(--line);font-size:11px;line-height:1.5;color:#42596a}",
      ".v08-diagnostic{border:1px solid var(--line);border-radius:8px;padding:10px;margin:8px 0;font-size:12px;line-height:1.5}",
      ".v08-diagnostic code{white-space:normal;overflow-wrap:anywhere}",
      "button:disabled{cursor:not-allowed;opacity:.5}",
      ".v08-shell{display:grid;gap:16px}",
      ".v08-hero{background:linear-gradient(120deg,#062f4f,#0a668f);color:white;border-radius:14px;padding:18px 20px;display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap}",
      ".v08-hero h2{margin:3px 0 7px;font-size:24px}",
      ".v08-hero p{margin:0;max-width:900px;line-height:1.45}",
      ".v08-banner{background:#fff4cf;border-left:5px solid #d2a000;padding:11px 14px;border-radius:9px;line-height:1.45}",
      ".v08-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}",
      ".v08-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}",
      ".v08-kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px}",
      ".v08-kpi span{font-size:11px;color:var(--muted);display:block}",
      ".v08-kpi b{font-size:24px;display:block;margin-top:5px}",
      ".v08-grid2{display:grid;grid-template-columns:1.2fr .8fr;gap:16px}",
      ".v08-panel{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}",
      ".v08-panel-head{padding:13px 15px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}",
      ".v08-panel-head h3{margin:0;font-size:17px}",
      ".v08-pad{padding:14px}",
      "#v08map{height:480px}",
      ".v08-legend{padding:10px 14px;border-top:1px solid var(--line);font-size:12px;color:var(--muted);line-height:1.45}",
      ".v08-targets{display:grid;gap:10px;max-height:540px;overflow:auto;padding:12px}",
      ".v08-target{border:1px solid var(--line);border-radius:11px;padding:12px;background:#fff}",
      ".v08-target h4{margin:2px 0 3px;font-size:15px}",
      ".v08-target-meta{font-size:11px;color:var(--muted);margin-bottom:9px}",
      ".v08-rain-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}",
      ".v08-rain{background:#f5f8fa;border-radius:8px;padding:8px;min-height:65px}",
      ".v08-rain span:first-child{font-size:10px;color:var(--muted);display:block;margin-bottom:4px}",
      ".v08-rain b{font-size:15px}",
      ".v08-missing{font-size:11px;color:#8a5b00;font-weight:700}",
      ".v08-small{font-size:11px;color:var(--muted);line-height:1.4}",
      ".v08-chip{display:inline-block;padding:4px 7px;border-radius:999px;font-size:10px;font-weight:800;white-space:nowrap}",
      ".v08-ok{background:#e4f4e9;color:#1d6539}",
      ".v08-warn{background:#fff0c8;color:#745800}",
      ".v08-bad{background:#fde3e3;color:#8b1919}",
      ".v08-neutral{background:#edf1f4;color:#4f6474}",
      ".v08-table{overflow:auto}",
      ".v08-table table{min-width:1250px}",
      ".v08-table td,.v08-table th{vertical-align:top}",
      ".v08-assets{display:flex;gap:4px;flex-wrap:wrap}",
      ".v08-source-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}",
      ".v08-source{border:1px solid var(--line);border-radius:10px;padding:11px;background:#fafcfd}",
      ".v08-source h4{margin:0 0 5px;font-size:14px}",
      ".v08-core-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}",
      ".v08-core{border:1px solid var(--line);border-radius:10px;padding:12px}",
      ".v08-core h4{margin:0 0 6px}",
      ".v08-error{padding:18px;background:#fdeaea;color:#8a2530;border-radius:10px}",
      ".v08-section-note{font-size:12px;color:var(--muted);line-height:1.45}",
      "@media(max-width:1100px){.v08-kpis{grid-template-columns:repeat(3,1fr)}.v08-grid2{grid-template-columns:1fr}.v08-core-grid{grid-template-columns:1fr}.v08-source-grid{grid-template-columns:1fr}}",
      "@media(max-width:650px){.v08-kpis{grid-template-columns:repeat(2,1fr)}.v08-rain-grid{grid-template-columns:repeat(2,1fr)}#v08map{height:360px}}"
    ].join("\n");
    document.head.appendChild(style);
  }

  function prepareLegacy() {
    const wrap = document.querySelector(".wrap");
    if (!wrap) return;
    [".notice", ".toolbar", ".statusline", ".kpis"].forEach(selector => {
      const node = wrap.querySelector(":scope > " + selector);
      if (node) node.classList.add("legacy-global");
    });

    const legacyTab = document.querySelector('.tab[data-tab="op"]');
    if (legacyTab) legacyTab.textContent = "Legado v0.7.1";

    document.querySelectorAll(".tab").forEach(tab => {
      if (tab.dataset.tab !== "v08monitor") {
        tab.addEventListener("click", () => document.body.classList.remove("v08-active"));
      }
    });
  }

  function prepareHeader() {
    document.title = "IRFEN Perú v0.8 · Monitoreo científico";
    const h1 = document.querySelector("header h1");
    if (h1) h1.innerHTML = "IRFEN Perú <span style=\"font-weight:400\">v0.8</span>";
    const subtitle = document.querySelector("header h1 + div");
    if (subtitle) subtitle.textContent = "Observación hidrometeorológica · validación científica · alerta temprana en desarrollo";
  }

  function ensureUI() {
    if (document.getElementById("v08monitor")) return;
    const tabs = document.querySelector(".tabs");
    const firstSection = document.querySelector(".section");
    if (!tabs || !firstSection) return;

    const tab = document.createElement("div");
    tab.className = "tab active";
    tab.dataset.tab = "v08monitor";
    tab.textContent = "Monitoreo v0.8";
    tabs.insertBefore(tab, tabs.firstChild);

    const section = document.createElement("section");
    section.id = "v08monitor";
    section.className = "section active";
    section.innerHTML =
      "<div class=\"v08-shell\">" +
        "<div class=\"v08-hero\">" +
          "<div><div style=\"font-size:11px;font-weight:800;letter-spacing:.08em;opacity:.85\">IRFEN · PANEL CIENTÍFICO</div><h2>Monitoreo y avance v0.8</h2><p>Datos observados y estados de validación publicados por IRFEN. Los colores de esta vista describen disponibilidad y madurez científica; no representan niveles de riesgo.</p></div>" +
          "<div>" + chip("RESEARCH / TEST MODE", "v08-warn") + " " + chip("PRODUCCIÓN: NO", "v08-bad") + "</div>" +
        "</div>" +
        "<div class=\"v08-banner\"><b>Uso científico:</b> esta vista no sustituye avisos oficiales de SENAMHI, INDECI, CENEPRED, ANA o INGEMMET. <b>Ausencia de datos nunca se interpreta como lluvia cero ni como riesgo bajo.</b></div>" +
        "<div class=\"v08-toolbar\"><button id=\"v08refresh\">Actualizar panel</button><span class=\"v08-small\" id=\"v08updated\">Cargando…</span><span class=\"v08-small\">Actualización automática de pantalla cada 5 min.</span></div>" +
        "<div class=\"v08-kpis\" id=\"v08kpis\"></div>" +
        "<div class=\"v08-grid2\">" +
          "<div class=\"v08-panel\"><div class=\"v08-panel-head\"><h3>Mapa hidrológico monitorizado</h3><span>" + chip("RESEARCH_ONLY", "v08-warn") + "</span></div><div id=\"v08map\"></div><div class=\"v08-legend\">Polígonos incorporados desde contratos espaciales reproducibles. El estilo identifica unidades de investigación, no riesgo ni alerta.</div></div>" +
          "<div class=\"v08-panel\"><div class=\"v08-panel-head\"><h3>Lluvia observada por unidad</h3><span class=\"v08-small\">NASA IMERG Early + Late</span></div><div class=\"v08-targets\" id=\"v08targets\"></div></div>" +
        "</div>" +
        "<div class=\"v08-panel\"><div class=\"v08-panel-head\"><h3>Avance científico Phase-2 · 18 candidatos</h3><span class=\"v08-section-note\">La tabla muestra activos, contrato y gate; no una clasificación de riesgo.</span></div><div class=\"v08-table\"><table><thead><tr><th>Candidato</th><th>Territorio</th><th>Activos científicos</th><th>Contrato</th><th>Mecanismo</th><th>Activation gate</th></tr></thead><tbody id=\"v08candidateRows\"></tbody></table></div></div>" +
        "<div class=\"v08-grid2\">" +
          "<div class=\"v08-panel\"><div class=\"v08-panel-head\"><h3>Fuentes y carriles de evidencia</h3></div><div class=\"v08-pad\"><div class=\"v08-source-grid\" id=\"v08sources\"></div></div></div>" +
          "<div class=\"v08-panel\"><div class=\"v08-panel-head\"><h3>Núcleo v0.8</h3></div><div class=\"v08-pad\"><div class=\"v08-core-grid\" id=\"v08core\"></div></div></div>" +
        "</div>" +
      "</div>";

    firstSection.parentNode.insertBefore(section, firstSection);
    document.querySelectorAll(".section").forEach(s => {
      if (s.id !== "v08monitor") s.classList.remove("active");
    });
    document.querySelectorAll(".tab").forEach(t => {
      if (t.dataset.tab !== "v08monitor") t.classList.remove("active");
    });

    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
      tab.classList.add("active");
      section.classList.add("active");
      document.body.classList.add("v08-active");
      setTimeout(() => {
        if (state.map) state.map.invalidateSize();
      }, 100);
    });

    document.body.classList.add("v08-active");
    document.getElementById("v08refresh").addEventListener("click", load);
    const tools = document.createElement("div");
    tools.className = "v08-map-tools";
    tools.innerHTML = '<label for="v08unitSelect">Unidad:</label><select id="v08unitSelect" aria-label="Seleccionar unidad hidrológica"><option value="">Seleccionar…</option></select><button type="button" id="v08focus">Ver en el mapa</button><button type="button" id="v08all">Ver todas</button>';
    const mapNode = document.getElementById("v08map");
    mapNode.before(tools);
    const report = document.createElement("div");
    report.id = "v08mapStatus"; report.className = "v08-map-status";
    report.setAttribute("role", "status"); report.textContent = "Comprobando geometrías…";
    tools.after(report);
    document.getElementById("v08focus").onclick = () => focusTarget(document.getElementById("v08unitSelect").value);
    document.getElementById("v08unitSelect").onchange = e => focusTarget(e.target.value);
    document.getElementById("v08all").onclick = fitAll;
    document.getElementById("v08targets").addEventListener("click", e => {
      const button = e.target.closest("button[data-v08-target]");
      if (button) focusTarget(button.dataset.v08Target);
    });
    const diagnostics = document.createElement("div"); diagnostics.className = "v08-panel";
    diagnostics.innerHTML = '<div class="v08-panel-head"><h3>Continuidad y trazabilidad IMERG Early</h3></div><div class="v08-pad" id="v08continuity"></div>';
    section.querySelector(".v08-shell").appendChild(diagnostics);
  }

  function renderKpis(rain, spatial, catalog) {
    const s = rain.summary || {};
    const ss = spatial.summary || {};
    const zones = catalog.zones || [];
    const openGates = zones.filter(z => z.activation_gate && z.activation_gate !== "BLOCKED").length;
    const approved = zones.filter(z => z.contract_status === "APPROVED").length;
    const items = [
      ["Candidatos Phase-2", ss.candidate_count != null ? ss.candidate_count : zones.length],
      ["Unidades con contrato espacial", ss.research_subunit_contract_count ?? "—"],
      ["Early 1h disponibles", s.early_targets_with_1h ?? "—"],
      ["Late 24h / 72h / 7d", (s.late_targets_with_24h ?? "—") + " / " + (s.late_targets_with_72h ?? "—") + " / " + (s.late_targets_with_7d ?? "—")],
      ["Contratos aprobados", approved],
      ["Activation gates abiertos", openGates]
    ];
    document.getElementById("v08kpis").innerHTML = items.map(item =>
      "<div class=\"v08-kpi\"><span>" + esc(item[0]) + "</span><b>" + esc(item[1]) + "</b></div>"
    ).join("");
  }

  function renderTargets(rain, spatial) {
    const contracts = new Map();
    (spatial.candidate_records || []).forEach(candidate => {
      (candidate.subunit_contracts || []).forEach(contract => contracts.set(targetKey(candidate, contract), contract));
    });
    const daily = new Map(((state.last.daily || {}).targets || []).map(r => [r.target_id, r]));
    const probe = state.last.probe || {};
    document.getElementById("v08targets").innerHTML = (rain.targets || []).map(target => {
      const early = (target.near_real_time_imerg_early || {}).windows || {};
      const late = (target.daily_imerg_late || {}).windows || {};
      const contract = contracts.get(target.target_id) || {};
      const geom = contract.geometry_ref || {};
      const rawDaily = daily.get(target.target_id) || {};
      const observationDate = (late["24h"] || {}).end_date;
      const day = (rawDaily.series || []).find(r => r.date === observationDate);
      const coverage = (day || {}).sampling || {};
      const lastStart = Object.values(early).filter(w => usableWindow(w) && w.end_utc)
        .map(w => w.end_utc).sort().pop();
      const cards = [
        ["Early 1h", early["1h"]], ["Early 3h", early["3h"]],
        ["Early 6h", early["6h"]], ["Early 12h", early["12h"]],
        ["Early 24h", early["24h"]], ["Late 24h", late["24h"]],
        ["Late 72h", late["72h"]], ["Late 7d", late["7d"]]
      ];
      const scope = String(contract.contract_scope || "").includes("OFFICIAL")
        ? "Unidad hidrológica oficial; no delimita una quebrada local ni un área inundable"
        : "Microcuenca candidata; outlet y área oficiales pendientes";
      return '<div class="v08-target">' +
        '<h4>' + esc(human(target.subunit_id)) + '</h4>' +
        '<div class="v08-target-meta">' + esc(fmt(geom.declared_area_km2, 3)) + ' km² · ' + esc(geom.geometry_type || "—") + '</div>' +
        chip(target.activation_gate || "DESCONOCIDO", "v08-neutral") + ' ' + chip("RESEARCH_ONLY", "v08-warn") +
        '<div class="v08-small">' + esc(scope) + '</div>' +
        '<button type="button" data-v08-target="' + esc(target.target_id) + '" disabled>Ver en el mapa</button>' +
        '<div class="v08-rain-grid" style="margin-top:8px">' + cards.map(pair =>
          '<div class="v08-rain"><span>' + esc(pair[0]) + '</span>' + windowValue(pair[1]) +
          '<div class="v08-small">' + windowDetail(pair[1]) + '</div></div>').join("") + '</div>' +
        '<div class="v08-time"><b>Early · último inicio de muestra:</b> ' + esc(fmtDate(lastStart)) +
        '<br><b>Antigüedad de esa muestra:</b> ' + esc(ageText(lastStart)) +
        '<br><b>Registro de adquisición Early:</b> ' + esc(fmtDate(probe.generated_at)) +
        '<br><b>Late · fecha diaria observada:</b> ' + esc(observationDate || "—") +
        '<br><b>Registro de adquisición Late:</b> ' + esc(fmtDate((target.daily_imerg_late || {}).artifact_generated_at)) +
        '<br><b>Cobertura espacial Late de esa fecha:</b> ' + esc(fmt(coverage.valid_geometry_coverage_pct, 2)) +
        '% · celdas válidas ' + esc(fmt(coverage.valid_cells, 0)) + '/' + esc(fmt(coverage.cells_intersected, 0)) +
        '<br>Cobertura completa no equivale a precisión local. La lluvia satelital no valida una activación.</div></div>';
    }).join("") || '<div class="v08-small">No hay unidades de investigación monitorizadas.</div>';
  }

  function renderContinuity(rain, archive, probe) {
    const root = document.getElementById("v08continuity");
    if (!Array.isArray(archive.granules)) {
      root.textContent = "Archivo de gránulos no disponible: no se puede diagnosticar continuidad. No se sustituye por cero.";
      return;
    }
    const stamps = [...new Set((archive.records || []).map(r => Date.parse(r.probe_generated_at)).filter(Number.isFinite))].sort((a,b) => a-b);
    const lastGap = stamps.length > 1 ? (stamps[stamps.length-1] - stamps[stamps.length-2]) / 3600000 : null;
    let html = '<p class="v08-section-note">Diagnóstico independiente de intervalos de 30 minutos sobre el archivo retenido. No crea acumulados ni modifica las validaciones. Un hueco aquí significa <b>sin muestra válida en este archivo</b>; no demuestra que NASA carezca del gránulo.</p>' +
      '<p class="v08-small"><b>Intervalo entre las dos últimas adquisiciones registradas:</b> ' + esc(fmt(lastGap, 2)) + ' h. ' +
      '<b>Último estado consultado:</b> ' + esc(probe.status || "DESCONOCIDO") + '. ' +
      '<b>Descargas de la última adquisición:</b> ' + esc(fmt(probe.granules_downloaded, 0)) + '.</p>';
    html += (rain.targets || []).map(t => {
      const d = continuityForTarget(archive, t.target_id, 48, probe.latest_granule_time_utc);
      const short = continuityForTarget(archive, t.target_id, 6, d.anchor);
      return '<div class="v08-diagnostic"><b>' + esc(human(t.subunit_id)) + '</b> · últimas 24h de la fuente: <b>' +
        esc(fmt(d.present,0)) + '/48</b> intervalos válidos. <b>Huecos:</b> ' + esc(d.missing ? d.missing.length : "no calculable") +
        '<div class="v08-small">Ancla: inicio de última muestra ' + esc(fmtDate(d.anchor)) + '.</div>' +
        '<details><summary>Ver intervalos faltantes (UTC)</summary><b>Últimas 3h:</b> <code>' + esc(short.missing ? short.missing.join(", ") || "ninguno" : "no calculable") +
        '</code><br><b>Últimas 24h:</b> <code>' + esc(d.missing ? d.missing.join(", ") || "ninguno" : "no calculable") + '</code></details></div>';
    }).join("");
    root.innerHTML = html;
  }

  function renderCandidates(catalog) {
    const zones = catalog.zones || [];
    const rows = zones.map(z => {
      const assets = z.asset_status || {};
      const chips = Object.keys(assetLabels).map(key => {
        const value = assets[key] || "MISSING";
        return "<span title=\"" + esc(assetLabels[key]) + "\">" + chip(assetLabels[key] + ": " + value, statusClass(value)) + "</span>";
      }).join(" ");
      return "<tr>" +
        "<td><b>" + esc(z.system_name || z.candidate_id) + "</b><br><span class=\"v08-small\">" + esc(z.candidate_id) + "</span></td>" +
        "<td>" + esc(z.department || "—") + "<br><span class=\"v08-small\">" + esc(z.province_or_corridor || "") + "</span></td>" +
        "<td><div class=\"v08-assets\">" + chips + "</div></td>" +
        "<td>" + chip(z.contract_status || "DRAFT", statusClass(z.contract_status)) + "<br><span class=\"v08-small\">" + esc(z.readiness_stage || "") + "</span></td>" +
        "<td>" + chip(z.mechanism_status || "—", statusClass(z.mechanism_status)) + "</td>" +
        "<td>" + chip(z.activation_gate || "BLOCKED", z.activation_gate === "BLOCKED" ? "v08-bad" : "v08-warn") + "</td>" +
      "</tr>";
    }).join("");
    document.getElementById("v08candidateRows").innerHTML = rows;
  }

  function renderSources(rain, scientific, climate) {
    const target = (rain.targets || [])[0] || {};
    const early = target.near_real_time_imerg_early || {};
    const late = target.daily_imerg_late || {};
    const nr = scientific.near_real_time_rainfall_lane || {};
    const registry = climate.source_registry || [];
    const rows = [
      {
        title: "NASA GPM IMERG Early",
        status: (state.last.probe || {}).status || "UNKNOWN",
        body: (early.source || nr.source || "—") + " · Registro de adquisición: " + fmtDate((state.last.probe || {}).generated_at) + ". Consultar la antigüedad de las observaciones en cada ficha; fuente accesible no significa dato actual."
      },
      {
        title: "NASA GPM IMERG Late",
        status: late.status || "UNKNOWN",
        body: (late.source || "NASA GPM IMERG Late Daily") + " · última observación " + (late.latest_observation_date || "—") + "."
      }
    ];

    registry.forEach(src => {
      if (src.source_id && (src.source_id.includes("GOES19") || src.source_id.includes("GEOS_CF"))) {
        rows.push({
          title: src.source_id.includes("GOES19") ? "GOES-19 RRQPE" : "NASA GEOS-CF",
          status: src.source_kind || "TEST_ONLY",
          body: "Registros: " + (src.record_count == null ? "—" : src.record_count) + " · " + (src.note || "")
        });
      }
    });

    document.getElementById("v08sources").innerHTML = rows.map(row =>
      "<div class=\"v08-source\"><div style=\"display:flex;justify-content:space-between;gap:8px;align-items:flex-start\"><h4>" + esc(row.title) + "</h4>" + chip(row.status, statusClass(row.status)) + "</div><div class=\"v08-small\">" + esc(row.body) + "</div></div>"
    ).join("");
  }

  function renderCore(scientific) {
    const zones = scientific.zones || [];
    document.getElementById("v08core").innerHTML = zones.map(z => {
      let secondary = "";
      if (z.hydraulic_gate) secondary = typeof z.hydraulic_gate === "string" ? z.hydraulic_gate : z.hydraulic_gate.status;
      if (!secondary && z.river_state) secondary = z.river_state.secondary_proxy_status || z.river_state.primary_numeric_automation;
      return "<div class=\"v08-core\"><h4>" + esc(z.name || z.id) + "</h4>" +
        chip(z.test_status || "TEST_ONLY", statusClass(z.test_status)) +
        "<div class=\"v08-small\" style=\"margin-top:8px\"><b>Producción:</b> " + (z.production_ready ? "READY" : "NO") +
        (secondary ? "<br><b>Gate/contexto:</b> " + esc(secondary) : "") + "</div></div>";
    }).join("");
  }

  function selectFeature(documentJson, selector) {
    const features = documentJson && documentJson.type === "FeatureCollection"
      ? (documentJson.features || []) : [documentJson];
    if (!selector || !selector.property) return [];
    return features.filter(feature => feature && feature.properties &&
      feature.properties[selector.property] === selector.value);
  }

  function fitAll() {
    if (!state.map || !state.mapLayers.size) return;
    let bounds = null;
    state.mapLayers.forEach(layer => {
      bounds = bounds ? bounds.extend(layer.getBounds()) : L.latLngBounds(layer.getBounds().getSouthWest(), layer.getBounds().getNorthEast());
    });
    state.map.invalidateSize();
    state.map.fitBounds(bounds.pad(0.12), {maxZoom: 9});
    state.mapFitted = true;
  }

  function focusTarget(id) {
    const layer = state.mapLayers.get(id);
    if (!layer || !state.map) return;
    state.selectedTarget = id;
    document.getElementById("v08unitSelect").value = id;
    state.map.invalidateSize();
    state.map.fitBounds(layer.getBounds().pad(0.15), {maxZoom: 16});
    state.mapLayers.forEach((item, key) => item.setStyle({weight: key === id ? 4 : 2}));
    layer.bringToFront(); layer.openPopup();
    document.getElementById("v08map").scrollIntoView({block:"center", behavior:"smooth"});
  }

  async function renderMap(spatial, rain) {
    const contracts = [];
    (spatial.candidate_records || []).forEach(candidate => {
      (candidate.subunit_contracts || []).forEach(contract => {
        if (contract.contract_status === "RESEARCH_SAMPLING_ELIGIBLE") contracts.push({candidate, contract});
      });
    });
    const errors = [];
    const selector = document.getElementById("v08unitSelect");
    const previousSelection = state.selectedTarget;
    const targets = new Map((rain.targets || []).map(t => [t.target_id, t]));
    const docs = new Map();
    if (typeof L !== "undefined" && !state.map) {
      state.map = L.map("v08map").setView([-9.3, -76.5], 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18, attribution: "&copy; OpenStreetMap contributors"
      }).addTo(state.map);
      state.layer = L.layerGroup().addTo(state.map);
    }
    const replacement = typeof L !== "undefined" ? L.layerGroup() : null;
    const layers = new Map();
    for (const {candidate, contract} of contracts) {
      const id = targetKey(candidate, contract);
      try {
        if (!replacement) throw new Error("Biblioteca cartográfica no disponible");
        if (layers.has(id)) throw new Error("Identificador de unidad duplicado");
        const ref = contract.geometry_ref || {};
        const path = geometryPath(ref);
        if (!docs.has(path)) docs.set(path, fetchJson(path));
        const documentJson = await docs.get(path);
        const features = selectFeature(documentJson, ref.feature_selector);
        if (features.length !== 1) throw new Error("El selector debe resolver exactamente una geometría");
        const feature = features[0];
        if (!feature.geometry || !["Polygon", "MultiPolygon"].includes(feature.geometry.type)) throw new Error("Geometría de área ausente o no válida");
        const target = targets.get(id) || {};
        const early = ((target.near_real_time_imerg_early || {}).windows || {})["1h"];
        const late = (target.daily_imerg_late || {}).windows || {};
        const official = String(contract.contract_scope || "").includes("OFFICIAL");
        const geo = L.geoJSON(feature, {style: {
          color: official ? "#2563eb" : "#0f766e", weight: id === previousSelection ? 4 : 2,
          fillColor: official ? "#93c5fd" : "#5eead4", fillOpacity: 0.14, dashArray: "5 4"
        }});
        if (!geo.getBounds().isValid()) throw new Error("Límites geométricos no válidos");
        geo.bindTooltip(esc(human(contract.subunit_id)), {permanent: true, direction: "auto", className: "v08-map-label"});
        const rows = [["Early 1h", early], ["Late 24h", late["24h"]], ["Late 72h", late["72h"]], ["Late 7d", late["7d"]]];
        geo.bindPopup('<b>' + esc(human(contract.subunit_id)) + '</b><br>Área declarada: ' + esc(fmt(ref.declared_area_km2)) + ' km²<br>RESEARCH_ONLY · Activation gate: ' + esc(contract.activation_gate || "DESCONOCIDO") + '<br>' +
          rows.map(([label, w]) => esc(label) + ': ' + windowValue(w) + '<br><small>' + windowDetail(w) + '</small>').join('<br>') +
          '<br><small>Fechas de las observaciones; no se actualizan al refrescar la pantalla. No representa riesgo ni alerta.</small>');
        geo.on("click", () => {state.selectedTarget = id; selector.value = id;});
        geo.addTo(replacement); layers.set(id, geo);
      } catch (error) { errors.push(human(contract.subunit_id) + ": " + String(error.message || error)); }
    }
    if (state.map && replacement) {
      replacement.addTo(state.map);
      if (state.layer) state.map.removeLayer(state.layer);
      state.layer = replacement;
    }
    state.mapLayers = layers;
    selector.innerHTML = '<option value="">Seleccionar…</option>' + contracts.map(({candidate, contract}) => {
      const id = targetKey(candidate, contract);
      return '<option value="' + esc(id) + '"' + (layers.has(id) ? '' : ' disabled') + '>' + esc(human(contract.subunit_id)) + (layers.has(id) ? '' : ' · error de carga') + '</option>';
    }).join("");
    selector.value = layers.has(previousSelection) ? previousSelection : "";
    document.querySelectorAll("button[data-v08-target]").forEach(button => {button.disabled = !layers.has(button.dataset.v08Target);});
    document.getElementById("v08all").disabled = !layers.size;
    document.getElementById("v08focus").disabled = !layers.size;
    document.getElementById("v08mapStatus").innerHTML = '<b>Geometrías esperadas:</b> ' + contracts.length + ' · <b>Cargadas:</b> ' + layers.size + ' · <b>Con error:</b> ' + errors.length +
      (errors.length ? '<details open><summary>Detalles de carga</summary>' + errors.map(esc).join('<br>') + '</details>' : ' · Use el selector para ver las unidades pequeñas.');
    // Refresh replaces evidence/layers but never recenters the user's viewport.
    if (!state.mapFitted && layers.size) fitAll();
  }

  async function load() {
    if (state.loading) return;
    state.loading = true;
    const updated = document.getElementById("v08updated");
    const refresh = document.getElementById("v08refresh");
    if (refresh) refresh.disabled = true;
    if (updated) updated.textContent = "Consultando archivos publicados; esto no implica nuevas observaciones…";
    try {
      const values = await Promise.all([fetchJson(DATA.rainfall), fetchJson(DATA.spatial), fetchJson(DATA.catalog)]);
      const [rainfall, spatial, catalog] = values;
      if (!Array.isArray(rainfall.targets) || !Array.isArray(spatial.candidate_records) || !Array.isArray(catalog.zones)) throw new Error("Contrato de datos incompleto");
      for (const data of [rainfall, spatial, catalog]) {
        if (data.production_use !== false || data.production_ready !== false) throw new Error("Estado científico incompatible con esta vista de investigación");
      }
      const optionalKeys = ["scientific", "climate", "probe", "daily", "archive"];
      const extraResults = await Promise.allSettled(optionalKeys.map(key => fetchJson(DATA[key])));
      const extra = {}; const failed = [];
      extraResults.forEach((result, index) => {
        const key = optionalKeys[index];
        extra[key] = result.status === "fulfilled" ? result.value : {};
        if (result.status !== "fulfilled") failed.push(DATA[key]);
      });
      state.last = {rainfall, spatial, catalog, ...extra};
      renderKpis(rainfall, spatial, catalog);
      renderTargets(rainfall, spatial);
      renderCandidates(catalog);
      renderSources(rainfall, extra.scientific, extra.climate);
      renderCore(extra.scientific);
      renderContinuity(rainfall, extra.archive, extra.probe);
      await renderMap(spatial, rainfall);
      state.refreshedAt = new Date().toISOString();
      if (updated) updated.innerHTML = '<b>Consulta de pantalla:</b> ' + esc(fmtDate(state.refreshedAt)) +
        ' · <b>Consolidación del archivo:</b> ' + esc(fmtDate(rainfall.generated_at)) +
        ' · Las fechas observadas y la antigüedad figuran en cada unidad.' +
        (failed.length ? '<br><b>Fuentes complementarias no cargadas:</b> ' + failed.map(esc).join(', ') : '');
    } catch (error) {
      if (updated) updated.innerHTML = '<span class="v08-error">Actualización fallida: ' + esc(error.message || error) +
        '. ' + (state.refreshedAt ? 'Se conserva la vista anterior, consultada ' + esc(fmtDate(state.refreshedAt)) + '; no es una adquisición nueva.' : 'No hay datos confirmados para esta vista.') + '</span>';
    } finally {state.loading = false; if (refresh) refresh.disabled = false;}
  }

  function init() {
    injectStyles();
    prepareHeader();
    prepareLegacy();
    ensureUI();
    load();
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(load, 5 * 60 * 1000);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {fmt, statusClass, usableWindow, windowValue, selectFeature, geometryPath, continuityForTarget, ageText};
  }
  if (typeof document !== "undefined") init();
})();