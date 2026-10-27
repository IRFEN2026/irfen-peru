# Informe · Validación con observaciones históricas oficiales (SENAMHI GBON/RBON)

**Estado:** RESEARCH_ONLY / TEST_ONLY.
**Rama:** `research/senamhi-gbon-historical-validation-20261027`, apilada sobre #420, sin merge.
**Fecha:** 27-oct-2026. **Issue:** #400.

> **Resultado.**
> * **Identidad y coordenadas oficiales:** resueltas para **11 estaciones automáticas GBON/RBON del norte**, con identificador WIGOS y precisión de 0,0001° o mejor. Ocho están en Piura y Lambayeque, que el plan prioriza; Tumbes solo tiene la estación sinóptica.
> * **Registros:** **ningún registro instrumental** del conjunto abierto de SENAMHI. La plataforma respondió **HTTP 418** a la descarga desde GitHub. Es un bloqueo del proveedor y no se intentó eludirlo.
> * **Pares reales: 0.** No hay solapamiento con el IMERG de píxel archivado en el repositorio. **Calibración: BLOQUEADA.**

## 1. Conjunto de datos abierto (punto 1)

* **Página:** [Variables Meteorologicas de las Estaciones automáticas de intercambio internacional – SENAMHI](https://www.datosabiertos.gob.pe/dataset/variables-meteorologicas-de-las-estaciones-autom%C3%A1ticas-de-intercambio-internacional-servicio). Identificador CKAN `b884a001-f444-4c87-91b2-bee1891e6eb7`; licencia ODC-BY.
* **Fechas:** creado el 31-may-2024 y modificado por última vez el 08-sep-2025, según los metadatos de la API (`package_show`).
* **Archivos:**
  * CSV de 48,14 MB;
  * diccionario de datos XLSX (10,56 KB);
  * metadatos DOCX (20,18 KB).
* **Contenido declarado:** datos **horarios validados** de temperatura, humedad relativa y precipitación (mm) de las estaciones automáticas GBON y RBON.
  * Campos de estación: nombre, latitud, longitud, altitud, departamento, provincia, distrito, ubigeo y red.
  * Campos meteorológicos: fecha, hora y las tres variables.
  * La página indica que hay que filtrar los registros vacíos.
* **No declarado en las páginas:** la cobertura temporal, la **zona horaria** de la hora, el **periodo de acumulación** de la precipitación, los códigos de faltante y el método de validación. Esos datos estarían en el diccionario y en los metadatos, que no se pudieron leer.

## 2. Descarga acotada (punto 2): **BLOQUEADA por el proveedor**

* **Desde GitHub:** una ejecución única ([run 40424302421](https://github.com/IRFEN2026/irfen-peru/actions/runs/40424302421)) pidió los 4 recursos una sola vez. Los cuatro respondieron **HTTP 418**, con el mismo cuerpo de 3.195 bytes (`open_data_20261027/download_log.json`). El flujo no se repite.
* **Desde esta sesión:**
  * el servidor de trabajo no llega al dominio;
  * la herramienta de lectura web rechaza las URLs de archivos por longitud;
  * el enlace corto `/node/18076/dataset/download` devuelve un binario que no puede interpretar.
* No se probaron otros agentes de usuario ni otras vías: hacerlo sería eludir la restricción.
* Por eso **no hay inventario de registros**: ni filas, ni cobertura, ni faltantes, ni acumulaciones. No se inventa ninguno.

## 3. Estaciones (puntos 3 y 6): identidad y precisión oficiales vía WMO OSCAR

* **Fuente:** la consulta única a OSCAR/Surface del 26-oct, ya versionada (HTTP 200, 83 estaciones de Perú). Tabla completa en `historical/inventory_north_gbon_rbon_20261027.json`.
* **Píxel asignable** significa: precisión de 0,02° o mejor, y el punto a más de media precisión del borde de la celda.
* **Las coordenadas redondeadas nunca seleccionan un píxel.** Las de 0,1° no son asignables; las sinópticas de un minuto de arco son casos límite, por eso solo se consideran para prueba las automáticas `0-604`.

| Estación | WIGOS | Lat / Lon | Precisión | Programas (OSCAR) | Estado | Píxel |
|---|---|---|---|---|---|---|
| TUMBES (sinóptica) | 0-20000-0-84370 | −3,55 / −80,38333 | 1′ (≈ 0,017°) | GSN, RBON | Operativa | sí, en el límite |
| TALARA (sinóptica) | 0-20000-0-84390 | −4,56667 / −81,25 | 1′ | RBON | Operativa | sí, en el límite |
| PAIMAS | 0-604-1-09615102 | −4,6343 / −79,9458 | 0,0001° | RBON | Operativa | **sí** |
| LANCONES | 0-604-1-07610101 | −4,642897 / −80,547161 | 1e-6° | RBON | Operativa | **sí** |
| SAUSAL DE CULUCAN | 0-604-1-09613301 | −4,75237 / −79,75792 | 1e-6° | RBON | Desconocido | **sí** |
| CHULUCANAS | 0-604-1-08602104 | −5,108444 / −80,169539 | 1e-6° | RBON | Operativa | **sí** |
| SAN IGNACIO (Cajamarca) | 0-604-1-11605101 | −5,1442 / −78,9998 | 0,0001° | GBON | Sin reportar | **sí** |
| PIURA (sinóptica) | 0-20000-0-84401 | −5,2 / −80,6 | **0,1°** | GSN, RBON | Operativa | **NO** (esquina de celdas) |
| CANCHAQUE | 0-604-1-09601402 | −5,4005 / −79,6052 | 0,0001° | RBON | Operativa | **sí** |
| EL VIRREY | 0-604-1-09595002 | −5,5357 / −79,9841 | 0,0001° | RBON | Operativa | **sí** |
| TONGORRAPE | 0-604-1-09582002 | −6,06692 / −79,68203 | 1e-5° | GBON, RBON | Operativa | **sí** |
| TINAJONES (Lambayeque medio) | 0-604-1-10575101 | −6,654889 / −79,427919 | 1e-6° | RBON | Sin reportar | **sí** |
| CHICLAYO (sinóptica) | 0-20000-0-84452 | −6,78333 / −79,81667 | 1′ | GSN, RBON | Operativa | sí, en el límite |

* **Tumbes** no tiene estaciones automáticas GBON/RBON en OSCAR; solo la sinóptica del aeródromo. **Ninguna de las 10 estaciones del episodio** del 21–26 de octubre figura en OSCAR.
* **Identidad pendiente.** Cuando se obtenga el CSV, cada estación debe vincularse por **nombre y coordenadas a la vez** con su fila de OSCAR. Si las coordenadas difieren en más de la precisión, no se asume equivalencia.

## 4. Solapamiento con IMERG archivado (punto 4)

* **IMERG de píxel archivado en el repositorio:**
  * sólo los campos diarios de IMERG Late V07 a 0,1°, suma 07–07, de los días pluviométricos **2026-10-09 a 2026-10-13**;
  * cada uno con 48/48 medias horas y una caja de lat −9,55…−3,05 y lon −81,65…−76,65 (rama `v09/forecast-data`);
  * cubren las celdas de todas las estaciones de la tabla.
* El resto del IMERG del repositorio son medias por polígono, que no sirven para emparejar con un punto.
* **Registros instrumentales disponibles: 0.** Aunque se obtuviera el CSV, su última modificación (08-sep-2025) es anterior a esos días.
* **Solapamiento real: 0 pares.**

## 5. Gránulos que harían falta (punto 5, sin descargar)

La lista exacta de gránulos no se puede fijar sin la cobertura del CSV, y no se inventa. Cuando el CSV esté inventariado, la regla es la siguiente:

* **Selección de días.** Por cada estación con píxel asignable, se toman los días pluviométricos con registros horarios completos dentro de la cobertura. Se priorizan los periodos lluviosos de la costa norte, por ejemplo febrero a abril, si están cubiertos, más una muestra comparable de días secos.
* **Producto recomendado para una prueba independiente:** IMERG **Late** V07 medio-horario (`GPM_3IMERGHHL`), 48 gránulos por día, con nombres y versión confirmados en CMR antes de descargar. No se asume que V07B y V07C sean intercambiables.
* **IMERG Final** (`GPM_3IMERGHH`) está ajustado con pluviómetros GPCC. Puede incorporar estaciones sinópticas de SENAMHI (TUMBES, PIURA, CHICLAYO, TALARA), así que la comparación con ellas **no sería independiente**. Las estaciones automáticas `0-604` son preferibles.
* **Volumen indicativo:** un mes de prueba equivale a unos 1.440 gránulos de unos 7 MB, cerca de 10 GB descargados y borrados tras extraer un bloque regional. **Requiere nueva autorización.**

## 6. Pruebas (punto 7)

* Local: 71 pruebas, 68 OK y 3 omitidas (HDF5, porque no hay h5py local).
* Prueba nueva `test_historical_inventory_20261027.py`, que verifica:
  * los identificadores y la precisión tomados de OSCAR;
  * que la celda calculada coincida con la del inventario;
  * que las coordenadas de 0,1° nunca resulten asignables;
  * que los cuatro recursos respondieran 418;
  * que el solapamiento sea cero.
* **Métricas:** ninguna, porque no hay pares elegibles. La calibración sigue **BLOQUEADA**.

## 7. Bloqueos y siguiente paso

1. **El CSV, el diccionario y los metadatos** de datosabiertos.gob.pe. Vía recomendada: que el responsable los descargue en un navegador y los adjunte. El paquete los procesaría offline: inventario, cobertura, zona horaria y acumulación según el diccionario, y vinculación de identidad con OSCAR.
2. **La zona horaria y la acumulación** de la precipitación horaria: confirmarlas en el diccionario antes de cualquier par. Si no se pueden confirmar, la precisión de la ventana no sería `EXACT`.
3. **Nueva autorización acotada para IMERG Late histórico** de los días seleccionados (§5), una vez conocida la cobertura.
4. **Registros de octubre de 2026** de las automáticas del norte, vía WIS2 o exportación oficial. Es la única vía para emparejar con los campos de píxel ya archivados (09–13 oct) sin descargar más gránulos.
