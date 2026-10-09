# Auditoría nacional de completitud del inventario IRFEN (v0.1)

**Estado:** `RESEARCH_ONLY / TEST_ONLY` · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `activation_gate=BLOCKED` · `decision_thresholds=null` · `hydraulic_factors=null`

**Registro de datos:** `config/phase2_national_inventory_completeness_audit_v0_1.json` · **Verificador:** `python scripts/validate_phase2_national_inventory_audit.py` · **Pruebas en CI:** `tests/test_phase2_national_inventory_completeness_audit.py`

Este documento es un inventario/backlog. No crea unidades hidrológicas, geometrías, outlets, eventos en ningún ledger, umbrales, alertas ni capas de mapa. La falta de geometría no excluye a ninguna unidad, y la ausencia de una quebrada en este archivo no significa que no exista.

> Se genera a partir del JSON; para cambiar una fila, cambie el JSON y regenere.

## 1. Qué se hizo y qué no

- **401 filas deduplicadas** tomadas de fuentes de ANA, INGEMMET, INDECI, CENEPRED/SIGRID, IGP, ANIN, gobiernos regionales y municipalidades (más pistas de ONG/prensa, marcadas como tales).
- Cada fila se contrastó con `main`, con las 531 ramas y con los 41 PR abiertos antes de proponerla.
- **0** filas `MAP_ELIGIBLE`, **0** geometrías nuevas, **0** outlets nuevos, **0** aliases fusionados, **0** cuencas padre asignadas.
- **0** filas `EVENT_EVIDENCE`: las 42 filas con afirmaciones fechadas de evento quedan como `EVENT_LEAD_UNVERIFIED` hasta que su fuente se reabra, verifique y archive (0 de 27 fuentes tienen `source_text_verified=true`).
- **Advertencia de extracción.** Los documentos se leyeron con una herramienta automática de lectura web. Los nombres de archivo que entrega el servidor de SIGRID son identificadores fiables; las transcripciones de texto y tablas **no están verificadas byte a byte** y ningún archivo fuente se archivó ni se hasheó. Durante la auditoría se detectó y descartó una tabla fabricada por el lector (Áncash). QA independiente debe reabrir cada fuente antes de promover cualquier fila.
- **Revisión r5 (2026-10-09, Rímac, PR #363).** Dos Barrios se registra con identidad documental y, tras el QA independiente, con una pista `EVENT_LEAD_UNVERIFIED` del 05/04/2012 atribuida a INGEMMET A6608 §5.6 (no es evento validado ni entra en ningún ledger; P1 por definición). La fuente primaria es INGEMMET A6608 (2012), §5.6 «Quebrada Dos Barrios / Pablo Patrón» (p. 30), donde Pablo Patrón es un sector del abanico, no un nombre de cauce. SENAMHI 2020 (p. 3) y una tesis doctoral de 2018 alojada por INGEMMET (TE0306, p. 85) repiten A6608. Las fuentes están archivadas con SHA-256 en `data/phase2/source_archive/rimac_dos_barrios/`. El resultado anterior «sin fuente en este barrido» se conserva y se marca como superado. Advertencia: la portada de A6608 dice «Octubre 2011», mientras el título y el texto fechan el flujo el 05/04/2012 y el catálogo data el informe en 2012. El distrito no consta en las fuentes. Las relaciones con «Pablo Patrón/Dos Amigos» (PREDES) y con «Mariscal Castilla» (RIIGEO 2012) quedan `UNRESOLVED`. Registro: `config/phase2_rimac_dos_barrios_identity_v0_1.json`. (Las etiquetas r3 y r4 corresponden a los PR #365 y #366.)
- **Aviso clean-room.** El JSON contiene afirmaciones con resultado sobre el evento del 23-03-2015 en Chosica; los trabajos sellados de `agent/chosica-2015-*` (PR #146, #149, #150, #151) no deben leerlo.

### Resumen

| Corredor | Filas | En main (registrada / nombrada) | Mención sin confirmar | Solo rama/PR | No está en IRFEN | P1 | P2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. Carretera Central / Rímac / Chosica / Chaclacayo / Ricardo Palma / Santa Eulalia | 45 | 17 | 0 | 0 | 28 | 24 | 16 |
| 2. Pisco / Ica | 48 | 12 | 3 | 2 | 31 | 0 | 1 |
| 3. Santa / Casma | 16 | 1 | 1 | 1 | 13 | 0 | 0 |
| 4. Tumbes / Zorritos | 68 | 4 | 4 | 2 | 58 | 0 | 0 |
| 5a. Otros valles de Lima y Lima Metropolitana | 73 | 4 | 9 | 1 | 59 | 0 | 0 |
| 5b. Costa de Piura | 40 | 2 | 1 | 5 | 32 | 0 | 0 |
| 5c. Lambayeque | 46 | 1 | 6 | 0 | 39 | 0 | 0 |
| 5d. La Libertad (parcial) | 9 | 0 | 0 | 0 | 9 | 0 | 0 |
| 5e. Áncash interior | 18 | 0 | 0 | 0 | 18 | 0 | 0 |
| 5f. Piura interior | 38 | 0 | 0 | 0 | 38 | 0 | 0 |

Estado sugerido (uno por fila): `EVENT_LEAD_UNVERIFIED` 29, `IDENTITY_ONLY` 349, `GEOMETRY_PENDING` 20, `GEOMETRY_REPRODUCIBLE` 3.

### Regla de verificación de eventos

Un ítem EVENT solo cuenta como `EVENT_EVIDENCE` si `source_text_verified` es `true` en la fuente **y** en el ítem, con sus registros de verificación. El verificador y las pruebas (`tests/test_phase2_national_inventory_completeness_audit.py`) lo imponen. Para promover una fila:

1. Reabrir el archivo fuente (no un resumen) y archivarlo de forma reproducible.
2. Poner `sources[id].source_text_verified=true` y rellenar `verification_record`: `archived_sha256` (64 hex), `archive_locator` (ruta en el repositorio o URL estable de los bytes archivados), `verified_on` (AAAA-MM-DD) y `verified_by`.
3. En cada ítem EVENT confirmado en esos bytes, poner `source_text_verified=true` y rellenar `verification`: `locator` (página, tabla, fila) y `verified_statement` (el texto tal como aparece).
4. Regenerar `state_flags`, `suggested_state`, `verified_event_dates`, `event_lead_dates_unverified` y `summary`; el verificador rechaza cualquier desajuste.

### Vocabulario de estados

- `IDENTITY_ONLY` — Solo evidencia de identidad, punto crítico, obra o pista. Sin evento fechado de fuente institucional y sin pista de geometría.
- `GEOMETRY_PENDING` — Existe una pista de geometría (resolución ANA de faja marginal con hitos, o geometría congelada en una rama que no es main), pero no hay nada reproducible en main para la unidad.
- `GEOMETRY_REPRODUCIBLE` — Ya existe geometría reproducible en main para la unidad (previa a esta auditoría, que no añadió ninguna).
- `OUTLET_PENDING` — Marca adicional: la unidad tiene pista de geometría o evidencia de evento, pero no un nodo de salida/confluencia reproducible.
- `EVENT_LEAD_UNVERIFIED` — Se leyó, por extracción automática, al menos una afirmación fechada de evento en una fuente institucional primaria, pero el texto de la fuente no se ha reabierto, verificado ni archivado. Es una pista por verificar: no es evidencia adjudicada ni una entrada de ledger. La atribución a nivel de lista distrital se marca como tal.
- `EVENT_EVIDENCE` — Reservado para filas con al menos un ítem EVENT cuyo texto fuente está verificado: `source_text_verified=true` en la fuente (con `verification_record`: SHA-256 del archivo archivado, localizador, fecha y verificador) y en el ítem (con su localizador y la frase verificada). Ninguna fila lo tiene en v0.1.
- `MAP_ELIGIBLE` — Esta auditoría no lo asigna a ninguna fila.
- Regla: El estado sugerido es el más avanzado de GEOMETRY_REPRODUCIBLE > GEOMETRY_PENDING > EVENT_EVIDENCE > EVENT_LEAD_UNVERIFIED > IDENTITY_ONLY; las marcas adicionales aparecen entre paréntesis.

## 2. Carretera Central: nombres pedidos expresamente

| Nombre pedido | Fila(s) del inventario | Estado sugerido | En IRFEN | Prioridad |
|---|---|---|---|---|
| Quirio / Nicolás de Piérola | `lima_lurigancho_quirio` (Quirio)<br>`lima_lurigancho_nicolas_de_pierola_label` (Nicolás de Piérola (label component)) | `GEOMETRY_PENDING`<br>`IDENTITY_ONLY` | main: unidad registrada `quirio` · PR #149<br>main: solo nombre/contexto · PR #149 | EXISTING<br>P2 |
| Pedregal / San Antonio | `lima_lurigancho_pedregal_san_antonio` (Pedregal) | `GEOMETRY_PENDING` | main: unidad registrada `pedregal_san_antonio` · PR #148, #149, #326 | EXISTING |
| California | `lima_lurigancho_california` (California) | `EVENT_LEAD_UNVERIFIED` | main: solo nombre/contexto · PR #149 | P1 |
| Rayos de Sol / Rayito de Sol | `lima_lurigancho_rayos_de_sol` (Rayos de Sol) | `EVENT_LEAD_UNVERIFIED` | main: solo nombre/contexto · PR #146, #149, #151 | P1 |
| Corrales | `lima_lurigancho_corrales` (Corrales) | `GEOMETRY_PENDING` | main: solo nombre/contexto · PR #149 | P1 |
| Carossio | `lima_lurigancho_carossio` (Carossio) | `GEOMETRY_PENDING` | main: solo nombre/contexto · PR #146, #149, #151 | P1 |
| La Libertad | `lima_lurigancho_la_libertad` (La Libertad) | `GEOMETRY_PENDING` | main: solo nombre/contexto · PR #146, #149, #151 | P1 |
| Santo Domingo | `lima_lurigancho_santo_domingo` (Santo Domingo) | `GEOMETRY_PENDING` | main: solo nombre/contexto | P1 |
| La Cantuta | `lima_lurigancho_la_cantuta` (La Cantuta) | `GEOMETRY_PENDING` | no está | P1 |
| La Ronda | `lima_lurigancho_la_ronda` (La Ronda) | `GEOMETRY_PENDING` | main: solo nombre/contexto | P1 |
| Dos Barrios | `lima_district_unknown_dos_barrios` (Dos Barrios) | `EVENT_LEAD_UNVERIFIED` | no está | P1 |
| Coricancha | `lima_lurigancho_coricancha` (Coricancha) | `IDENTITY_ONLY` | no está | P2 |
| Los Cóndores | `lima_chaclacayo_los_condores` (Los Cóndores) | `GEOMETRY_PENDING` | no está | P1 |
| Pablo Patrón / Dos Amigos | `lima_lurigancho_pablo_patron_dos_amigos` (Pablo Patrón/Dos Amigos) | `IDENTITY_ONLY` | no está | P2 |
| Huampaní | `lima_lurigancho_huampani` (Huampaní) | `IDENTITY_ONLY` | main: solo nombre/contexto | P2 |
| Chacrasana | `lima_lurigancho_chacrasana` (Chacrasana) | `GEOMETRY_PENDING` | main: solo nombre/contexto | P1 |
| Santa María / Yanacoto | `lima_lurigancho_santa_maria` (Santa María)<br>`lima_lurigancho_yanacoto` (Yanacoto) | `EVENT_LEAD_UNVERIFIED`<br>`GEOMETRY_PENDING` | no está<br>main: solo nombre/contexto | P1<br>P1 |
| Mariscal Castilla | `lima_lurigancho_mariscal_castilla` (Mariscal Castilla)<br>`lima_lurigancho_castilla_faja` (Castilla) | `EVENT_LEAD_UNVERIFIED`<br>`GEOMETRY_PENDING` | main: solo nombre/contexto<br>no está | P1<br>P1 |
| Señor de los Milagros | `lima_lurigancho_senor_de_los_milagros` (Señor de los Milagros) | `EVENT_LEAD_UNVERIFIED` | no está | P1 |
| Laderas Virgen del Rosario | `lima_lurigancho_virgen_del_rosario` (Virgen del Rosario)<br>`lima_lurigancho_rosario_igp` (Rosario) | `EVENT_LEAD_UNVERIFIED`<br>`IDENTITY_ONLY` | no está<br>no está | P1<br>P2 |
| Huascarán | `lima_chaclacayo_huascaran` (Huascarán) | `GEOMETRY_PENDING` | no está | P1 |
| Cusipata | `lima_chaclacayo_cusipata` (Cusipata) | `GEOMETRY_PENDING` | no está | P1 |
| Cashahuacra | `lima_santa_eulalia_cashahuacra` (Cashahuacra) | `GEOMETRY_REPRODUCIBLE` | main: unidad registrada `cashahuacra` · PR #136, #146, #149, #151 | EXISTING |

- **Dos Barrios** — El barrido original no encontró fuente (resultado histórico conservado). En r5 se archivaron INGEMMET A6608 (2012, §5.6 «Quebrada Dos Barrios / Pablo Patrón», p. 30), SENAMHI 2020 (p. 3) y la tesis doctoral de Villacorta 2018 (TE0306, pp. 83 y 85). Fila `lima_district_unknown_dos_barrios`: identidad documental y pista `EVENT_LEAD_UNVERIFIED` del 05/04/2012 (A6608 §5.6), sin distrito, geometría ni confluencia. Pablo Patrón es el sector afectado del abanico, no un alias.
- **Laderas Virgen del Rosario** — Las fuentes halladas usan «Virgen del Rosario» (INDECI DDI Lima 2023) y «Rosario» (IGP 2023). El prefijo «Laderas» no aparece en ninguna fuente leída; las tres etiquetas se mantienen separadas hasta su adjudicación.

Además aparecieron en fuente institucional, sin estar en la lista pedida: Barba Blanca (distrito no indicado), Callahuanca (distrito no indicado), Centro Santa Eulalia 1, 2 y 3 (Santa Eulalia), Chucumayo (Matucana), Cuchimachay (Surco), Cuculí (Santa Eulalia), Cupiche (Ricardo Palma), Don Bosco (Chaclacayo), El Cuadro (Chaclacayo), Huayaringa (Santa Eulalia), Huayaringa Centro y Portada de Huayaringa (Santa Eulalia), Huaycán (Ate) (Ate), Julio César Tello (Santa Eulalia), La Floresta (Chaclacayo), Payhua (Matucana), Vizcachera (Lurigancho-Chosica).

## 3. Tabla maestra deduplicada

No hay columna de cuenca o sistema padre: ninguna fuente leída lo sustenta para un candidato nuevo y no se infiere por proximidad (campo `parent_basin_or_system = null` en todas las filas). *Fechas (pista sin verificar)* lista fechas leídas por extracción automática en fuente institucional primaria; ninguna está verificada todavía (`verified_event_dates` está vacío en todas las filas). Las fechas del informe IGP 001-2023 se guardan en el JSON pero no cuentan ni como pista. *Outlet* = existe nodo de salida/confluencia reproducible.

### 1. Carretera Central / Rímac / Chosica / Chaclacayo / Ricardo Palma / Santa Eulalia (45 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Huaycán (Ate) | — | Ate · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P1 | INDECI-DDI-LIMA-2023-BALANCE |
| Callahuanca ⚠ | — | distrito no indicado · Huarochirí † | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | ANDINA-MVCS-2023-02-23 |
| Cusipata | Cusipata (San Bartolomé) | Chaclacayo · Lima | EVENT, FAJA | 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 13203); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023 |
| Don Bosco | — | Chaclacayo · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P1 | INDECI-DDI-LIMA-2023-BALANCE |
| El Cuadro | — | Chaclacayo · Lima | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | PRESS-LEAD |
| Huascarán | Huascarán cauce principal (Huascarán 01) | Chaclacayo · Lima | EVENT, FAJA, IDENTITY | 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 19205); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; PRESS-LEAD |
| La Floresta | — | Chaclacayo · Lima | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | PREDES-CARTILLA-2017 |
| Los Cóndores | Qda. Los Cóndores | Chaclacayo · Lima | EVENT, FAJA | 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 10436); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023 |
| Huaycoloro | — | Lurigancho / San Juan de Lurigancho · Lima | CRITICAL_POINT, EVENT, FAJA | 2023-03 | Sí (ya en main) | No | Contratos del piloto existentes | `GEOMETRY_REPRODUCIBLE` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: unidad registrada `huaycoloro (v0.8 pilot)` | EXISTING | ANA-FAJA-RD-SIGRID (SIGRID 6058); ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5763); INDECI-DDI-LIMA-2023-BALANCE |
| California | — | Lurigancho-Chosica · Lima | EVENT, WORKS | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: solo nombre/contexto · PR #149 | P1 | INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; PRESS-LEAD |
| Carossio | Carosio; Carosio | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT, WORKS | 2015-03-23, 2023-03 | No en main · geometría congelada en rama legacy | No | MML 2013 (R6): «desembocadura sin salida directa al río Rímac»; no se afirma conexión superficial | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: solo nombre/contexto · PR #146, #149, #151 | P1 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5767); MUNI-LURIGANCHO-EVAR-2015; INDECI-DDI-LIMA-2023-BALANCE; ANA-2017-2019-BARRERAS-DINAMICAS |
| Chacrasana | — | Lurigancho-Chosica · Lima | EVENT, FAJA, IDENTITY, WORKS | 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: solo nombre/contexto | P1 | ANA-FAJA-RD-SIGRID (SIGRID 12478); INDECI-DDI-LIMA-2023-BALANCE; CENEPRED-SIGRID-13867; ANIN-MUNI-LURIGANCHO-2026; PRESS-LEAD |
| Coricancha | — | Lurigancho-Chosica · Lima | CRITICAL_POINT, IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | INGEMMET-A7459; PREDES-CARTILLA-2017 |
| Corrales | Corrales (Rayos del Sol); Rayo de Sol – Corrales | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT, FAJA | 2023-03 | No en main · faja ANA + geometría congelada en rama legacy | No | Solo en rama legacy: primera intersección D8 con el Rímac | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: solo nombre/contexto · PR #149 | P1 | ANA-FAJA-RD-SIGRID (SIGRID 6062); ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5768); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023 |
| La Cantuta | Cantuta | Lurigancho-Chosica · Lima | EVENT, FAJA | 2009-02, 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 6074); ANA-FAJA-RD-SIGRID (SIGRID 19341); INDECI-DDI-LIMA-2023-BALANCE; MUNI-LURIGANCHO-EVAR-2015 |
| La Libertad | Libertad | Lurigancho-Chosica · Lima | EVENT, FAJA, WORKS | 2015-03-23, 2023-03 | No en main · faja ANA + geometría congelada en rama legacy | No | Solo en rama legacy | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: solo nombre/contexto · PR #146, #149, #151 | P1 | IRFEN-REPO; MUNI-LURIGANCHO-EVAR-2015; INDECI-DDI-LIMA-2023-BALANCE; ANA-2017-2019-BARRERAS-DINAMICAS |
| Mariscal Castilla | — | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT, WORKS | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: solo nombre/contexto | P1 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5765); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; ANA-2017-2019-BARRERAS-DINAMICAS |
| Nicolás de Piérola (label component) | Quirio – Nicolás de Piérola | Lurigancho-Chosica · Lima | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | main: solo nombre/contexto · PR #149 | P2 | ANA-2017-2019-BARRERAS-DINAMICAS |
| Pablo Patrón/Dos Amigos | — | Lurigancho-Chosica · Lima | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | PREDES-CARTILLA-2017 |
| Pedregal | San Antonio de Pedregal; Pedregal o San Antonio; San Antonio | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT, FAJA, WORKS | 2023-03 | No en main · faja ANA + geometría congelada en rama legacy | Sí | Intersección D8 reproducible con el Rímac (techo HYDROLOGICALLY_CONNECTED en main) | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED) | main: unidad registrada `pedregal_san_antonio` · PR #148, #149, #326 | EXISTING | ANA-FAJA-RD-SIGRID (SIGRID 6066); ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5766); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; ANA-2017-2019-BARRERAS-DINAMICAS |
| Quirio | Quirio – Nicolás de Piérola; Quiro | Lurigancho-Chosica · Lima | EVENT, FAJA, IDENTITY, WORKS | 2023-03 | No en main · faja ANA + geometría congelada en rama legacy | Sí | Intersección D8 reproducible con el Rímac (techo HYDROLOGICALLY_CONNECTED en main) | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED) | main: unidad registrada `quirio` · PR #149 | EXISTING | ANA-FAJA-RD-SIGRID (SIGRID 6067); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; ANA-2017-2019-BARRERAS-DINAMICAS; MUNI-LURIGANCHO-PPRRD-2022-2025 |
| Rayos de Sol | Rayo de Sol – Corrales; Rayito del Sol; Quebrada Rayo del Sol; Corrales (Rayos del Sol) | Lurigancho-Chosica · Lima | EVENT, IDENTITY, WORKS | 2015-03-23 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: solo nombre/contexto · PR #146, #149, #151 | P1 | MUNI-LURIGANCHO-EVAR-2015; CENEPRED-2025-RAYO-DEL-SOL-RF; ANA-2017-2019-BARRERAS-DINAMICAS |
| Rosario | — | Lurigancho-Chosica · Lima | EVENT, IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | IGP-IT-001-2023; INGEMMET-SIGRID-434-TITLE |
| Santa María | — | Lurigancho-Chosica · Lima | EVENT, IDENTITY | 2015, 2017 | No | No | INGEMMET A7437 indica desembocadura en el río Rímac (margen derecha); nodo no reproducido | `EVENT_LEAD_UNVERIFIED` | no está | P1 | INGEMMET-A7437; MUNI-LURIGANCHO-PPRRD-2022-2025 |
| Santo Domingo | — | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT, FAJA, WORKS | — | No · pista: faja ANA (hitos por extraer) | No | Título de la ficha SIGRID: «tributario del río Rímac - margen izquierda»; nodo de confluencia no reproducido | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | main: solo nombre/contexto | P1 | ANA-FAJA-RD-SIGRID (SIGRID 19950); ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5808); IGP-IT-001-2023; ANA-2017-2019-BARRERAS-DINAMICAS |
| Señor de los Milagros | — | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P1 | INDECI-DDI-LIMA-2023-BALANCE; INGEMMET-A7459 |
| Virgen del Rosario | — | Lurigancho-Chosica · Lima | CRITICAL_POINT, EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P1 | INDECI-DDI-LIMA-2023-BALANCE; INGEMMET-A7459 |
| Vizcachera | — | Lurigancho-Chosica · Lima | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | INGEMMET-A7459 |
| Yanacoto | — | Lurigancho-Chosica · Lima | EVENT, FAJA, WORKS | 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: solo nombre/contexto | P1 | ANA-FAJA-RD-SIGRID (SIGRID 6068); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; ANIN-MUNI-LURIGANCHO-2026 |
| La Ronda | — | Lurigancho-Chosica · Lima † | EVENT, FAJA, WORKS | 2023-03 | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ EVENT_LEAD_UNVERIFIED, OUTLET_PENDING) | main: solo nombre/contexto | P1 | ANA-FAJA-RD-SIGRID (SIGRID 6064); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; ANA-2017-2019-BARRERAS-DINAMICAS |
| Huampaní | Huampani | Lurigancho-Chosica · Lima † | IDENTITY, WORKS | — | No | No | — | `IDENTITY_ONLY` | main: solo nombre/contexto | P2 | ANA-2017-2019-BARRERAS-DINAMICAS; PREDES-CARTILLA-2017 |
| Chucumayo | — | Matucana · Huarochirí | FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 19929) |
| Payhua | Paihua | Matucana · Huarochirí | EVENT | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | IGP-IT-001-2023 |
| Barba Blanca | — | distrito no indicado † | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | CENEPRED-SIGRID-13867 |
| Dos Barrios | — | distrito no indicado | EVENT, IDENTITY | 2012-04-05 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P1 | INGEMMET-A6608-2012-LA-RONDA-LOS-CONDORES (p. 30); SENAMHI-2020-QDAS-SANTO-DOMINGO-CANTUTA (p. 3); VILLACORTA-2018-UPM-THESIS-INGEMMET-TE0306 (p. 85) |
| Castilla | — | Lurigancho · Lima † | FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 6065) |
| Cupiche | — | Ricardo Palma · Huarochirí | CRITICAL_POINT, FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 6061); ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5775) |
| Cashahuacra | Casahuacra | Santa Eulalia · Huarochirí | CRITICAL_POINT, EVENT, GEOMETRY | — | Sí (ya en main) | No | El nodo de confluencia Santa Eulalia–Rímac está MISSING en main (no se admite aproximación) | `GEOMETRY_REPRODUCIBLE` (+ OUTLET_PENDING) | main: unidad registrada `cashahuacra` · PR #136, #146, #149, #151 | EXISTING | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5769); IRFEN-REPO; IGP-IT-001-2023 |
| Centro Santa Eulalia 1, 2 y 3 | — | Santa Eulalia · Huarochirí | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5807) |
| Cuculí | — | Santa Eulalia · Huarochirí | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | ANDINA-MVCS-2023-02-23 |
| Huayaringa | — | Santa Eulalia · Huarochirí | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5772) |
| Huayaringa Centro y Portada de Huayaringa | — | Santa Eulalia · Huarochirí | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5806) |
| Julio César Tello | — | Santa Eulalia · Huarochirí | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P2 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5770) |
| Shingolay | Chingolay | Santa Eulalia · Huarochirí | GEOMETRY | — | Sí (ya en main) | No | No afirmada | `GEOMETRY_REPRODUCIBLE` (+ OUTLET_PENDING) | main: unidad registrada `shingolay` · PR #136, #213, #326, #358 | EXISTING | IRFEN-REPO |
| Cuchimachay | — | Surco · Huarochirí | FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | no está | P1 | ANA-FAJA-RD-SIGRID (SIGRID 19619) |

