# v0.9 · ubicaciones documentales ANA 2016-2017 en la costa (30-10-2026, RESEARCH_ONLY / TEST_ONLY)

## Fuente
- **Documento:** ANA (DEPHM), «Complementación de identificación de poblaciones vulnerables por activación de quebradas 2016-2017».
  - Registro: CENEPRED SIGRID 2799 (`https://sigrid.cenepred.gob.pe/sigridv3/documento/2799`). Copia citada en el maestro: SINIA/MINAM, que hoy responde 403.
  - PDF: 80 páginas, 15 439 325 bytes, SHA-256 `45f206b7aae21414168cb46643d7907707854ca5b0ff61ec832dd255ef343d0b`, `Last-Modified` 16-11-2017.
  - Descargado el 30-10-2026 (`data/v09/sources/ana2017_complementacion_quebradas/source_record.json`). El PDF no se versiona: su SHA-256 identifica los bytes leídos.
- **Cuadros:** «Centros poblados vulnerables por activación de quebradas» de los departamentos costeros:
  - Cuadros 9 (Tumbes), 11 (Piura), 17 (Lambayeque), 19 (La Libertad) y 23 (Áncash);
  - Cuadros 29 (Lima), 41 (Ica), 43 (Arequipa), 47 (Moquegua) y 49 (Tacna);
  - columnas: N°, Este, Norte, provincia, distrito, centro poblado, quebrada, viviendas y habitantes en riesgo.
- **Datum:** declarado en el pie de cada cuadro: «WGS 84 – ZONA 17/18/19 SUR».
- **Callao:** el documento no tiene cuadro para Callao.

## Qué representa cada punto
- **Es** el centro poblado vulnerable que ANA asocia a la activación de una quebrada nombrada.
- **No es** la ubicación de la quebrada, de su cauce ni de su desembocadura, ni una zona de inundación.
- No entra en la lluvia, en la prioridad ni en el paquete territorial.

## Método reproducible
1. `scripts/v09_ana2017_source_capture.py`: descarga y texto por página. En el PDF los cuadros están dibujados como vectores o imágenes y pypdf solo lee sus títulos.
2. `scripts/v09_ana2017_table_images.py`: renderizado a 300 ppp con poppler `pdftoppm` (SHA-256 por página en `table_pages_index.json`).
3. `scripts/v09_ana2017_table_ocr.py`: rejilla detectada con OpenCV y OCR Tesseract celda a celda.
   - Tres lecturas independientes por celda numérica; se acepta un valor si al menos dos coinciden.
   - Datum leído del pie del cuadro.
   - Salida en bruto: `ocr_tables.json`.
4. `scripts/v09_build_ana2017_coastal_points.py` (`--check`) construye `site/data/v09/ana2017_coastal_points_v0_1.json`.
   - **Coordenadas:** consenso 2 de 3 en Este (6 cifras) y Norte (7 cifras).
   - **Datum:** el del cuadro.
   - **Jurisdicción:** el punto, transformado de EPSG:327nn a WGS 84 (serie de Krüger, contrastada con pyproj en CI), debe caer en la provincia INEI que declara la fila.
     - Límites: INEI referenciales vía SERFOR, `data/v09/sources/inei_coastal_provinces/`, SHA-256 en `provenance.json`.
   - **Lo que no cumple** queda listado con su motivo y no se dibuja.
5. **Comprobación independiente:** el maestro ya tenía transcritas por otra vía las filas de Tumbes, Piura y Lambayeque. De esas, 164 tienen consenso OCR propio y las 164 coordenadas coinciden exactamente.
   - En 4 filas sin consenso OCR, una de las tres lecturas coincide con el maestro y se acepta como dos lecturas independientes.
6. **Cifras de exposición:** se publican solo para la columna cuya suma coincide con el TOTAL del cuadro.
   - Viviendas y habitantes directos: Áncash, Lima, Ica y Tacna.
   - Habitantes indirectos: nunca cuadran, no se publican.
7. **Inventario:**
   - **Enlace por fila:** cuando el maestro cita la misma fila del cuadro.
   - **Enlace por nombre:** si la quebrada tiene el mismo nombre normalizado en el departamento. Se marca «por comprobar».
   - Nunca se añaden filas al maestro (sigue con 400).

## Matriz de cobertura (HEAD de la rama)
| Departamento | Registros en el inventario maestro | Filas ANA leídas / declaradas | Ubicaciones documentales admitidas | Fuera de provincia | Pendientes de OCR | Registros del maestro enlazados | Elementos IRFEN dibujados | Geometrías reproducibles (maestro) | Estado cartográfico |
|---|---|---|---|---|---|---|---|---|---|
| Tumbes | 68 | 44 / 44 | 44 | 0 | 0 | 44 | 4 | 0 | geometrías IRFEN + ubicaciones documentales |
| Piura | 78 | 77 / 79 | 76 | 1 | 2 | 75 | 11 | 0 | geometrías IRFEN + ubicaciones documentales |
| Lambayeque | 46 | 47 / 47 | 46 | 1 | 0 | 45 | 6 | 0 | geometrías IRFEN + ubicaciones documentales |
| La Libertad | 9 | 68 / 69 | 65 | 3 | 1 | 7 | 19 | 0 | geometrías IRFEN + ubicaciones documentales |
| Ancash | 34 | 67 / 67 | 63 | 4 | 0 | 20 | 0 | 0 | solo ubicaciones documentales (geometría pendiente) |
| Lima | 117 | 97 / 97 | 91 | 6 | 0 | 51 | 22 | 3 | geometrías IRFEN + ubicaciones documentales |
| Callao | 0 | — | 0 | 0 | 0 | 0 | 0 | 0 | cobertura pendiente |
| Ica | 48 | 53 / 53 | 51 | 2 | 0 | 42 | 0 | 0 | solo ubicaciones documentales (geometría pendiente) |
| Arequipa | 0 | 116 / 120 | 116 | 0 | 4 | 0 | 0 | 0 | solo ubicaciones documentales (geometría pendiente) |
| Moquegua | 0 | 36 / 37 | 33 | 2 | 1 | 0 | 0 | 0 | solo ubicaciones documentales (geometría pendiente) |
| Tacna | 0 | 25 / 25 | 24 | 0 | 1 | 0 | 0 | 0 | solo ubicaciones documentales (geometría pendiente) |
| **Total** | 400 | 630 / 638 | 609 | 19 | 9 | 284 | 62 | 3 | |

- **Pendientes de OCR:** filas no leídas por la rejilla (Piura 12 y 13, La Libertad 1, Arequipa 11, 14, 22 y 70, Moquegua 1) y celdas sin consenso.
- **Fuera de provincia:** sobre todo límites provinciales (Santa Eulalia, entre Lima y Huarochirí) e incoherencias del propio cuadro.
  - Ejemplo: el distrito de Ilo aparece bajo Mariscal Nieto y el punto cae en la provincia de Ilo.
  - Se listan con `point_in_inei_province` y no se dibujan.
- **Nombres:** se publican tal como los lee el OCR (pueden faltar tildes). Se revisan antes de cualquier uso nominal.

## Límites y pendientes
- **No hay geometrías hidrológicas nuevas.** Ningún punto es cuenca, cauce ni outlet; Áncash, Ica, Arequipa, Moquegua y Tacna siguen con la geometría pendiente.
- **Departamentos del sur fuera del maestro:** Arequipa, Moquegua y Tacna aportan centros poblados y nombres de quebradas que el maestro no contiene. Quedan como candidatos documentales para una reconciliación del inventario, sin incorporarse.
- **Revisión visual:** queda pendiente para las 9 filas no leídas y para los nombres.
