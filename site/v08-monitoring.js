(() => {
  "use strict";

  const DATA = {
    rainfall: "data/phase2/subunit_rainfall_evidence_v0_1.json",
    spatial: "data/phase2/spatial_observation_contracts_v0_1.json",
    catalog: "data/phase2/catalog.json",
    scientific: "data/scientific_status.json",
    climate: "data/phase2/climate_evidence_normalized_v0_1.json"
  };

  const state = {
    map: null,
    layer: null,
    last: null,
    timer: null
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
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits).replace(/\.?0+$/, "") : "—";
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
    const response = await fetch(path + "?t=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error(path + " HTTP " + response.status);
    return response.json();
  };

  const statusClass = status => {
    const s = String(status || "").toUpperCase();
    if (s.includes("READY") || s.includes("AVAILABLE") || s.includes("PRESENT") || s.includes("ELIGIBLE")) return "v08-ok";
    if (s.includes("PARTIAL") || s.includes("CANDIDATE") || s.includes("REVIEW") || s.includes("TEST")) return "v08-warn";
    if (s.includes("MISSING") || s.includes("BLOCKED") || s.includes("INSUFFICIENT") || s.includes("UNKNOWN")) return "v08-bad";
    return "v08-neutral";
  };

  const chip = (text, kind) => "<span class=\"v08-chip " + (kind || statusClass(text)) + "\">" + esc(text || "—") + "</span>";

  const windowValue = w => {
    if (!w || !w.available || w.accum_mm == null) return "<span class=\"v08-missing\">Datos insuficientes</span>";
    return "<b>" + fmt(w.accum_mm) + " mm</b>";
  };

  const windowDetail = w => {
    if (!w) return "Sin evidencia";
    if (w.available) {
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
  }

  function renderKpis(rain, spatial, catalog) {
    const s = rain.summary || {};
    const ss = spatial.summary || {};
    const zones = catalog.zones || [];
    const openGates = zones.filter(z => z.activation_gate && z.activation_gate !== "BLOCKED").length;
    const approved = zones.filter(z => z.contract_status === "APPROVED").length;
    const items = [
      ["Candidatos Phase-2", ss.candidate_count != null ? ss.candidate_count : zones.length],
      ["Unidades con contrato espacial", ss.research_subunit_contract_count || 0],
      ["Early 1h disponibles", s.early_targets_with_1h || 0],
      ["Late 24h / 72h / 7d", (s.late_targets_with_24h || 0) + " / " + (s.late_targets_with_72h || 0) + " / " + (s.late_targets_with_7d || 0)],
      ["Contratos aprobados", approved],
      ["Activation gates abiertos", openGates]
    ];
    document.getElementById("v08kpis").innerHTML = items.map(item =>
      "<div class=\"v08-kpi\"><span>" + esc(item[0]) + "</span><b>" + esc(item[1]) + "</b></div>"
    ).join("");
  }

  function renderTargets(rain, spatial) {
    const contractsBySubunit = {};
    (spatial.candidate_records || []).forEach(candidate => {
      (candidate.subunit_contracts || []).forEach(contract => {
        contractsBySubunit[contract.subunit_id] = contract;
      });
    });

    const targets = rain.targets || [];
    document.getElementById("v08targets").innerHTML = targets.map(target => {
      const early = (target.near_real_time_imerg_early || {}).windows || {};
      const late = (target.daily_imerg_late || {}).windows || {};
      const contract = contractsBySubunit[target.subunit_id] || {};
      const geom = contract.geometry_ref || {};
      const coverage = target.daily_imerg_late && target.daily_imerg_late.status
        ? target.daily_imerg_late.status
        : "—";
      const cards = [
        ["Early 1h", early["1h"]],
        ["Early 3h", early["3h"]],
        ["Early 6h", early["6h"]],
        ["Late 24h", late["24h"]],
        ["Late 72h", late["72h"]],
        ["Late 7d", late["7d"]]
      ];
      return "<div class=\"v08-target\">" +
        "<div style=\"display:flex;justify-content:space-between;gap:8px;align-items:flex-start\">" +
          "<div><h4>" + esc(human(target.subunit_id)) + "</h4><div class=\"v08-target-meta\">" +
            esc(fmt(target.declared_area_km2, 3)) + " km² · " + esc(geom.geometry_type || "geometría de área") +
          "</div></div>" +
          "<div>" + chip(target.activation_gate || "BLOCKED", "v08-bad") + "</div>" +
        "</div>" +
        "<div class=\"v08-rain-grid\">" +
          cards.map(pair => "<div class=\"v08-rain\"><span>" + esc(pair[0]) + "</span>" + windowValue(pair[1]) + "<div class=\"v08-small\">" + windowDetail(pair[1]) + "</div></div>").join("") +
        "</div>" +
        "<div class=\"v08-small\" style=\"margin-top:8px\"><b>Early:</b> " + esc((target.near_real_time_imerg_early || {}).source || "—") +
        " · <b>Late:</b> " + esc((target.daily_imerg_late || {}).source || "—") +
        " · <b>Estado Late:</b> " + esc(coverage) + "</div>" +
      "</div>";
    }).join("") || "<div class=\"v08-small\">No hay unidades de investigación monitorizadas.</div>";
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
        status: nr.last_confirmed_status || (early.source ? "SOURCE_AVAILABLE" : "UNKNOWN"),
        body: (early.source || nr.source || "—") + " · resolución temporal " + (nr.temporal_resolution_minutes || 30) + " min · resolución espacial " + (nr.grid_resolution_deg || 0.1) + "°."
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
      ? (documentJson.features || [])
      : [documentJson];
    if (!selector || !selector.property) return features.filter(Boolean);
    return features.filter(feature =>
      feature && feature.properties && feature.properties[selector.property] === selector.value
    );
  }

  async function renderMap(spatial, rain) {
    if (typeof L === "undefined") return;
    if (!state.map) {
      state.map = L.map("v08map").setView([-9.3, -76.5], 5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
        attribution: "&copy; OpenStreetMap contributors"
      }).addTo(state.map);
      state.layer = L.layerGroup().addTo(state.map);
    }
    state.layer.clearLayers();

    const targets = {};
    (rain.targets || []).forEach(t => { targets[t.subunit_id] = t; });
    const docs = {};
    const bounds = [];
    const contracts = [];
    (spatial.candidate_records || []).forEach(candidate => {
      (candidate.subunit_contracts || []).forEach(contract => {
        if (contract.contract_status === "RESEARCH_SAMPLING_ELIGIBLE") {
          contracts.push({ candidate, contract });
        }
      });
    });

    for (let i = 0; i < contracts.length; i += 1) {
      const item = contracts[i];
      const ref = item.contract.geometry_ref || {};
      if (!ref.path) continue;
      const path = ref.path.replace(/^site\//, "");
      if (!docs[path]) {
        try {
          docs[path] = await fetchJson(path);
        } catch (_) {
          continue;
        }
      }
      const features = selectFeature(docs[path], ref.feature_selector);
      features.forEach(feature => {
        if (!feature || !feature.geometry) return;
        const target = targets[item.contract.subunit_id] || {};
        const early = ((target.near_real_time_imerg_early || {}).windows || {})["1h"];
        const late = (target.daily_imerg_late || {}).windows || {};
        const geo = L.geoJSON(feature, {
          style: {
            color: item.contract.contract_scope && item.contract.contract_scope.includes("OFFICIAL") ? "#2563eb" : "#0f766e",
            weight: 2,
            fillColor: item.contract.contract_scope && item.contract.contract_scope.includes("OFFICIAL") ? "#93c5fd" : "#5eead4",
            fillOpacity: 0.14,
            dashArray: "5 4"
          }
        }).addTo(state.layer);
        geo.bindPopup(
          "<b>" + esc(human(item.contract.subunit_id)) + "</b><br>" +
          "Área declarada: " + esc(fmt(ref.declared_area_km2, 3)) + " km²<br>" +
          "Estado: RESEARCH_ONLY · " + esc(item.contract.contract_status) + "<br>" +
          "Early 1h: " + (early && early.available ? esc(fmt(early.accum_mm)) + " mm" : "datos insuficientes") + "<br>" +
          "Late 24h: " + (late["24h"] && late["24h"].available ? esc(fmt(late["24h"].accum_mm)) + " mm" : "datos insuficientes") + "<br>" +
          "Late 72h: " + (late["72h"] && late["72h"].available ? esc(fmt(late["72h"].accum_mm)) + " mm" : "datos insuficientes") + "<br>" +
          "Late 7d: " + (late["7d"] && late["7d"].available ? esc(fmt(late["7d"].accum_mm)) + " mm" : "datos insuficientes") + "<br>" +
          "Activation gate: " + esc(item.contract.activation_gate || "BLOCKED")
        );
        const b = geo.getBounds();
        if (b && b.isValid()) bounds.push(b);
      });
    }

    if (bounds.length) {
      const merged = bounds.reduce((acc, b) => acc ? acc.extend(b) : L.latLngBounds(b.getSouthWest(), b.getNorthEast()), null);
      state.map.fitBounds(merged.pad(0.12), { maxZoom: 9 });
    }
  }

  async function load() {
    const updated = document.getElementById("v08updated");
    if (updated) updated.textContent = "Actualizando datos reales…";
    try {
      const values = await Promise.all([
        fetchJson(DATA.rainfall),
        fetchJson(DATA.spatial),
        fetchJson(DATA.catalog),
        fetchJson(DATA.scientific),
        fetchJson(DATA.climate)
      ]);
      const rainfall = values[0];
      const spatial = values[1];
      const catalog = values[2];
      const scientific = values[3];
      const climate = values[4];
      state.last = { rainfall, spatial, catalog, scientific, climate };

      renderKpis(rainfall, spatial, catalog);
      renderTargets(rainfall, spatial);
      renderCandidates(catalog);
      renderSources(rainfall, scientific, climate);
      renderCore(scientific);
      await renderMap(spatial, rainfall);

      if (updated) {
        updated.innerHTML = "<b>Datos del panel:</b> " + esc(fmtDate(rainfall.generated_at)) +
          " · <b>Phase-2:</b> " + esc(rainfall.deployment_status || "RESEARCH_ONLY") +
          " · <b>Gate:</b> " + esc(rainfall.activation_gate || "BLOCKED");
      }
    } catch (error) {
      if (updated) updated.innerHTML = "<span class=\"v08-error\">Error cargando panel v0.8: " + esc(error.message || error) + "</span>";
    }
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

  init();
})();