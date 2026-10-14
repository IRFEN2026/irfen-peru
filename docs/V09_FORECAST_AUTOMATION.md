# IRFEN v0.9 — Automatización aislada del motor de pronóstico (TEST_ONLY)

## Arquitectura

| Pieza | Dónde vive | Qué hace | Permisos |
| --- | --- | --- | --- |
| `v09-forecast-trigger.yml` | `main` (único archivo a fusionar) | A las 08:40 y 20:40 UTC pide a GitHub ejecutar el motor en su rama. No descarga código ni datos | `actions: write`; nada más |
| `v09-forecast-engine.yml` + scripts | Rama `v09/forecast-engine` | Recolecta IMERG Late, corre ECMWF ENS y el modelo propio, evalúa | `contents: write`, usado solo para empujar a la rama de datos |
| `v09-own-model-train.yml` | Rama `v09/forecast-engine` | A pedido: descarga insumos históricos y entrena el modelo propio | Igual que el motor; comparte su grupo de concurrencia |
| Resultados | Rama huérfana `v09/forecast-data` | Registros de pronóstico, observaciones IMERG, evaluación | Escrita solo por el motor |

Interruptor sin commit: el disparador corre solo si la variable de repositorio `IRFEN_FORECAST_ENGINE_ENABLED` vale
exactamente `true` (Settings → Secrets and variables → Actions → Variables).

## Barreras de aislamiento del motor

1. El job se niega a correr si la ref no es `refs/heads/v09/forecast-engine`.
2. El código se descarga con `persist-credentials: false`: desde esa copia no se puede empujar.
3. La única copia con credenciales es `./_data`, que es la rama `v09/forecast-data`.
4. Antes de guardar, un paso falla si cambió algo fuera de `data/v09/forecast/`, `data/v09/obs_imerg/` y
   `data/v09/model/`, o si `_data`
   no está en la rama de datos.
5. El empuje va a `refs/heads/v09/forecast-data` explícitamente, con rebase acotado y sin `--force`.
6. Grupo de concurrencia propio (`v09-forecast-engine`, compartido solo por el motor y el entrenamiento): no espera
   ni bloquea a los workflows de IRFEN.
7. No usa `upload-pages-artifact`, no toca `site/`, no escribe en `main` y todas las salidas llevan
   `RESEARCH_ONLY` / `TEST_ONLY` y `operational_alerting_enabled: false`.

## Qué escribe (solo en `v09/forecast-data`)

| Archivo | Crecimiento |
| --- | --- |
| `data/v09/forecast/ecmwf_ens_provinces_north_v0_1.json` | Se reescribe (última corrida) |
| `data/v09/forecast/ecmwf_ens_provinces_ledger_v0_1.jsonl` | +1 línea por corrida (~13 kB); ~4 MB por temporada |
| `data/v09/forecast/modelo_propio_ledger_v0_1.jsonl` | Igual, cuando el modelo propio esté activo |
| `data/v09/forecast/evaluacion_v0_1.json`, `evaluacion_resumen.md` | Se reescriben |
| `data/v09/obs_imerg/fields/AAAA-MM-DD.npz` | 1 por día pluviométrico completo (~10 kB) |
| `data/v09/obs_imerg/partial/AAAA-MM-DD.npz` | Temporal hasta completar las 48 medias horas |
| `data/v09/obs_imerg/imerg_late_provincias_v0_1.csv`, `imerg_late_status_v0_1.json` | Se reescriben |
| `data/v09/model/inputs/*.csv.gz` | Insumos resumidos por provincia y día (pocos MB) |
| `data/v09/model/modelo_propio_v0_1.json`, `modelo_propio_validacion_v0_1.json`, `insumos_estado_v0_1.json` | Se reescriben al entrenar |

## Recursos compartidos con IRFEN

- `EARTHDATA_TOKEN`: el motor descarga como máximo 150 gránulos IMERG Late por corrida, dos veces al día. El archivo
  IMERG Early de IRFEN usa otro producto y su propio presupuesto (hasta 60 gránulos cada 30 min).
- Minutos de Actions: repositorio público.
- Ningún archivo, rama ni grupo de concurrencia en común con los workflows existentes.

## Reversión

| Qué revertir | Cómo | Efecto |
| --- | --- | --- |
| Pausar sin tocar código | Poner `IRFEN_FORECAST_ENGINE_ENABLED` en `false` (o borrarla) | El disparador queda inerte en la siguiente hora programada |
| Quitar la automatización de `main` | `git revert <commit que agregó el disparador>` o borrar `.github/workflows/v09-forecast-trigger.yml` | `main` vuelve exactamente a su estado previo |
| Detener el motor | `gh workflow disable v09-forecast-engine.yml` | Ninguna ejecución, ni manual |
| Borrar todo rastro | Borrar las ramas `v09/forecast-engine` y `v09/forecast-data` | Sin efecto sobre `main` ni sobre otros workflows |