### 2. Pisco / Ica (48 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| quebrada huachinga | — | Alto Larán | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5631) |
| quebrada pampas de chincha | — | Alto Larán | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5629) |
| quebrada pampas de los arrieros | — | El Carmen | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5630) |
| quebrada huancano ⚠ | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5622) |
| quebrada huayanga | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5730) |
| quebrada Huayanto | — | Huancano · Pisco | EVENT | 2025-02-06 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: nombrada como quebrada | P2 | COER-ICA-NP-041-2025 |
| quebrada huayanto-pampano | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5732) |
| quebrada paracas | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: unidad registrada `ica_paracas` | EXISTING | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5733) |
| quebrada quitasol | — | Huancano · Pisco | CRITICAL_POINT, EVENT | 2025-02-06 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: unidad registrada `ica_quitasol` | EXISTING | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5729); COER-ICA-NP-041-2025 |
| quebrada reposo | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5731) |
| quebrada san vicente | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5728) |
| quebrada villanueva | — | Huancano | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5621) |
| quebrada auquix | — | Humay | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5617) |
| quebrada hoyada rancheria | — | Humay | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5618) |
| quebrada huaya grande | — | Humay | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5620) |
| quebrada humay ⚠ | — | Humay | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #213 | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5726) |
| quebrada montesierpe | — | Humay | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5727) |
| quebrada el molino | — | Ingenio | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | solo rama/PR · PR #330 | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5637) |
| quebrada la ayapana | — | Ingenio | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | solo rama/PR · PR #330 | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5638) |
| quebrada carlos tijero | — | Llipata | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5725) |
| quebrada san antonio | — | Llipata | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5723) |
| quebrada la falda | — | Palpa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5720) |
| quebrada pueblo nuevo | — | Palpa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5724) |
| quebrada sacramento | — | Palpa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5722) |
| quebrada san ignacio | — | Palpa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5721) |
| quebrada saramarca | — | Palpa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5719) |
| quebrada cardal-sanjon | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5736) |
| quebrada chantay | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5713) |
| quebrada huambo | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5714) |
| quebrada la isla | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5715) |
| quebrada pacoya | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5737) |
| quebrada palmar | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5712) |
| quebrada río grande ⚠ | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #330 | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5718) |
| quebrada san jacinto | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5717) |
| quebrada santa rosa | — | Río Grande | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5716) |
| quebrada el suchi | — | San José de los Molinos | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5734) |
| quebrada la yesera | — | San José de los Molinos | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: unidad registrada `ica_la_yesera` | EXISTING | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5624) |
| quebrada rancheria | — | San José de los Molinos | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5735) |
| quebrada tortolita | — | San José de los Molinos | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: unidad registrada `ica_tortolita` | EXISTING | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5623) |
| quebrada alto laran | — | Santa Cruz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5641) |
| quebrada el carmen | — | Santa Cruz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5640) |
| quebrada pampa blanca | — | Santa Cruz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5711) |
| quebrada tibillo ⚠ | — | Tibillo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5639) |
| quebrada cansas | — | Tinguiña | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: unidad registrada `ica_cansas` · PR #330 | EXISTING | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5628) |
| quebrada cabeza de cura | — | Vista Alegre | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5635) |
| quebrada nueva villa | — | Vista Alegre | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5634) |
| quebrada nuevo vista alegre | — | Vista Alegre | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5633) |
| quebrada virgen de chapi | — | Vista Alegre | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5632) |

