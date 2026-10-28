# Correspondencia `qc…` → estación SENAMHI: Reque y códigos del inventario (RESEARCH_ONLY / TEST_ONLY)

**Rama:** `research/senamhi-qc-correspondence-20261028`, apilada sobre #434 y sin merge. **Fecha:** 28-oct-2026.
No se toca el modelo predictivo, no se activan alertas ni calibraciones y no se publica nada.

## Resumen

| Código | Estación | Estado | Píxel IMERG |
|---|---|---|---|
| **qc00000332** | **REQUE**, Lambayeque / Chiclayo / Eten | **CONFIRMADO_USUARIO_CORROBORADO** | sí: celda (1001, 831), a 0,014° del borde |
| qc00000340 | EL ESPINAL, Lambayeque / Chiclayo / Oyotún | CANDIDATO_REGLA | sí, pero a 0,0017° del borde (≈ 180 m): sensible |
| qc00153102 | CUEVA BLANCA, Lambayeque / Ferreñafe / Incahuasi | CANDIDATO_REGLA | sí |
| qc00000132 | PUERTO PIZARRO, Tumbes / Tumbes / Tumbes | CANDIDATO_REGLA | **no**: las coordenadas difieren 0,070° entre versiones |
| qc00000247 | SAN MIGUEL, Piura / Piura / Catacaos | CANDIDATO_REGLA | **no**: 0,058° entre versiones |
| qc00000208 | MALLARES, Piura / Sullana / Marcavelica | CANDIDATO_REGLA | **no**: 0,0055° entre versiones (el máximo admitido es 0,005°) |
| qc00000791 | FONAGRO (CHINCHA), **Ica** | **CANDIDATO_FUERA_DE_REGION** | no evaluado |

**La lista de 55 códigos no está disponible.** El PR #428 solo publica conteos y cuatro duplicados, y los TXT no están ni en esta sesión ni en el repositorio. Se analizaron los 7 códigos conocidos. El índice `north_lookup_index_by_rule.csv` (223 estaciones) permite resolver los 48 restantes en cuanto se aporten sus nombres de archivo.

## 1. Reque: tres líneas de evidencia, registradas por separado

