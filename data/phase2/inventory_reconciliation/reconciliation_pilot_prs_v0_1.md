# Conciliación documental del inventario nacional (RESEARCH_ONLY / TEST_ONLY)

Esquema `phase2_inventory_reconciliation_v0_1` · huella comparable `8e03df2cfad3f90b` · generado por `scripts/phase2_inventory_completeness_reconcile.py`. No fusiona, no divide, no promueve y no escribe en sus entradas.

## Resumen

- Entradas: 9 · filas documentales: 464 · identificadores distintos: 420.
- Errores bloqueantes: **0** · hallazgos para revisión humana: 184.
- `map_eligible` fijado por esta herramienta: 0 · fusiones: 0 · divisiones: 0.
- Conexión costera: COASTAL_IMPACT_DOCUMENTED 0, COASTAL_IMPACT_CANDIDATE 0, COASTAL_IMPACT_UNKNOWN 0, COASTAL_IMPACT_NOT_ASSESSED 420.
- La completitud se mide dentro de las filas cargadas; no existe un denominador demostrado de todas las quebradas del Perú.

| Tipo de hallazgo | n |
|---|---|
| COMPOUND_NAME_REVIEW | 51 |
| CROSS_PR_OVERLAP | 44 |
| DOCUMENTARY_RELATION_UNRESOLVED | 65 |
| HOMONYM_DISTINCT_CONTEXT | 28 |
| INSUFFICIENT_EVIDENCE | 19 |
| LEDGER_CROSS_REFERENCE | 2 |
| POTENTIAL_ALIAS | 1 |
| SOURCE_UNAVAILABLE_NOT_ABSENCE | 2 |
| UNNAMED_IDENTITY_UNRESOLVED | 4 |

## Entradas

| Etiqueta | Rol | Adaptador | Origen | SHA-256 |
|---|---|---|---|---|
| candidate_inventory_v0_1_superseded | LEDGER | system_ledger | `config/phase2_candidate_inventory_v0_1.json` | `8ff244398320…` |
| candidate_inventory_v0_2 | LEDGER | system_ledger | `config/phase2_candidate_inventory_v0_2.json` | `f8ea83e4957e…` |
| master | MASTER | national_inventory | `config/phase2_national_inventory_completeness_audit_v0_1.json` | `d3a0b1810d85…` |
| north_coast_discovery | LEDGER | discovery_ledger | `config/phase2_north_coast_discovery_inventory_v0_1.json` | `c3a36b4d3650…` |
| pisco_quitasol_paracas_identity | IDENTITY | identity_entries | `config/phase2_pisco_quitasol_paracas_sigrid_identity_v0_1.json` | `f9c3d4a371c6…` |
| pr404 | DELTA | national_inventory | `config/phase2_national_inventory_r8_sigrid_sweep_v0_1.json @ 4aa58886` | `8b30ed69a25e…` |
| pr404_sweep | DELTA | sweep_ledger | `data/phase2/source_archive/sigrid_ana2016_sweep_20261022/sweep_ledger_v0_1.json @ 4aa58886` | `e2dcdf744305…` |
| pr407 | DELTA | corridor_units | `config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json @ c8d2811b` | `c1dbfe228fbc…` |
| sidecar | SIDECAR | annotations | `config/phase2_inventory_annotations_v0_1.json` | `d1fe18215338…` |
| zorritos_capture_attempts | LOG | capture_log | `site/data/phase2/sources/zorritos_priority_ana_capture_attempts_v0_1.json` | `a048909d47c4…` |

## Errores bloqueantes

- Ninguno.

## Corredores

| Corredor | Estado | Filas | IDs | Solapes posibles | Identidad pendiente | Sin distrito | Sin geometría | Sin outlet | Costa (NOT_ASSESSED) | Fuentes pendientes |
|---|---|---|---|---|---|---|---|---|---|---|
| ANCASH_INTERIOR | AUDITADO_PARCIAL | 18 | 18 | 0 | 3 | 1 | 18 | 18 | 18 | 4 |
| CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | AUDITADO_PARCIAL | 95 | 51 | 44 | 26 | 9 | 46 | 49 | 51 | 7 |
| LAMBAYEQUE | AUDITADO_PARCIAL | 46 | 46 | 0 | 3 | 0 | 46 | 46 | 46 | 4 |
| LA_LIBERTAD | AUDITADO_PARCIAL | 9 | 9 | 0 | 2 | 0 | 9 | 9 | 9 | 4 |
| LIMA_OTHER_VALLEYS_AND_METROPOLITAN | AUDITADO_PARCIAL | 73 | 73 | 0 | 12 | 8 | 73 | 73 | 73 | 4 |
| PISCO_ICA | AUDITADO_PARCIAL | 52 | 52 | 0 | 7 | 0 | 52 | 52 | 52 | 8 |
| PIURA_COAST | AUDITADO_PARCIAL | 40 | 40 | 0 | 1 | 0 | 40 | 40 | 40 | 4 |
| PIURA_INTERIOR | AUDITADO_PARCIAL | 38 | 38 | 0 | 0 | 0 | 38 | 38 | 38 | 4 |
| SANTA_CASMA | AUDITADO_PARCIAL | 25 | 25 | 0 | 9 | 0 | 25 | 25 | 25 | 7 |
| TUMBES_ZORRITOS | AUDITADO_PARCIAL | 68 | 68 | 2 | 11 | 24 | 68 | 68 | 68 | 7 |