### 3. Santa / Casma (16 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| quebrada el olivar ⚠ | — | Buenavista · Casma | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5986) |
| río seco ⚠ | — | Buenavista · Casma | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | rama: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5985) |
| quebrada cochapeti ⚠ | — | Cáceres del Perú · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5978) |
| quebrada lampanin ⚠ | — | Cáceres del Perú · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5980) |
| quebrada pampa la julia | — | Casma · Casma | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5984) |
| quebrada tomeque | — | Casma · Casma | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5993) |
| quebrada cascajal ⚠ | — | Chimbote · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5975) |
| quebradas el progreso 1 - el progreso 2 | — | Chimbote · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5974) |
| quebrada el milagro | — | Coishco · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5976) |
| quebrada virgen del carmen - luis a. sánchez | — | Coishco · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5977) |
| quebrada de chumpi | — | Moro · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5981) |
| quebradas san cristóbal y solivin | — | Nepeña · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5988) |
| quebrada san antonio | — | Nuevo Chimbote · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5979) |
| río samanco ⚠ | — | Samanco · Santa | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5992) |
| quebrada nivin ⚠ | — | Yaután · Casma | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5987) |
| quebrada tomeque ⚠ | — | Yaután · Casma | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5982) |

### 4. Tumbes / Zorritos (68 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Piedritas | — | Aguas Verdes · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.17) |
| Cancas ⚠ | — | Canoas de Punta Sal · Contralmirante Villar | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.23) |
| Canoas de Punta Sal ⚠ | — | Canoas de Punta Sal · Contralmirante Villar | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #231, #324, #351 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.24) |
| Corrales ⚠ | — | Corrales · Tumbes | CRITICAL_POINT, IDENTITY | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #231 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.32); ANDINA-TUMBES-2024-02-21 |
| Cristales ⚠ | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.34) |
| El Rodeo ⚠ | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.2) |
| La Arena | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.1) |
| Malval ⚠ | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.36) |
| Relengal ⚠ | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.3) |
| San Francisco ⚠ | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.33) |
| Urcos ⚠ | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.35) |
| Vista al valle | — | Corrales · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.4) |
| Charán | — | La Cruz · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.28) |
| La Cruz ⚠ | — | La Cruz · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #323, #351 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.29) |
| La Cruz 01 | — | La Cruz · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.27) |
| Los Cerezos ⚠ | — | La Cruz · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.30) |
| Faical | — | Matapalo · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.22) |
| Cruz Blanca ⚠ | — | Pampas de Hospital · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.31) |
| Altura de la posta jardín de niños | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.12) |
| Barrio San José-Uña de Gato ⚠ | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.14) |
| Barrio Santa Rosa-Uña de Gato ⚠ | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.10) |
| El Matujo o Piñata | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.11) |
| Juan Velasco Alvarado | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.13) |
| La Chava | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.7) |
| La Chiva | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.8) |
| La Palma ⚠ | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.6) |
| Papayal ⚠ | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.5) |
| San Miguel | — | Papayal · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.9) |
| Casa Blanqueada - I.E. 7 de Junio ⚠ | — | San Jacinto · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.21) |
| Chorillos | — | San Jacinto · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.44) |
| La Urbina | — | San Jacinto · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.43) |
| Oidor ⚠ | — | San Jacinto · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.42) |
| Badén Tacural | — | San Juan de la Virgen · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.16) |
| San Juan de la Virgen ⚠ | — | San Juan de la Virgen · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.41) |
| Tacural ⚠ | — | San Juan de la Virgen · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.15) |
| La Chira | — | Tumbes · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.38) |
| Luey (Lucy) | — | Tumbes · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.40) |
| Pampa Grande 02 | — | Tumbes · Tumbes | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.39) |
| Pedregal | — | Tumbes · Tumbes | CRITICAL_POINT, IDENTITY | — | No | No | — | `IDENTITY_ONLY` | rama: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.37); ANDINA-TUMBES-2024-02-21 |
| Zarumilla Marco Felipe | — | Zarumilla · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.18) |
| Zarumilla Quintiliano | — | Zarumilla · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.19) |
| Zarumilla Tecnológico-Zarumilla | — | Zarumilla · Zarumilla | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.20) |
| La Tucilla | — | Zorritos · Contralmirante Villar | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada · PR #351 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.25) |
| Los Pozos | — | Zorritos · Contralmirante Villar | CRITICAL_POINT, IDENTITY | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada · PR #323, #324, #351 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 9 f.26); ANDINA-TUMBES-2023-04-01 |
| Algarabillo | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Algarrobal | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Bocapán | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada · PR #231, #317 | P3 | MEF-DS-181-2023-EF-TUMBES |
| Bonanza | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Chabaco | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Charán | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2024-02-21 |
| Coloma | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2024-02-21 |
| El Charán | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Garbanzal | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| La Jota | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2023-04-01; ANDINA-TUMBES-2024-02-21 |
| La Rocana | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Las Vacas | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2024-02-21 |
| Los Cedros | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Los Cerezos | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2024-02-21 |
| Los Pinos | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada · PR #231 | P3 | ANDINA-TUMBES-2024-02-21 |
| Luey | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Panales-Casitas | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2024-02-21 |
| Pedregal | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | rama: mención sin confirmar | P3 | MEF-DS-181-2023-EF-TUMBES |
| Primero de Febrero | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Punta Sal | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #231, #324, #351 | P3 | MEF-DS-181-2023-EF-TUMBES |
| San Isidro | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| San José | — | distrito no indicado | IDENTITY | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANDINA-TUMBES-2024-02-21 |
| Vaquería | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |
| Villa Jardín | — | distrito no indicado | WORKS | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | MEF-DS-181-2023-EF-TUMBES |

### 5a. Otros valles de Lima y Lima Metropolitana (73 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| quebrada chipial / lashcamayo | — | Ámbar · Huaura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5705) |
| quebrada huisca | — | Ámbar · Huaura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5780) |
| quebrada huyunte | — | Ámbar · Huaura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5706) |
| Los Inocentes | — | Ancón · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| quebrada río chico ⚠ | — | Asia | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #213 | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5798) |
| quebrada río grande ⚠ | — | Asia | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5799) |
| quebrada río seco ⚠ | — | Asia | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | rama: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5797) |
| quebradas rampe i y ii - huayopampa | — | Atavillos Bajo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5760) |
| quebrada calango ⚠ | — | Calango | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no evaluable | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5776) |
| quebrada correviento | — | Calango | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5777) |
| quebrada la capilla | — | Calango | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5778) |
| quebrada la vuelta-yuncaviri | — | Calango | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5781) |
| quebrada millay | — | Calango | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5782) |
| quebrada minay | — | Calango | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5783) |
| Hacienda Caballero | — | Carabayllo · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Huatocay | — | Carabayllo · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Rio Seco ⚠ | — | Carabayllo · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| San Lorenzo | — | Carabayllo · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| quebrada ihuanco | — | Cerro Azul | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5803) |
| Chilca Brazo Norte | — | Chilca · Cañete | FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | main: unidad registrada `lima_sur_chilca_pucusana (source ANA-CHILCA-BRAZO-NORTE-RD0641-2024)` | EXISTING | ANA-FAJA-RD-SIGRID (SIGRID 17739) |
| Huaycán | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Huaycán de Cieneguilla | — | Cieneguilla · Lima | FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | no está | P3 | ANA-FAJA-RD-SIGRID (SIGRID 18341) |
| La Cantera | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Molle | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Río Seco ⚠ | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Tambo Viejo | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Terrazas | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Tinajas | — | Cieneguilla · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| quebrada corralon | — | Coayllo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5800) |
| quebrada piedra hueca | — | Coayllo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5801) |
| quebrada san juan de quisque | — | Coayllo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5802) |
| río ucruschaca ⚠ | — | distrito no indicado (CP Bellavista) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5739) |
| río chanya ⚠ | — | distrito no indicado (CP Chanya) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5740) |
| quebrada guengue y río quichas tramo 2 | — | distrito no indicado (CP Guengue y Quichas) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5741) |
| quebrada huerequeque | — | distrito no indicado (CP Huayan) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5743) |
| quebrada lumbra ⚠ | — | distrito no indicado (CP Lumbra) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no evaluable | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5744) |
| quebrada pomaca y río quichas tramo 1 | — | distrito no indicado (CP Pomaca y Quichas) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5742) |
| quebrada huamacho | — | distrito no indicado (CP San Miguel) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5745) |
| río seco ⚠ | — | distrito no indicado (CP Santo Domingo y Campiña de Supe) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no evaluable | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5738) |
| quebrada tancaran | — | Ihuarí | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5756) |
| quebrada jeronimo | — | Lunahuaná | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5750) |
| quebrada jita | — | Lunahuaná | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5751) |
| quebrada los palomos | — | Lunahuaná | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5752) |
| quebrada lucumo | — | Lunahuaná | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5753) |
| quebrada paullo | — | Lunahuaná | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar · PR #213 | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5754) |
| Pucara | — | Lurín · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| quebrada huarangal | — | Mala | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5794) |
| quebrada ihuanco | — | Mala | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5795) |
| quebrada san juan | — | Mala | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5796) |
| quebrada carhuan o cutac | — | Manás · Cajatambo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5707) |
| quebradas cantera y cantera alta | — | Nuevo Imperial | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5749) |
| quebrada pocoto | — | Nuevo Imperial | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5748) |
| quebrada michimachay (río quichas) CP Michimachay | — | Oyón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5779) |
| quebrada romani | — | Pacarán | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5755) |
| quebrada tacayita | — | Pacarán | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5804) |
| quebrada shipra | — | Pacaraos | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5762) |
| Tinajas-Cosanche | — | Pachacámac · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Quebrada seca rio Chilca | — | Pucusana · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| Malanche | — | Punta Hermosa · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: unidad registrada `lima_sur_malanche (candidate inventory v0.2)` · PR #148, #213 | EXISTING | INDECI-DDI-LIMA-2023-BALANCE |
| Río Seco (Malanche) ⚠ | — | Punta Hermosa · Lima | FAJA | — | No · pista: faja ANA (hitos por extraer) | No | — | `GEOMETRY_PENDING` (+ OUTLET_PENDING) | main: mención sin confirmar | P3 | ANA-FAJA-RD-SIGRID (SIGRID 13056) |
| Cruz de Hueso | — | Punta Negra · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | no está | P3 | INDECI-DDI-LIMA-2023-BALANCE |
| quebrada roldan-la capilla | — | Quilmaná | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5746) |
| quebrada los jardines | — | San Antonio | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5785) |
| Jicamarca | — | San Juan de Lurigancho · Lima | EVENT | 2023-03 | No | No | — | `EVENT_LEAD_UNVERIFIED` | main: unidad registrada `Jicamarca discovery system (config/phase2_jicamarca_discovery_v0_2.json)` | EXISTING | INDECI-DDI-LIMA-2023-BALANCE |
| quebrada san carlos | — | San Vicente de Cañete | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5747) |
| quebrada río baños ⚠ | — | Santa Cruz de Andamarca | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5761) |
| quebrada las viñas de sta cruz | — | Santa Cruz de Flores | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5784) |
| quebradas ayrancho, llancay y chhuichihui | — | Sumbilca | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5759) |
| quebrada colca-huandaro | — | Sumbilca | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5758) |
| quebrada inquirhuay | — | Sumbilca | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5757) |
| río seco ⚠ | — | Supe · Barranca | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5709) |
| quebrada taitalaynas | — | Supe · Barranca | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5708) |
| quebrada picamaran | — | Zúñiga | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5805) |

