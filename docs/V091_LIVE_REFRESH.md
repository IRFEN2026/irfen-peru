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
   - **Parada comprobada:** `scripts/v091_live_refresh.py --control` (probado en `tests/test_v091_live_refresh.py`) devuelve `run=false` desde el 09-11-2026 00:00 UTC, con `enabled=false`, al llegar a `max_hops_per_chain` (600; la fecha llega antes) o si se altera una guarda. Sin `run=true` no se programa la siguiente ejecución: la última ejecución posible es una de unos 20 s a las 00:20 UTC del 09-11. La vigencia no se amplía sin autorización.
   - **Sin duplicados:** el grupo de concurrencia `v091-live-refresh` admite una ejecución en curso y una pendiente; si llega otra (por ejemplo, un push mientras la cadena duerme), GitHub cancela la pendiente anterior. Medido el 02-11: 32 ejecuciones seguidas, separadas entre 20,4 y 21,1 min, sin dos ciclos a la vez.
   - **Consumo:** cada eslabón dura unos 20,6 min (20 min de espera + ~30 s de trabajo), así que la cadena ocupa un runner de forma continua: ~1.450 min de runner al día. **Coste facturable 0** (repositorio público; la API `/timing` devuelve `billable: 0 ms`). Para no mantener un runner esperando hay dos alternativas, ambas requieren autorización (§6).
9. **Último intento de captura.** Antes de reconstruir, el workflow lee (solo GET) la última ejecución terminada en main de cada productor y el resultado de su paso: IMERG («Archive every missing half-hour…»), GOES-19 («GOES-19 RRQPE…») y avisos (ejecución completa), con la línea de error si falló. Cada fuente muestra por separado:
   - **última observación** (hora del dato válido más reciente);
   - **último intento de captura** (hora de la ejecución);
   - **resultado del intento:** correcto, fallido (con el motivo), no ejecutado (falló un paso anterior) o desconocido.

   Un intento nuevo, aunque falle, publica un paquete marcado `SOLO_INTENTO_DE_CAPTURA` con las mismas observaciones válidas: la página dice explícitamente «última captura fallida» sin borrar la observación anterior, que sigue coloreando solo mientras sea reciente.

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

## 4. Fallos de fuentes y caducidad (comprobado)

| Situación | Qué pasa | Prueba |
|---|---|---|
| Falla la captura de IMERG, GOES-19 o avisos (workflow de main con error) | main no cambia: se mantiene el último paquete validado; se publica el intento fallido | `test_failed_capture_attempt_is_published_explicitly_with_previous_observation`; caso real del 02-11 10:04 UTC |
| Archivo de una fuente dañado en main | Se usa la última versión aceptada; el mapa se publica | `test_each_source_failure_keeps_last_package_and_expires_to_grey` (IMERG, GOES-19, avisos) |
| Fuente ausente sin versión aceptada | Esa fuente queda ausente (gris), nunca la copia congelada | `test_invalid_input_uses_last_accepted_and_missing_source_is_grey` |
| Observación caducada (IMERG > 12 h, GOES-19 > 90 min) | Los puntos afectados pasan a gris, aunque no llegue paquete nuevo: la página evalúa a la hora actual | mismas pruebas + `v091_live_page_check.py` (paridad JS/Python a +0, +2 h, caducado y +72 h; todo gris tras caducar) |
| GOES-19 caducado con IMERG reciente y seco | Gris, nunca verde | `test_goes_expiry_forbids_green_even_with_fresh_imerg` |
| Lluvia satelital extrema + todos los avisos en vigor | Amarillo «lluvia satelital detectada»; nunca rojo; los avisos no cambian el color | `test_avisos_rain_and_events_stay_separate` |
| Evento verificado y localizado | Rojo solo en ese punto | ídem |

## 5. Aún no conectado

- **IMERG en la costa centro y sur** (La Libertad–Tacna, y los 5 puntos del semáforo que usan una celda costera): solo existe la instantánea del 01-11. Ningún workflow de main la actualiza, y no se ha creado un recolector nuevo.
- **Imágenes de nubosidad GOES-19:** no existe un recolector y no se ha creado.
- **Caudal y nivel de ríos y avisos hidrológicos de SENAMHI:** sin acceso automático permitido.
- **Registro de eventos verificados (rojo):** es manual y está vacío.
- **Frecuencia de las capturas de main:** depende de los cron de GitHub (3–8 h reales). Mejorarla requiere un reloj autorizado por el propietario.

## 6. Vista privada conectada a la rama de datos: propuesta pendiente de autorización (no desplegada)

