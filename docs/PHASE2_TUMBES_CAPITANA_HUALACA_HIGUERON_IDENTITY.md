# Tumbes: identidad documental de La Capitana, Hualaca e Higuerón (v0.1)

**Estado:** `RESEARCH_ONLY / TEST_ONLY` · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `activation_gate=BLOCKED` · `missing_data_rule=UNKNOWN_NOT_LOW_RISK` · `decision_thresholds=null` · `hydraulic_factors=null` · `map_publishable=false`

| Archivo | Papel |
|---|---|
| `config/phase2_tumbes_capitana_hualaca_higueron_capture_seeds_v0_1.json` | Contrato de captura: búsquedas, semillas, sondas, barrido SIGRID 3740–3770, hosts y límites |
| `scripts/archive_phase2_tumbes_capitana_hualaca_higueron_sources.py` | Captura acotada (`--capture`, en runner) y verificación offline de hashes (modo por defecto) |
| `site/data/phase2/sources/tumbes_capitana_hualaca_higueron/` | Bytes originales (`raw/`), texto por página (`text/`) y `archive_manifest_v0_1.json` con SHA-256 reales |
| `config/phase2_tumbes_capitana_hualaca_higueron_identity_v0_1.json` | Registro de identidad: fuentes, 38 citas literales, decisiones, unidades, contexto de asentamientos, bloqueos |
| `scripts/validate_phase2_tumbes_capitana_hualaca_higueron_identity.py` | Verificador stdlib, sin red |
| `tests/test_phase2_tumbes_capitana_hualaca_higueron_identity.py` | 17 pruebas: el registro pasa y cada guarda rechaza su violación |

Cada afirmación del registro cita un texto literal del archivo archivado. Las pruebas comprueban que la cita es una subcadena literal de esa página, con espacios normalizados. También comprueban que el archivo coincide con el SHA-256 del manifest.

## Decisiones de identidad

| Pregunta | Decisión | Base documental |
|---|---|---|
| Hualaca vs Higuerón | **No se puede resolver con la evidencia** | Higuerón aparece en INGEMMET A6764, la Ley 32573 y los mapas ANA 2016. Hualaca no aparece en ninguna fuente oficial archivada. |
| Hualaca vs Hualtacal | **No se equiparan** | Los nombres se parecen, pero ninguna fuente los relaciona. |
| Higuerón vs Hualtacal | **Quebradas distintas por nombre** | La Ley 32573 §1.2 enumera «quebrada Higuerón y quebrada Hualtacal». ANA 3743 los rotula por separado. |
| La Capitana vs Higuerón | **Quebradas distintas por nombre** | INGEMMET A6764, Cuadro 3.2: filas C-27 y C-28. Rótulos separados en ANA 3743 y 3755. |
| Quebrada vs centro poblado «La Capitana» | **Dos tipos de entidad; relación no declarada** | La quebrada aparece en INGEMMET y ANA. El centro poblado o caserío aparece en INDECI 2024, COEN 2025 y ANA 3743. |
| Quebrada vs caserío/sector «Higuerón» | **Dos tipos de entidad; relación no declarada** | Nombre de la carretera; zonas INGEMMET 2 y 8; ANA «HIGUERON» y «HIGUERON SECO»; COEN 2025. |
| ¿Un solo cauce Higuerón en Tumbes? | **Sin resolver** | (A) cruce vial C-28 en la ruta de San Jacinto; (B) divisoria interprovincial Contralmirante Villar–Tumbes; (C) dos grafías en una misma hoja ANA. |
| «Capitán Hoyle» (RC 13112) vs La Capitana | **No se equiparan** | Etiqueta distinta en la fuente. |
| El Higuerón de Piura, Cajamarca y La Libertad | **Distinto departamento; no se fusionan** | No se archivan como fuentes de Tumbes. |

## Eventos documentados

Solo hay evidencia a nivel de periodo, sin fecha diaria. Proviene de INGEMMET A6764, Cuadro 3.2 («Tramos carreteros afectados por los peligros detonados con las fuertes lluvias de El Niño Costero 2017»):

- C-27: tramo de carretera afectado por flujo proveniente de la quebrada La Capitana (bloque de flujos).
- C-42: vía afirmada afectada por erosión fluvial en la quebrada La Capitana.
- C-28: tramo de carretera afectado por flujo proveniente de la quebrada Higuerón (solo la mención A).

Estas filas no son eventos fechados, huellas de inundación ni datos de caudal o capacidad. Los Reportes Complementarios 13111 y 13112 (27-28/9/2026) no nombran ninguna de las tres quebradas. Eso no prueba que hubieran estado inactivas.

## Geometría y outlet

Ambas unidades tienen geometría y outlet en `MISSING`. Ninguna fuente archivada trae línea de cauce, cuenca ni punto de desembocadura. El orden de los rótulos en el texto de los mapas ANA no es un orden espacial. No se publica nada en el mapa.

## Integración con la auditoría nacional

Se aplaza hasta el QA independiente. En esta PR no se editan `config/phase2_national_inventory_completeness_audit_v0_1.json` ni su Markdown generado. La propuesta está en `national_inventory_crosswalk`: dos filas `IDENTITY_ONLY` y Hualaca en `requested_names_without_source`.

## Bloqueos externos

1. **Origen del nombre «Hualaca».** Solo pueden aclararlo quien lo aportó o una fuente local: Municipalidad Distrital de San Jacinto, ALA Tumbes o Gobierno Regional.
2. **¿Uno o varios cauces Higuerón?** Hace falta hidrografía ANA georreferenciada, la cartografía de la Ley 32573 (IGN 0863/0864) o una verificación de campo.
3. **Geometría y outlet.** `geosnirh.ana.gob.pe` y `repositorio.ana.gob.pe` no respondieron desde los runners.
4. **Eventos fechados.** Hace falta un reporte INDECI/COEN, SINPAD o municipal que nombre la quebrada.
