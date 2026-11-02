# IRFEN v0.9.1 · actualización automática del visor privado (RESEARCH_ONLY / TEST_ONLY)

Esta integración se apoya en el PR #469 (estado de fuentes) y el PR #466 (semáforo, revisión 0.2). **No es un sistema de alerta.**
- No fusiona en `main`.
- No publica una web.
- No envía notificaciones.
- No toca el motor predictivo.

## 1. Continuidad real de las capturas existentes en `main` (verificado el 02-11-2026)

| Workflow (main) | Cron declarado | Intervalos reales (últimas 12 ejecuciones) | Observación |
|---|---|---|---|
| `v09-rain-north.yml`: IMERG Early norte, GOES-19 RRQPE por zona y panel | 22 y 52 de cada hora | 3,7–6,9 h | En la ejecución de las 02:35 UTC del 02-11, Earthdata era inaccesible: `SOURCE_UNREACHABLE`. GOES-19 sí se actualizó |
| `v09-senamhi-avisos-capture.yml`: avisos INDECI/COEN | 7 y 37 de cada hora | 3,9–7,6 h | La comprobación de avisos suele superar los 180 min: el visor la rotula «vigente según el texto archivado» |
| `goes19-rrqpe-probe.yml` (sondeo v0.8) | :18 de cada hora | 3,9–8,0 h | No lo usa el visor |

GitHub retrasa mucho los cron de este repositorio. Consecuencias:
- **IMERG norte:** suele cumplir el máximo de 12 h.
- **GOES-19 por zona:** solo está «al día» (≤ 90 min) justo después de cada ejecución.
- **Avisos:** a menudo superan su máximo de 180 min.

Las capturas son más frecuentes solo si las ejecuta un reloj autorizado por el propietario. Para eso está el reloj externo del PR #373, en borrador, con `ENABLED="false"`; **no se ha activado**.

## 2. Qué hace la integración

`.github/workflows/v091-live-refresh.yml`, en la rama `research/v091-live-integration-20261102`, sigue este ciclo:

1. **Lee main sin escribir en ella.** Toma los cuatro archivos que ya escriben los workflows existentes:
   - `site/data/v09/dashboard_v0_1.json`;
   - `data/v09/rain/imerg_early_north_v0_1.json`;
   - `data/v09/rain/goes19_rrqpe_north_v0_1.json`;
   - `data/v09/senamhi_avisos/health_v0_1.json`.

   **No captura nada y no crea recolectores nuevos.**
2. **Valida cada entrada:** que sea JSON, que las guardas sigan sin alterar y que no haya fechas futuras.
   - Si una entrada es inválida, usa la última versión aceptada, que es el commit de main del ciclo anterior.
   - Si falta y no hay versión aceptada, la fuente queda **ausente (gris)**; nunca se usa la copia congelada de la rama.