`scripts/v091_build_private_site.py --out <carpeta>` genera la vista desplegable:
- `index.html`: la misma página, con `<meta name="irfen-live">` apuntando a `https://raw.githubusercontent.com/IRFEN2026/irfen-peru/research/v091-live-data/current/`. Carga el último paquete validado, consulta `manifest.json` cada 5 min y se recarga sola al aparecer un ciclo nuevo, conservando la vista. Si la consulta falla, mantiene el paquete y lo indica.
- `_headers`: `noindex`, `no-referrer`, `nosniff`, sin marcos y una política de contenido que solo permite leer datos de `raw.githubusercontent.com`.
- La página **no se vuelve a desplegar en cada ciclo**: los datos llegan solos desde la rama de datos. Solo se sube de nuevo si cambia el código de la página.
- Probado sin desplegar: `v091_live_page_check.py --cross-origin` sirve la carpeta y los datos desde dos orígenes distintos (como Cloudflare y GitHub) y comprueba la carga, el cambio de ciclo sin intervención y la conservación de la pestaña.
- `?live=` en la URL solo admite carpetas relativas: nadie puede hacer que la página cargue datos de otro sitio cambiando la URL.

| Opción | Coste | Control de acceso | Qué tiene que hacer el propietario | Recomendación |
|---|---|---|---|---|
| **B. Cloudflare Pages (subida directa) + Cloudflare Access** (Zero Trust gratuito, hasta 50 usuarios) | 0 | Dos aplicaciones de Access, siguiendo el procedimiento de Cloudflare «Enable Access on your `*.pages.dev` domain» (Pages, *Known issues*): una para `<proyecto>.pages.dev` y otra para las vistas previas `*.<proyecto>.pages.dev`. Política «Allow» solo con los correos autorizados; método «One-time PIN» por correo; sesión de 24 h; sin tokens de servicio ni reglas «Bypass»; sin dominio propio (si se añade uno, necesita su propia aplicación de Access) | 1) Crear el proyecto de Pages y subir la carpeta generada (una vez). 2) Crear la aplicación de Access y la política. 3) Comprobar en una ventana privada que sin código no se ve nada. **No hace falta ningún token ni secreto en GitHub**: la página lee los datos ella sola | **Recomendada** para verla desde el móvil o con varias personas |
| **A. Visor local** (`scripts/v091_private_viewer.py`) | 0 | Solo escucha en 127.0.0.1 | Ejecutarlo en un ordenador con Python y git | Alternativa sin cuentas |
| GitHub Pages | 0 | Sería pública (Pages privadas exigen Enterprise) | — | **No** |
| Página alojada en Claude | 0 | Privada | Estática: no puede leer paquetes nuevos | Solo demostración histórica |

Límite: el control de acceso protege la **interfaz**. Los datos de `research/v091-live-data` están en un repositorio público, igual que los que main ya publica. Si los datos también deben ser privados, habría que hacer privado el repositorio (los minutos de Actions dejarían de ser gratuitos) o servirlos desde el propio Pages con un token de despliegue: ambas cosas requieren otra autorización.

## 7. Bloqueos y decisiones pendientes

1. **La captura de lluvia de main se cae entera cuando falla una descarga de IMERG.** 02-11 10:04 UTC: `earthaccess.exceptions.DownloadFailure … Status code: 400` en `scripts/v09_imerg_north_archive.py` (la descarga no está dentro del `try` que sí cubre la búsqueda). El job termina con error, **GOES-19 no se ejecuta** y no se guarda nada. Arreglo propuesto, sin fusionar: capturar el error de descarga como fallo de la fuente (como ya se hace con `SOURCE_UNREACHABLE`) para que GOES-19 siga. Requiere autorización para cambiar main. Si el 400 persiste, revisar también la validez de `EARTHDATA_TOKEN` (solo el propietario puede verlo; no se pide aquí).
2. **Frecuencia de las capturas de main:** 3–8 h reales por los retrasos del cron de GitHub. Mejorarla requiere el reloj externo (#373), no activado.
3. **Reloj sin runner esperando** (opcional, para no ocupar un runner 24 h): *a)* que los workflows de captura de main lancen `v091-live-refresh` al terminar (un paso de una línea; ciclo ~1 min después de cada captura, ~10 ejecuciones cortas al día); o *b)* un entorno de GitHub con temporizador de espera («wait timer») de 20 min en lugar de `sleep`: el job no empieza, ni ocupa runner, hasta que vence el temporizador. *a)* cambia main y *b)* cambia la configuración del repositorio: ninguna se ha hecho.
4. **Alojamiento B:** pendiente de autorización y de que el propietario cree el proyecto y la política de acceso.