### 5b. Costa de Piura (40 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Boqueron de Núñez | — | Bellavista · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.24) |
| El Gallo | — | Castilla · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.16) |
| Señor de los Milagros | — | Castilla · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.33) |
| Tacala ⚠ | — | Castilla · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.32) |
| Cumbibira Centro ⚠ | — | Catacaos · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.31) |
| Cumbibira Sur ⚠ | — | Catacaos · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.30) |
| Bolognesi | — | Colan · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada · PR #332 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.9) |
| Grau | — | Colan · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | solo rama/PR · PR #332 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.10) |
| Sucre | — | Colan · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada · PR #332 | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.11) |
| Coveñas | — | La Union · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.34) |
| El Mercado ⚠ | — | Miguel Checa Sojo · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.77) |
| Los Acaros ⚠ | — | Miguel Checa Sojo · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.76) |
| Rambo ⚠ | — | Miguel Checa Sojo · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.78) |
| Teodolo Miguel Cortez ⚠ | — | Miguel Checa Sojo · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.79) |
| 9 de diciembre | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | solo rama/PR | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.5) |
| Arroyo Mio | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.4) |
| Atahualpa | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.8) |
| Cahuide | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.7) |
| Centenario | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | solo rama/PR | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.2) |
| Libertad | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | rama: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.3) |
| Salaverry | — | Paita · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | rama: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.6) |
| Mocho Delgado | — | Salitral · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.1) |
| Parachique ⚠ | — | Sechura · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.27) |
| Puerto Rico ⚠ | — | Sechura · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.26) |
| Puerto Rico-Bayovar | — | Sechura · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.25) |
| Cieneguillo | — | Sullana · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.23) |
| Añalque | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.42) |
| Carneros | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.41) |
| El Ereo | — | Tambogrande · Sullana | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.12) |
| Honda | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.38) |
| Los Luises | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.36) |
| Parales | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.37) |
| Salinas (Pueblo Nuevo) | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.39) |
| Santa Julia Atahualpa | — | Tambogrande · Piura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.40) |
| Cementerio | — | Vice · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.35) |
| Don Juan y San José Vice | — | Vice · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.15) |
| El Alto Perú | — | Vice · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.28) |
| El Pozo | — | Vice · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.29) |
| Las Monjas | — | Vice · Sechura | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.14) |
| Avelino | — | Vichayal · Paita | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.22) |

### 5c. Lambayeque (46 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cojal ⚠ | — | Cayalti · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.27) |
| Guayaquil ⚠ | — | Cayalti · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.43) |
| La Curva ⚠ | — | Cayalti · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.44) |
| Chochope ⚠ | — | Chochope · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.36) |
| El Espinal (Tres Puntas) | — | Chochope · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.3) |
| La Rinconada | — | Chochope · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.1) |
| Lindero | — | Chochope · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.2) |
| Tineo | — | Chochope · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.4) |
| Chumillan | — | Chongoyape · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.34) |
| quebrada utiyacu | — | Chongoyape · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5611); ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.33) |
| La Guitarra | — | Lagunas-Motupe · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.41) |
| La Pared | — | Mesones Muro · Ferreñafe | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.23) |
| Río Loco ⚠ | — | Mesones Muro · Ferreñafe | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.24) |
| Alto Perú ⚠ | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.14) |
| Canal de los Incas | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.13) |
| Cerro La Vieja ⚠ | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.12) |
| El Zapote | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.7) |
| Las Pirias | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.6) |
| Olos | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.11) |
| Piedra del Toro | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.39) |
| Salitral ⚠ | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.5) |
| Santa Elmira | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.8) |
| Sonolipe ⚠ | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.35); ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.40) |
| Totoras | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.9) |
| Yocape | — | Motupe · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.10) |
| La Viña ⚠ | — | Nueva Arica · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.26) |
| Leque Leque | — | Nueva Arica · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.45) |
| Nueva Arica ⚠ | — | Nueva Arica · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.25) |
| Agua Blanca Km. 12 | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.15) |
| Chapita Km. 03 | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.17) |
| Cruce Antiguo ⚠ | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.22) |
| Cruce Nuevo Km. 01 ⚠ | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.20) |
| El Palmo Km. 04 | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.19) |
| El Virrey ⚠ | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.47) |
| Insculas ⚠ | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.37) |
| La Torre Km. 12 | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.16) |
| Las vecinas Km. 01 | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.21) |
| Los Positos | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.38) |
| Teniente Palmo Boliches | — | Olmos · Lambayeque | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.18) |
| Algarrobal | — | Oyotun · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: nombrada como quebrada | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.28) |
| German Muñoz | — | Oyotun · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.30) |
| La Compuerta ⚠ | — | Oyotun · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.46) |
| Nueva Esperanza | — | Oyotun · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | main: mención sin confirmar | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.29) |
| s/n | — | Patapo · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.31) |
| Utiyacu | — | Patapo · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.32) |
| San Nicolás ⚠ | — | Zaña · Chiclayo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 17 f.42) |

### 5d. La Libertad (parcial) (9 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| quebrada gashpa - la botella | — | Chicama | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5590) |
| quebradas la monica - piedra molino | — | Chicama | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5660) |
| quebrada corrales-muyque | — | Cochorco | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5604) |
| quebrada sholca | — | Huamachuco | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5603) |
| quebrada santo domingo | — | Laredo | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5605) |
| quebrada leon | — | Poroto | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5606) |
| quebrada cancate | — | Santiago de Chuco | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5580) |
| quebrada s/n | — | Virú | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5607) |
| quebrada seca | — | Virú | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P3 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5608) |

### 5e. Áncash interior (18 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| quebrada llamachupan ⚠ | — | Acas · Ocros | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6001) |
| quebradas piña urán y esperanza | — | Anta · Carhuaz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5997) |
| quebrada chamana ⚠ | — | Antonio Raymondi · Bolognesi | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5998) |
| quebrada llamarumi ⚠ | — | Antonio Raymondi · Bolognesi | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5999) |
| quebrada huachecza | — | Chavín de Huántar · Huari | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6009) |
| quebrada venado muerto ⚠ | — | Cochas · Ocros | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6002) |
| quebrada capellanía | — | distrito no indicado (CP Hornillos) | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6000) |
| quebrada s/n | — | Huallanca · Bolognesi | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6007) |
| río seco ⚠ | — | Huaraz · Huaraz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5996) |
| quebrada pomachaca ⚠ | — | Masin · Huari | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6010) |
| quebrada s/n | — | Pariahuanca · Carhuaz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5994) |
| quebrada cañari | — | Pomabamba · Pomabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6005) |
| quebrada colpa (aylahuallon) | — | Pomabamba · Pomabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6004) |
| quebradas jatun parco y ichic parco | — | Pomabamba · Pomabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6003) |
| quebrada pariacolca ⚠ | — | Quillo · Yungay | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5983) |
| quebradas vincocota, huaytuna y collpu uran | — | Rahuapampa, Masin, Pariahuanca · Huari, Carhuaz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6008) |
| quebradas pachacutec-manco capac-chuna-colpa chirimoyo-pingullo alto/bajo-chico huitron | — | Sihuas · Sihuas | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 6006) |
| quebrada lloclla | — | Taricá · Huaraz | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5995) |

### 5f. Piura interior (38 filas)

| Nombre documental | Variantes observadas (sin adjudicar) | Distrito · provincia | Evidencia | Fechas (pista sin verificar) | Geometría reproducible | Outlet | Relación con colector | Estado | En IRFEN | Prio. | Fuente e identificador |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Carrizo | — | Buenos Aires · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.19) |
| El Ingenio ⚠ | — | Buenos Aires · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.21) |
| La Pilca ⚠ | — | Buenos Aires · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.20) |
| El Carrizo | — | Canchaque · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.71); ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.72) |
| La Sabana (Chorro Blanco) | — | Canchaque · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.74) |
| Pusmalca | — | Canchaque · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.73) |
| Algarrobos (Río Limón) | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.52) |
| Chignia Alta | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.51) |
| Cuchupampa | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.49) |
| El Buitre | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.57) |
| El Cementerio | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.50) |
| El Overal | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.56) |
| El Tocto | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.43) |
| Peña Azul | — | Huamarca · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.48) |
| El Virrey ⚠ | — | La Matanza · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.75) |
| San Francisco | — | La Matanza · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.44) |
| Caracucho ⚠ | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.60) |
| Cruz Alta ⚠ | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.64) |
| El Alto Papayo | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.63) |
| El Guayaquil | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.62) |
| El Higuerón | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.55) |
| Guayaquil Alto | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.61) |
| La Curva | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.54) |
| La Laguna ⚠ | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.65) |
| La Loma-La Hoyada | — | Lalaquiz · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.53) |
| Malacasí | — | Salitral · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.18) |
| Bigote | — | San Juan de Bigote · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.17) |
| La Goya | — | San Juan de Bigote · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.45) |
| La Layo | — | San Juan de Bigote · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.46) |
| La Loca | — | San Juan de Bigote · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.47) |
| El Limón | — | San Miguel de El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.70) |
| El Pashul | — | San Miguel de El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.69) |
| El Yumbe | — | San Miguel de El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.68) |
| Agua Tocto | — | San Miguel El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.59) |
| Cerro Blanco | — | San Miguel El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.58) |
| El Algarrobo | — | San Miguel El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.66) |
| El Ceibo | — | San Miguel El Faique · Huancabamba | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.67) |
| Paccha ⚠ | — | Tambogrande · Morropón | CRITICAL_POINT | — | No | No | — | `IDENTITY_ONLY` | no está | P4 | ANA-2016-COMPLEMENTACION-NACIONAL (Cuadro 11 f.13) |