Ningún corredor se declara completo: «AUDITADO_PARCIAL» significa que quedan fuentes por revisar.

## Riesgos de duplicidad y alias (45)

- `CROSS_PR_OVERLAP` lima_ate_huaycan: pr407 repeats (same name and territory) master row 'lima_ate_huaycan'
- `CROSS_PR_OVERLAP` lima_chaclacayo_cusipata: pr407 repeats (same name and territory) master row 'lima_chaclacayo_cusipata'
- `CROSS_PR_OVERLAP` lima_chaclacayo_don_bosco: pr407 repeats (same name and territory) master row 'lima_chaclacayo_don_bosco'
- `CROSS_PR_OVERLAP` lima_chaclacayo_el_cuadro: pr407 repeats (same name and territory) master row 'lima_chaclacayo_el_cuadro'
- `CROSS_PR_OVERLAP` lima_chaclacayo_huascaran: pr407 repeats (same name and territory) master row 'lima_chaclacayo_huascaran'
- `CROSS_PR_OVERLAP` lima_chaclacayo_la_floresta: pr407 repeats (same name and territory) master row 'lima_chaclacayo_la_floresta'
- `CROSS_PR_OVERLAP` lima_chaclacayo_los_condores: pr407 repeats (same name and territory) master row 'lima_chaclacayo_los_condores'
- `CROSS_PR_OVERLAP` lima_huarochiri_barba_blanca: pr407 repeats (same name and territory) master row 'lima_huarochiri_barba_blanca'
- `CROSS_PR_OVERLAP` lima_huarochiri_callahuanca: pr407 repeats (same name and territory) master row 'lima_huarochiri_callahuanca'
- `CROSS_PR_OVERLAP` lima_huarochiri_matucana_chucumayo: pr407 repeats (same name and territory) master row 'lima_huarochiri_matucana_chucumayo'
- `CROSS_PR_OVERLAP` lima_huarochiri_matucana_payhua: pr407 repeats (same name and territory) master row 'lima_huarochiri_matucana_payhua'
- `CROSS_PR_OVERLAP` lima_huarochiri_surco_cuchimachay: pr407 repeats (same name and territory) master row 'lima_huarochiri_surco_cuchimachay'
- `CROSS_PR_OVERLAP` lima_huaycoloro: pr407 repeats (same name and territory) master row 'lima_huaycoloro'
- `CROSS_PR_OVERLAP` lima_lurigancho_california: pr407 repeats (same name and territory) master row 'lima_lurigancho_california'
- `CROSS_PR_OVERLAP` lima_lurigancho_carossio: pr407 repeats (same name and territory) master row 'lima_lurigancho_carossio'
- `CROSS_PR_OVERLAP` lima_lurigancho_castilla_faja: pr407 repeats (same name and territory) master row 'lima_lurigancho_castilla_faja'
- `CROSS_PR_OVERLAP` lima_lurigancho_chacrasana: pr407 repeats (same name and territory) master row 'lima_lurigancho_chacrasana'
- `CROSS_PR_OVERLAP` lima_lurigancho_coricancha: pr407 repeats (same name and territory) master row 'lima_lurigancho_coricancha'
- `CROSS_PR_OVERLAP` lima_lurigancho_corrales: pr407 repeats (same name and territory) master row 'lima_lurigancho_corrales'
- `CROSS_PR_OVERLAP` lima_lurigancho_huampani: pr407 repeats (same name and territory) master row 'lima_lurigancho_huampani'
- `CROSS_PR_OVERLAP` lima_lurigancho_la_cantuta: pr407 repeats (same name and territory) master row 'lima_lurigancho_la_cantuta'
- `CROSS_PR_OVERLAP` lima_lurigancho_la_libertad: pr407 repeats (same name and territory) master row 'lima_lurigancho_la_libertad'
- `CROSS_PR_OVERLAP` lima_lurigancho_la_ronda: pr407 repeats (same name and territory) master row 'lima_lurigancho_la_ronda'
- `CROSS_PR_OVERLAP` lima_lurigancho_mariscal_castilla: pr407 repeats (same name and territory) master row 'lima_lurigancho_mariscal_castilla'
- `CROSS_PR_OVERLAP` lima_lurigancho_nicolas_de_pierola_label: pr407 repeats (same name and territory) master row 'lima_lurigancho_nicolas_de_pierola_label'
- … 20 más en el JSON.