3. **Si nada cambió, no publica nada** (código 10).
4. **Reconstruye** el semáforo (`v09_build_semaforo.py`), el paquete del visor (`v09_build_surveillance_view.py`) y el estado de fuentes (`v091_build_observation_feed.py`, de #469).
5. **Control de calidad en la hora del ciclo** (`qa()`):
   - guardas;
   - un aviso no cambia el color de ningún punto;
   - no hay verde sin IMERG al día y sin GOES-19 al día donde existe;
   - no hay rojo sin una confirmación verificada y con fuente;
   - el amarillo solo puede venir de lluvia satelital.
6. **Comprobación de la página** en Chromium sin interfaz (`qa/replay_tools/v091_live_page_check.py`):
   - 0 errores;
   - el ciclo mostrado es el del manifiesto;
   - autocomprobación del semáforo;
   - paridad Python/JS en la hora del ciclo.

   Si falla, el paquete se retira y el visor sigue con el anterior.
7. **Publicación atómica** en la rama de datos `research/v091-live-data`, sin forzar:
   - `current/` contiene el paquete, el estado de fuentes, el manifiesto y `page_check.json`;
   - `cycles/<id>.json` guarda un manifiesto por ciclo;
   - `status/last_failure.json` registra el último ciclo fallido.

   **Cada paquete anterior es recuperable** en el historial de esa rama.
8. **Reloj.** El segundo job espera `poll_minutes` (20 min) y programa la siguiente ejecución de este mismo workflow en esta rama con `GITHUB_TOKEN`.
   - No hay cron, no hay secretos nuevos y no escribe en main.
   - Repositorio público: los minutos de Actions no tienen coste.

**Parada:** poner `enabled: false` en `config/v091_live_refresh.json`. Además se detiene sola en `expires_at_utc` (09-11-2026) o al llegar a `max_hops_per_chain`.

**Reanudar:** basta un commit en ese archivo o en el workflow.

## 3. La página en modo vivo

`site/v09/vigilancia.html?live=<carpeta>` carga `<carpeta>/surveillance_view_v0_1.json`. Después, cada 5 min (`&poll=` en segundos), consulta `<carpeta>/manifest.json`.

- **Paquete nuevo:** la página se recarga sola y conserva la vista (centro, zoom y pestaña).
- **Fallo de la consulta:** sigue con el paquete cargado y lo indica en el mapa.
- **Lluvia:** se muestran por defecto las 22 zonas del norte, que se actualizan solas. La lluvia de la costa completa es la instantánea del 01-11 y aparece rotulada «no conectada».
- **«Fuentes»:** muestra el ciclo, la versión de main usada, el estado de cada fuente, las entradas que se tomaron de una versión anterior y lo que aún no está conectado.
- **Semáforo** (reglas de la revisión 0.2, sin cambios):

| Color | Cuándo |
|---|---|
| Gris | Faltan datos locales recientes |
| Amarillo | Solo lluvia satelital reciente |
| Verde | Sin lluvia satelital en datos al día; no significa ausencia de peligro |
| Rojo | Solo eventos verificados y localizados (registro vacío) |

Los avisos se muestran como contexto territorial y no cambian el color.

## 4. Aún no conectado

- **IMERG en la costa centro y sur** (La Libertad–Tacna, y los 5 puntos del semáforo que usan una celda costera): solo existe la instantánea del 01-11. Ningún workflow de main la actualiza, y no se ha creado un recolector nuevo.
- **Imágenes de nubosidad GOES-19:** no existe un recolector y no se ha creado.
- **Caudal y nivel de ríos y avisos hidrológicos de SENAMHI:** sin acceso automático permitido.
- **Registro de eventos verificados (rojo):** es manual y está vacío.
- **Frecuencia de las capturas de main:** depende de los cron de GitHub (3–8 h reales). Mejorarla requiere un reloj autorizado por el propietario.

## 5. Alojamiento privado: propuesta pendiente de autorización (no desplegado)

| Opción | Coste | Control de acceso | Actualización | Recomendación |
|---|---|---|---|---|
| **A. Visor local** (`scripts/v091_private_viewer.py`) | 0 | Solo escucha en 127.0.0.1 (el propio ordenador). Sin cuentas ni secretos | Descarga la rama de datos cada 10 min. La página se recarga sola | **Para empezar**: privado por construcción. Requiere un ordenador encendido con Python y git |
| **B. Cloudflare Pages + Cloudflare Access** (plan Zero Trust gratuito, hasta 50 usuarios) | 0 | Aplicación de Access sobre `<proyecto>.pages.dev` **y** `*.<proyecto>.pages.dev` (vistas previas). Política «Allow» solo para los correos autorizados, inicio con código de un solo uso, sesión de 24 h, sin `workers_dev` ni rutas públicas | El workflow sube página y paquete con `wrangler pages deploy` tras cada ciclo válido. Para eso el propietario crea un token de Cloudflare limitado a «Pages: Edit» y lo guarda como secreto `CLOUDFLARE_API_TOKEN` | Para acceso desde el móvil o para varias personas. **Requiere autorización expresa** y que el propietario cree la cuenta, la política y el token |
| GitHub Pages | 0 | Sería pública (repositorio público; Pages privadas exigen Enterprise) | — | **No** |
| Página alojada en Claude | 0 | Privada | Estática: no puede descargar paquetes nuevos | Se mantiene como demostración histórica |

Nota: la rama de datos está en un repositorio público. Contiene el mismo tipo de datos que main ya publica, pero ninguna página web. La interfaz solo se sirve mediante A o B.
