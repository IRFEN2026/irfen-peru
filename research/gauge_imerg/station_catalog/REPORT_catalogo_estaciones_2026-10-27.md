# Catálogo verificable de estaciones SENAMHI — Lambayeque, Piura y Tumbes (RESEARCH_ONLY)

**Rama:** `research/senamhi-station-catalog-20261027`, apilada sobre #427 y sin merge. **Fecha:** 27-oct-2026.
No se tocan el modelo predictivo ni los parámetros operativos.

> **Resultado.** El catálogo tiene **73 filas confirmadas en fuentes oficiales**: 60 del Anexo 1 del Atlas climático de SENAMHI y 13 de WMO OSCAR/Surface. Hay **5 posibles equivalencias** entre las dos fuentes, que no se fusionan. **Ninguno de los 6 códigos `qc…` conocidos está identificado.**
> * La relación «código de archivo `qc…` → estación» no está documentada en ninguna fuente pública que se haya podido leer.
> * La descarga del portal exige cuenta de usuario y aceptar condiciones de uso, así que no se automatizó.
> * Ningún código `qc` recibe coordenadas.

## 1. Cómo relaciona el portal los códigos `qc…` con las estaciones (tarea 1)

| Fuente | Acceso | Qué aporta |
|---|---|---|
| [Portal de descarga SENAMHI](https://www.senamhi.gob.pe/site/descarga-datos/) | `robots_disallowed` para la herramienta de lectura; tiempo de espera agotado desde GitHub | Nada legible |
| [Tutorial oficial de descarga (PDF de SENAMHI)](https://www.senamhi.gob.pe/mapas/descarga-datos/pdf/tutorial-para-la-descarga-de-datos.pdf) | Leído | Pasos: elegir la estación, iniciar sesión o **registrarse**, introducir un código de verificación y **aceptar los términos**; el resultado es un archivo de texto. **No menciona** el nombre `qc…` ni cómo se forma |
| Páginas de datos por estación (`_dat_esta_tipo02.php` y `_dato_esta_tipo02.php`) | `robots_disallowed`; tiempo agotado desde GitHub | Un documento de terceros ([RPubs](https://rstudio-pubs-static.s3.amazonaws.com/936736_397c1d01f64747489f0d8f265970cc85.html)) muestra que usan los parámetros `estaciones=<código>` y `cod_old=`. Es decir, hay un **código actual y un código antiguo**. **No confirmado en SENAMHI** |
| [Anexo 1 del Atlas climático (SENAMHI)](https://www.senamhi.gob.pe/pdf/anexos-atlas-climatico.pdf) | Leído | Códigos de 6 dígitos (por ejemplo `105070 CHULUCANAS`). **No aparecen** 340, 000340, 153102, 132 ni 000132 |
| [Manual de metadatos MT-DRD-004 (SENAMHI)](https://www.senamhi.gob.pe/load/file/00711SENA-73.pdf) | `robots_disallowed` | Pendiente (podría definir los esquemas de código) |

**Conclusión.**
* Con las fuentes accesibles, el número `NNNNNNNN` de `qcNNNNNNNN.txt` **no se puede vincular** con un código del Atlas, un WIGOS ni un nombre. Tampoco consta que sea el `cod_old`.
* Equiparar `qc00000340` con «estación 000340», o con un código del Atlas, sería deducir la identidad a partir del nombre del archivo, que es justo lo que no se permite.
* La relación tiene que salir del **propio portal**, desde la sesión de usuario del responsable: la página de la estación desde la que se descargó cada TXT, con su nombre, código y coordenadas visibles en pantalla.

## 2. Metadatos recuperados (tarea 2)

| Fuente | Filas | Campos | Precisión de coordenadas | Integridad |
|---|---|---|---|---|
| SENAMHI, Atlas climático, Anexo 1 | 60 (Tumbes 12, Piura 32, Lambayeque 16) | Código, nombre, departamento, provincia, distrito, longitud, latitud, altitud y marcas PP/TMAX/TMIN | **0,1°**: no sirve para elegir una celda IMERG | Transcripción de la lectura web; el PDF no está archivado y no tiene SHA-256 |
| WMO OSCAR/Surface, búsqueda `PER` del 26-oct | 13 en el norte | WIGOS, nombre, latitud, longitud, altitud, programas (GBON/RBON/GSN) y estado | 1e-6° a 1e-4° en las automáticas `0-604`; un minuto de arco en las sinópticas | JSON archivado con su SHA-256 |

* La herramienta de lectura anunció 17 filas para Lambayeque y devolvió 16. Puede faltar una fila; hay que verificarlo con el PDF original.
* El Atlas no declara fecha, versión, tipo de estación ni si sigue activa.
* OSCAR no declara departamento ni distrito, y no se infieren.
* **Prioridad por cuenca** (las listas completas están en `catalog_confirmed.csv`):
  * **Lambayeque medio y alto:** Oyotún, El Espinal, Sipán, Pucalá, Cayaltí, Incahuasi, Cueva Blanca y Puchaca en el Atlas; Tinajones y Tongorrape en OSCAR.
  * **Piura:** Chulucanas, Morropón, Huancabamba y Lancones, entre otras.
  * **Tumbes:** 12 estaciones en el Atlas.

## 3. Catálogo, API o servicio geográfico (tarea 3)

* **IDESEP (GeoServer de SENAMHI):** tiempo agotado desde GitHub, también en agosto, y ahora con WFS 2.0.0 ([run 40589787519](https://github.com/IRFEN2026/irfen-peru/actions/runs/40589787519)).
* **[GEOCATMIN de INGEMMET](https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/SERV_OTRAS_FUENTES/MapServer/1)**, capa «Estación Meteorológica - SENAMHI»: es una republicación por otra entidad pública, que se contrastaría con SENAMHI.
  * Desde GitHub, falla la **verificación del certificado TLS**: la cadena del servidor está incompleta. No se desactivó la verificación.
  * La herramienta de lectura recibe `robots_disallowed`.
* **WIS2 / OAPI de SENAMHI:** tiempo agotado (sesiones anteriores).
* **WMO OSCAR:** accesible desde GitHub. Es la única vía automatizable verificada, pero no contiene códigos `qc`.
* **Conclusión:** no se encontró ningún catálogo público accesible que asocie automáticamente los `qc…` con las estaciones.

## 4. Estructura de los TXT (tarea 4)

**Documentado por SENAMHI** en el tutorial oficial:
* texto con separador de espacio;
* columnas A año, B mes, C día, D **precipitación acumulada**, E **temperatura máxima** y F **temperatura mínima**;
* **`-99.9` = sin información** para esa variable.

**No documentado en el tutorial:**
* las unidades (presumiblemente mm y °C, pero sin constancia oficial en lo leído);
* el separador decimal;
* el **periodo diario de observación** (hora de cierre de la precipitación diaria y si es 07–07);
* el significado de «qc» y el control de calidad aplicado.

Hasta que haya documentación SENAMHI, la ventana diaria se clasifica como `INFERRED` y no `EXACT`, lo que bloquea su uso para métricas.

**Observado en los 58 TXT examinados en otra sesión (PR #428):** seis campos y `-99.9`. Coincide con el tutorial. Esos archivos no están en esta sesión.

## 5. Entregables (tareas 5 y 6)

* `catalog_confirmed.csv`: 73 filas tal como aparecen en fuentes oficiales.
  * `qc_link_status = NO_DOCUMENTADO` en todas.
  * Confianza de identidad ALTA (fila oficial).
  * Confianza de coordenadas: BAJA para las del Atlas a 0,1°, ALTA para las de OSCAR.
* `catalog_candidates.csv`: 5 posibles equivalencias entre el Atlas y OSCAR por nombre y coordenadas compatibles con el redondeo, **sin fusionar**:

  | OSCAR | Atlas | Estado |
  |---|---|---|
  | CHULUCANAS | 105070 | Candidato (Δaltitud 0 m) |
  | SAUSAL DE CULUCAN | 104059 | Candidato (Δaltitud 0 m) |
  | LANCONES | 104016 | Candidato (Δaltitud 3 m) |
  | EL VIRREY | VIRREY 105013 | Candidato (Δaltitud 5 m) |
  | PIURA | 105001 | **Dudoso**: altitud 49 m frente a 22 m |

  Una estación automática (`0-604`) y una convencional pueden compartir nombre y sitio y ser instrumentos distintos.
* `qc_codes_pending.csv`: **6 códigos sin identificar**: `qc00000340`, `qc00153102`, `qc00000132`, `qc00000791`, `qc00000247` y `qc00000208`.
* `build_station_catalog.py`: genera los tres CSV de forma reproducible y offline. Hay una prueba de que no se asigna ningún `qc` ni se fusionan candidatos.

## 6. Pendiente

1. **Correspondencia `qc` → estación, desde el portal con la cuenta del responsable.** Por cada TXT descargado hace falta una captura de pantalla o el texto de la página de la estación (nombre, código, coordenadas, altitud, tipo y estado), junto con la URL de descarga. Con eso cada `qc` pasaría a «confirmado por SENAMHI».
2. **PDF original del Atlas climático**, adjuntado, para archivar su SHA-256 y verificar la fila 17 de Lambayeque.
3. **Documentación del formato `qc`:** unidades, hora de cierre de la precipitación diaria y control de calidad, mediante el manual MT-DRD-004 o una consulta a SENAMHI.
4. **GEOCATMIN:** se podría reintentar una sola vez completando la cadena TLS con el certificado intermedio oficial de su emisor, nunca desactivando la verificación, y solo con autorización. Su contenido seguiría siendo candidato hasta contrastarlo con SENAMHI.
