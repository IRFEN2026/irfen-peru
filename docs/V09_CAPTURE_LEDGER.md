# Registro de intervalos esperados IMERG / GOES-19 (v0.1, RESEARCH_ONLY / TEST_ONLY)

`scripts/v09_capture_ledger.py` dice, para cada intervalo esperado, si IRFEN lo capturó y qué responde el catálogo de la fuente:
- IMERG Early `GPM_3IMERGHHE` v07: 30 min.
- GOES-19 `ABI-L2-RRQPEF`: escaneos de 10 min.

Solo usa **metadatos de catálogo**:
- la búsqueda de gránulos de NASA CMR;
- `ListObjectsV2` del bucket público NOAA `noaa-goes19`.

Una lista de URL permitidas rechaza cualquier otra petición, así que nunca se descarga un gránulo o escaneo. Tampoco se lee ni se escribe ningún valor de precipitación.

## Ejecución (solo manual)
- **Workflow:** `.github/workflows/v09-capture-ledger-manual.yml`. Solo `workflow_dispatch`, `contents: read`, `ubuntu-24.04`. Entrega el resultado como artefacto y resumen del job, sin escribir en el repositorio.
- **Local:** `python scripts/v09_capture_ledger.py run --from 2026-10-13T00:00:00Z --to 2026-10-20T00:00:00Z --out /tmp/ledger`.
  - `fetch` guarda cada respuesta en bruto como `raw/<sha256>.bin` y `requests.json` (URL, hora, estado HTTP, intentos, error).
  - `build` deriva el registro de forma determinista a partir de esas respuestas y del historial git de los archivos de IRFEN.
- **Límites** (`config/v09_capture_ledger_contract_v0_1.json`):
  - ventana de 192 h como máximo y nunca en el futuro;
  - tiempo de espera de 30 s, 2 intentos y 3 s de espera entre ellos (sin reintento para 4xx salvo 429);
  - 5 páginas CMR como máximo y 20 MB por respuesta.
- **Salidas:** solo en `data/v09/capture_ledger/` o fuera del repositorio. Un directorio de respuestas existente no se reescribe, y un registro existente solo se acepta si es idéntico.

## Estados
| Estado | Cuándo |
|---|---|
| `CAPTURED` | Un archivo de IRFEN contiene el gránulo o escaneo. Evidencia: ruta, primer commit que lo contiene y nombre o clave |
| `MISSING_RETRYING` | No capturado, pero el catálogo lo lista: existe en origen. En v0.1 **no hay reintento activo** (`retry_active=false`) |
| `PENDING_SOURCE_LATENCY` | No capturado ni listado por un catálogo completo, y aún dentro del horizonte de latencia (IMERG 24 h, GOES 2 h, derivados de las latencias medidas; ver el contrato) |
| `ABSENT_AT_SOURCE` | El catálogo respondió HTTP 200, completo, no vacío y con entradas válidas, lista intervalos anteriores y posteriores pero no éste, y ya pasó el horizonte. Ausencia **en la fecha de la consulta** |
| `UNRECOVERABLE` | Fuera de una retención de la fuente **verificada**. Hoy ambas retenciones son `NOT_VERIFIED`, así que este estado no se asigna nunca |
| `UNKNOWN` | Todo lo demás |

`UNKNOWN` incluye un error HTTP, un tiempo agotado, una respuesta vacía, malformada o truncada, un `CMR-Hits` que no cuadra, un `KeyCount` incoherente, un cambio de modo de escaneo (distinto de M6), bytes almacenados que no coinciden con su SHA-256, y un intervalo sin intervalos listados a ambos lados.

Una respuesta vacía o un error **nunca** se convierten en ausencia confirmada. Ningún estado equivale a «sin lluvia» (`missing_data_rule=UNKNOWN_NOT_LOW_RISK`).

## Cada intervalo registra
- `product`, `product_name`, `product_version` (p. ej. `V07C`, o `M6/G19`);
- `interval_start_utc`, `interval_end_utc`, `state`, `reason`;
- `captured[]` (archivo, commit, hora de captura);
- `catalog` (hora de consulta, identificadores de petición, si la respuesta es completa, entradas listadas con id, título o clave, `updated`, `last_modified` y `etag`).

La procedencia se verifica así: cada `request_id` remite a `requests[]`, con la URL y el SHA-256 de la respuesta guardada en `raw/`.

## Instantánea de QA
`data/v09/capture_ledger/snapshots/20261013T0000Z_20261020T0000Z/` es una ejecución única de solo catálogo en `ubuntu-24.04`, confirmada por github-actions[bot]. `tests/test_v09_capture_ledger_snapshot.py` comprueba:
- los hashes de las respuestas guardadas;
- que solo hay URL de catálogo y ninguna descarga;
- que la clasificación se reproduce byte a byte a partir de las respuestas guardadas;
- con historial git disponible, que cada evidencia `CAPTURED` existe en su commit.

## Limitaciones conocidas
- **«Ausente en origen» es relativo a la consulta.** NASA puede publicar o reprocesar más tarde, y el registro no afirma permanencia.
- **La cuadrícula GOES de 10 min solo vale para el modo M6.** Una hora con otro modo queda `UNKNOWN`.
- **No se ha verificado la retención de ninguna fuente:** `UNRECOVERABLE` queda desactivado hasta documentarla.
- **Los GOES `MISSING_RETRYING` son, en su mayoría, consecuencia del diseño:** IRFEN muestrea un escaneo por ejecución. Que un escaneo sea recuperable no implica que deba recuperarse sin una decisión científica sobre el muestreo.
- **Las ventanas más recientes que los horizontes de latencia** quedan en `PENDING_SOURCE_LATENCY` o en `UNKNOWN`.

Diseño de recuperación (no activado): `docs/V09_CAPTURE_RECOVERY_DESIGN.md`.