⚠ = la etiqueta es un nombre de río o coincide con el nombre de un centro poblado/distrito; una coincidencia en el repositorio no confirma una unidad. † = ubicación con reserva; ver `location_note` en el JSON. Las etiquetas en minúsculas y sin tildes proceden del nombre de archivo de SIGRID o de la lectura automática del rótulo del mapa y no se corrigieron.

## 4. Candidatos ya presentes en IRFEN

**41** filas ya están en `main`; **24** son menciones sin confirmar; **11** existen solo en ramas o PR abiertos.

| Fila | Nombre | Corredor | Situación en IRFEN |
|---|---|---|---|
| `lima_huaycoloro` | Huaycoloro | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: unidad registrada `huaycoloro (v0.8 pilot)` · `config/historical_events.json` |
| `lima_lurigancho_california` | California | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · PR #149 · `config/phase2_rimac_local_historical_evidence_registry_v0_1.json` |
| `lima_lurigancho_carossio` | Carossio | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · PR #146, #149, #151 · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_chacrasana` | Chacrasana | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_corrales` | Corrales | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · PR #149 · `agent/chosica-2015-control-adjudication-v0.1` |
| `lima_lurigancho_la_libertad` | La Libertad | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · PR #146, #149, #151 · `README.md` |
| `lima_lurigancho_mariscal_castilla` | Mariscal Castilla | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_nicolas_de_pierola_label` | Nicolás de Piérola (label component) | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · PR #149 · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_pedregal_san_antonio` | Pedregal | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: unidad registrada `pedregal_san_antonio` · PR #148, #149, #326 · `config/phase2_ana2015_quirio_pedregal_faja_context_v0_1.json` |
| `lima_lurigancho_quirio` | Quirio | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: unidad registrada `quirio` · PR #149 · `config/phase2_ana2015_quirio_pedregal_faja_context_v0_1.json` |
| `lima_lurigancho_rayos_de_sol` | Rayos de Sol | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · PR #146, #149, #151 · `config/phase2_expansion_scope.json` |
| `lima_lurigancho_santo_domingo` | Santo Domingo | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_yanacoto` | Yanacoto | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_la_ronda` | La Ronda | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_lurigancho_huampani` | Huampaní | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: solo nombre/contexto · `config/phase2_rimac_receiver_context_v0_1.json` |
| `lima_santa_eulalia_cashahuacra` | Cashahuacra | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: unidad registrada `cashahuacra` · PR #136, #146, #149, #151 · `config/phase2_candidate_inventory_v0_1.json` |
| `lima_santa_eulalia_shingolay` | Shingolay | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | main: unidad registrada `shingolay` · PR #136, #213, #326, #358 · `config/phase2_candidate_inventory_v0_1.json` |
| `ica_huancano_huayanto` | quebrada Huayanto | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_2019_named_events_v0_1.json` |
| `ica_huancano_paracas` | quebrada paracas | PISCO_ICA | main: unidad registrada `ica_paracas` · `config/phase2_south_coast_ica_arequipa_discovery_v0_1.json` |
| `ica_huancano_quitasol` | quebrada quitasol | PISCO_ICA | main: unidad registrada `ica_quitasol` · `config/phase2_ica_2019_named_events_v0_1.json` |
| `ica_llipata_carlos_tijero` | quebrada carlos tijero | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_2019_named_events_v0_1.json` |
| `ica_palpa_sacramento` | quebrada sacramento | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_historical_events_v0_1.json` |
| `ica_palpa_san_ignacio` | quebrada san ignacio | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_historical_events_v0_1.json` |
| `ica_rio_grande_san_jacinto` | quebrada san jacinto | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_2019_named_events_v0_1.json` |
| `ica_rio_grande_santa_rosa` | quebrada santa rosa | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_2019_named_events_v0_1.json` |
| `ica_san_jose_de_los_molinos_la_yesera` | quebrada la yesera | PISCO_ICA | main: unidad registrada `ica_la_yesera` |
| `ica_san_jose_de_los_molinos_tortolita` | quebrada tortolita | PISCO_ICA | main: unidad registrada `ica_tortolita` |
| `ica_tinguina_cansas` | quebrada cansas | PISCO_ICA | main: unidad registrada `ica_cansas` · PR #330 · `phase2/ica-official-ravines-v0-1` |
| `ica_vista_alegre_nuevo_vista_alegre` | quebrada nuevo vista alegre | PISCO_ICA | main: nombrada como quebrada · `config/phase2_ica_historical_events_v0_1.json` |
| `ancash_casma_tomeque` | quebrada tomeque | SANTA_CASMA | main: nombrada como quebrada · `site/data/phase2/source_assessments/casma_gate_b_documentary_evidence_review_v0_1.json` |
| `tumbes_zorritos_la_tucilla` | La Tucilla | TUMBES_ZORRITOS | main: nombrada como quebrada · PR #351 · `site/data/phase2/sources/tumbes_zorritos_ana_hydrography_adjudication_matrix_v0_1.json` |
| `tumbes_zorritos_los_pozos` | Los Pozos | TUMBES_ZORRITOS | main: nombrada como quebrada · PR #323, #324, #351 · `site/data/phase2/sources/tumbes_zorritos_extended_identity_context_v0_1.json` |
| `tumbes_district_unknown_bocapan` | Bocapán | TUMBES_ZORRITOS | main: nombrada como quebrada · PR #231, #317 · `config/phase2_north_coast_discovery_inventory_v0_1.json` |
| `tumbes_district_unknown_los_pinos` | Los Pinos | TUMBES_ZORRITOS | main: nombrada como quebrada · PR #231 · `site/data/phase2/sources/tumbes_zorritos_bocapan_official_evidence_v0_1.json` |
| `lambayeque_oyotun_algarrobal` | Algarrobal | LAMBAYEQUE | main: nombrada como quebrada · `docs/CHONGOYAPE_OYOTUN_ZANA_HYDROLOGIC_MIGRATION.md` |
| `lima_chilca_chilca_brazo_norte` | Chilca Brazo Norte | LIMA_OTHER_VALLEYS_AND_METROPOLITAN | main: unidad registrada `lima_sur_chilca_pucusana (source ANA-CHILCA-BRAZO-NORTE-RD0641-2024)` |
| `lima_district_not_in_title_huerequeque` | quebrada huerequeque | LIMA_OTHER_VALLEYS_AND_METROPOLITAN | main: nombrada como quebrada · `site/data/phase2/sources/lima_norte_chancay_huaral_official_evidence_v0_1.json` |
| `lima_punta_hermosa_malanche` | Malanche | LIMA_OTHER_VALLEYS_AND_METROPOLITAN | main: unidad registrada `lima_sur_malanche (candidate inventory v0.2)` · PR #148, #213 · `config/phase2_candidate_inventory_v0_1.json` |
| `lima_san_juan_de_lurigancho_jicamarca` | Jicamarca | LIMA_OTHER_VALLEYS_AND_METROPOLITAN | main: unidad registrada `Jicamarca discovery system (config/phase2_jicamarca_discovery_v0_2.json)` · `config/phase2_jicamarca_igp_channel_line_freeze_v0_1.json` |
| `piura_colan_bolognesi` | Bolognesi | PIURA_COAST | main: nombrada como quebrada · PR #332 · `config/phase2_north_coast_discovery_inventory_v0_1.json` |
| `piura_colan_sucre` | Sucre | PIURA_COAST | main: nombrada como quebrada · PR #332 · `config/phase2_north_coast_discovery_inventory_v0_1.json` |
| `ica_ingenio_el_molino` | quebrada el molino | PISCO_ICA | solo rama/PR · PR #330 · `phase2/ica-official-ravines-v0-1` |
| `ica_ingenio_la_ayapana` | quebrada la ayapana | PISCO_ICA | solo rama/PR · PR #330 · `phase2/ica-official-ravines-v0-1` |
| `ancash_buenavista_rio_seco` | río seco | SANTA_CASMA | rama: mención sin confirmar · `ci/pytest-collection-gate-v0-4` |
| `tumbes_tumbes_pedregal` | Pedregal | TUMBES_ZORRITOS | rama: mención sin confirmar · `ci/pytest-collection-gate-v0-4` |
| `tumbes_district_unknown_pedregal` | Pedregal | TUMBES_ZORRITOS | rama: mención sin confirmar · `ci/pytest-collection-gate-v0-4` |
| `lima_asia_rio_seco` | quebrada río seco | LIMA_OTHER_VALLEYS_AND_METROPOLITAN | rama: mención sin confirmar · `ci/pytest-collection-gate-v0-4` |
| `piura_colan_grau` | Grau | PIURA_COAST | solo rama/PR · PR #332 · `phase2/piura-colan-child-hydrology-v0-1` |
| `piura_paita_9_de_diciembre` | 9 de diciembre | PIURA_COAST | solo rama/PR · `phase2-colan-local-identity-freeze-20260925` |
| `piura_paita_centenario` | Centenario | PIURA_COAST | solo rama/PR · `phase2-colan-child-identity-v02` |
| `piura_paita_libertad` | Libertad | PIURA_COAST | rama: mención sin confirmar · `phase2-colan-local-identity-freeze-20260925` |
| `piura_paita_salaverry` | Salaverry | PIURA_COAST | rama: mención sin confirmar · `phase2-colan-local-identity-freeze-20260925` |

## 5. Candidatos faltantes

**325** filas no aparecen en `main`, ramas ni PR. Las de mayor prioridad:

| Prio. | Nombre | Distrito | Estado | Fuente |
|---|---|---|---|---|
| P1 | Castilla | Lurigancho | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 6065) |
| P1 | Chucumayo | Matucana | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 19929) |
| P1 | Cuchimachay | Surco | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 19619) |
| P1 | Cupiche | Ricardo Palma | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 6061); ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5775) |
| P1 | Cusipata | Chaclacayo | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 13203); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023 |
| P1 | Don Bosco | Chaclacayo | `EVENT_LEAD_UNVERIFIED` | INDECI-DDI-LIMA-2023-BALANCE |
| P1 | Dos Barrios | no indicado | `EVENT_LEAD_UNVERIFIED` | INGEMMET-A6608-2012-LA-RONDA-LOS-CONDORES; SENAMHI-2020-QDAS-SANTO-DOMINGO-CANTUTA; VILLACORTA-2018-UPM-THESIS-INGEMMET-TE0306 |
| P1 | Huascarán | Chaclacayo | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 19205); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023; PRESS-LEAD |
| P1 | Huaycán (Ate) | Ate | `EVENT_LEAD_UNVERIFIED` | INDECI-DDI-LIMA-2023-BALANCE |
| P1 | La Cantuta | Lurigancho-Chosica | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 6074); ANA-FAJA-RD-SIGRID (SIGRID 19341); INDECI-DDI-LIMA-2023-BALANCE; MUNI-LURIGANCHO-EVAR-2015 |
| P1 | Los Cóndores | Chaclacayo | `GEOMETRY_PENDING` | ANA-FAJA-RD-SIGRID (SIGRID 10436); INDECI-DDI-LIMA-2023-BALANCE; IGP-IT-001-2023 |
| P1 | Santa María | Lurigancho-Chosica | `EVENT_LEAD_UNVERIFIED` | INGEMMET-A7437; MUNI-LURIGANCHO-PPRRD-2022-2025 |
| P1 | Señor de los Milagros | Lurigancho-Chosica | `EVENT_LEAD_UNVERIFIED` | INDECI-DDI-LIMA-2023-BALANCE; INGEMMET-A7459 |
| P1 | Virgen del Rosario | Lurigancho-Chosica | `EVENT_LEAD_UNVERIFIED` | INDECI-DDI-LIMA-2023-BALANCE; INGEMMET-A7459 |
| P2 | Barba Blanca | no indicado | `IDENTITY_ONLY` | CENEPRED-SIGRID-13867 |
| P2 | Callahuanca | no indicado | `IDENTITY_ONLY` | ANDINA-MVCS-2023-02-23 |
| P2 | Centro Santa Eulalia 1, 2 y 3 | Santa Eulalia | `IDENTITY_ONLY` | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5807) |
| P2 | Coricancha | Lurigancho-Chosica | `IDENTITY_ONLY` | INGEMMET-A7459; PREDES-CARTILLA-2017 |
| P2 | Cuculí | Santa Eulalia | `IDENTITY_ONLY` | ANDINA-MVCS-2023-02-23 |
| P2 | El Cuadro | Chaclacayo | `IDENTITY_ONLY` | PRESS-LEAD |
| P2 | Huayaringa | Santa Eulalia | `IDENTITY_ONLY` | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5772) |
| P2 | Huayaringa Centro y Portada de Huayaringa | Santa Eulalia | `IDENTITY_ONLY` | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5806) |
| P2 | Julio César Tello | Santa Eulalia | `IDENTITY_ONLY` | ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS (SIGRID 5770) |
| P2 | La Floresta | Chaclacayo | `IDENTITY_ONLY` | PREDES-CARTILLA-2017 |
| P2 | Pablo Patrón/Dos Amigos | Lurigancho-Chosica | `IDENTITY_ONLY` | PREDES-CARTILLA-2017 |
| P2 | Payhua | Matucana | `IDENTITY_ONLY` | IGP-IT-001-2023 |
| P2 | Rosario | Lurigancho-Chosica | `IDENTITY_ONLY` | IGP-IT-001-2023; INGEMMET-SIGRID-434-TITLE |
| P2 | Vizcachera | Lurigancho-Chosica | `IDENTITY_ONLY` | INGEMMET-A7459 |

El resto (P3/P4) está en la tabla maestra con «no está» en la columna *En IRFEN* y en `derived_views.missing_from_irfen` del JSON.

## 6. Aliases por adjudicar

Ninguna relación de nombres se resolvió en esta auditoría. Las variantes son etiquetas documentales, no alias. Cuando una fila reúne evidencia rotulada con una variante (campo `label_in_source` del JSON, p. ej. la faja «Cusipata (San Bartolomé)» en la fila Cusipata o las barreras «Quirio – Nicolás de Piérola» en la fila Quirio), su estado depende de que esa relación se adjudique; si se rechaza, la evidencia debe pasar a una fila propia.

| Etiquetas | Base documental | Situación en main | Estado | Qué falta |
|---|---|---|---|---|
| Corrales · Rayos de Sol · Rayo de Sol – Corrales · Rayito del Sol · Rayo del Sol · Corrales (Rayos del Sol) | El título de la RD 2071-2015 de ANA une ambas etiquetas («quebrada Corrales (Rayos del Sol)»); el inventario de barreras de ANA usa «Rayo de Sol – Corrales»; ANIN 2026 usa «Rayito del Sol»; CENEPRED 2025 usa «quebrada Rayo del Sol». La rama legacy trata Rayos de Sol como sector territorial sobre el drenaje Corrales (IGP 2012). | CROSS_SOURCE_RELATIONSHIP_UNRESOLVED_NOT_MERGED (config/phase2_rimac_receiver_context_v0_1.json) | `PENDING_ADJUDICATION` | Leer la RD 2071-2015 (escaneada) y decidir si «Rayos de Sol» es una etiqueta de sector del cauce Corrales o un cauce distinto. |
| Quirio · Quirio – Nicolás de Piérola · Quiro | Etiqueta compuesta del inventario de barreras de ANA; el nombre de archivo de SIGRID 13867 escribe «Quiro». | NAME_RELATIONSHIP_NOT_MERGED_IN_THIS_CONTRACT | `PENDING_ADJUDICATION` | Una fuente que diga qué designa «Nicolás de Piérola» (sector, AA.HH. o cauce). |
| Pedregal · San Antonio de Pedregal · Pedregal o San Antonio · San Antonio | MML 2013: «Quebrada Pedregal o San Antonio»; ANA: «San Antonio de Pedregal»; PREDES 2017 lista «San Antonio» por separado. | NAME_RELATIONSHIP_NOT_MERGED_IN_THIS_CONTRACT (unit id pedregal_san_antonio already exists) | `PENDING_ADJUDICATION` | Mantener «San Antonio» a solas como no confirmado; hay homónimos en Llipata (Ica) y Nuevo Chimbote (Áncash). |
| Carossio · Carosio | La grafía cambia según la fuente (mapa ANA 2016 y MML 2013: Carosio; EVAR 2015, INDECI 2023 y barreras ANA: Carossio). | SPELLING_RELATIONSHIP_NOT_MERGED_IN_THIS_CONTRACT | `PENDING_ADJUDICATION` | Registro formal de adjudicación de grafía. |
| Mariscal Castilla · Castilla | La RD 077-2016 de ANA se titula «quebrada Castilla»; el mapa ANA 2016, las barreras ANA, IGP e INDECI usan «Mariscal Castilla». Ninguna fuente leída las equipara. | not recorded | `PENDING_ADJUDICATION` | OCR de la RD 077-2016 (sector, hitos). La ficha de SIGRID la ubica en el distrito de Lurigancho. |
| Huaycán (Cieneguilla) · Huaycán de Cieneguilla | INDECI 2023 lista «Huaycán» en Cieneguilla; la RD 1560-2024 de ANA se titula «Quebrada Huaycán de Cieneguilla». Hay otro «Huaycán» listado en Ate. | not recorded | `PENDING_ADJUDICATION` | Texto de la RD 1560-2024; mantener aparte el homónimo de Ate. |
| Santa María · Yanacoto | INGEMMET A7437 describe la quebrada Santa María (margen derecha, afecta a Yanacoto II) y menciona aparte una «quebrada Yanacoto»; la RD 076-2016 de ANA delimita la «quebrada Yanacoto». El pedido las agrupaba como «Santa María/Yanacoto». | not recorded | `PENDING_ADJUDICATION_EVIDENCE_POINTS_TO_TWO_LABELS` | Hitos de la RD 076-2016 frente al mapa de INGEMMET A7437. |
| Virgen del Rosario · Rosario · Laderas Virgen del Rosario | INDECI 2023: «Virgen del Rosario»; IGP 2023: «Rosario»; «Laderas Virgen del Rosario» no aparece en ninguna fuente leída. | not recorded | `PENDING_ADJUDICATION` | Tabla de INGEMMET A7459 y plano municipal de sectores. |
| Cashahuacra · Casahuacra | El compendio INDECI 2017 escribe «Casahuacra». | NEAR_NAME_VARIANT_NOT_AUTO_ADJUDICATED (config/phase2_santa_eulalia_indeci2017_local_activation_names_v0_1.json) | `PENDING_ADJUDICATION` | Ya se sigue en main. |
| Shingolay · Chingolay | El compendio INDECI 2017 escribe «Chingolay». | CROSS_SOURCE_SPELLING_VARIANT_UNRESOLVED | `PENDING_ADJUDICATION` | Ya se sigue en main. |
| Huayaringa · Huayaringa Centro y Portada de Huayaringa | Dos mapas ANA 2016 distintos (SIGRID 5772 y 5806). | not recorded | `PENDING_ADJUDICATION` | Comparar ambos mapas. |
| Cusipata · Cusipata (San Bartolomé) | El título de la resolución de faja de ANA (SIGRID 13203) escribe «Quebrada Cusipata (San Bartolomé)». | not recorded | `PENDING_ADJUDICATION` | Texto de la RD; verificar también su número (0066-2022 en el título de SIGRID, 0666-2022 en el nombre de archivo). |
| Huascarán · Huascarán cauce principal (Huascarán 01) | La RD 0641-2025 de ANA nombra un «cauce principal (Huascarán 01)», lo que sugiere otros ramales no identificados aquí. | not recorded | `PENDING_ADJUDICATION` | Texto de la RD y plano anexo. |
| Payhua · Paihua | Ambas grafías en el informe IGP 001-2023 (lectura automática). | not recorded | `PENDING_ADJUDICATION` | Verificación byte a byte del informe IGP. |
| La Ronda (Lurigancho-Chosica) · La Ronda (Ricardo Palma) | INDECI 2023 lista La Ronda en Lurigancho-Chosica; PREDES 2017 escribe «La Ronda (Ricardo Palma)». | not recorded | `DISTRICT_CONFLICT_PENDING` | Texto de la RD 078-2016. |
| Huayanto-Pampano · Huayanto | Mapa ANA 2016: «Huayanto-Pampano» (Huancano); COER Ica 2025 e INDECI 2019 (ya en main): «Huayanto». | main records 'Quebrada Huayanto' in config/phase2_ica_2019_named_events_v0_1.json | `PENDING_ADJUDICATION` | Mapa ANA 5732 frente a los reportes COER/INDECI. |
| La Tucilla · Tucillal · Tucillay | Ya adjudicado como NO fusionado en main y en el PR #351 (INGEMMET A7454 nombra Tucillal). | NOT_MERGED (site/data/phase2/sources/tumbes_zorritos_extended_identity_context_v0_1.json) | `TRACKED_IN_MAIN_AND_PR_351` | Nada por parte de esta auditoría. |
| Charán · El Charán | ANA 2016 Cuadro 9: «Charán» (La Cruz); Andina 2024: «Charán» (sin distrito); MEF 2023: «El Charán» (sin distrito ni tipo de elemento). | not recorded | `PENDING_ADJUDICATION` | Reporte del COER Tumbes y anexo del D.S. 181-2023-EF. |
| Luey (Lucy) · Luey | ANA 2016 Cuadro 9 escribe «Luey (Lucy)» (Tumbes, Andrés Araujo Morán); MEF 2023 escribe «Luey». | not recorded | `PENDING_ADJUDICATION` | Anexo del D.S. 181-2023-EF. |
| Dos Barrios · Pablo Patrón/Dos Amigos | INGEMMET A6608 §5.6 places the Pablo Patrón sector on the lower fan of the quebrada Dos Barrios; the row 'Pablo Patrón/Dos Amigos' comes from a PREDES booklet. 'Dos Amigos' appears in neither A6608 nor RIIGEO 2012, and no source equates the PREDES label with the quebrada Dos Barrios. | not recorded | `PENDING_ADJUDICATION` | A source that states what 'Dos Amigos' designates and whether the PREDES row is the quebrada Dos Barrios; each keeps its own row. |
| Dos Barrios · Mariscal Castilla | INGEMMET A6608 §5.6 names Mariscal Castilla as a barrio on the old fan of the quebrada Dos Barrios; RIIGEO 2012 lists a quebrada 'Mariscal Castilla' among the left-bank quebradas. No source states that the RIIGEO label designates the same channel. | not recorded | `PENDING_ADJUDICATION` | A source or georeferenced map that places the quebrada 'Mariscal Castilla' of RIIGEO 2012 relative to the quebrada Dos Barrios. |

**Misma etiqueta, distrito distinto o desconocido (no fusionadas):** rio seco (ancash: 2 filas); tomeque (ancash: 2 filas); utiyacu (lambayeque: 2 filas); huaycan (lima: 2 filas); ihuanco (lima: 2 filas); rio seco (lima: 6 filas); charan (tumbes: 2 filas); los cerezos (tumbes: 2 filas); luey (tumbes: 2 filas); pedregal (tumbes: 2 filas).

**Homónimos entre departamentos:** Santo Domingo (2 fila(s)); San Antonio (3 fila(s)); Pedregal (3 fila(s)); Corrales (2 fila(s)); Señor de los Milagros (2 fila(s)); Huarangal (1 fila(s) — main already tracks a different Quebrada Huarangal in Huancano/Pisco (ica_huarangal_pisco)); La Capilla (1 fila(s) — main already tracks a Quebrada La Capilla elsewhere; do not merge).

## 7. Geometrías pendientes

Una faja marginal es contexto regulatorio: no es huella de evento ni eje de cauce. Los PDF de 2015-2016 probados son imágenes escaneadas; los hitos requieren OCR y QA antes de congelar nada.

| Nombre | Distrito | Pista de geometría | Outlet reproducible | En IRFEN |
|---|---|---|---|---|
| Cusipata | Chaclacayo | SIGRID record title: 'Resolución Directoral N°0066-2022-ANA-AAA.CF. Delimitación de la faja marginal de la Quebrada Cusipata (San Bartolomé) de 10,25 Km, distrito de Chaclacayo'. The server file name reads 'n00666-2022': the resolution number (0066 vs 0666) must be verified in the PDF — SIGRID 13203 | No | no está |
| Huascarán | Chaclacayo | R.D. N° 0641-2025-ANA-AAA.CF – actualización de la faja marginal de la quebrada Huascarán cauce principal (Huascarán 01) — SIGRID 19205 | No | no está |
| Los Cóndores | Chaclacayo | R.D. N° 064-2021-ANA-AAA-CAÑETE-FORTALEZA – faja marginal de la Qda. Los Cóndores (SINIA title: 11,90 km, distrito de Chaclacayo) — SIGRID 10436 | No | no está |
| Carossio | Lurigancho-Chosica | Geometría congelada (D8 reproducible por hash) en la rama legacy `agent/chosica-2015-multibasin-v0.1` (PR #146); no está en main | No | main: solo nombre/contexto · PR #146, #149, #151 |
| Chacrasana | Lurigancho-Chosica | R.D. N° 0715-2021-ANA-AAA.CF – faja marginal de la quebrada Chacrasana de 1,918 km, distrito de Lurigancho-Chosica — SIGRID 12478 | No | main: solo nombre/contexto |
| Corrales | Lurigancho-Chosica | R.D. N° 2071-2015-ANA-AAA.CAÑETE-FORTALEZA – delimitación de faja marginal de la quebrada Corrales (Rayos del Sol) [scanned PDF, no text layer] — SIGRID 6062<br>Geometría congelada (D8 reproducible por hash) en la rama legacy `agent/chosica-2015-multibasin-v0.1` (PR #146); no está en main | No | main: solo nombre/contexto · PR #149 |
| La Cantuta | Lurigancho-Chosica | R.D. N° 075-2016-ANA-AAA.CAÑETE-FORTALEZA – faja marginal de la quebrada Cantuta — SIGRID 6074<br>SIGRID record title: 'Resolución Directoral N° 0609-2025-ANA-AAA.CF: Actualización de la delimitación de faja marginal en ambas márgenes en el cauce principal de la quebrada La Cantuta, ubicada en el distrito de Lurigancho' — SIGRID 19341 | No | no está |
| La Libertad | Lurigancho-Chosica | R.D. N° 2059-2015-ANA-AAA.CAÑETE-FORTALEZA cited as static bank geometry in legacy branch agent/chosica-2015-multibasin-v0.1 (not re-read in this audit)<br>Geometría congelada (D8 reproducible por hash) en la rama legacy `agent/chosica-2015-multibasin-v0.1` (PR #146); no está en main | No | main: solo nombre/contexto · PR #146, #149, #151 |
| Pedregal | Lurigancho-Chosica | R.D. N° 2070-2015-ANA-AAA.CAÑETE-FORTALEZA – delimitación de faja marginal de la quebrada Pedregal — SIGRID 6066<br>Geometría congelada (D8 reproducible por hash) en la rama legacy `agent/chosica-2015-multibasin-v0.1` (PR #146); no está en main | Sí | main: unidad registrada `pedregal_san_antonio` · PR #148, #149, #326 |
| Quirio | Lurigancho-Chosica | R.D. N° 2256-2015-ANA-AAA.CAÑETE-FORTALEZA – delimitación de faja marginal de la quebrada Quirio — SIGRID 6067<br>Geometría congelada (D8 reproducible por hash) en la rama legacy `agent/chosica-2015-multibasin-v0.1` (PR #146); no está en main | Sí | main: unidad registrada `quirio` · PR #149 |
| Santo Domingo | Lurigancho-Chosica | SIGRID record title: 'Estudio de delimitación de la faja marginal de la Quebrada Santo Domingo, tributario del río Rímac - margen izquierda (1.45 km), distrito de Lurigancho'. An automated reading of the PDF gave R.D. N° 1156-2025-ANA-AAA.CF (2025-09-25), cauce principal 1,48 km, 57 hitos: the length differs between title (1.45) and reading (1.48) and must be verified — SIGRID 19950 | No | main: solo nombre/contexto |
| Yanacoto | Lurigancho-Chosica | R.D. N° 076-2016-ANA-AAA.CAÑETE-FORTALEZA – faja marginal de la quebrada Yanacoto — SIGRID 6068 | No | main: solo nombre/contexto |
| La Ronda | Lurigancho-Chosica | R.D. N° 078-2016-ANA-AAA.CAÑETE-FORTALEZA – faja marginal de la quebrada La Ronda — SIGRID 6064 | No | main: solo nombre/contexto |
| Chucumayo | Matucana | SIGRID record title: 'Resolución Directoral N° 1151-2025-ANA-AAA.CF: Delimitación de faja marginal de la quebrada Chucumayo, distrito de Matucana, provincia de Huarochirí' — SIGRID 19929 | No | no está |
| Castilla | Lurigancho | R.D. N° 077-2016-ANA-AAA.CAÑETE-FORTALEZA – faja marginal de la quebrada Castilla [scanned PDF, no text layer] — SIGRID 6065 | No | no está |
| Cupiche | Ricardo Palma | R.D. N° 079-2016-ANA-AAA.CAÑETE-FORTALEZA – faja marginal de la quebrada Cupiche — SIGRID 6061 | No | no está |
| Cuchimachay | Surco | SIGRID record title: 'Resolución Directoral N° 1042-2025-ANA-AAA.CF: Delimitación de faja marginal de la quebrada Cuchimachay, ubicada en el distrito de Surco, provincia de Huarochirí' — SIGRID 19619 | No | no está |
| Chilca Brazo Norte | Chilca | R.D. N° 0641-2024-ANA-AAA.CF – quebrada Chilca Brazo Norte, distrito de Chilca (automated title reading) — SIGRID 17739 | No | main: unidad registrada `lima_sur_chilca_pucusana (source ANA-CHILCA-BRAZO-NORTE-RD0641-2024)` |
| Huaycán de Cieneguilla | Cieneguilla | SIGRID record title: 'Resolución Directoral N° 1560-2024-ANA-AAA.CF: Delimitación de faja marginal de la Quebrada Huaycán de Cieneguilla, en ambas márgenes del río Lurín y su aportante la quebrada 1, en el distrito Cieneguilla' — SIGRID 18341 | No | no está |
| Río Seco (Malanche) | Punta Hermosa | R.D. N° 0828-2020-ANA-AAA-CAÑETE-FORTALEZA – faja marginal de la Qda. Río Seco (Malanche), distrito de Punta Hermosa y S… (server file name, truncated) — SIGRID 13056 | No | main: mención sin confirmar |

## 8. Eventos territoriales sin unidad nombrada

- `ica_humay_pallasca_2025_02_14` — Centro poblado Pallasca, distrito Humay, provincia Pisco, Ica, 2025-02-14 14:10 (`COER-ICA-RP-065-2025`): «Producto de lluvias intensas se activó la quebrada originando un huayco»; la quebrada no se nombra. No asignar este evento a Humay, Montesierpe, Auquix, Huaya Grande ni a ninguna otra quebrada nombrada de Humay.

## 9. Fuentes primarias identificadas

Las notas de acceso de cada fuente (qué parte se leyó y con qué límites) están en `sources[*].access_note` del JSON.

| ID | Institución | Título | Fecha | Clase | Acceso en esta auditoría | URL / identificador |
|---|---|---|---|---|---|---|
| `ANA-2016-COMPLEMENTACION-NACIONAL` | Autoridad Nacional del Agua (ANA) / MINAGRI | Complementación de Identificación de poblaciones vulnerables por activación de quebradas 2016-2017 | 2016-2017 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION_PARTIAL` | https://sinia.minam.gob.pe/sites/default/files/sial-sialtrujillo/archivos/public/docs/ana2017.pdf · SIGRID 2799; https://sinia.minam.gob.pe/documentos/complementacion-identificacion-poblaciones-vulnerables-activacion |
| `ANA-2016-SIGRID-VULNERABLE-POPULATION-MAPS` | ANA (published in CENEPRED SIGRID biblioteca) | Mapa de ubicación de poblaciones vulnerables por inundación / activación de quebrada (one map per quebrada, Sept. 2016) | 2016-09 | `PRIMARY_INSTITUTIONAL` | `SERVER_TITLE_OR_AUTOMATED_MAP_TITLE_READING` | https://sigrid.cenepred.gob.pe/sigridv3/documento/{sigrid_id} |
| `ANA-FAJA-RD-SIGRID` | ANA – AAA Cañete-Fortaleza / AAA Chaparra-Chincha (SIGRID biblioteca) | Resoluciones de delimitación de faja marginal de quebradas (series 2014-2025) | 2014-2025 | `PRIMARY_INSTITUTIONAL` | `SERVER_TITLE` | https://sigrid.cenepred.gob.pe/sigridv3/documento/{sigrid_id} |
| `INDECI-DDI-LIMA-2023-BALANCE` | INDECI – Dirección Desconcentrada Lima Metropolitana y Callao | Balance de la preparación y respuesta en la emergencia generada por la activación de quebradas e inundaciones en Lima Metropolitana | 2023-05-24 | `PRIMARY_INSTITUTIONAL_HOSTED_BY_THIRD_PARTY` | `AUTOMATED_TEXT_EXTRACTION` | https://www.mesadeconcertacion.org.pe/storage/documentos/2023-05-29/2-indeci-ddi-balance-lluvias-24-05-230.pdf |
| `IGP-IT-001-2023` | Instituto Geofísico del Perú | Análisis y evaluación histórica de precipitaciones en Chaclacayo, Chosica y áreas aledañas (Informe Técnico N°001-2023/IGP) | 2023 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION` | https://repositorio.igp.gob.pe/bitstreams/7ab825b4-0aca-4275-95a8-4243998bbe4c/download · hdl 20.500.12816/5351 (already cited in main as IGP_HANDLE_20.500.12816_5351) |
| `MUNI-LURIGANCHO-EVAR-2015` | Municipalidad Distrital de Lurigancho-Chosica (with INGEMMET, ANA, CONIDA, COFOPRI, INEI, MVCS) | Evaluación de riesgos por flujo de detritos – área de influencia de las quebradas Rayos de Sol, Carossio y Libertad | 2015-12 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION` | https://sigrid.cenepred.gob.pe/sigridv3/documento/1610 · SIGRID 1610 |
| `MUNI-LURIGANCHO-PPRRD-2022-2025` | Municipalidad Distrital de Lurigancho-Chosica | Plan de prevención y reducción del riesgo de desastres del distrito de Lurigancho-Chosica 2022-2025 | 2022 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION_PARTIAL` | https://sigrid.cenepred.gob.pe/sigridv3/documento/14006 · SIGRID 14006 |
| `INGEMMET-A7437` | INGEMMET | Informe Técnico N° A7437 – Evaluación de peligros geológicos en los locales de Yanacoto I y II, distrito Lurigancho-Chosica | 2023 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION` | https://sigrid.cenepred.gob.pe/sigridv3/documento/16610 · SIGRID 16610; Informe Técnico N° A7458 (SIGRID 16857) covers the same sites |
| `INGEMMET-A7459` | INGEMMET | Informe Técnico N° A7459 – Evaluación de zonas críticas por peligros geológicos ante Fenómeno El Niño 2023-2024 en el departamento de Lima, Tomo I Lima Metropolitana | 2023 | `PRIMARY_INSTITUTIONAL_NOT_READ` | `NOT_READ_FILE_TOO_LARGE` | https://sigrid.cenepred.gob.pe/sigridv3/documento/16933 · SIGRID 16933 |
| `CENEPRED-2025-RAYO-DEL-SOL-RF` | CENEPRED | Determinación de las zonas susceptibles y elementos expuestos a flujo de detritos en la quebrada Rayo del Sol del distrito de Lurigancho-Chosica mediante el modelo de Random Forest | 2025-12 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION` | https://sigrid.cenepred.gob.pe/sigridv3/documento/20918 · SIGRID 20918 |
| `ANA-2017-2019-BARRERAS-DINAMICAS` | ANA / MINAGRI (via Andina, agencia estatal, 2019-02-24; ANA note of 2017-04-11 already cited in main) | 22 barreras dinámicas en nueve quebradas de Lurigancho-Chosica | 2017-04-11 / 2019-02-24 | `INSTITUTIONAL_COMMUNICATION` | `AUTOMATED_TEXT_EXTRACTION` | https://andina.pe/agencia/noticia-minagri-mallas-para-contener-huaicos-chosica-estan-listas-743456.aspx · https://www.gob.pe/institucion/ana/noticias/137419-autoridad-nacional-del-agua-supervisa-estado-de-barreras-dinamicas-instaladas-en-lurigancho-chosica |
| `ANIN-MUNI-LURIGANCHO-2026` | ANIN / Municipalidad de Lurigancho-Chosica | Intervención en 10 quebradas priorizadas (2026-07-20) y alcance de 6 quebradas (2026-07-14) | 2026-07 | `INSTITUTIONAL_COMMUNICATION` | `ALREADY_IN_MAIN` | https://www.gob.pe/institucion/munilurigancho/noticias/1421374-anin-realizara-intervencion-en-10-quebradas-priorizadas-de-lurigancho-chosica · https://www.gob.pe/institucion/anin/noticias/1418899-comunicado |
| `MML-SGDC-RIMAC-2013` | Municipalidad Metropolitana de Lima – Subgerencia de Defensa Civil | Informe N° 048-2013/MML/SGDC/RHQM – Monitoreo de los sectores críticos de la cuenca del río Rímac | 2013-06-20 | `PRIMARY_INSTITUTIONAL` | `ALREADY_IN_MAIN` | https://sigrid.cenepred.gob.pe/sigridv3/documento/442 · SIGRID 442 |
| `CENEPRED-SIGRID-13867` | CENEPRED SIGRID biblioteca | Informe de caracterización geológica-geodinámica preliminar por flujos de detritos (huaycos) en las quebradas Quiro, Chacrasana, La Ronda, Barba Blanca y R… (title truncated by server) | unknown | `PRIMARY_INSTITUTIONAL` | `SERVER_TITLE_ONLY` | https://sigrid.cenepred.gob.pe/sigridv3/documento/13867 · SIGRID 13867 |
| `COER-ICA-NP-041-2025` | Gobierno Regional de Ica – COER Ica | Nota de Prensa N° 041-2025 | 2025-02-07 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION` | https://coer.regionica.gob.pe/images/2025/notas/febrero/NOTA%20DE%20PRENSA%2041.pdf |
| `COER-ICA-RP-065-2025` | Gobierno Regional de Ica – COER Ica | Reporte Preliminar N° 065-2025-MOD. OPERACIONES | 2025-02-15 | `PRIMARY_INSTITUTIONAL` | `AUTOMATED_TEXT_EXTRACTION` | https://coer.regionica.gob.pe/images/2025/REPORTE_PRELIMINAR/REPORTE_PRELIMINAR_065-2025-MOD_OPERACIONES.pdf |
| `MEF-DS-181-2023-EF-TUMBES` | Ministerio de Economía y Finanzas | Nota de prensa sobre D.S. 181-2023-EF: intervenciones en quebradas, diques y puentes de Tumbes | 2023-08-23 | `INSTITUTIONAL_COMMUNICATION` | `AUTOMATED_TEXT_EXTRACTION` | https://mef.gob.pe/es/comunicados-y-notas-de-prensa/7922-poder-ejecutivo-articula-acciones-con-los-gobiernos-regionales-del-norte-tumbes-recibira-mas-de-s-28-millones-para-intervenir-en-quebradas-ante-fenomeno-el-nino |
| `ANDINA-TUMBES-2023-04-01` | Andina (agencia estatal) citing Gobierno Regional de Tumbes | Tumbes: intensa lluvia activa quebradas en diversos sectores | 2023-04-01 | `STATE_NEWS_AGENCY_SECONDARY` | `AUTOMATED_TEXT_EXTRACTION` | https://andina.pe/agencia/noticia-tumbes-intensa-lluvia-activa-quebradas-diversos-sectores-935064.aspx |
| `ANDINA-TUMBES-2024-02-21` | Andina (agencia estatal) citing COER Tumbes spokesperson | Tumbes: intensa lluvia de tres horas inundó viviendas y aumentó caudal de río | 2024-02-21 | `STATE_NEWS_AGENCY_SECONDARY` | `AUTOMATED_TEXT_EXTRACTION` | https://andina.pe/agencia/noticia-tumbes-intensa-lluvia-tres-horas-inundo-viviendas-y-aumento-caudal-rio-975177.aspx |
| `ANDINA-MVCS-2023-02-23` | Andina (agencia estatal) citing MVCS | Santa Eulalia: MVCS interviene en 7 quebradas por riesgos de inundaciones | 2023-02-23 | `STATE_NEWS_AGENCY_SECONDARY` | `AUTOMATED_TEXT_EXTRACTION` | https://andina.pe/agencia/noticia-santa-eulalia-mvcs-interviene-7-quebradas-riesgos-inundaciones-930376.aspx |
| `PREDES-CARTILLA-2017` | PREDES (ONG, no es institución pública) | Cartilla práctica 'Conoce el riesgo de desastres' – Chosica | 2016-04 / 2017-05 | `NON_INSTITUTIONAL_LEAD` | `AUTOMATED_TEXT_EXTRACTION` | https://predes.org.pe/wp-content/uploads/2017/06/Cartillas-4-acciones-CHOSICA-WEB.pdf |
| `PRESS-LEAD` | Prensa (Perú21 2024-01-07; La República 2024-02-08 y 2025-01-31; Infobae 2026-02-25) | Notas de prensa que citan a INGEMMET, COEN-INDECI, Contraloría o municipalidades | 2024-2026 | `NON_INSTITUTIONAL_LEAD` | `AUTOMATED_TEXT_EXTRACTION` | see per-evidence url |
| `IRFEN-REPO` | IRFEN repository | Existing IRFEN contracts on main, or on the legacy branch named in the evidence detail | 2026-10-06 | `INTERNAL` | `REPO` | https://github.com/IRFEN2026/irfen-peru |
| `INGEMMET-SIGRID-434-TITLE` | INGEMMET (SIGRID biblioteca) | Inestabilidad de rocas zona de Rosario, Chosica (revisión de informe) | unknown | `PRIMARY_INSTITUTIONAL` | `SERVER_TITLE_ONLY` | https://sigrid.cenepred.gob.pe/sigridv3/documento/434 · SIGRID 434 |
| `INGEMMET-A6608-2012-LA-RONDA-LOS-CONDORES` | INGEMMET (Informe Técnico N.º A6608; Zavala, Vílchez y Núñez), via CENEPRED SIGRID documento 401 | Flujos de detritos del 05/04/2012 entre las quebradas La Ronda y Los Cóndores, margen izquierda del río Rímac. Características geodinámicas y evaluación de peligro | 2012 (cover prints 'Octubre 2011', inconsistent with the 05/04/2012 event in the title) | `PRIMARY_INSTITUTIONAL` | `ARCHIVED_BYTES_TEXT_LAYER_QUOTES_TESTED` | https://sigrid.cenepred.gob.pe/sigridv3/documento/401/descargar |
| `SENAMHI-2020-QDAS-SANTO-DOMINGO-CANTUTA` | Servicio Nacional de Meteorología e Hidrología del Perú (SENAMHI), Dirección de Hidrología | Caracterización del peligro por movimientos en masa debido a lluvias extremas en las quebradas Santo Domingo y Cantuta. Informe final (Asencios, Millán, Sabino Rojas y Breña) | 2020-05 | `PRIMARY_INSTITUTIONAL` | `ARCHIVED_BYTES_TEXT_LAYER_QUOTES_TESTED` | https://www.senamhi.gob.pe/load/file/01401SENA-88.pdf |
| `VILLACORTA-2018-UPM-THESIS-INGEMMET-TE0306` | Universidad Politécnica de Madrid (doctoral thesis of S. P. Villacorta Chambi); PDF hosted by the INGEMMET biblioteca as TE0306 | Evolución geomorfológica del abanico aluvial de Lima y sus relaciones con la peligrosidad por inundaciones (Tesis Doctoral) | 2018-11 | `ACADEMIC_THESIS_HOSTED_BY_INSTITUTION` | `ARCHIVED_BYTES_TEXT_LAYER_QUOTES_TESTED` | https://app.ingemmet.gob.pe/biblioteca/pdf/TE0306.pdf |

