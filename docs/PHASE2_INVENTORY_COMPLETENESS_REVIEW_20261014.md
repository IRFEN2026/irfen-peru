# Revisión de completitud del inventario de quebradas (14-10-2026)

RESEARCH_ONLY / TEST_ONLY. Ledger documental: `config/phase2_inventory_completeness_review_v0_1.json`, generado por `scripts/phase2_inventory_completeness_review.py` a partir de fuentes ya archivadas con SHA-256 (`data/phase2/source_archive/tumbes_capitana_hualaca_higueron`, rama del PR #365/#364). **No edita ninguna fila del inventario nacional**, no crea geometría y no promueve nada al mapa.

## Tres estados separados

- **INVENTARIADO**: Fila en el inventario nacional (main o carril abierto). Un candidato de esta revisión aún NO está inventariado.
- **GEOMETRIA_REPRODUCIBLE**: Geometría reproducible en main con SHA-256 (reproducible_geometry.exists=true).
- **PUBLICABLE_EN_MAPA**: Admitida por el catálogo canónico map_semantics y QA. Ningún candidato lo es.

## Cuadro por región

| Región | Inventariado (main + carriles) | Geometría reproducible | Publicable en mapa | Candidatos nuevos (listas institucionales) | Candidatos solo rótulo de mapa | Posibles relaciones / homónimos | Filas existentes verificadas byte a byte |
|---|---|---:|---:|---:|---:|---:|---:|
| Tumbes | 82 (68 ; #365 +14) | 0 | 0 | 12 | 113 | 4 | 44 |
| Piura | 78 (78) | 0 | 0 | 22 | 0 | 8 | 78 |
| Lambayeque | 46 (46) | 0 | 0 | 3 | 0 | 0 | 0 |
| La Libertad | 9 (9) | 0 | 0 | 26 | 0 | 1 | 0 |
| Rímac | 45 (44 ; #363 +1) | 3 | 0 | 11 | 0 | 3 | 0 |
| Pisco/Ica | 51 (48 ; #366 +3) | 0 | 0 | 6 | 0 | 1 | 0 |
| Santa/Casma | 16 (16) | 0 | 0 | 2 | 0 | 0 | 0 |

Los candidatos no son quebradas independientes confirmadas: son etiquetas documentadas que el inventario aún no contiene. Ninguno se descarta por carecer de GIS.

## Fuentes verificadas (bytes archivados, SHA-256)

- `ANA-DU015-2023-ANEXO-II` — ANA (publicado por MEF/gob.pe): DU 015-2023, Anexo II: Listado de puntos críticos para limpieza y descolmatación. SHA-256 `c00095672208cb0afbd368aa02fe8172c2661d0df629385fb91b9f464db883b9`.
- `ANA-DU015-2023-ANEXO-III` — ANA (publicado por MEF/gob.pe): DU 015-2023, Anexo III: Listado de quebradas a ser intervenidas. SHA-256 `5963b140cd49b8ee6599044ab094e7a511a77d5ad0d9efdebcad35f633ac1cad`.
- `ANA-2016-MAPA-TUMBES-SIGRID-3743` — ANA (vía SIGRID/CENEPRED): Mapa de ubicación de poblaciones vulnerables por activación de quebradas, Tumbes 2016. SHA-256 `3b63261930a7e908722c8109b4818908e08cdb28591d96edc7a54171d165f8c8`.
- `ANA-2016-MAPA-PIURA-SIGRID-3741` — ANA (vía SIGRID/CENEPRED): Mapa de ubicación de poblaciones vulnerables por activación de quebradas, Piura 2016. SHA-256 `c246b48b3f94ec72cecdd6531da35073c1102bf9ce8f1a694adc321577bb4004`.
- `INGEMMET-A6764-TUMBES-2017` — INGEMMET (vía SIGRID): Informe técnico A6764: evaluación geológica de las zonas afectadas por El Niño Costero, Tumbes 2017. SHA-256 `e32e0c506300368351e54d5d190219c764995b913f3604e466f8185edd7b5231`.
- `INDECI-RC-3755-2025-TUMBES` — INDECI / COEN: Reporte complementario N.º 3755, 18-03-2025: lluvias intensas en el departamento de Tumbes. SHA-256 `a0eb6ecac12b3c8577170c735b62d08893ea2fc454cdc6e10dd7c21b83bcf460`.

## Candidatos nombrados por el propietario

| Nombre | Veredicto | Evidencia | Nota |
|---|---|---|---|
| Tronco Mocho | `NEW_CANDIDATE_NAMED_AS_QUEBRADA` | ANA-2016-MAPA-TUMBES-SIGRID-3743 (rótulo del mapa) | Solo rótulo de mapa: falta distrito y una segunda fuente con contexto (ANA puntos críticos, INDECI, INGEMMET). |
| Grau | `ALREADY_IN_INVENTORY` | ANA-2016-MAPA-PIURA-SIGRID-3741 (tabla, fila 10); INGEMMET-A6764-TUMBES-2017 (punto P-23, p. 72); INDECI-RC-3755-2025-TUMBES (p. 4) | En Piura ya es fila del inventario (piura_colan_grau). En Tumbes «Grau» y «Prolongación Grau» son centro poblado / sector afectado por flujos de quebradas no nombradas: no son una quebrada y no se añaden. En main sigue abierta la relación Bolognesi / Grau (config/phase2_north_coast_discovery_inventory_v0_1.json). |
| Banchero | `NOT_A_QUEBRADA_IN_SOURCES_READ` | INDECI-RC-3755-2025-TUMBES (p. 25 (Municipalidad Distrital de La Cruz)) | Ninguna fuente archivada nombra una «quebrada Banchero». La única mención es «Banchero Rossi» en una lista de calles limpiadas. Queda en vigilancia: se añadiría solo si una fuente la nombra como quebrada. |
| Banchero Rossi | `NOT_A_QUEBRADA_IN_SOURCES_READ` | INDECI-RC-3755-2025-TUMBES (p. 25 (Municipalidad Distrital de La Cruz)) | Aparece entre vías limpiadas (calles), no como cauce. No se añade; no se descarta que exista una quebrada de ese nombre en otra fuente. |
| Mariátegui | `NOT_A_QUEBRADA_IN_SOURCES_READ` | ANA-2016-MAPA-PIURA-SIGRID-3741 (tabla, fila 23) | «AH José Carlos Mariátegui» es el asentamiento humano expuesto; la quebrada de esa fila es Cieneguillo, ya inventariada. No se crea una quebrada «Mariátegui». |
| Las Gardenias | `NEW_CANDIDATE_NAMED_AS_QUEBRADA` | INGEMMET-A6764-TUMBES-2017 (punto P-28, p. 72 (y cuadro de la p. 21)); INGEMMET-A6764-TUMBES-2017 (p. 36); INDECI-RC-3755-2025-TUMBES (p. 21) | Nombrada como quebrada por INGEMMET (2017) y por INDECI (2025). Distrito UNRESOLVED: INGEMMET la sitúa en la provincia de Tumbes; en INDECI «en el distrito La Cruz» cierra una frase con varios sectores. La intervención de 2025 es obra, no evento fechado de activación. |
| Sen Sen | `NEW_CANDIDATE_NAMED_AS_QUEBRADA` | ANA-DU015-2023-ANEXO-II (sección IX (ANCASH), fila 88) | Cuenca Casma según el anexo, en la provincia de Huaraz. No consta en main ni en el carril Casma (#371). |
| Bombon-Poctao | `NEW_CANDIDATE_NAMED_AS_QUEBRADA` | ANA-DU015-2023-ANEXO-II (sección IX (ANCASH), fila 89) | En main aparece «Bombon Matua»; la relación con «Bombon-Poctao» queda UNRESOLVED (sin fusionar). |
| Piedras Gordas | `NAMED_ON_MAIN_OUTSIDE_INVENTORY` | ANA-DU015-2023-ANEXO-II (sección XV (ICA), fila 79) | Ya figura en un contrato de eventos de main, pero no en el inventario nacional: incorporar por referencia, sin duplicar el evento. |
| Catambo | `NAMED_ON_MAIN_OUTSIDE_INVENTORY` | ANA-DU015-2023-ANEXO-II (sección XV (ICA), fila 73) | Identidad oficial (términos de referencia ANA 2023) en main; falta fila en el inventario. |
| Topara | `NAMED_ON_MAIN_OUTSIDE_INVENTORY` | ANA-DU015-2023-ANEXO-II (sección XV (ICA), fila 80); ANA-DU015-2023-ANEXO-II (sección X (LIMA), fila 45) | En main Topará es una cuenca (unidad ANA 137534). El anexo la llama «Qda.» a ambos lados del límite Ica–Lima. Si es uno o dos cauces queda UNRESOLVED, y el polígono de la cuenca no se usa como área colectora de la quebrada. |

## Pendientes por región

**Tumbes**
- Rótulos del mapa ANA 2016 sin distrito: lectura visual del mapa y cruce con los mapas por quebrada SIGRID 3745–3770 (carril #364/#365).
- SIGRID 11733 (ANA puntos críticos Tumbes 2015) archivado pero no leído en esta revisión.
- Distrito de Las Gardenias (Tumbes vs La Cruz) sin adjudicar.

**Piura**
- Homónimos del anexo (Atahualpa ×2, San Francisco ×3 en Tambogrande, 9 de Diciembre, Cementerio, Paccha) sin adjudicar.
- Informes INGEMMET de Piura y fichas GORE Piura no barridos.
- Rótulos del mapa ANA 2016 de Piura no usados: el mapa incluye Lambayeque y Cajamarca y no permite asignar departamento.

**Lambayeque**
- Cuadro 17 (ANA 2016) aún sin copia archivada para verificar byte a byte las 46 filas.
- «El Hualtacal» (Oyotún) no se equipara con Hualtacal de Tumbes.

**La Libertad**
- Cuadro 19 (ANA 2016) no recuperado.
- 22 de los 26 candidatos del anexo están en la sierra (Pataz, Bolívar, Sánchez Carrión), fuera del ámbito costero del piloto, pero se conservan.

**Rímac**
- QA independiente del carril #363 pendiente.
- Anexo III: 11 etiquetas no inventariadas; relación «Cóndores 1/2» con «Los Cóndores» y «Milagros» con «Señor de los Milagros» sin adjudicar.
- PPRRD municipales de Chaclacayo, Ricardo Palma y Santa Eulalia no barridos.

**Pisco/Ica**
- Cuadro 41 (ANA 2016) no recuperado.
- Río Seco: homónimos Salas/Llipata (contrato de homónimos en main).
- Topará: ¿uno o dos cauces a ambos lados del límite Ica–Lima?

**Santa/Casma**
- Cuadro 23 (ANA 2016) no recuperado.
- Relación «Bombon-Poctao» / «Bombon Matua» sin adjudicar.
- El carril #371 trata geometría de Casma, no inventario.

## Reglas

No se infieren alias ni cuencas padre; una misma etiqueta en otro distrito es otro candidato; una coincidencia parcial es `POSSIBLE_RELATION_UNRESOLVED`; un punto crítico no es un evento; los puntos UTM del Anexo III son puntos de referencia del sector, no outlets ni geometría.
