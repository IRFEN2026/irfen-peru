# Informe · Repositorio Institucional SENAMHI, hdl:20.500.12542/3635

**Estado:** RESEARCH_ONLY / TEST_ONLY. **Rama:** `research/senamhi-repositorio-3635-20261027`, apilada sobre #422 y sin merge. **Fecha:** 27-oct-2026.

> **Resultado:** el handle es oficial y está activo, pero **el repositorio no es accesible**. Desde GitHub agota el tiempo de conexión. La herramienta de lectura recibe `robots_disallowed` y el servidor de esta sesión no tiene salida a ese dominio. **No se obtuvo el CSV**, así que no hay fechas, unidades, horarios ni registros de Tongorrape, Tinajones, Chulucanas o Lancones. No se descargó IMERG. Se deja un presupuesto acotado y una regla de selección de fechas fijada de antemano, para cuando exista el CSV.

## 1. Consulta única (run [40540249464](https://github.com/IRFEN2026/irfen-peru/actions/runs/40540249464))

| Solicitud | Resultado |
|---|---|
| API del handle `hdl.handle.net/api/handles/20.500.12542/3635` | **HTTP 200**: `URL = http://repositorio.senamhi.gob.pe/handle/20.500.12542/3635` (`handle_api.json`) |
| `hdl.handle.net/20.500.12542/3635`, sin seguir la redirección | **HTTP 302** a la misma URL del repositorio |
| Página de metadatos completos del ítem (`?show=full`) | `ConnectTimeout` (15 s) |
| API REST de DSpace del ítem | `ConnectTimeout` |
| Archivo CSV de 2024 ya catalogado (`/bitstream/20.500.12542/3635/3/…_2024.csv`) | `ConnectTimeout` |

* Es el mismo síntoma que en las sondas del 19-sep (HTTP y HTTPS) y que en todos los dominios `*.senamhi.gob.pe` consultados desde GitHub. Desde esta sesión, el proxy rechaza el dominio (403) y la herramienta de lectura indica `robots_disallowed`.
* **No se volvió a consultar datosabiertos.gob.pe** y no se intentó ninguna vía alternativa.
* **Procedencia e integridad:** no verificables, porque no hay archivo. El nombre del archivo que figura en el repositorio (`…intercambio-internacional_2024.csv`) proviene del catálogo del 19-sep, no de una lectura actual.

## 2. Inventario (de #422, sin cambios)

| Estación | WIGOS (OSCAR) | Lat / Lon | Celda IMERG (i, j) y centro | Distancia al borde | Estado en OSCAR |
|---|---|---|---|---|---|
| Lancones | 0-604-1-07610101 | −4,642897 / −80,547161 | (994, 853) · −80,55 / −4,65 | 0,043° | Operativa |
| Chulucanas | 0-604-1-08602104 | −5,108444 / −80,169539 | (998, 848) · −80,15 / −5,15 | **0,008°** (≈ 0,9 km): informar también la celda vecina | Operativa |
| Tongorrape | 0-604-1-09582002 | −6,06692 / −79,68203 | (1003, 839) · −79,65 / −6,05 | 0,018° | Operativa |
| Tinajones | 0-604-1-10575101 | −6,654889 / −79,427919 | (1005, 833) · −79,45 / −6,65 | 0,028° | Sin reportar (26-oct-2026) |

**Identidad.** Que una estación del CSV sea la misma de OSCAR **no se presupone**. Al tener el CSV, se aceptará solo si coinciden el nombre **y** las coordenadas dentro de la precisión declarada. Si además trae altitud o código, también se contrastarán. Cualquier diferencia mantiene la estación fuera.

## 3. Bloqueos reales

1. **El CSV y sus metadatos**, porque el repositorio y el portal no son accesibles desde la infraestructura disponible. Vía práctica: que el responsable lo descargue en un navegador desde Perú, o pida el archivo a SENAMHI (`jrodriguez@senamhi.gob.pe`, contacto del conjunto de datos), y lo adjunte. Se verificarían el SHA-256, los metadatos y las fechas.
2. **La zona horaria de la columna de hora y el periodo de acumulación** de la precipitación. Se fijarán con el diccionario de datos. Sin confirmarlos, ninguna ventana es `EXACT` y no hay pares de métricas.
3. **La autorización de IMERG**, que queda pendiente. No se descargó nada.

## 4. Presupuesto de descarga acotado (propuesta, sin autorizar)

El detalle está en `historical/imerg_download_budget_proposal_20261027.json`.

* **Bloque espacial único:** i 993–1006, j 832–854, es decir 322 celdas (lon −80,7…−79,3; lat −6,8…−4,5). Incluye la vecindad 3×3 de las cuatro estaciones.
* **Regla de fechas, fijada antes de ver IMERG:**
  1. Elegir el mes calendario más lluvioso según la suma de los cuatro pluviómetros, solo entre meses con al menos 90 % de horas válidas en al menos tres estaciones.
  2. Usar **todos** los días del mes, húmedos y secos.
  3. Ventanas 12–12 UTC, que equivalen a 07–07 hora Perú.
  4. Un día entra solo con 24 de 24 horas válidas en la estación.
* **Producto:** IMERG Late V07 medio-horario (`GPM_3IMERGHHL`), con nombre y subversión verificados en CMR antes de descargar. IMERG Final no se usa, porque está ajustado con GPCC y la prueba no sería independiente.

| Opción | Días | Gránulos | Transferencia estimada | Runner | Pares máximos | Alcance esperado |
|---|---|---|---|---|---|---|
| A, mínima | 10 | 480 | ≈ 3,4 GB | ≈ 15 min | 40 | Solo descriptiva; calibración bloqueada |
| **B, recomendada (un mes)** | 31 | 1.488 | ≈ 10,4 GB | ≈ 45 min | 124 | Métricas evaluables si hay ≥ 30 pares y ≥ 10 días. Calibración, como mucho local (una sola temporada) |
| C, diaria UTC | 31 | 31 (`GPM_3IMERGDL`) | ≈ 0,3–0,6 GB (a confirmar) | Minutos | 124 | Ventanas 00–24 UTC, que no coinciden con el día 07–07. Requiere una extensión menor del analizador |

* **Tamaño por gránulo:** se estimó con el medido en CMR para IMERG Early V07C (≈ 7,0 MB).
* **Almacenamiento:** solo el bloque de celdas, de 1 a 3 MB de JSON. Los HDF5 se borran tras la extracción, como en la recuperación anterior, y ahora con la decodificación de hora corregida.