## 10. Prioridad sugerida para incorporación

- **P1** (24 filas) — Unidad de Carretera Central / Rímac / Santa Eulalia que no es unidad local registrada en main y que tiene una pista institucional de evento (sin verificar) y/o una pista regulatoria de geometría.
- **P2** (17 filas) — (a) Unidad de Pisco/Ica, Santa/Casma o Tumbes/Zorritos con pista institucional de evento (sin verificar) y/o pista de geometría; o (b) nombre de Carretera Central sustentado solo por identidad, obras, ONG/prensa o lectura no verificada, que necesita antes una fuente institucional primaria verificada.
- **P3** (291 filas) — Solo evidencia de identidad o punto crítico, en un corredor prioritario o en un corredor ya presente en IRFEN (otros valles de Lima y Lima Metropolitana, costa de Piura, Lambayeque, La Libertad).
- **P4** (56 filas) — Filas de interior/sierra fuera de los corredores presentes o previstos en IRFEN; se conservan para no mutilar las tablas de la fuente.
- **EXISTING** (13 filas) — Ya registrada en main (unidad local, sistema candidato o fuente citada). No requiere incorporación; la auditoría solo añade referencias cruzadas.

Orden de trabajo propuesto, sin tocar el mapa:

1. Verificar byte a byte las fuentes de las filas P1 (INDECI DDI Lima 2023, resoluciones de faja ANA, INGEMMET A7437), archivarlas con SHA-256 y solo entonces promover sus pistas de evento a `EVENT_EVIDENCE`.
2. Extraer por OCR los hitos de las fajas ANA de Carretera Central (La Cantuta, La Ronda, Yanacoto, Castilla, Cupiche, Corrales, Santo Domingo, Chacrasana, Los Cóndores, Cusipata, Huascarán) como contexto regulatorio.
3. Adjudicar las relaciones de nombres de la sección 6 antes de crear cualquier hijo local.
4. Completar el barrido que quedó pendiente (sección 11).

