# IRFEN v0.9 — Automatización aislada del motor de pronóstico (TEST_ONLY)

Revisión independiente: veredicto **APTO para fusionar el disparador**, sin hallazgos bloqueantes ni altos. Los tres
hallazgos de severidad media y los menores se corrigieron en `v09/forecast-engine`, salvo la protección de ramas
(MEDIA-3), que es un ajuste de configuración del repositorio y queda para quien lo administra.

## Arquitectura

| Pieza | Dónde vive | Qué hace | Permisos del token |
| --- | --- | --- | --- |
| `v09-forecast-trigger.yml` | `main` (único archivo a fusionar) | A las 08:40 y 20:40 UTC pide a GitHub ejecutar el motor en su rama; si ya hay una ejecución en espera omite el ciclo y lo avisa. No hace checkout ni ejecuta código del repositorio | `actions: write`; nada más |
| `v09-forecast-engine.yml`, job `compute` | Rama `v09/forecast-engine` | Recolecta IMERG Late, corre ECMWF ENS y el modelo propio, evalúa; entrega un artefacto | `contents: read`; checkouts sin credenciales guardadas |
| `v09-forecast-engine.yml`, job `persist` | Rama `v09/forecast-engine` | Solo git: aplica el artefacto sobre `v09/forecast-data` y empuja | `contents: write` |
| `v09-own-model-train.yml` (`compute` + `persist`) | Rama `v09/forecast-engine` | A pedido: insumos históricos y entrenamiento del modelo propio | Igual que el motor |
| Resultados | Rama huérfana `v09/forecast-data` | Registros, observaciones IMERG, evaluación, modelo | La escriben el motor y el entrenamiento, ambos solo desde su job `persist` |

Interruptor sin commit: el disparador corre solo si la variable de repositorio `IRFEN_FORECAST_ENGINE_ENABLED` vale
exactamente `true` (Settings → Secrets and variables → Actions → Variables). Mientras no exista, el disparador es inerte.

El motor ya no se dispara por `push` (corrección MEDIA-1): solo por el disparador o por `workflow_dispatch`
manual. Lo verificó la autoprueba del 14-10-2026: `GITHUB_TOKEN` con solo `actions: write` lanzó
`v09-forecast-engine.yml` en su rama (ejecución 38634172181, actor `github-actions[bot]`), aunque el archivo no exista
en `main`.

## Barreras de aislamiento

1. Ambos jobs se niegan a correr si la ref no es `refs/heads/v09/forecast-engine`.
2. `compute` (Python y paquetes de PyPI) solo puede leer el repositorio: `contents: read` y `persist-credentials:
   false` en los dos checkouts. Lo que produce sale como artefacto.
3. `persist` no ejecuta Python ni paquetes externos, solo git y rsync. Sus acciones están fijadas por SHA de commit
   (`checkout`, `download-artifact`; también `upload-artifact` en `compute`).
4. Antes de guardar, `persist`:
   - comprueba que la base del cálculo pertenece a `v09/forecast-data` (`merge-base --is-ancestor`);
   - rechaza enlaces simbólicos, archivos especiales y rutas fuera de `data/v09/{forecast,obs_imerg,model}/`;
   - **solo agregar**: rechaza cualquier borrado salvo `data/v09/obs_imerg/partial/`, y exige que cada registro
     `*.jsonl` de la base sea prefijo exacto del nuevo. Un script fallido o un paquete comprometido no puede
     truncar ni reescribir historia.
   - rechaza reescribir un día IMERG ya cerrado (`data/v09/obs_imerg/fields/`): el recolector nunca lo reprocesa.
5. El empuje va a `refs/heads/v09/forecast-data` explícitamente, con rebase acotado; ante conflicto aborta sin
   sobrescribir. Nunca usa `--force`.
6. Grupos de concurrencia propios (`v09-forecast-trigger`, `v09-forecast-engine`, `v09-forecast-data-write`); ninguno
   coincide con los de IRFEN (`pages`, `geos-forecast-v08`, `v09-rain-north-*`, …).
7. No usa `upload-pages-artifact`, no toca `site/` ni `main`; toda salida y cada línea de los registros llevan
   `RESEARCH_ONLY` / `TEST_ONLY` y `operational_alerting_enabled: false`.

### Límite conocido: protección de ramas (MEDIA-3, pendiente de configuración)