## Identidades y relaciones sin resolver (120)

- `COMPOUND_NAME_REVIEW` ancash_anta_pina_uran_y_esperanza: 'piña urán y esperanza' (master)
- `COMPOUND_NAME_REVIEW` ancash_chimbote_cayhuamarca, ancash_chimbote_tablones: 'Tablones' (pr404)
- `COMPOUND_NAME_REVIEW` ancash_chimbote_cayhuamarca, ancash_chimbote_tablones: 'Cayhuamarca' (pr404)
- `COMPOUND_NAME_REVIEW` ancash_chimbote_el_establo_1, ancash_chimbote_el_establo_2: 'El Establo 1' (pr404)
- `COMPOUND_NAME_REVIEW` ancash_chimbote_el_establo_1, ancash_chimbote_el_establo_2: 'El Establo 2' (pr404)
- `COMPOUND_NAME_REVIEW` ancash_chimbote_el_progreso_1_el_progreso_2: 'el progreso 1 - el progreso 2' (master)
- `COMPOUND_NAME_REVIEW` ancash_coishco_virgen_del_carmen_luis_a_sanchez: 'virgen del carmen - luis a. sánchez' (master)
- `COMPOUND_NAME_REVIEW` ancash_nepena_san_cristobal_y_solivin: 'san cristóbal y solivin' (master)
- `COMPOUND_NAME_REVIEW` ancash_pomabamba_colpa_aylahuallon: 'colpa (aylahuallon)' (master)
- `COMPOUND_NAME_REVIEW` ancash_pomabamba_jatun_parco_y_ichic_parco: 'jatun parco y ichic parco' (master)
- `COMPOUND_NAME_REVIEW` ancash_rahuapampa_masin_pariahuanca_vincocota_huaytuna_y_collpu_uran: 'vincocota, huaytuna y collpu uran' (master)
- `COMPOUND_NAME_REVIEW` ancash_sihuas_pachacutec_manco_capac_chuna_colpa_chirimoyo_pingullo_alto_bajo_chico_huitron: 'pachacutec-manco capac-chuna-colpa chirimoyo-pingullo alto/bajo-chico huitron' (master)
- `COMPOUND_NAME_REVIEW` ica_huancano_huayanto_pampano: 'huayanto-pampano' (master)
- `COMPOUND_NAME_REVIEW` ica_humay_pallasca, ica_humay_pantayco: 'Pallasca' (pr404)
- `COMPOUND_NAME_REVIEW` ica_humay_pallasca, ica_humay_pantayco: 'Pantayco' (pr404)
- `COMPOUND_NAME_REVIEW` ica_nasca_cabeza_de_cura, ica_nasca_cerro_blanco: 'Cabeza de Cura' (pr404)
- `COMPOUND_NAME_REVIEW` ica_nasca_cabeza_de_cura, ica_nasca_cerro_blanco: 'Cerro Blanco' (pr404)
- `COMPOUND_NAME_REVIEW` ica_rio_grande_cardal_sanjon: 'cardal-sanjon' (master)
- `COMPOUND_NAME_REVIEW` jicamarca_named_channel_label: 'Quebrada Jicamarca (named channel)' (pr407)
- `COMPOUND_NAME_REVIEW` la_libertad_chicama_gashpa_la_botella: 'gashpa - la botella' (master)
- `COMPOUND_NAME_REVIEW` la_libertad_chicama_la_monica_piedra_molino: 'la monica - piedra molino' (master)
- `COMPOUND_NAME_REVIEW` la_libertad_cochorco_corrales_muyque: 'corrales-muyque' (master)
- `COMPOUND_NAME_REVIEW` lambayeque_chochope_el_espinal_tres_puntas: 'El Espinal (Tres Puntas)' (master)
- `COMPOUND_NAME_REVIEW` lima_ambar_chipial_lashcamayo: 'chipial / lashcamayo' (master)
- `COMPOUND_NAME_REVIEW` lima_atavillos_bajo_rampe_i_y_ii_huayopampa: 'rampe i y ii - huayopampa' (master)
- … 95 más en el JSON.

## Lagunas de evidencia (21)

