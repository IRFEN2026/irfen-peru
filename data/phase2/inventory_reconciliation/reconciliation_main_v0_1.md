# Conciliación documental del inventario nacional (RESEARCH_ONLY / TEST_ONLY)

Esquema `phase2_inventory_reconciliation_v0_1` · huella comparable `5133427e03fd6f8c` · generado por `scripts/phase2_inventory_completeness_reconcile.py`. No fusiona, no divide, no promueve y no escribe en sus entradas.

## Resumen

- Entradas: 6 · filas documentales: 400 · identificadores distintos: 400.
- Errores bloqueantes: **0** · hallazgos para revisión humana: 99.
- `map_eligible` fijado por esta herramienta: 0 · fusiones: 0 · divisiones: 0.
- Conexión costera: COASTAL_IMPACT_DOCUMENTED 0, COASTAL_IMPACT_CANDIDATE 0, COASTAL_IMPACT_UNKNOWN 0, COASTAL_IMPACT_NOT_ASSESSED 400.
- La completitud se mide dentro de las filas cargadas; no existe un denominador demostrado de todas las quebradas del Perú.

| Tipo de hallazgo | n |
|---|---|
| COMPOUND_NAME_REVIEW | 42 |
| DOCUMENTARY_RELATION_UNRESOLVED | 39 |
| HOMONYM_DISTINCT_CONTEXT | 23 |
| INSUFFICIENT_EVIDENCE | 14 |
| LEDGER_CROSS_REFERENCE | 2 |
| POTENTIAL_ALIAS | 1 |
| SOURCE_UNAVAILABLE_NOT_ABSENCE | 1 |
| UNNAMED_IDENTITY_UNRESOLVED | 3 |

## Entradas

| Etiqueta | Rol | Adaptador | Origen | SHA-256 |
|---|---|---|---|---|
| candidate_inventory_v0_1_superseded | LEDGER | system_ledger | `config/phase2_candidate_inventory_v0_1.json` | `8ff244398320…` |
| candidate_inventory_v0_2 | LEDGER | system_ledger | `config/phase2_candidate_inventory_v0_2.json` | `f8ea83e4957e…` |
| master | MASTER | national_inventory | `config/phase2_national_inventory_completeness_audit_v0_1.json` | `d3a0b1810d85…` |
| north_coast_discovery | LEDGER | discovery_ledger | `config/phase2_north_coast_discovery_inventory_v0_1.json` | `c3a36b4d3650…` |
| pisco_quitasol_paracas_identity | IDENTITY | identity_entries | `config/phase2_pisco_quitasol_paracas_sigrid_identity_v0_1.json` | `f9c3d4a371c6…` |
| sidecar | SIDECAR | annotations | `config/phase2_inventory_annotations_v0_1.json` | `d1fe18215338…` |
| zorritos_capture_attempts | LOG | capture_log | `site/data/phase2/sources/zorritos_priority_ana_capture_attempts_v0_1.json` | `a048909d47c4…` |

## Errores bloqueantes

- Ninguno.

## Corredores

| Corredor | Estado | Filas | IDs | Solapes posibles | Identidad pendiente | Sin distrito | Sin geometría | Sin outlet | Costa (NOT_ASSESSED) | Fuentes pendientes |
|---|---|---|---|---|---|---|---|---|---|---|
| ANCASH_INTERIOR | AUDITADO_PARCIAL | 18 | 18 | 0 | 3 | 1 | 18 | 18 | 18 | 4 |
| CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | AUDITADO_PARCIAL | 44 | 44 | 0 | 23 | 2 | 41 | 42 | 44 | 4 |
| LAMBAYEQUE | AUDITADO_PARCIAL | 46 | 46 | 0 | 3 | 0 | 46 | 46 | 46 | 4 |
| LA_LIBERTAD | AUDITADO_PARCIAL | 9 | 9 | 0 | 2 | 0 | 9 | 9 | 9 | 4 |
| LIMA_OTHER_VALLEYS_AND_METROPOLITAN | AUDITADO_PARCIAL | 73 | 73 | 0 | 12 | 8 | 73 | 73 | 73 | 4 |
| PISCO_ICA | AUDITADO_PARCIAL | 48 | 48 | 0 | 3 | 0 | 48 | 48 | 48 | 4 |
| PIURA_COAST | AUDITADO_PARCIAL | 40 | 40 | 0 | 1 | 0 | 40 | 40 | 40 | 4 |
| PIURA_INTERIOR | AUDITADO_PARCIAL | 38 | 38 | 0 | 0 | 0 | 38 | 38 | 38 | 4 |
| SANTA_CASMA | AUDITADO_PARCIAL | 16 | 16 | 0 | 4 | 0 | 16 | 16 | 16 | 4 |
| TUMBES_ZORRITOS | AUDITADO_PARCIAL | 68 | 68 | 2 | 11 | 24 | 68 | 68 | 68 | 6 |