## 11. Cobertura del barrido y huecos

- Serie de mapas ANA 2016 en SIGRID — rangos barridos: 5601-5643 (partial: 5602, 5609, 5610, 5612, 5613, 5615, 5616, 5636 timed out); 5700-5819 (complete except 5710 image-only); 5965-6018. **No barridos:** 5560-5600; 5644-5699; 5820-5964; any ids below 5560. Arequipa, Moquegua, Tacna y la mayor parte de La Libertad no se localizaron en los rangos barridos.
- Informe nacional ANA 2016-2017 — tablas transcritas: Cuadro 9 Tumbes (44), Cuadro 11 Piura (79), Cuadro 17 Lambayeque (47). **No recuperables:** Cuadro 19 La Libertad, Cuadro 23 Ancash, Cuadro 29 Lima (97 centres), Cuadro 41 Ica, Cuadro 43 Arequipa, all remaining departments.
- **Sin barrer:** inventario anual de puntos críticos de ANA; servicio GEOCATMIN de peligros geológicos de INGEMMET; reportes de emergencia COEN-INDECI/SINPAD por distrito; avisos SENAMHI de activación de quebradas; lista de estaciones de la red de monitoreo de huaicos del IGP; Arequipa, Moquegua, Tacna, La Libertad (más allá de 9 títulos de mapa) y Lima norte más allá de los títulos SIGRID; PPRRD municipales de Chaclacayo, Ricardo Palma y Santa Eulalia.
- **Rímac, Dos Barrios (2026-10-09)** — Dos Barrios (INGEMMET A6608 §5.6 pp. 30-31 and conclusions p. 43; SENAMHI 2020 p. 3; doctoral thesis 2018 pp. 83 and 85). Sources archived with SHA-256 in data/phase2/source_archive/rimac_dos_barrios/ (runner capture; SENAMHI owner-supplied copy); quotes checked on the archived text layer and rendered pages. **Revisadas sin la etiqueta:** RIIGEO 2012 (huaycos del 5 de abril de 2012), IGP 2020 (SIGRID 13867), ANA faja Santo Domingo (SIGRID 19950).

