"use strict";
// Copy of the SHARED-RULES block of site/v09/index.html (kept identical by tests/test_v09_territory.py).
/* SHARED-RULES-BEGIN — mirror of scripts/v09_zone_rain_engine.py (aviso_status_at, imerg_usable_at, goes_usable_at,
   geos_windows_at, review_priority, sort_key). Pure functions, no DOM: tests/test_v09_rule_parity.py runs them with
   node against the Python engine on the same cases. A stale observation counts as missing, never as zero. */
const NEGATIVE_RELATION = "BASIN_IN_LISTED_DEPARTMENT_OUTSIDE_LISTED_PROVINCES";
const PRIORITY_ORDER = ["R1_REVISION_PRIORITARIA","R2_VIGILANCIA_ACTIVA","R3_PREPARAR_VIGILANCIA","R4_LLUVIA_OBSERVADA_SIN_AVISO","R5_DATOS_INSUFICIENTES","R6_SIN_SENAL_EN_DATOS_DISPONIBLES"];
const DEFAULT_FRESHNESS = {imerg_stale_after_h:12, goes_stale_after_min:90, geos_max_cycle_age_h:54};
function tms(ts){ // ISO (any offset), "Z", or numpy datetime64 without zone (UTC) -> epoch ms
  if (!ts) return null;
  let t = String(ts).replace(/(\.\d{3})\d+/, "$1");
  if (!/(Z|[+-]\d\d:\d\d)$/.test(t)) t += "Z";
  const v = Date.parse(t); return isNaN(v) ? null : v;
}
function avisoStatusAt(a, t){
  if (a.cancellation_text || a.status === "CANCELADO") return "CANCELADO";
  if (a.superseded_by || a.status === "REEMPLAZADO") return "REEMPLAZADO";
  const s = tms(a.validity_start), e = tms(a.validity_end);
  if (s == null || e == null || e < s) return "DESCONOCIDO";
  return t < s ? "FUTURO" : t <= e ? "VIGENTE" : "VENCIDO";
}
function imergUsableAt(im, t, F){ const e = tms(im && im.window_end_utc); return e != null && t - e <= F.imerg_stale_after_h * 3.6e6; }
function goesUsableAt(g, t, F){ const e = tms(g && g.scan_end_utc); return !!g && g.status === "CALCULADO" && e != null && t - e <= F.goes_stale_after_min * 6e4; }
function geosWindowsAt(g, t, F){
  if (!g || g.status !== "CALCULADO") return {status:"NO_DISPONIBLE", reason:(g && g.reason) || "sin pronóstico GEOS-CF para esta zona"};
  const start = tms(g.dataset_time_start);
  if (start == null) return {status:"NO_DISPONIBLE", reason:"ciclo GEOS-CF sin fecha: no se puede comprobar su antigüedad"};
  if (t - start > F.geos_max_cycle_age_h * 3.6e6) return {status:"DESACTUALIZADO", cycle_start_ms:start,
    reason:`ciclo GEOS-CF que empieza el ${new Date(start).toISOString()}: más de ${F.geos_max_cycle_age_h} h antes de la evaluación`};
  const fut = (g.hourly||[]).map(h => [tms(h.valid_time_utc), h.precip_mm]).filter(x => x[0] != null).sort((a,b) => a[0]-b[0]).filter(x => x[0] >= t);
  const out = {status:"CALCULADO", cycle_start_ms:start, windows:{}, next: fut.slice(0,48)};
  for (const [name, n] of [["6h",6],["24h",24]]) {
    const seq = fut.slice(0,n);
    const ok = seq.length === n && seq[0][0] - t < 3.6e6 && seq.every(x => x[1] != null) && seq.every((x,i) => i === 0 || x[0] - seq[i-1][0] === 3.6e6);
    out.windows[name] = ok ? {status:"CALCULADO", accum_mm: Math.floor(seq.reduce((s,x) => s + x[1], 0) * 10 + 0.5) / 10, start_ms:seq[0][0], end_ms:seq[n-1][0]}
                           : {status:"NO_DISPONIBLE", reason:`el ciclo no cubre ${n} horas consecutivas desde la evaluación`};
  }
  return out;
}
function reviewPriorityAt(avisos, imerg, goes, percentile, t, F){
  const live = (avisos||[]).filter(a => a.relation_method !== NEGATIVE_RELATION).map(a => Object.assign({}, a, {status_at: avisoStatusAt(a, t)}));
  const vig = live.filter(a => a.status_at === "VIGENTE"), fut = live.filter(a => ["FUTURO","DESCONOCIDO"].includes(a.status_at));
  const imOk = imergUsableAt(imerg, t, F), goOk = goesUsableAt(goes, t, F);
  const w = (imerg && imerg.windows) || {}, w24 = w["24h"] || {};
  const observedNonzero = (imOk && Object.values(w).some(v => v.status === "CALCULADO" && (v.accum_mm || 0) > 0)) || (goOk && (goes.rate_max_mm_h || 0) > 0);
  const completeZero = imOk && goOk && w24.status === "CALCULADO" && w24.accum_mm === 0 && goes.rate_max_mm_h === 0;
  const reasons = [], missing = [];
  if (!imerg || !imerg.window_end_utc) missing.push("IMERG Early sin muestras para esta zona");
  else if (!imOk) missing.push(`IMERG Early desactualizado: la última ventana termina el ${imerg.window_end_utc} (más de ${F.imerg_stale_after_h} h antes de la evaluación); no cuenta para la prioridad`);
  else if (w24.status !== "CALCULADO") missing.push("IMERG 24 h incompleta");
  if (!goes || goes.status !== "CALCULADO") missing.push("GOES-19 no disponible para esta zona");
  else if (!goOk) missing.push(`GOES-19 desactualizado: último escaneo ${goes.scan_end_utc} (más de ${F.goes_stale_after_min} min antes de la evaluación); no cuenta para la prioridad`);
  const pctOk = percentile && percentile.status === "CALCULADO";
  if (!pctOk) missing.push("percentil histórico no disponible: anomalía no evaluable");
  let code;
  if (vig.length && pctOk && (percentile.percentile_24h || 0) >= 95) code = "R1_REVISION_PRIORITARIA";
  else if (vig.length) code = "R2_VIGILANCIA_ACTIVA";
  else if (fut.length) code = "R3_PREPARAR_VIGILANCIA";
  else if (observedNonzero) code = "R4_LLUVIA_OBSERVADA_SIN_AVISO";
  else if (completeZero) code = "R6_SIN_SENAL_EN_DATOS_DISPONIBLES";
  else code = "R5_DATOS_INSUFICIENTES";
  vig.concat(fut).forEach(a => reasons.push(`Aviso ${a.aviso_key} (${a.status_at}; nivel oficial: ${a.official_level || "no consta"}) — ${a.relation_method}`));
  if (observedNonzero) reasons.push("Lluvia observada no nula en la última ventana completa de IMERG o en la última muestra GOES válida");
  if (vig.length && !pctOk) reasons.push("Situación C (aviso vigente + anomalía) no evaluable: no hay percentiles interpretables");
  const edges = [];
  live.forEach(a => { const s = tms(a.validity_start), e = tms(a.validity_end); if (s != null) edges.push(s); if (e != null) edges.push(e + 1000); });
  if (imerg && imerg.window_end_utc) edges.push(tms(imerg.window_end_utc) + F.imerg_stale_after_h * 3.6e6 + 1000);
  if (goes && goes.status === "CALCULADO" && goes.scan_end_utc) edges.push(tms(goes.scan_end_utc) + F.goes_stale_after_min * 6e4 + 1000);
  const nxt = edges.filter(x => x > t).sort((a,b) => a-b)[0];
  return {code, reasons_es:reasons, missing_es:missing, imerg_usable:imOk, goes_usable:goOk,
          data_complete: imOk && goOk && w24.status === "CALCULADO", next_change_ms: nxt == null ? null : nxt};
}
function prioritySortKey(zoneId, imerg, rp){
  const w = (imerg && imerg.windows) || {}, acc = (w["24h"]||{}).accum_mm, six = (w["6h"]||{}).accum_mm;
  const obs = rp.imerg_usable ? (acc != null ? acc : (six != null ? six : null)) : null;
  return [PRIORITY_ORDER.indexOf(rp.code), obs == null ? 0 : 1, -(obs || 0), zoneId];
}
function compareKeys(a, b){ for (let i = 0; i < a.length; i++) { if (a[i] < b[i]) return -1; if (a[i] > b[i]) return 1; } return 0; }
/* SHARED-RULES-END */
