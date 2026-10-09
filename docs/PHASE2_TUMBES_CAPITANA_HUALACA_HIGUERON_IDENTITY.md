# Tumbes: identidad documental de La Capitana, Hualaca e Higuerón (v0.1, revisión r2)

**Estado:** `RESEARCH_ONLY / TEST_ONLY` · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `activation_gate=BLOCKED` · `missing_data_rule=UNKNOWN_NOT_LOW_RISK` · `decision_thresholds=null` · `hydraulic_factors=null` · `map_publishable=false`

**Revisión r2 (2026-10-09).** Responde a la revisión científica independiente de ChatGPT del 2026-10-08:

1. Hualaca queda incorporada a partir del Anexo II del DU 015-2023 (fila 17), archivado con su SHA-256 real.
2. Todas las relaciones entre cauces quedan como `UNRESOLVED`.
3. El archivo de fuentes se movió fuera de `site/`.

| Archivo | Papel |
|---|---|
| `config/phase2_tumbes_capitana_hualaca_higueron_capture_seeds_v0_1.json` | Contrato de captura: búsquedas, semillas, sondas, barrido SIGRID 3740–3770 y documentos suplementarios (DU 015-2023) con sus rutas |
| `scripts/archive_phase2_tumbes_capitana_hualaca_higueron_sources.py` | Tiene tres modos. `--capture`: captura completa. `--capture-supplements`: solo los suplementos que faltan; nunca reescribe los registros anteriores. Sin argumentos: verificación offline de los hashes |
| `data/phase2/source_archive/tumbes_capitana_hualaca_higueron/` | Bytes originales (`raw/`), texto por página (`text/`) y `archive_manifest_v0_1.json`. **Está fuera de `site/`**, así que GitHub Pages no lo publica |
| `config/phase2_tumbes_capitana_hualaca_higueron_identity_v0_1.json` | Registro de identidad: 19 fuentes, 47 citas literales, decisiones, 3 unidades, asentamientos y bloqueos |
| `scripts/validate_phase2_tumbes_capitana_hualaca_higueron_identity.py` | Verificador stdlib, sin red |
| `tests/test_phase2_tumbes_capitana_hualaca_higueron_identity.py` | 20 pruebas: el registro pasa y cada guarda rechaza su violación |

Cada afirmación del registro cita un texto literal de un archivo archivado. Las pruebas comprueban que la cita es una subcadena literal de su página y que el archivo coincide con el SHA-256 del manifest.

## Hualaca

Fuente: **Anexo II del Decreto de Urgencia N.° 015-2023** (16-06-2023). Su título es «Listado de puntos críticos para limpieza y descolmatación». Lo emite la Autoridad Nacional del Agua, Dirección de Planificación y Desarrollo de los Recursos Hídricos.

La fila 17 dice: «17 Tumbes Quebrada Qda. Hualaca Jequetepeque- Zarumilla Tumbes Tumbes Tumbes San Jacinto Higueron». Es decir:

| Campo | Valor |
|---|---|
| CUENCA | Tumbes |
| FUENTE | Quebrada |
| RIO_Qda. | Qda. Hualaca |
| AAA | Jequetepeque-Zarumilla |
| ALA | Tumbes |
| DEPARTAMENTO / PROVINCIA | Tumbes / Tumbes |
| DISTRITO | San Jacinto |
| SECTOR | Higueron |

La asignación de columnas se comprobó a ojo sobre la página renderizada.

- **Copia archivada.** La copia de ANA citada por la revisión (`www.ana.gob.pe/.../Anexo_II_DU015_2023.pdf`) agotó el tiempo de espera desde los runners de GitHub y no tiene captura en Wayback. Se archivó la copia que publica el MEF en gob.pe. El artículo 2.4 del decreto (también archivado) establece que los anexos se publican en las sedes digitales del MEF y del MIDAGRI. **No está verificado** que esta copia sea idéntica byte a byte a la de ANA.
- **Uso permitido.** Es un listado de puntos críticos para intervenciones previstas. No es un evento, ni una huella, ni un dato de capacidad. La palabra «Tumbes» en la columna CUENCA se registra como texto y no se adopta como cuenca padre.
- **Unidad creada:** `tumbes_san_jacinto_quebrada_hualaca`, con geometría y outlet en `MISSING` y `receiver_relation=UNKNOWN_NOT_ASSUMED`.