### Conflictos e incidencias de extracción

- **ANA 2016, Cuadro 11 (Piura), filas 72-79** — Dos lecturas automáticas difieren en una posición en la numeración del final de la tabla (la segunda omite una fila). Nombres y coordenadas coinciden; los números de fila son «según la primera lectura».
- **ANA 2016, Cuadro 11 fila 75 frente a Cuadro 17 fila 47 («El Virrey», E 612920 N 9388199)** — El mismo nombre y las mismas coordenadas aparecen en Piura (Morropón / La Matanza) y en Lambayeque (Lambayeque / Olmos). O la fuente repite el punto o la extracción lo duplicó. Se conservan ambas filas, sin fusionar.
- **ANA 2016, Cuadro 11 filas 12-13** — Los pares provincia/distrito leídos («Sullana / Tambogrande», «Morropón / Tambogrande») son administrativamente incoherentes (Tambogrande pertenece a la provincia de Piura). Se dejan como se leyeron.
- **ANA 2016, Cuadro 9 filas 23-24** — Una lectura dio el distrito «Canos de Punta Sal»; aquí se normalizó a «Canoas de Punta Sal». Es la única normalización de grafía aplicada en la auditoría.
- **IGP 001-2023, «Tablachaca»** — La lectura automática situó una quebrada «Tablachaca» en Santa Eulalia mientras describía Mina Casapalca / río Rímac (1959). Es incoherente, así que NO se registró como candidato.
- **INGEMMET 2015, «Peligros geológicos Chaclacayo» (repositorio.ingemmet.gob.pe 20.500.12544/4953)** — Acceso denegado (HTTP 403) desde este entorno. No se leyó; probablemente es la mejor fuente primaria para las quebradas de Chaclacayo.
- **Primera lectura automática del PDF ANA 2016 (tabla de Áncash)** — El lector devolvió una tabla de Áncash con aspecto fabricado (coordenadas con saltos regulares, provincias de Lima dentro de Áncash). Se descartó entera; ninguna fila de Áncash de este inventario procede de ella.

## 12. Usos prohibidos

- usar cualquier fila como unidad de activación, entrada de alerta o fuente de umbrales
- dibujar en el mapa las coordenadas `source_reference_point` o usarlas como outlet
- tratar una faja marginal como huella de evento o eje de cauce
- tratar barreras, diques, limpieza o alcance de proyecto como capacidad hidráulica histórica
- tratar un mapa de vulnerabilidad o un listado de zonas críticas como evento observado
- fusionar dos etiquetas porque se parecen o están cerca
- asignar cuenca padre por nombre del receptor, distrito o proximidad
- tratar la ausencia en este archivo como ausencia de quebrada
