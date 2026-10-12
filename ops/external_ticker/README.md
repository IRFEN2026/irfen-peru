# IRFEN v0.9 · Disparador externo del respaldo (TEST_ONLY)

## Problema medido

`v09-senamhi-avisos-capture.yml` está programado cada 30 min en `main`. Entre el 10-10 y el 12-10-2026 GitHub
Actions lanzó **15 ejecuciones correctas en 72 h (144 nominales)**: hueco mediano 4,1 h, P90 7,4 h, máximo 9,1 h
(`scripts/v09_continuity_report.py`). El planificador `schedule` de GitHub no garantiza puntualidad y en este
repositorio no sirve para vigilancia. En cambio, las ejecuciones `workflow_dispatch` arrancan en segundos
(la del 12-10 14:56:21 UTC ya había guardado su resultado a las 14:56:49).

## Propuesta

Un **reloj externo** fuera de GitHub Actions que cada 10 min pide a GitHub ejecutar **un único workflow**:
`.github/workflows/v08-scheduler-fallback.yml` en `main` (respaldo por workflow, PR #372). Toda la lógica sigue en
el repositorio, versionada y probada:

| Comprobación | Dónde |
|---|---|
| No lanzar el respaldo si ya está en cola o en curso | `worker.js` / `tick.sh` (y `concurrency` del respaldo) |
| Por cada workflow: existe en `main`, no hay ejecución en curso/cola, última ejecución más antigua que su enfriamiento | `scripts/scheduler_fallback.py` (#372) |
| Enfriamientos: captura de avisos y lluvia v0.9 60 min; colectores v0.8 sin cambios | `TARGETS` en #372 |
| Guardas científicas comprobadas antes de despachar | paso «Verificar guardas» del respaldo |

El reloj **no** contiene ciencia, no cambia datos, ramas ni guardas, y solo tiene permiso para lanzar workflows.

### Opción A (recomendada): Cloudflare Workers Cron Trigger

`worker.js` + `wrangler.toml` (cron `*/10 * * * *`, `ENABLED="false"` = ensayo que solo registra).

1. Token *fine-grained* del propietario: solo este repositorio, permiso **Actions: Read and write**, con caducidad.
2. `wrangler secret put GITHUB_TOKEN` y `wrangler deploy` desde `ops/external_ticker/`.
3. Ensayo 24 h con `ENABLED="false"`: revisar los registros del Worker.
4. Tras integrar #372 en `main`, `ENABLED="true"` y `wrangler deploy`.

Condiciones de la cuenta y límites del plan: a comprobar por el propietario antes de usarlo.

### Opción B: cualquier cron externo

`tick.sh` (curl) en un servidor propio o un programador en la nube:
`*/10 * * * * GITHUB_TOKEN=… ENABLED=true /ruta/tick.sh >> /var/log/irfen-ticker.log 2>&1`.
Depende de la disponibilidad de esa máquina.

### Lo que no resuelve

* Si GitHub Actions está caído o degradado, nada se ejecuta: el panel lo muestra (fuente DESACTUALIZADA a los
  180 min, IMERG > 12 h y GOES-19 > 90 min cuentan como ausentes, GEOS-CF > 48 h sin sumas).
* No hay intervalo garantizado. Lo esperable con reloj de 10 min y enfriamiento de 60 min es un hueco máximo del
  orden de 70 min más la cola de Actions, **pendiente de verificar** con `scripts/v09_continuity_report.py`
  durante 48 h tras activarlo. No se debe comunicar ninguna cadencia antes de esa medición.

## Verificación

```
GH_TOKEN=… python scripts/v09_continuity_report.py --hours 48
```

Informe de solo lectura por workflow: ejecuciones correctas y por origen, hueco máximo, mediana, P90 y hueco
abierto (la antigüedad de la última ejecución correcta cuenta como hueco).
