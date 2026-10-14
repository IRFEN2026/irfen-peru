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

### Opción A (elegida para el piloto): Cloudflare Workers Cron Trigger

`worker.js` + `wrangler.toml` (cron `*/10 * * * *`, `ENABLED="false"` = ensayo: consulta, decide y registra, pero
no despacha). #372 ya está en `main`; el disparador **no se activa** hasta que el propietario lo decida tras el ensayo.

## Instrucciones mínimas

Guía paso a paso para el propietario: [`GUIA_PROPIETARIO.md`](GUIA_PROPIETARIO.md).

### 0 · Requisitos previos (comprobados por Claude el 13-10-2026)
- [x] Ñácara (`senamhi-nacara-probe.yml`) deshabilitado en Actions (`disabled_manually`).
- [x] **PR #375 integrado en `main` (7e678dfd, 14-10-2026).** Era obligatorio: el respaldo actual de `main` intentaría lanzar Ñácara
      (ya deshabilitado) y ese intento hace fallar el barrido. #375 excluye además los workflows que consultan SENAMHI
      directamente y la publicación en Pages, salta los workflows deshabilitados y anota cada disparo.
- [x] Alcance del respaldo tras #375: solo colectores con `contents: write` sobre `main` y el secreto
      `EARTHDATA_TOKEN` (IMERG). Ninguno publica Pages ni consulta SENAMHI (pruebas en CI).
- [ ] El propietario comprueba en *Settings → Secrets and variables → Actions* que solo existen los secretos
      esperados (`EARTHDATA_TOKEN`); el proxy de Claude no permite listarlos.
- [x] El Worker solo hace `GET …/runs` y `POST …/dispatches` del respaldo; no registra el token ni datos.

### 1 · Token (propietario, una vez)
1. GitHub → Settings → Developer settings → *Fine-grained tokens* → *Generate new token*.
   Resource owner `IRFEN2026`; *Only select repositories* → `irfen-peru`; permisos de repositorio: **Actions: Read
   and write** (Metadata: read lo añade GitHub). Ningún otro permiso. Caducidad: 30 días (el piloto).
2. El token solo se guarda como secreto cifrado del Worker (paso 2). Nunca en `wrangler.toml`, en el repositorio,
   en una incidencia, en un chat ni en registros; `worker.js` no lo imprime.
3. Cuenta de Cloudflare con 2FA y sin otros miembros con acceso al Worker.
4. Revocación inmediata si hay duda: GitHub → Fine-grained tokens → *Revoke*; el Worker deja de poder actuar.

### 2 · Comprobación corta sin despachos (recomendada, 30 min)
Verificado antes: la lógica del Worker contra la API real, en modo ensayo, hace 5 lecturas y ningún `POST`.
```
cd ops/external_ticker
npx wrangler@4 login
npx wrangler@4 secret put GITHUB_TOKEN        # pegar el token cuando lo pida
npx wrangler@4 deploy                         # ENABLED="false" en wrangler.toml: solo registra
npx wrangler@4 tail                           # o Workers → irfen-v09-external-ticker → Logs
```
Deben aparecer 3 líneas `{"at":…,"dispatched":false,"reason":"DRY_RUN: …"}` en 30 min y ninguna `LIST_FAILED`.

### 3 · Ensayo activo de 24 h (autorizado por el propietario el 13-10-2026)
El archivo `wrangler.toml` del repositorio **sigue con `ENABLED="false"`**; el ensayo lo activa solo en el despliegue:
```
npx wrangler@4 deploy --var ENABLED:true      # anotar la hora UTC: inicio de la ventana de 24 h
```
Durante el ensayo: cada 10 min el Worker lanza el respaldo si no está en cola o en curso; el respaldo decide por
workflow (en `main`, activo, sin ejecución en curso o en cola, enfriamiento cumplido) y anota cada disparo
(`FALLBACK_DISPATCH`). Trazabilidad: registro del Worker → ejecución del respaldo (origen `workflow_dispatch`,
lanzada por IRFEN2026) → ejecuciones despachadas (anotaciones).

Parada (al terminar o ante cualquier anomalía): `npx wrangler@4 deploy` (vuelve a `ENABLED="false"`) o
`npx wrangler@4 delete`, y revocar el token si hay duda. La activación permanente requiere una autorización
expresa posterior a la revisión de resultados.

### 4 · Evaluación al terminar (24 h)
```
GH_TOKEN=<token de solo lectura> python scripts/v09_continuity_report.py --hours 24 --json continuity_24h.json
```
**Criterio fijado por el propietario el 13-10-2026** (codificado en `CRITERION`), para
`v09-senamhi-avisos-capture.yml` y `v09-rain-north.yml`:

| Condición | Umbral |
|---|---|
| Intervalos entre ejecuciones correctas (incluidos el inicial y el abierto) | ninguno > 90 min (100 % ≤ 90 min) |
| Duplicados indebidos (dos ejecuciones creadas a < 10 min o con ejecución solapada) | 0 |
| Visibilidad de datos desactualizados | prueba de navegador en CI + revisión del panel durante el ensayo |

El informe da, por workflow: frecuencia esperada, ejecuciones esperadas y reales, hueco máximo, duplicados,
porcentaje de intervalos ≤ 90 min y `PASA` / `NO_PASA` (los colectores v0.8 se muestran como informativos), más la
traza de cada disparo del respaldo. Cualquier incumplimiento se reporta tal cual.

Línea base sin disparador (24 h hasta el 13-10-2026 12:20 UTC): captura de avisos 5 ejecuciones correctas de 48
esperadas, hueco máximo 9,1 h, **NO_PASA**; lluvia 2 de 48, hueco máximo 12,7 h, **NO_PASA**.

## Alternativa no elegida: cualquier cron externo

`tick.sh` (curl) en un servidor propio o un programador en la nube:
`*/10 * * * * GITHUB_TOKEN=… ENABLED=true /ruta/tick.sh >> /var/log/irfen-ticker.log 2>&1`.
Depende de la disponibilidad de esa máquina.

## Lo que no resuelve

* Si GitHub Actions está caído o degradado, nada se ejecuta: el panel lo muestra (fuente DESACTUALIZADA a los
  180 min, IMERG > 12 h y GOES-19 > 90 min cuentan como ausentes, GEOS-CF fuera de su límite de frescura sin sumas).
* No hay intervalo garantizado. Lo esperable con reloj de 10 min y enfriamiento de 60 min es un hueco máximo del
  orden de 70 min más la cola de Actions, **pendiente de verificar** con `scripts/v09_continuity_report.py`
  durante 48 h tras activarlo. No se debe comunicar ninguna cadencia antes de esa medición.

## Verificación

```
GH_TOKEN=… python scripts/v09_continuity_report.py --hours 48
```

Informe de solo lectura por workflow: ejecuciones correctas y por origen, hueco máximo, mediana, P90 y hueco
abierto (la antigüedad de la última ejecución correcta cuenta como hueco).
