# Inventario maestro de Tumbes: cierre de huecos con el Anexo II del DU 015-2023 (v0.1)

**Estado:** `RESEARCH_ONLY / TEST_ONLY` · `activation_gate=BLOCKED` · `missing_data_rule=UNKNOWN_NOT_LOW_RISK` · `decision_thresholds=null` · `hydraulic_factors=null` · geometría y outlet `UNKNOWN` · nada publicable en el mapa.

La revisión independiente señaló 12 nombres del Anexo II del DU 015-2023 (ANA) sin coincidencia literal en el inventario nacional. Este documento resume cómo quedó clasificado cada uno.

**Archivos de la PR:**

| Archivo | Contenido |
|---|---|
| `config/phase2_tumbes_inventory_anexo_ii_gap_v0_1.json` | Registro con citas literales, cruce de filas y madurez |
| `config/phase2_national_inventory_completeness_audit_v0_1.json` | Inventario nacional, revisión r3 |
| `scripts/validate_phase2_tumbes_inventory_anexo_ii_gap.py` | Verificador |
| `tests/test_phase2_tumbes_inventory_anexo_ii_gap.py` | Pruebas |

**Fuentes.** Esta PR se apila sobre el PR #364 y reutiliza su archivo (`data/phase2/source_archive/tumbes_capitana_hualaca_higueron/`, fuera de `site/`) sin volver a descargar documentos:

- Anexo II del DU 015-2023, copia publicada por el MEF;
- INGEMMET A6764;
- Ley 32573;
- mapa regional ANA 2016 (SIGRID 3743);
- COEN RC 3755.

**Cada cita** se comprueba en las pruebas como subcadena literal de la página archivada, cuyo SHA-256 coincide con el manifest.

## Madurez

- `M1_SINGLE_OFFICIAL_LISTING`: Named as a quebrada by one archived official source only (here: a critical-point listing).
- `M2_MULTI_SOURCE_IDENTITY`: Named by two or more archived official sources; their referring to the same channel is NOT asserted.
- `M3_PERIOD_EVENT_LEAD`: M2 plus a per-unit damage statement in an archived official source, period-level only (no day): EVENT_LEAD_UNVERIFIED in the audit.

## Los 12 nombres

| Nombre | Filas Anexo II | Registro | Fila del inventario | Madurez | Marcas | Nota |
|---|---|---|---|---|---|---|
| Fernández | 7, 8 | fila propia (r3/r3b) | `tumbes_canoas_de_punta_sal_fernandez` | `M2_MULTI_SOURCE_IDENTITY` | homónimos, alias pendiente | Main names a Quebrada Fernández system (Bocapán evidence) and quarantines its same-name use for the Máncora child; Anexo II also lists Qda. Fernández in Piura (II-68). Not merged. |
| Seca | 9 | fila propia (r3/r3b) | `tumbes_canoas_de_punta_sal_seca` | `M2_MULTI_SOURCE_IDENTITY` | homónimos, alias pendiente | Several Tumbes features carry the label: Anexo II row 3 uses 'Quebrada Seca' as a SECTOR of a Río Zarumilla point (Matapalo); INGEMMET names a 'Quebrada Seca - Pajaritos' road section; Ley 32573 names a quebrada Seca whose upper reach is called Hualtacal. None is attached to the row. |
| Casitas | 10, 11 | fila propia (r3/r3b) | `tumbes_casitas_casitas` | `M2_MULTI_SOURCE_IDENTITY` | homónimos, alias pendiente | Main holds the Casitas-Bocapán drainage only as ANA hydrographic-unit context; the audit row 'Panales-Casitas' (Andina 2024) is kept separate. |
| Carretas | 15 | fila propia (r3/r3b) | `tumbes_san_jacinto_carretas` | `M1_SINGLE_OFFICIAL_LISTING` | — | Sector of the same name; ANA 2016 map 3743 prints a centro poblado 'CARRETAS'. |
| 07 de Junio | 16 | fila propia (r3/r3b) | `tumbes_san_jacinto_07_de_junio` | `M1_SINGLE_OFFICIAL_LISTING` | alias pendiente | Own row. Possible equivalence with the existing row 'Casa Blanqueada - I.E. 7 de Junio' (ANA 2016, same district; Anexo II gives sector Casa Blanqueada) is UNRESOLVED. Equivalencia posible con `tumbes_san_jacinto_casa_blanqueada_i_e_7_de_junio`: `UNRESOLVED`. |
| Hualaca | 17 | fila propia (r3/r3b) | `tumbes_san_jacinto_hualaca` | `M1_SINGLE_OFFICIAL_LISTING` | alias pendiente | Already registered in PR #364 (unit tumbes_san_jacinto_quebrada_hualaca); the audit row indexes it. Relation to Higuerón UNRESOLVED. |
| Hualtacal | 18 | fila propia (r3/r3b) | `tumbes_san_jacinto_hualtacal` | `M2_MULTI_SOURCE_IDENTITY` | homónimos, alias pendiente | Named in PR #364 as context. Contexts: San Jacinto / Rica Playa (Anexo II), Contralmirante Villar–Tumbes divide and upper reach of a quebrada Seca (Ley 32573), ANA 2016 Cancas and Canoas maps. |
| Plateros | 20 | fila propia (r3/r3b) | `tumbes_san_jacinto_plateros` | `M3_PERIOD_EVENT_LEAD` | — | Sector of the same name. INGEMMET 2017 road damage from flows of the quebrada Plateros is period-level only. |
| Santa María | 23 | fila propia (r3/r3b) | `tumbes_pampas_de_hospital_santa_maria` | `M1_SINGLE_OFFICIAL_LISTING` | homónimos | INGEMMET 2017 names a 'Quebrada Santa María' (district not printed in the row) and 'Santa María de Dios' in distrito Tumbes: not attached. Lima homonym in the audit. |
| Nueva Esperanza | 25 | fila propia (r3/r3b) | `tumbes_pampas_de_hospital_nueva_esperanza` | `M1_SINGLE_OFFICIAL_LISTING` | homónimos | COEN RC 3755 names settlements/sectors 'Nueva Esperanza' in Corrales and in Aguas Verdes (not quebradas). Lambayeque homonym in the audit. |
| Santa Rosa | 21 | fila propia (r3/r3b) | `tumbes_san_jacinto_santa_rosa` | `M1_SINGLE_OFFICIAL_LISTING` | homónimos | Kept apart from 'Barrio Santa Rosa-Uña de Gato' (Papayal) and from the INGEMMET quebrada Santa Rosa in distrito Tumbes. Ica homonym in the audit. |
| Malvales | 29 | fila propia (r3/r3b) | `tumbes_corrales_malvales` | `M1_SINGLE_OFFICIAL_LISTING` | alias pendiente | Own row. Possible equivalence with the existing row 'Malval' (ANA 2016, same district Corrales) is UNRESOLVED. INGEMMET C-36 (flows from the slopes of sector Malval) and COEN (sector Malvales) are not attached as quebrada evidence. Equivalencia posible con `tumbes_corrales_malval`: `UNRESOLVED`. |

