# IRFEN v0.9 · fuentes hidrográficas oficiales y preparación de la fase lluvia–territorio (30-10-2026)

RESEARCH_ONLY / TEST_ONLY. Guardas sin cambios:
- `production_use=false`
- `activation_gate=BLOCKED`
- `UNKNOWN_NOT_LOW_RISK`
- `decision_thresholds=null`
- `hydraulic_factors=null`

No se tocó el motor de lluvia, la priorización, los avisos, el mapa público ni `main`. Rama apilada sobre el PR #455 (conciliación ANA).

Reproducir sin red:
```bash
python scripts/v09_hydro_source_registry.py --check     # registro de fuentes ← registros de solicitudes
python scripts/v09_hydro_association.py --check         # centros poblados ↔ unidades hidrográficas
python -m unittest tests.test_v09_hydro_association
```

## 1. Fuentes: qué se pudo recuperar
Captura: [run 41139283191](https://github.com/IRFEN2026/irfen-peru/actions/runs/41139283191), en tres etapas con límite de tiempo propio y un registro escrito tras cada solicitud.
- Política: 2 intentos por solicitud de 75 s. No se reintenta la misma fuente en esta fase.
- Primer intento: [41134595221](https://github.com/IRFEN2026/irfen-peru/actions/runs/41134595221). Se canceló a los 40 min sin escribir nada; por eso se pasó a capturar por etapas.

Detalle completo en `data/v09/sources/ana_hydrographic_units/source_registry_v0_1.json`: URL, hora, bytes, SHA-256 y error de cada solicitud.

| Fuente | URL | Captura (UTC) | Licencia | SRC | Qué representa | Recuperado | Veredicto |
|---|---|---|---|---|---|---|---|
| ANA · Unidades Hidrográficas (IDEP `ANA_WMS`, capas 7 y 8) | `https://www.idep.gob.pe/geoportal/rest/services/INSTITUCIONALES/ANA_WMS/MapServer/8` | 30-10 22:37:03–22:37:32 | Sin licencia explícita: el servicio declara `copyrightText` «IGN» y la capa lo deja vacío. Uso interno de investigación con atribución; confirmar con ANA antes de publicar | Origen EPSG:4326 (servicio en 3857); salida `outSR=4326`, 6 decimales | **Cuencas e intercuencas** (polígonos Pfafstetter, niveles mixtos). No son cauces, desembocaduras ni zonas inundables | 127 polígonos del Pacífico (`NIVEL1='1'`) de 231 en la capa. 6 respuestas GeoJSON (gzip) con SHA-256 | ✅ **UTILIZABLE** |
| ANA · Ríos y Quebradas (SNIRH `ONRH/Rios_Quebradas_AAVI`, capa 0) | `https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0` | 30-10 22:37:32–22:52:44 | Sin licencia explícita (servicio con autoría DCERH-ANA) | 4326 según el contrato archivado (no verificado ahora) | **Ríos y quebradas** (líneas con `NOMBRE_CA`, `CODIGO_UH`) | Nada. 16 solicitudes, todas con tiempo agotado (`URLError: timed out`); la etapa alcanzó su límite de 15 min | ⛔ **BLOQUEADA** desde los runners de GitHub. Coincide con los dos intentos anteriores: proxy 403 en el entorno de revisión y CONNECT_TIMEOUT en el run 36798969133 del 01-10 |
| IGN · Corriente de Agua (IDEP `TEMA_BASE`, capa 5) | `https://www.idep.gob.pe/geoportal/rest/services/DATOS_ESPACIALES/TEMA_BASE/MapServer/5` | 30-10 22:52:46–22:52:52 | Sin licencia explícita | Fuente en EPSG:24878 (PSAD56 / UTM 18S), según el sondeo archivado | **Corrientes de agua** (ríos y quebradas de la cartografía base) | Nada. Las 7 respuestas son HTTP 200 con el error `500: Service DATOS_ESPACIALES/TEMA_BASE/MapServer not started` | ⛔ **SERVICIO PARADO** (estado del servidor, no un resultado negativo) |

**Estabilidad de la fuente utilizable:**
- El metadato del servicio `ANA_WMS` tiene el mismo SHA-256 (`765c43c9…`) que la captura del 20-08-2026.
- Los polígonos de Chancay-Lambayeque y Zaña tienen los mismos vértices que en agosto: 5132 y 3294, con diferencias ≤ 1e-6° por el redondeo a 6 decimales.

**Limitaciones de las UH ANA:**
1. **Solo la parte peruana.** Tumbes (−80,127° E) y Zarumilla terminan en la frontera; la cabecera del Puyango-Tumbes y del Catamayo-Chira, en Ecuador, no está. La lluvia aguas arriba en Ecuador queda fuera de cualquier media por UH.
2. **Niveles Pfafstetter mezclados.** Hay cuencas grandes (Piura, 10 872 km²) e intercuencas costeras pequeñas (13939, 188 km²); no son unidades comparables.
3. **Vertiente atlántica no capturada.** 30 centros poblados admitidos (Áncash 19, La Libertad 8 y Piura 3, en Huancabamba) caen fuera de todas las UH del Pacífico. Son de la vertiente atlántica: no es un error.
4. **Licencia sin declarar.** Basta para investigación interna, pero no para publicar.

## 2. Asociación de centros poblados con unidades hidrográficas
Archivo: `data/v09/research/hydro_association_v0_1.json`. 619 centros poblados admitidos (tras #455) frente a 127 UH.

**Qué afirma la relación `UH_QUE_CONTIENE_AL_CENTRO_POBLADO`:** solo que la coordenada documental del centro poblado cae dentro del polígono.
- **No** dice que la quebrada nombrada drene a esa UH.
- **No** dice que el agua llegue al centro poblado.
- **No** es un cauce, una desembocadura ni una huella de inundación.

| Departamento | Admitidos | Dentro de una UH del Pacífico | A < 1 km del límite de la UH | Fuera (vertiente atlántica) | UH distintas |
|---|---|---|---|---|---|
| **Tumbes** | 44 | 44 | **14** | 0 | 5 |
| **Piura** | 78 | 75 | 3 | 3 | 6 |
| Lambayeque | 46 | 46 | 0 | 0 | 7 |
| La Libertad | 66 | 58 | 7 | 8 | 7 |
| Áncash | 63 | 44 | 4 | 19 | 8 |
| Lima | 91 | 91 | 6 | 0 | 12 |
| Ica | 51 | 51 | 1 | 0 | 6 |
| Arequipa | 120 | 120 | 9 | 0 | 13 |
| Moquegua | 35 | 35 | 0 | 0 | 2 |
| Tacna | 25 | 25 | 3 | 0 | 5 |

**Tumbes.** Centros poblados por UH:
- Cuenca Tumbes: 21
- Cuenca Zarumilla: 11
- Intercuenca 13939: 6
- Intercuenca 13951: 4
- Intercuenca 13935: 2

14 de los 44 están a menos de 1 km del límite de la UH; en la intercuenca 13935 hay uno a 82 m. La coordenada del cuadro no declara precisión, así que la pertenencia de esos 14 a una UH concreta es frágil: se marcan `near_boundary` y no deben usarse sin revisar.

**Piura.** Centros poblados por UH:
- Cuenca Piura: 50
- Intercuenca 1379: 10
- Cuenca Chira: 9
- Intercuenca 13779: 3
- Cuenca Cascajal: 2
- Cuenca Olmos: 1

Otros 3 caen en la vertiente atlántica (Huancabamba). La pertenencia es más estable porque las UH son grandes.

**Cauces oficiales por nombre (Tumbes y Piura):** no se pudo comprobar. Las dos fuentes lineales están bloqueadas, así que todos los centros poblados quedan en `FUENTE_NO_DISPONIBLE`, que significa desconocido, no ausencia de cauce. El método ya está implementado y probado en vacío:
- nombre normalizado idéntico;
- distancia a la línea ≤ 3 km → `NOMBRE_COINCIDE_CERCA` (candidato, no identidad);
- más lejos → `NOMBRE_COINCIDE_LEJOS`;
- sin coincidencia → `SIN_LINEA_OFICIAL_CON_ESE_NOMBRE`.

Funcionará en cuanto haya líneas archivadas.

**Geometrías de quebradas oficiales verificables hoy:**
- **Tumbes y Piura: ninguna reproducible en esta sesión.**
- En el repositorio, para otras zonas:
  - tramos críticos ANA/SIGRID de Chongoyape y Oyotún (Lambayeque, solo revisión);
  - faja marginal ANA de Jicamarca (una faja marginal **no** es huella de inundación).
- Plan de congelación de `Inundacion_Tumbes`: son huellas de inundación de 2023, no cauces, y no se pueden trasladar a otras quebradas.

## 3. Lluvia IMERG y avisos: propuesta, sin tocar el motor
**Estado actual:**
- Las zonas de vigilancia de Tumbes y Piura son `ADMINISTRATIVE_CONTEXT_NO_BASIN`: no tienen cuenca. En Tumbes solo existe la zona Bocapán, que es la UH ANA 13936.
- El muestreador IMERG (`probe_imerg_early_live.polygon_mean`) ya calcula la media ponderada por área de las celdas de 0,1° que tocan un polígono. Admite una UH ANA sin cambios.
- El cruce con avisos (`BASIN_INTERSECTS_LISTED_PROVINCE`) también admite cualquier polígono.

**¿Puede IMERG (0,1°) distinguir cada UH?**

| UH | km² | Celdas que la tocan | Celdas enteras dentro | Lectura |
|---|---|---|---|---|
| Cuenca Piura (1378) | 10 872 | 113 | 67 | resoluble |
| Cuenca Chira (138) | 10 535 | 115 | 59 | resoluble (sin la parte de Ecuador) |
| Intercuenca 13779 | 4 708 | 56 | 21 | resoluble |
| Cuenca Cascajal (13778) | 3 942 | 50 | 16 | resoluble |
| Cuenca Tumbes (1394) | 1 806 | 29 | 6 | marginal (sin la parte de Ecuador) |
| Cuenca Olmos (137774) | 1 069 | 22 | 0 | resolución insuficiente |
| Intercuenca 1379 | 913 | 18 | 1 | resolución insuficiente |
| Intercuenca 13935 | 448 | 9 | 0 | resolución insuficiente |
| Cuenca Zarumilla (13952) | 373 | 8 | 0 | resolución insuficiente (sin la parte de Ecuador) |
| Intercuenca 13951 | 340 | 6 | 0 | resolución insuficiente |
| Intercuenca 13939 | 188 | 6 | 0 | resolución insuficiente |

**Propuesta: tabla de investigación `uh_rain_context`.** Es un archivo aparte que ni el motor ni la priorización leen. Tiene una fila por UH y ventana, con cuatro bloques que nunca se mezclan:
1. **Observación:** media IMERG Early de la UH en 24 y 72 h, con su completitud (medias horas presentes / esperadas). Una ventana incompleta queda `INCOMPLETA`; nunca se convierte en 0 mm.
2. **Inferencia territorial:** los centros poblados ANA 2016-17 que contiene la UH, con el aviso «relación territorial, no hidráulica» y el indicador `near_boundary`.
3. **Contexto oficial:** los avisos SENAMHI/INDECI vigentes cuya provincia listada interseca la UH, con el método `BASIN_INTERSECTS_LISTED_PROVINCE` y el nivel oficial sin transformar.
4. **Desconocido:** cabecera fuera del Perú (`CABECERA_FUERA_DE_PERU_NO_INCLUIDA`), resolución insuficiente (`RESOLUCION_IMERG_INSUFICIENTE` si ninguna celda cae entera dentro), cauce no identificado y fuente lineal no disponible.

**Qué falta para pasar del mapa documental a una priorización experimental:**
- **Geometría de cauce:** solo es necesaria para hablar de quebradas y no de cuencas, y hoy está bloqueada.
- **Serie de lluvia por UH:** requiere leer los gránulos IMERG con el token de Earthdata en un workflow de investigación separado de las capturas.
- **Una línea base:** percentiles por UH a partir del histórico IMERG Final, sin umbrales de decisión.
- **Revisión del propietario** de la regla de combinación. Solo entonces podría tocarse el motor; hoy está bloqueado (`decision_thresholds=null`).