Ningún corredor se declara completo: «AUDITADO_PARCIAL» significa que quedan fuentes por revisar.

## Riesgos de duplicidad y alias (1)

- `POTENTIAL_ALIAS` tumbes_papayal_la_chava, tumbes_papayal_la_chiva: ONE_EDIT_SPELLING_VARIANT in the same territory — tumbes_papayal_la_chava: 'La Chava' Papayal/Zarumilla/Tumbes [master] / tumbes_papayal_la_chiva: 'La Chiva' Papayal/Zarumilla/Tumbes [master]

## Identidades y relaciones sin resolver (84)

- `COMPOUND_NAME_REVIEW` ancash_anta_pina_uran_y_esperanza: 'piña urán y esperanza' (master)
- `COMPOUND_NAME_REVIEW` ancash_chimbote_el_progreso_1_el_progreso_2: 'el progreso 1 - el progreso 2' (master)
- `COMPOUND_NAME_REVIEW` ancash_coishco_virgen_del_carmen_luis_a_sanchez: 'virgen del carmen - luis a. sánchez' (master)
- `COMPOUND_NAME_REVIEW` ancash_nepena_san_cristobal_y_solivin: 'san cristóbal y solivin' (master)
- `COMPOUND_NAME_REVIEW` ancash_pomabamba_colpa_aylahuallon: 'colpa (aylahuallon)' (master)
- `COMPOUND_NAME_REVIEW` ancash_pomabamba_jatun_parco_y_ichic_parco: 'jatun parco y ichic parco' (master)
- `COMPOUND_NAME_REVIEW` ancash_rahuapampa_masin_pariahuanca_vincocota_huaytuna_y_collpu_uran: 'vincocota, huaytuna y collpu uran' (master)
- `COMPOUND_NAME_REVIEW` ancash_sihuas_pachacutec_manco_capac_chuna_colpa_chirimoyo_pingullo_alto_bajo_chico_huitron: 'pachacutec-manco capac-chuna-colpa chirimoyo-pingullo alto/bajo-chico huitron' (master)
- `COMPOUND_NAME_REVIEW` ica_huancano_huayanto_pampano: 'huayanto-pampano' (master)
- `COMPOUND_NAME_REVIEW` ica_rio_grande_cardal_sanjon: 'cardal-sanjon' (master)
- `COMPOUND_NAME_REVIEW` la_libertad_chicama_gashpa_la_botella: 'gashpa - la botella' (master)
- `COMPOUND_NAME_REVIEW` la_libertad_chicama_la_monica_piedra_molino: 'la monica - piedra molino' (master)
- `COMPOUND_NAME_REVIEW` la_libertad_cochorco_corrales_muyque: 'corrales-muyque' (master)
- `COMPOUND_NAME_REVIEW` lambayeque_chochope_el_espinal_tres_puntas: 'El Espinal (Tres Puntas)' (master)
- `COMPOUND_NAME_REVIEW` lima_ambar_chipial_lashcamayo: 'chipial / lashcamayo' (master)
- `COMPOUND_NAME_REVIEW` lima_atavillos_bajo_rampe_i_y_ii_huayopampa: 'rampe i y ii - huayopampa' (master)
- `COMPOUND_NAME_REVIEW` lima_ate_huaycan: 'Huaycán (Ate)' (master)
- `COMPOUND_NAME_REVIEW` lima_calango_la_vuelta_yuncaviri: 'la vuelta-yuncaviri' (master)
- `COMPOUND_NAME_REVIEW` lima_district_not_in_title_guengue_y_rio_quichas_tramo_2: 'guengue y río quichas tramo 2' (master)
- `COMPOUND_NAME_REVIEW` lima_district_not_in_title_pomaca_y_rio_quichas_tramo_1: 'pomaca y río quichas tramo 1' (master)
- `COMPOUND_NAME_REVIEW` lima_lurigancho_nicolas_de_pierola_label: 'Nicolás de Piérola (label component)' (master)
- `COMPOUND_NAME_REVIEW` lima_nuevo_imperial_cantera_y_cantera_alta: 'cantera y cantera alta' (master)
- `COMPOUND_NAME_REVIEW` lima_oyon_michimachay_rio_quichas_cp_michimachay: 'michimachay (río quichas) CP Michimachay' (master)
- `COMPOUND_NAME_REVIEW` lima_pachacamac_tinajas_cosanche: 'Tinajas-Cosanche' (master)
- `COMPOUND_NAME_REVIEW` lima_punta_hermosa_rio_seco_malanche: 'Río Seco (Malanche)' (master)
- … 59 más en el JSON.