También se indexan en el inventario las dos unidades del PR #364 que no figuran en el Anexo II:

- **La Capitana**: `tumbes_san_jacinto_la_capitana`, `M3_PERIOD_EVENT_LEAD`. Not in Anexo II. PR #364 unit tumbes_san_jacinto_quebrada_la_capitana.
- **Higuerón**: `tumbes_district_unknown_higueron`, `M3_PERIOD_EVENT_LEAD`. Not a quebrada row in Anexo II ('Higueron' is only the sector of Qda. Hualaca). PR #364 label group; number of channels UNRESOLVED.

**Resultado (r3b, tras la QA independiente).** Cada uno de los 12 nombres tiene su propia fila. «Malvales» y «07 De Junio» se registran aparte de las filas existentes Malval y Casa Blanqueada - I.E. 7 de Junio, que no cambian. Su posible equivalencia queda en `UNRESOLVED`, dentro de grupos de alias en `PENDING_ADJUDICATION`. Tener 12 filas no implica que existan 12 cauces independientes: ninguna relación entre cauces está adjudicada.

## Cruce de la sección I - TUMBES (filas 1-29)

| Fila | Texto archivado | Resultado | Fila del inventario |
|---|---|---|---|
| 1 | 1 Zarumilla Río Zarumilla Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Matapalo Ciriaco Aguirre | `RIVER_POINT_NOT_A_QUEBRADA_ROW` | — |
| 2 | 2 Zarumilla Río Zarumilla Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Matapalo Raymundo López | `RIVER_POINT_NOT_A_QUEBRADA_ROW` | — |
| 3 | 3 Zarumilla Río Zarumilla Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Matapalo Quebrada Seca | `RIVER_POINT_NOT_A_QUEBRADA_ROW` | — |
| 4 | 4 Tumbes Río Zarumilla Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Aguas Verdes Uña de Gato-Bocatoma La Palma | `RIVER_POINT_NOT_A_QUEBRADA_ROW` | — |
| 5 | 5 Tumbes Río Zarumilla Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Aguas Verdes Uña de Gato-Puente Europa | `RIVER_POINT_NOT_A_QUEBRADA_ROW` | — |
| 6 | 6 Tumbes Río Zarumilla Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Aguas Verdes Puente Europa-Chacra Gonzales | `RIVER_POINT_NOT_A_QUEBRADA_ROW` | — |
| 7 | 7 Fernández Quebrada Qda. Fernández Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Canoas de Punta Sal Barrancos | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_canoas_de_punta_sal_fernandez` |
| 8 | 8 Fernández Quebrada Qda. Fernández Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Canoas de Punta Sal Fernandez | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_canoas_de_punta_sal_fernandez` |
| 9 | 9 Quebrada Seca Quebrada Qda. Seca Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Canoas de Punta Sal Pajaritos | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_canoas_de_punta_sal_seca` |
| 10 | 10 Bocapan Quebrada Qda. Casitas Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Casitas Casitas La rinconada | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_casitas_casitas` |
| 11 | 11 Bocapan Quebrada Qda. Casitas Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Casitas Huaquillas | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_casitas_casitas` |
| 12 | 12 Bocapan Quebrada Qda. Bocapán Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Casitas Cherrelique Bellavista | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_district_unknown_bocapan` |
| 13 | 13 Bocapan Quebrada Qda. Bocapán Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Casitas Cañaveral | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_district_unknown_bocapan` |
| 14 | 14 Bocapan Quebrada Qda. Bocapán Jequetepeque- Zarumilla Tumbes Tumbes Contralmirante Villar Casitas La Florida | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_district_unknown_bocapan` |
| 15 | 15 Tumbes Quebrada Qda Carretas Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Carretas | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_san_jacinto_carretas` |
| 16 | 16 Tumbes Quebrada Qda. 07 De Junio Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Casa Blanqueada | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_san_jacinto_07_de_junio` |
| 17 | 17 Tumbes Quebrada Qda. Hualaca Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Higueron | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_san_jacinto_hualaca` |
| 18 | 18 Tumbes Quebrada Qda. Hualtacal Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Rica Playa | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_san_jacinto_hualtacal` |
| 19 | 19 Tumbes Quebrada Qda. Oidor Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Oidor | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_san_jacinto_oidor` |
| 20 | 20 Tumbes Quebrada Qda. Plateros Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Plateros | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_san_jacinto_plateros` |
| 21 | 21 Tumbes Quebrada Qda. Santa Rosa Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Santa Rosa | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_san_jacinto_santa_rosa` |
| 22 | 22 Tumbes Quebrada Qda. Urbina Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto La Peña | `NEAR_LABEL_SAME_DISTRICT_NOT_ADJUDICATED` | `tumbes_san_jacinto_la_urbina` |
| 23 | 23 Tumbes Quebrada Qda Santa Maria Jequetepeque- Zarumilla Tumbes Tumbes Tumbes Pampas de Hospital Quebrada Santa Maria | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_pampas_de_hospital_santa_maria` |
| 24 | 24 Tumbes Quebrada Qda. Cruz Blanca Jequetepeque- Zarumilla Tumbes Tumbes Tumbes Pampas de Hospital Quebrada Cruz Blanca | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_pampas_de_hospital_cruz_blanca` |
| 25 | 25 Tumbes Quebrada Qda. Nueva Esperanz a Jequetepeque- Zarumilla Tumbes Tumbes Tumbes Pampas de Hospital Quebrada Nueva Esperanza | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_pampas_de_hospital_nueva_esperanza` |
| 26 | 26 Zarumilla Quebrada Qda. Faical Jequetepeque- Zarumilla Tumbes Tumbes Zarumilla Matapalo Leandro Campos | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_matapalo_faical` |
| 27 | 27 Intercuenca Quebrada Qda. Los Cerezos Jequetepeque- Zarumilla Tumbes Tumbes Tumbes La Cruz Quebrada Los Cerezos | `LITERAL_MATCH_EXISTING_ROW` | `tumbes_la_cruz_los_cerezos` |
| 28 | 28 Intercuenca Quebrada Qda. La Jota Jequetepeque- Zarumilla Tumbes Tumbes Tumbes Corrales Quebrada san Jose sector La Jota | `LITERAL_LABEL_EXISTING_ROW_DISTRICT_UNKNOWN_THERE` | `tumbes_district_unknown_la_jota` |
| 29 | 29 Tumbes Quebrada Qda. Malvales Jequetepeque- Zarumilla Tumbes Tumbes Tumbes Corrales Malvales | `REQUESTED_NAME_NEW_ROW_IN_MASTER_INVENTORY` | `tumbes_corrales_malvales` |

## Plan de Intervenciones (ANA)

`NOT_READ_SOURCE_INCOMPLETE`: ANA host timed out; the only Wayback snapshot (20240112092222) delivers 4 996 784 of 21 682 076 declared bytes and refuses resumes; the received part has no page tree. Not used as evidence for any name.

## Bloqueos

- Plan de Intervenciones (ANA): no complete copy reachable (ANA host timeout; truncated Wayback snapshot). A full download from a network with access to www.ana.gob.pe is needed before contrasting the 12 names with it.
- ANA-hosted Anexo II: unreachable; the archived MEF copy is used and byte identity with the ANA copy is not asserted.
- Alias groups (Malval/Malvales, Casa Blanqueada - I.E. 7 de Junio / 07 de Junio, Seca/Hualtacal, Casitas/Cherrelique/El Ciénego/Bocapán/Panales-Casitas, Hualaca/Higuerón, Fernández Tumbes/Piura) need georeferenced hydrography (ANA, ALA Tumbes intervention files for DU 015-2023) or field checks.
- Geometry and outlet: none of the 14 names has a reproducible channel, catchment or outlet; ANA geoservers were unreachable from the runners.
- Anexo II sections II-X (Piura to Ica) are not crosswalked in this PR.

