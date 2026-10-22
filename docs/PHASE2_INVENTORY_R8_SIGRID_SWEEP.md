# Inventario maestro nacional · ronda r8: barrido SIGRID de la serie ANA 2016 (RESEARCH_ONLY / TEST_ONLY)

Primera fase del inventario de completitud para los corredores prioritarios.
- **No es un segundo inventario maestro.** `config/phase2_national_inventory_r8_sigrid_sweep_v0_1.json` es una **ronda delta**, con el mismo esquema de fila que `config/phase2_national_inventory_completeness_audit_v0_1.json`.
- **Por qué delta.** Se mantiene aparte porque cinco PR abiertos (#363, #365, #366, #381 y #385) editan ese archivo. Sus filas se incorporarán al maestro cuando esos PR estén revisados.
- **Sin publicación.** Ningún constructor de sitio, mapa, catálogo o motor lo lee.

## Método
- **Qué se barrió:** `scripts/phase2_sigrid_ana2016_sweep.py` pide solo la ficha pública `https://sigrid.cenepred.gob.pe/sigridv3/documento/<id>` de los ids que `sweep_coverage` del maestro registra como no barridos o con tiempo agotado: 5560–5600, 5644–5699 y 5820–5964, más los 8 ids con tiempo agotado y una franja exploratoria 5500–5559.
- **Qué no se hizo:** no se descargó ningún PDF, mapa ni imagen; no se siguen redirecciones y cualquier otra URL se rechaza.
- **Ejecución:** una sola vez en `ubuntu-24.04`, confirmada por github-actions[bot] con un workflow temporal que se retiró después.
  - 310 ids: 205 fichas de quebrada, 53 de otro tipo y 52 HTTP 404.
  - Un 404 no prueba que no haya quebrada.
- **Procedencia:** cada respuesta queda con su SHA-256. Las fichas de quebrada se archivan comprimidas (`data/phase2/source_archive/sigrid_ana2016_sweep_20261022/pages/`), y la prueba vuelve a parsearlas y obtiene exactamente los mismos campos.

## A · Diagnóstico de completitud
Los estados describen la cobertura documental, nunca ausencia hidrológica.

| Corredor | Estado | En `main` | En PR abiertos | Nuevas r8 |
|---|---|---|---|---|
| Carretera Central / Rímac / Huaycoloro | AUDITADO_PARCIAL | 44 | #381 +11; #363 (inventario propio) | 0. Todos los mapas ANA hallados ya están en `main` o en #381; una variante ortográfica pendiente |
| Pisco / Ica (incl. Quitasol y Paracas) | AUDITADO_PARCIAL | 48 (46 sin provincia) | #366 +3; #381 +6 | 4 |
| Santa / Casma | AUDITADO_PARCIAL | 16 | #381 +1 | 9 (de 8 mapas) |
| Tumbes / Zorritos | AUDITADO_PARCIAL | 68 | #365 +14; #385 +3; #364; #378 | 0 (se deja a esos carriles) |
| Arequipa, Moquegua, Tacna | NO_AUDITADO | — | — | — |

## B · Estructura
- Las filas usan el esquema del maestro y la misma regla: un mapa ANA 2016 es evidencia `CRITICAL_POINT`, no un evento.
- Todas son `IDENTITY_ONLY`, P3, con `map_eligible=false`, sin geometría, outlet ni cuenca padre.
- Cada evidencia añade `record_page_sha256` y `record_page_archive`.
- La prueba aplica el **validador del propio maestro** a «maestro + r8» y exige cero errores. También verifica que las manipulaciones (fila publicable, coordenadas, cuenca padre, evento sin evidencia, id duplicado) se rechazan.

## C · Nuevos candidatos (13 identidades documentales)
- **Pisco / Ica:**
  - Pallasca y Pantayco (Humay, Pisco; SIGRID 5615);
  - Cabeza de Cura y Cerro Blanco (Nasca; 5636).
- **Santa / Casma:**
  - s/n del C. P. Los Chimús (Samanco; 5665);
  - Cayhuamarca y Tablones (Chimbote; 5838);
  - La Cantera (5839);
  - San Juan (5840);
  - El Establo 1 y El Establo 2 (5841): dos identidades independientes desde el 23-10-2026;
  - s/n (Nepeña; 5864);
  - s/n (Moro; 5865).

Las filas divididas a partir de un mismo mapa llevan `split_basis`:
- el texto de la ficha archivada que lo justifica;
- las filas hermanas;
- la decisión (`SOURCE_PLURAL_ENUMERATION`, o `OWNER_DIRECTED_SPLIT_OF_EXPLICIT_ENUMERATION` para El Establo);
- la fila sustituida (`ancash_chimbote_el_establo_1_el_establo_2`).

Las hermanas comparten fuente SIGRID, SHA-256 y archivo. Que sean cauces hidrológicamente independientes no se adjudica, y no se infiere geometría, outlet ni relación de cuenca.

## D · Duplicidades e incertidumbres
- **Pendiente de adjudicar, no fusionada:** «Yanocoto (Santa María)» (5842) frente a `lima_lurigancho_yanacoto`.
- **Mismo nombre en otro distrito, no fusionada:** «Cabeza de Cura» (Nasca) frente a la de Vista Alegre.
- **Homónimos de otros departamentos:** Cerro Blanco, La Cantera, San Juan y Pallasca.
- **Denominaciones compuestas:** `scripts/phase2_inventory_compound_name_audit.py` clasifica las 51 del maestro y de r8 (`compound_name_audit`). Solo lee el texto de evidencia de cada fila y **no divide, fusiona ni renombra nada**.

  | Categoría | Nº | Qué requiere |
  |---|---|---|
  | `SOURCE_TEXT_NOT_READ` (nombre tomado de un nombre de archivo o de una lectura automática) | 21 | leer y archivar la fuente |
  | `PARENTHETICAL_ALIAS_OR_SUBNAME_PENDING` | 8 | adjudicar el alias |
  | `SPLIT_RECORDED_WITH_BASIS` (r8) | 8 | nada |
  | `SOURCE_TABLE_SINGLE_CELL_COMPOUND` | 4 | releer la tabla archivada |
  | `SOURCE_TABLE_LOCALITY_LABEL` | 3 | conservar tal como se imprimió |
  | `SECONDARY_OR_LIST_SOURCE_ONLY` | 2 | buscar una fuente primaria |
  | `ENUMERATED_DISTINCT_NAMES_IN_SOURCE` (Huayaringa Centro y Portada de Huayaringa) | 1 | revisar la división |
  | `NUMBERED_SERIES_IN_SOURCE` (Centro Santa Eulalia 1, 2 y 3) | 1 | revisar la división, mismo patrón que El Establo |
  | `DISTRICT_QUALIFIER`, `LOCALITY_QUALIFIER`, `LABEL_COMPONENT_ALREADY_FLAGGED` | 3 | nada |

  `el progreso 1 - el progreso 2` (main) no se divide: su nombre no aparece en el texto de fuente registrado.
- **Mapas adicionales para filas ya existentes:** California, Huampaní, Quirio, La Libertad y Huascarán. Quedan como referencias cruzadas que se incorporarán al integrar.
- **Ya cubiertos por PR abiertos:** Panorama y «U3 y P-P1» (#381), y Cabuyal / Casitas Bocapán (#378).

## E · Backlog nacional
`national_backlog` contiene:
- 187 fichas de quebrada fuera de los corredores prioritarios: La Libertad 50, Lima otros valles 18, Lambayeque 16, Áncash interior 10, Piura 1, 85 fuera del ámbito actual y 7 sin ubicación interpretable;
- las 52 ids sin ficha pública;
- las fuentes por consultar:
  - INGEMMET bloquea el acceso automatizado, no se eludió y queda para captura manual;
  - Cuadros 23, 29 y 41 del informe ANA 2016;
  - fajas marginales de Ica y Santa/Casma;
  - ids de SIGRID por encima de 6018;
  - reportes COER / COEN;
  - planes PPRRD de Chaclacayo, Ricardo Palma y Santa Eulalia.

No se afirma completitud nacional.