| | Fuente | Qué aporta | Clase |
|---|---|---|---|
| **E1** | Responsable, 28-oct-2026: el archivo se descargó desde la página de la estación REQUE del portal, con capturas | Que `qc00000332` ↔ REQUE (Lambayeque / Chiclayo / Eten) | Usuario, portal SENAMHI. Las capturas **no** están en el repositorio y no se pudieron leer |
| **E2** | Catálogo interno del paquete senamhiR (GPL-3), compilado en 2018 desde `senamhi.gob.pe/include_mapas/_map_data_hist03.php?drEsta=NN`, según su propio código. Versiones `018b442` (27-jun-2018, blob SHA-256 `760f6cde…`) y `c3f618d` (11-abr-2018, `d811072e…`) | **ID `000332` = REQUE**, estación convencional meteorológica (CON / M), datos de 1964 a 2018, «working». Lat **−6,886306**, lon **−79,835500**, **13 m**, Chiclayo / Eten. Entre las dos versiones, las coordenadas difieren 0,00014° | Terceros derivados de SENAMHI: corrobora, no confirma |
| **E3** | SENAMHI, Atlas climático, Anexo 1 ([PDF](https://www.senamhi.gob.pe/pdf/anexos-atlas-climatico.pdf)) | REQUE (código del Atlas **106046**), Chiclayo / Eten, −79,8 / −6,9, **13 m**. Distrito y altitud coinciden y las coordenadas de E2 redondean exactamente a las del Atlas | SENAMHI oficial, con 0,1° de precisión |

* **E1 y E2 son independientes:** el catálogo de 2018 no proviene del usuario. E3 confirma nombre, distrito, altitud y ubicación aproximada.
* **El nombre es inequívoco:** solo hay una REQUE en Lambayeque entre las 1.828 estaciones del catálogo.
* **Las coordenadas precisas solo vienen de E2**, es decir de un tercero, aunque se tomaron de la publicación de SENAMHI. Ni la página oficial de la estación ni OSCAR (que no tiene Reque) permiten contrastarlas hoy. Por eso la tabla georreferenciada la limita a **uso exploratorio hasta verificar las coordenadas en SENAMHI**.
* **Dos esquemas de código distintos:** el código del Atlas (106046) no es el ID del portal (000332). En el catálogo no se fusionan; se enlazan por E1 + E2 + E3.

## 2. ¿Existe una relación reproducible `qc` ↔ ID oficial?

* **Hipótesis H-QC:** `qcNNNNNNNN.txt` lleva el identificador de estación del portal rellenado a 8 dígitos (`qc` + `00` + ID de 6 dígitos).
* **Respaldo:**
  * un caso confirmado (Reque);
  * cinco códigos más que, aplicada la regla, caen en estaciones meteorológicas de Lambayeque, Piura y Tumbes, coherentes con el Atlas y con la etiqueta regional que dio el responsable a sus lotes;
  * senamhiR documenta el mismo formato de ID de 6 dígitos con ceros a la izquierda (por ejemplo `000280`);
  * las páginas de datos de SENAMHI usan `estaciones=000320` (una URL indexada).
* **Contraindicio:** `qc00000791` cae en FONAGRO (Chincha, Ica), fuera de la región. O bien el archivo proviene de Ica, o la regla falla en ese código. **Requiere verificación** del responsable.
* **Estado:** H-QC es una **hipótesis reproducible, no una regla publicada por SENAMHI**. Solo Reque se promueve. Los demás quedan como `CANDIDATO_REGLA` hasta tener una evidencia E1 por archivo, o hasta verificar el contenido (ver §4).

## 3. Tabla georreferenciada para la futura validación SENAMHI–IMERG

`georeferenced_stations_for_imerg.csv` reúne:
* las 6 estaciones resueltas por la regla en la región;
* las 11 estaciones automáticas de OSCAR (#422).

Cada fila incluye celda IMERG, distancia al borde, dispersión de coordenadas, estado de identidad y **uso permitido**:
* **Reque:** `EXPLORATORY_UNTIL_COORDINATES_VERIFIED_AT_SENAMHI`.
* **Resto de estaciones:** `NONE_UNTIL_IDENTITY_CONFIRMED` o `NONE_UNTIL_INSTRUMENT_RECORDS_AVAILABLE`.
* **Ninguna fila habilita métricas ni calibración.**

## 4. Verificaciones independientes que faltan (prioridad)

1. **Por cada TXT:** la página de la estación del portal, con nombre, código y coordenadas en G/M/S, o la captura de la barra de direcciones con `estaciones=` al descargar. Para Reque, eso verificaría directamente las coordenadas de E2.
2. **Contenido de `qc00000332.txt`** (del PR #428): primer y último año frente a 1964–2018 de E2; ausencia de registros posteriores a la fecha de descarga; y coherencia de temperaturas con 13 m de altitud. Es una prueba técnica barata de la identidad.
3. **La lista de los 55 nombres de archivo**, para aplicar el índice por regla y marcar cuáles requieren E1.
4. **`qc00000791`:** confirmar si es de Ica.

## Archivos

* `read_rda.py`: lector `.rda` sin R ni dependencias, probado con un `.rda` sintético.
* `extract_senamhiR_catalogue.py`: extracción reproducible desde el repositorio público de senamhiR.
* `senamhiR_catalogue_north_2018.json`: 223 estaciones del norte en ambas versiones, más un índice nacional de ID → nombre y región.
* `user_evidence_qc_20261028.json`: evidencia E1, separada del resto.
* `qc_codes_known_v1.json`: los 7 códigos conocidos.
* `resolve_qc.py`: genera `qc_resolution.csv`, `georeferenced_stations_for_imerg.csv` y, con `--index`, `north_lookup_index_by_rule.csv`.
* `../catalog_confirmed.csv`: la fila del Atlas `106046 REQUE` ahora lleva `qc00000332` con `CONFIRMADO_USUARIO_CORROBORADO`. Ninguna otra fila se enlaza.
* Pruebas: `tests/test_qc_resolution_20261028.py` y `tests/test_station_catalog_20261027.py` (actualizada).