Las ramas del repositorio no tienen protección ni reglas. El token de `persist` podría técnicamente escribir en
cualquier rama; solo el código (`HEAD:refs/heads/v09/forecast-data` con rama fija) lo impide. Además, el disparador
ejecuta lo que esté en la punta de `v09/forecast-engine` en ese momento, con `EARTHDATA_TOKEN`. No es una escalada
respecto de quien ya puede empujar a `main`, y `GITHUB_TOKEN` no puede modificar workflows. Recomendación para el
administrador: un *ruleset* sobre `v09/forecast-engine` y `v09/forecast-data` que bloquee force-push y borrado, y que
restrinja quién empuja a `v09/forecast-engine`. Exigir PR en `main` no es viable porque los recolectores de IRFEN
empujan ahí con `GITHUB_TOKEN`.

### Concurrencia

GitHub mantiene una sola ejecución en espera por grupo y la reemplaza con la siguiente, aunque
`cancel-in-progress` sea `false`. Por eso:
- el disparador consulta primero si hay un entrenamiento o un motor en espera y, si lo hay, omite el ciclo con un
  aviso `V09_FORECAST_TRIGGER` en vez de reemplazarlo;
- el entrenamiento debe lanzarse lejos de las 08:40 y 20:40 UTC.
- si la consulta previa del disparador falla, despacha igual con aviso: perder un ciclo es peor que reemplazar una
  espera.

Los artefactos se suben con `overwrite: true`, así que «re-ejecutar todos los jobs» o solo `persist` funciona en la
misma ejecución.

## Qué se fusionaría en `main`

Exactamente un archivo nuevo: `.github/workflows/v09-forecast-trigger.yml`. No cambia ningún archivo existente, no
agrega pruebas a la colección de pytest y ningún workflow de `main` se dispara por su ruta.

## Qué escribe (solo en `v09/forecast-data`)

| Archivo | Crecimiento |
| --- | --- |
| `data/v09/forecast/ecmwf_ens_provinces_north_v0_1.json` | Se reescribe (última corrida) |
| `data/v09/forecast/ecmwf_ens_provinces_ledger_v0_1.jsonl` | +1 línea por corrida (~13 kB); ~4 MB por temporada |
| `data/v09/forecast/modelo_propio_ledger_v0_1.jsonl` | Igual, cuando el modelo propio esté entrenado |
| `data/v09/forecast/evaluacion_v0_1.json`, `evaluacion_resumen.md` | Se reescriben |
| `data/v09/obs_imerg/fields/AAAA-MM-DD.npz` | 1 por día pluviométrico completo (~10 kB) |
| `data/v09/obs_imerg/partial/AAAA-MM-DD.npz` | Temporal, hasta completar las 48 medias horas |
| `data/v09/obs_imerg/imerg_late_provincias_v0_1.csv`, `imerg_late_status_v0_1.json` | Se reescriben |
| `data/v09/model/inputs/*.csv.gz` | Insumos resumidos por provincia y día (pocos MB) |
| `data/v09/model/modelo_propio_v0_1.json`, `modelo_propio_validacion_v0_1.json`, `insumos_estado_v0_1.json` | Se reescriben al entrenar |

## Recursos compartidos con IRFEN

- `EARTHDATA_TOKEN`: la misma cuenta de NASA Earthdata que usan en `main` `v09-rain-north.yml`, `history.yml`,
  `imerg-early-probe.yml` y `update-and-deploy.yml`; no hay presupuesto separado. El motor descarga IMERG Late
  (`GPM_3IMERGHHL`), otro producto que IMERG Early. En operación normal pide como máximo 288 gránulos por ciclo
  (6 días × 48), dos veces al día, y en la práctica solo los que faltan. Un reproceso de 10 días puede pedir hasta 672.
- Minutos de Actions: el repositorio es público.
- Ningún archivo, rama ni grupo de concurrencia en común con los workflows existentes.

## Reversión (en este orden)

| Paso | Cómo | Efecto |
| --- | --- | --- |
| 1. Pausar sin tocar código | Poner `IRFEN_FORECAST_ENGINE_ENABLED` en `false` o borrarla | El disparador queda inerte desde la siguiente hora programada |
| 2. Quitar la automatización de `main` | `git revert <commit que agregó el disparador>` o borrar `.github/workflows/v09-forecast-trigger.yml` | `main` vuelve exactamente a su estado previo |
| 3. Detener el motor y el entrenamiento | `gh workflow disable v09-forecast-engine.yml` y `gh workflow disable v09-own-model-train.yml` | Ninguna ejecución, tampoco manual. Hacerlo después del paso 1: con el disparador activo y el motor desactivado, `gh workflow run` fallaría con 422 cada 12 h |
| 4. Borrar todo rastro | Borrar las ramas `v09/forecast-engine` y `v09/forecast-data` | Sin efecto sobre `main` ni sobre otros workflows |

Quedan, y caducan solos: artefactos de resultados (7 días), caché de pip de la rama, registros de ejecuciones
(90 días) y los workflows en la lista de Actions (se pueden borrar sus ejecuciones).