## Relaciones (todas sin demostrar)

Que dos nombres aparezcan en fuentes oficiales prueba que las fuentes usan dos etiquetas. **No prueba** que haya dos cauces hidráulicamente independientes: un mismo cauce puede llevar nombres distintos según el tramo o el sector, y dos nombres pueden corresponder a cauces conectados.

Mientras no haya geometría reproducible, `same_channel` y `hydraulically_independent` quedan en `UNRESOLVED`, y el verificador rechaza cualquier otro valor.

| Relación | Decisión | Observación |
|---|---|---|
| Hualaca – Higuerón | `UNRESOLVED` | El Anexo II sitúa la Qda. Hualaca en el sector «Higueron». No dice si es la quebrada Higuerón, un tramo o un afluente de ella, o un cauce distinto. |
| Hualaca – Hualtacal | `UNRESOLVED` | Filas 17 y 18 del Anexo II (sectores Higueron y Rica Playa). Se retira la hipótesis de que «Hualaca» fuera una grafía de «Hualtacal». |
| Higuerón – Hualtacal | `UNRESOLVED` | Se enumeran por separado en la Ley 32573 §1.2 y llevan rótulos separados en ANA 2016. |
| La Capitana – Higuerón | `UNRESOLVED` | Filas C-27 y C-28 de INGEMMET A6764 y rótulos separados en ANA 2016. |
| La Capitana – Hualaca | `UNRESOLVED` | Ninguna fuente nombra a ambas. |
| ¿Uno o varios Higuerón? ¿Uno o varios Hualtacal? | `UNRESOLVED` | Aparecen en varios contextos: cruce vial, divisoria legal, rótulos de mapa y sectores del Anexo II. |
| Quebrada vs asentamiento (La Capitana, Higuerón) | `DIFFERENT_FEATURE_TYPES_RELATION_UNRESOLVED` | Son tipos de entidad distintos; su relación no se declara. |
| «Capitán Hoyle» (RC 13112) vs La Capitana | `UNRESOLVED` | No se equiparan. |
| El Higuerón de Piura, Cajamarca y La Libertad | `DIFFERENT_DEPARTMENTS_NOT_MERGED` | Las propias fuentes los sitúan en otros departamentos. |

## Eventos

- **La Capitana e Higuerón.** Solo hay evidencia a nivel de periodo, de INGEMMET A6764, Cuadro 3.2 (El Niño Costero 2017, sin fecha diaria): C-27 y C-42 para La Capitana, C-28 para Higuerón.
- **Hualaca.** No tiene eventos. Solo figura en el listado de puntos críticos de 2023.
- **RC 13111/13112 (2026).** No nombran ninguno de los cuatro nombres. Eso no prueba inactividad.

## Almacenamiento

El 2026-10-09 se movió el archivo con `git mv` desde `site/data/phase2/sources/...` a `data/phase2/source_archive/...`:

- Los bytes y los SHA-256 no cambian.
- El manifest reescribe solo los prefijos de ruta y registra el traslado en `relocations`.
- GitHub Pages publica únicamente `site/`.
- El archivador, el workflow, el verificador y las pruebas rechazan cualquier copia o ruta del archivo dentro de `site/`.

## Bloqueos externos

1. **Copia de ANA.** Hace falta la copia de ANA del Anexo II, descargada desde una red con acceso, para comparar su SHA-256 con la del MEF.
2. **Relaciones entre Hualaca, Higuerón, Hualtacal y La Capitana.** Resolverlas requiere datos georreferenciados:
   - hidrografía ANA o expedientes de ALA Tumbes de los puntos del DU 015-2023;
   - cartografía de la Ley 32573 (IGN 0863/0864);
   - o verificación de campo.
3. **Geometría y outlet.** `geosnirh.ana.gob.pe` y `repositorio.ana.gob.pe` no responden desde los runners.
4. **Eventos fechados.** Hace falta un reporte INDECI/COEN, SINPAD o municipal que nombre la quebrada.
