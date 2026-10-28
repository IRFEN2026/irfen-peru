/* Smoke / negative controls for national v0.9 screening; runs offline with node.
   This asserts presence/age of evidence, never a risk class or operational warning. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const S = require("../../site/v09/screening_rules.js");
const root = path.resolve(__dirname, "../..");
const T = JSON.parse(fs.readFileSync(path.join(root,"site/data/v09/territory_v0_1.json"),"utf8"));
const V = JSON.parse(fs.readFileSync(path.join(root,"site/data/v09/inventory_master_v0_1.json"),"utf8"));
assert.equal(S.accept(T),true);assert.equal(S.accept(V),true);
assert.equal(S.accept({...T,operational_alerting_enabled:true}),false);
assert.equal(S.accept({...T,activation_gate:"OPEN"}),false);
assert.equal(S.DEPARTMENTS.length,25);
assert.equal(new Set(S.DEPARTMENTS.map(S.normalize)).size,25);
assert.equal(S.department("ANCASH"),"Áncash");
assert.equal(S.department("CALLAO"),"Callao");
assert.equal(S.department("A-UNKNOWN"),null);
assert.equal(V.rows.length,400);
assert.equal(Object.keys(T.zone_rain).length,22);
assert.equal(V.rows.filter(x=>x.map.eligible).length,0);
assert.equal(S.zoneDepartment("tumbes_bocapan"),"Tumbes");
assert.equal(S.zoneDepartment("piura_province_context:AYABACA"),"Piura");
assert.equal(S.zoneDepartment("lambayeque_motupe"),"Lambayeque");
assert.equal(S.zoneDepartment("lalibertad_viru"),"La Libertad");
assert.equal(S.zoneDepartment("unmapped"),null);
const now = Date.parse("2026-10-28T16:00:00Z"),stamp="2026-10-28T15:00:00Z",config={imerg_stale_after_h:12};
const standard = {
 imerg:{window_end_utc:stamp,coverage_24h:{required_half_hours:48,available_half_hours:48,missing_half_hours_utc:[]},
        windows:{"6h":{accum_mm:1.4},"24h":{accum_mm:3.2}}},
 avisos: []
};
const warning = {validity_start:"2026-10-28T14:00:00Z",validity_end:"2026-10-28T20:00:00Z",
                 status:"VIGENTE",aviso_key:"OFFICIAL-TEST",relation_method:"BASIN_INTERSECTS_LISTED_PROVINCE"};
const decision = (z,when=now,capture=stamp)=>S.screenZone(z,when,config,capture).key;
assert.equal(decision(standard),"LLUVIA_SATELITAL");
assert.equal(decision({...standard,avisos:[warning]}),"CONCURRENCIA");
assert.equal(decision({...standard,avisos:[warning]},now,"2026-10-27T02:00:00Z"),"LLUVIA_SATELITAL");
assert.equal(decision({...standard,avisos:[warning],imerg:{...standard.imerg,coverage_24h:{required_half_hours:48,available_half_hours:47,missing_half_hours_utc:[stamp]}}}),"AVISO_OFICIAL");
assert.equal(decision({...standard,imerg:{...standard.imerg,window_end_utc:"2026-10-28T22:00:00Z"}}),"SIN_LECTURA_VIGENTE");
assert.equal(decision({...standard,imerg:{...standard.imerg,window_end_utc:"2026-10-27T00:00:00Z"}}),"SIN_LECTURA_VIGENTE");
assert.equal(decision({...standard,imerg:{...standard.imerg,windows:{"6h":{accum_mm:0},"24h":{accum_mm:0}}}}),"LECTURA_DISPONIBLE");
assert.equal(decision({...standard,imerg:null,avisos:[warning]},now,"2026-10-27T02:00:00Z"),"AVISO_SIN_CRUCE_RECIENTE");
assert.equal(decision({...standard,avisos:[{...warning,validity_start:"2026-10-29T00:00:00Z"}]}),"LLUVIA_SATELITAL");
assert.equal(S.rainEvidence({...standard,imerg:{...standard.imerg,windows:{"24h":{accum_mm:null}}}},now,config).available,false);
assert.equal(S.recent("2026-10-28T18:00:00Z",now,12),false);
assert.equal(Object.keys(S.LABELS).some(k=>/RIESGO|EVACUACION|ALERTA_ROJA/.test(k)),false);
console.log("NATIONAL_SCREENING_TEST_ONLY_OK: 25 units, 400 documentary rows, 22 surveillance zones; stale/future/missing and false-risk controls PASS.");
