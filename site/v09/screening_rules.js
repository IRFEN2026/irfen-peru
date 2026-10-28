/* IRFEN v0.9 — Indicadores de cribado científico, NO riesgo ni alertas.
   Sin umbrales de activación: clasifica evidencias disponibles, no probabilidad de desborde.
   Funciones puras para navegador y Node; RESEARCH_ONLY / TEST_ONLY. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.IRFEN_SCREENING = api;
})(typeof window === "object" ? window : undefined, function () {
  "use strict";
  const DEPARTMENTS = [
    "Amazonas","Áncash","Apurímac","Arequipa","Ayacucho","Cajamarca","Callao",
    "Cusco","Huancavelica","Huánuco","Ica","Junín","La Libertad","Lambayeque",
    "Lima","Loreto","Madre de Dios","Moquegua","Pasco","Piura","Puno",
    "San Martín","Tacna","Tumbes","Ucayali"
  ];
  function normalize(v) {
    return String(v || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z]/g, "");
  }
  const KNOWN = new Map(DEPARTMENTS.map(d => [normalize(d), d]));
  function department(name) { return KNOWN.get(normalize(name)) || null; }
  function zoneDepartment(id) {
    const key = String(id || "");
    if (key.startsWith("tumbes_")) return "Tumbes";
    if (key.startsWith("piura_")) return "Piura";
    if (key.startsWith("lambayeque_")) return "Lambayeque";
    if (key.startsWith("lalibertad_")) return "La Libertad";
    return null; // no inferir departamento a partir de proximidad o nombre libre
  }
  function ms(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    const n = Date.parse(value);
    return Number.isFinite(n) ? n : null;
  }
  function recent(date, now, maxHours) {
    const time = ms(date);
    return time !== null && Number.isFinite(now) && Number.isFinite(maxHours) &&
      maxHours > 0 && time <= now && now - time <= maxHours * 3600000;
  }
  function completeWindow(w) {
    return !!w && typeof w.accum_mm === "number" && Number.isFinite(w.accum_mm) &&
      w.accum_mm >= 0 && (w.status === undefined || w.status === "CALCULADO");
  }
  function rainEvidence(z, now, config) {
    const im = z && z.imerg;
    const end = im && im.window_end_utc;
    const fresh = recent(end, now, Number(config.imerg_stale_after_h || 0));
    const cov = im && im.coverage_24h || {};
    const complete = Number.isInteger(cov.required_half_hours) &&
      cov.required_half_hours > 0 &&
      Number.isInteger(cov.available_half_hours) &&
      cov.available_half_hours === cov.required_half_hours &&
      Array.isArray(cov.missing_half_hours_utc) &&
      cov.missing_half_hours_utc.length === 0 &&
      completeWindow(im.windows && im.windows["24h"]);
    const w6 = im && im.windows && im.windows["6h"];
    return {fresh, complete, available: Boolean(fresh && complete),
      mm24: fresh && complete ? im.windows["24h"].accum_mm : null,
      mm6: fresh && complete && completeWindow(w6) ? w6.accum_mm : null,
      end: end || null};
  }
  function warningEvidence(z, now, capturedAt) {
    const recentCapture = recent(capturedAt, now, 3); // freshness de cruce del visor
    const relevant = (z && z.avisos || []).filter(a => {
      const start = ms(a.validity_start), end = ms(a.validity_end);
      return start !== null && end !== null && start <= now && now <= end &&
        !["CANCELADO","REEMPLAZADO"].includes(a.status);
    });
    return {recentCapture, observedInPackage: relevant.length,
      verifiedCurrent: recentCapture ? relevant.length : 0,
      keys: relevant.map(a => a.aviso_key),
      relationMethods: [...new Set(relevant.map(a => a.relation_method).filter(Boolean))]};
  }
  function screenZone(z, now, config, capturedAt) {
    const rain = rainEvidence(z, now, config);
    const warn = warningEvidence(z, now, capturedAt);
    // "Concurrencia" es prioridad DE LECTURA, jamás una probabilidad calibrada.
    let key, order;
    if (warn.verifiedCurrent && rain.available && rain.mm24 > 0) { key = "CONCURRENCIA"; order = 0; }
    else if (warn.verifiedCurrent) { key = "AVISO_OFICIAL"; order = 1; }
    else if (rain.available && rain.mm24 > 0) { key = "LLUVIA_SATELITAL"; order = 2; }
    else if (warn.observedInPackage && !warn.recentCapture) { key = "AVISO_SIN_CRUCE_RECIENTE"; order = 3; }
    else if (rain.available) { key = "LECTURA_DISPONIBLE"; order = 4; }
    else { key = "SIN_LECTURA_VIGENTE"; order = 5; }
    return {key, order, rain, warn};
  }
  const LABELS = Object.freeze({
    CONCURRENCIA:"Coinciden indicios: revisar primero",
    AVISO_OFICIAL:"Aviso oficial con cruce reciente",
    LLUVIA_SATELITAL:"Lluvia satelital detectada",
    AVISO_SIN_CRUCE_RECIENTE:"Aviso registrado; cruce desactualizado",
    LECTURA_DISPONIBLE:"Datos recientes; sin afirmar riesgo bajo",
    SIN_LECTURA_VIGENTE:"Información insuficiente o antigua"
  });
  const GUARDS = Object.freeze({
    deployment_status:"RESEARCH_ONLY", test_mode:"TEST_ONLY", production_use:false,
    production_ready:false, operational_alerting_enabled:false, public_alerting:false,
    activation_gate:"BLOCKED", missing_data_rule:"UNKNOWN_NOT_LOW_RISK",
    decision_thresholds:null, hydraulic_factors:null, map_publishable:false
  });
  function accept(bundle) {
    return !!bundle && Object.keys(GUARDS).every(k => Object.prototype.hasOwnProperty.call(bundle,k) &&
      bundle[k] === GUARDS[k]);
  }
  return Object.freeze({DEPARTMENTS, LABELS, GUARDS, normalize, department,
    zoneDepartment, ms, recent, completeWindow, rainEvidence, warningEvidence, screenZone, accept});
});