- `INSUFFICIENT_EVIDENCE` jicamarca_canto_grande_upper_branch: 'Canto Grande upper branch' (pr407): no persistent reference
- `INSUFFICIENT_EVIDENCE` jicamarca_colca: 'Colca' (pr407): no persistent reference
- `INSUFFICIENT_EVIDENCE` jicamarca_el_silencio: 'El Silencio' (pr407): no persistent reference
- `INSUFFICIENT_EVIDENCE` jicamarca_media_luna: 'Media Luna' (pr407): no persistent reference
- `INSUFFICIENT_EVIDENCE` jicamarca_named_channel_label: 'Quebrada Jicamarca (named channel)' (pr407): no persistent reference
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
- `SOURCE_UNAVAILABLE_NOT_ABSENCE` : 52 capture/sweep item(s) failed for corridor NATIONAL_SWEEP_NO_CORRIDOR
- `SOURCE_UNAVAILABLE_NOT_ABSENCE` : 2 capture/sweep item(s) failed for corridor TUMBES_ZORRITOS

## Casos vigilados por corredor

**CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA**
- Quirio: `lima_lurigancho_nicolas_de_pierola_label` (Lurigancho-Chosica; master+pr407; COMPOUND_NAME_REVIEW, CROSS_PR_OVERLAP, DOCUMENTARY_RELATION_UNRESOLVED); `lima_lurigancho_quirio` (Lurigancho-Chosica; master+pr407; CROSS_PR_OVERLAP, DOCUMENTARY_RELATION_UNRESOLVED)
- Cashahuacra: `lima_santa_eulalia_cashahuacra` (Santa Eulalia; master+pr407; CROSS_PR_OVERLAP, DOCUMENTARY_RELATION_UNRESOLVED)
- Huaycoloro: `lima_huaycoloro` (Lurigancho / San Juan de Lurigancho; master+pr407; CROSS_PR_OVERLAP)
- Río Seco: `jicamarca_rio_seco` (distrito no consta; pr407; HOMONYM_DISTINCT_CONTEXT)
- La Ronda: `lima_lurigancho_la_ronda` (Lurigancho-Chosica; master+pr407; CROSS_PR_OVERLAP, DOCUMENTARY_RELATION_UNRESOLVED)
- Media Luna: `jicamarca_media_luna` (distrito no consta; pr407; INSUFFICIENT_EVIDENCE)
- Dos Barrios: `lima_district_unknown_dos_barrios` (distrito no consta; pr407; DOCUMENTARY_RELATION_UNRESOLVED)
- Jicamarca: `jicamarca_named_channel_label` (distrito no consta; pr407; COMPOUND_NAME_REVIEW, HOMONYM_DISTINCT_CONTEXT, INSUFFICIENT_EVIDENCE)

**PISCO_ICA**
- Quitasol: `ica_huancano_quitasol` (Huancano; master; sin hallazgos)
- Paracas: `ica_huancano_paracas` (Huancano; master; sin hallazgos)
- Pallasca: `ica_humay_pallasca` (Humay; pr404; COMPOUND_NAME_REVIEW, DOCUMENTARY_RELATION_UNRESOLVED)
- Pantayco: `ica_humay_pantayco` (Humay; pr404; COMPOUND_NAME_REVIEW)
- Cabeza de Cura: `ica_nasca_cabeza_de_cura` (Nasca; pr404; COMPOUND_NAME_REVIEW, DOCUMENTARY_RELATION_UNRESOLVED, HOMONYM_DISTINCT_CONTEXT); `ica_vista_alegre_cabeza_de_cura` (Vista Alegre; master; DOCUMENTARY_RELATION_UNRESOLVED, HOMONYM_DISTINCT_CONTEXT)
- Cerro Blanco: `ica_nasca_cerro_blanco` (Nasca; pr404; COMPOUND_NAME_REVIEW, DOCUMENTARY_RELATION_UNRESOLVED, HOMONYM_DISTINCT_CONTEXT)

**SANTA_CASMA**
- El Establo: `ancash_chimbote_el_establo_1` (Chimbote; pr404; COMPOUND_NAME_REVIEW); `ancash_chimbote_el_establo_2` (Chimbote; pr404; COMPOUND_NAME_REVIEW)
- s/n: `ancash_moro_s_n` (Moro; pr404; UNNAMED_IDENTITY_UNRESOLVED); `ancash_nepena_s_n` (Nepeña; pr404; UNNAMED_IDENTITY_UNRESOLVED); `ancash_samanco_s_n_los_chimus` (Samanco; pr404; UNNAMED_IDENTITY_UNRESOLVED)
- Cayhuamarca: `ancash_chimbote_cayhuamarca` (Chimbote; pr404; COMPOUND_NAME_REVIEW)
- Tablones: `ancash_chimbote_tablones` (Chimbote; pr404; COMPOUND_NAME_REVIEW)
- La Cantera: `ancash_chimbote_la_cantera` (Chimbote; pr404; DOCUMENTARY_RELATION_UNRESOLVED, HOMONYM_DISTINCT_CONTEXT)
- San Juan: `ancash_chimbote_san_juan` (Chimbote; pr404; DOCUMENTARY_RELATION_UNRESOLVED, HOMONYM_DISTINCT_CONTEXT)

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