## Lagunas de evidencia (15)

- `INSUFFICIENT_EVIDENCE` lima_chaclacayo_el_cuadro: 'El Cuadro' (master): only ['NON_INSTITUTIONAL_LEAD']
- `INSUFFICIENT_EVIDENCE` lima_chaclacayo_la_floresta: 'La Floresta' (master): only ['NON_INSTITUTIONAL_LEAD']
- `INSUFFICIENT_EVIDENCE` lima_huarochiri_callahuanca: 'Callahuanca' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` lima_lurigancho_pablo_patron_dos_amigos: 'Pablo Patrón/Dos Amigos' (master): only ['NON_INSTITUTIONAL_LEAD']
- `INSUFFICIENT_EVIDENCE` lima_santa_eulalia_cuculi: 'Cuculí' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` lima_santa_eulalia_shingolay: 'Shingolay' (master): only ['INTERNAL']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_charan: 'Charán' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_coloma: 'Coloma' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_la_jota: 'La Jota' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_las_vacas: 'Las Vacas' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_los_cerezos: 'Los Cerezos' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_los_pinos: 'Los Pinos' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_panales_casitas: 'Panales-Casitas' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `INSUFFICIENT_EVIDENCE` tumbes_district_unknown_san_jose: 'San José' (master): only ['STATE_NEWS_AGENCY_SECONDARY']
- `SOURCE_UNAVAILABLE_NOT_ABSENCE` : 2 capture/sweep item(s) failed for corridor TUMBES_ZORRITOS

## Casos vigilados por corredor

**CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA**
- Quirio: `lima_lurigancho_nicolas_de_pierola_label` (Lurigancho-Chosica; master; COMPOUND_NAME_REVIEW, DOCUMENTARY_RELATION_UNRESOLVED); `lima_lurigancho_quirio` (Lurigancho-Chosica; master; DOCUMENTARY_RELATION_UNRESOLVED)
- Cashahuacra: `lima_santa_eulalia_cashahuacra` (Santa Eulalia; master; DOCUMENTARY_RELATION_UNRESOLVED)
- Huaycoloro: `lima_huaycoloro` (Lurigancho / San Juan de Lurigancho; master; sin hallazgos)
- Río Seco: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- La Ronda: `lima_lurigancho_la_ronda` (Lurigancho-Chosica; master; DOCUMENTARY_RELATION_UNRESOLVED)
- Media Luna: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- Dos Barrios: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- Jicamarca: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)

**PISCO_ICA**
- Quitasol: `ica_huancano_quitasol` (Huancano; master; sin hallazgos)
- Paracas: `ica_huancano_paracas` (Huancano; master; sin hallazgos)
- Pallasca: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- Pantayco: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- Cabeza de Cura: `ica_vista_alegre_cabeza_de_cura` (Vista Alegre; master; sin hallazgos)
- Cerro Blanco: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)

**SANTA_CASMA**
- El Establo: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- s/n: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- Cayhuamarca: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- Tablones: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- La Cantera: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)
- San Juan: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)

**TUMBES_ZORRITOS**
- Bocapán: `tumbes_district_unknown_bocapan` (distrito no consta; master; sin hallazgos)
- Tucilla: `tumbes_zorritos_la_tucilla` (Zorritos; master; DOCUMENTARY_RELATION_UNRESOLVED)
- Casitas: `tumbes_district_unknown_panales_casitas` (distrito no consta; master; COMPOUND_NAME_REVIEW, INSUFFICIENT_EVIDENCE)
- Zorritos: ninguna fila con ese nombre en las entradas cargadas (no prueba ausencia)

## Próximas acciones

1. Resolver los errores bloqueantes, si los hay, antes de cualquier integración.
2. Revisar los pares `CROSS_PR_OVERLAP` / `POTENTIAL_ALIAS` con la fuente primaria; registrar SAME_UNIT solo con un documento que lo diga.
3. Las filas `s/n` y los nombres compuestos se identifican sobre el mapa o la ficha archivada; nunca se dividen ni se fusionan por el nombre.
4. La conexión costera sigue NOT_ASSESSED salvo anotación con fuente; anotar en `config/phase2_inventory_annotations_v0_1.json`.
5. Fuentes pendientes por corredor: ver `corridors.*.pending_sources` en el JSON.

