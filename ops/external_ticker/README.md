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

### 1 · Token (propietario, una vez)
1. GitHub → Settings → Developer settings → *Fine-grained tokens* → *Generate new token*.
   Resource owner `IRFEN2026`; *Only select repositories* → `irfen-peru`; permisos de repositorio: **Actions: Read
   and write** (Metadata: read lo añade GitHub). Ningún otro permiso. Caducidad: 30 días (el piloto).
2. El token solo se guarda como secreto cifrado del Worker (paso 2). Nunca en `wrangler.toml`, en el repositorio,
   en una incidencia, en un chat ni en registros; `worker.js` no lo imprime.
3. Cuenta de Cloudflare con 2FA y sin otros miembros con acceso al Worker.
4. Revocación inmediata si hay duda: GitHub → Fine-grained tokens → *Revoke*; el Worker deja de poder actuar.

### 2 · Ensayo de 24 h con `ENABLED="false"` (sin despachos reales)
Verificado antes del ensayo: la lógica del Worker contra la API real de GitHub, en modo ensayo, hace 5 lecturas
(`GET …/runs`) y devuelve `DRY_RUN`, sin ningún `POST` (13-10-2026 00:58 UTC).
```
cd ops/external_ticker
npx wrangler@4 login
npx wrangler@4 secret put GITHUB_TOKEN        # pegar el token cuando lo pida
grep 'ENABLED = "false"' wrangler.toml        # debe aparecer: ensayo sin despachos
npx wrangler@4 deploy
npx wrangler@4 tail                           # o Workers → irfen-v09-external-ticker → Logs
```
Lista de comprobación a las 24 h:
- [ ] unas 144 líneas `{"at":…,"dispatched":false,"reason":"DRY_RUN: …"}` (o `FALLBACK_ACTIVE`), una cada 10 min;
- [ ] ninguna `LIST_FAILED` (token, permisos o red);
- [ ] en Actions, ninguna ejecución del respaldo lanzada por el Worker (`workflow_dispatch` del token);
- [ ] el token sigue limitado a `irfen-peru` y Actions R/W, con caducidad.
Si algo falla, no activar.

### 3 · Activación (solo con autorización del propietario)
Cambiar `ENABLED = "true"` en `wrangler.toml` (cambio revisado en esta rama) y `npx wrangler@4 deploy`. Anotar la
hora de activación: es el inicio de la ventana de 48 h. Marcha atrás: `ENABLED = "false"` + `deploy`, o
`npx wrangler@4 delete`, y revocar el token.

### 4 · Evaluación de 48 h tras activar
```
GH_TOKEN=<token de solo lectura> python scripts/v09_continuity_report.py --hours 48 --json continuity_48h.json
```
**Criterio fijado por el propietario el 13-10-2026, antes del ensayo activo** (codificado en `CRITERION`), para
`v09-senamhi-avisos-capture.yml` y `v09-rain-north.yml`:

| Condición | Umbral |
|---|---|
| Intervalos entre ejecuciones correctas dentro de 90 min | ≥ 95 % |
| Hueco máximo (incluido el abierto y el inicial) | ≤ 120 min |
| Duplicados (dos ejecuciones creadas a < 10 min o con ejecución solapada) | 0 |
| Visibilidad de datos desactualizados | prueba de navegador en CI + revisión del panel durante el ensayo |

El informe da `PASA` / `NO_PASA` por workflow. Línea base sin disparador (72 h hasta el 13-10 00:59 UTC): captura
de avisos **NO_PASA** (6,2 % de intervalos ≤ 90 min, hueco máximo 9,1 h, 0 duplicados). No se comunica ninguna
cadencia hasta tener la evaluación de 48 h.

## Alternativa no elegida: cualquier cron externo

`tick.sh` (curl) en un servidor propio o un programador en la nube:
`*/10 * * * * GITHUB_TOKEN=… ENABLED=true /ruta/tick.sh >> /var/log/irfen-ticker.log 2>&1`.
Depende de la disponibilidad de esa máquina.

## Lo que no resuelve

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
