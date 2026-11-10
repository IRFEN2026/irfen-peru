# IRFEN v0.9.1 — cierre técnico del bloqueo de navegador de los 536 checkpoints (03-11-2026)

**Alcance:** investigación privada. Sin fusión a main, sin publicación pública, sin correos, sin reglas naranja ni cambios a los estados operativos.

## Diagnóstico verificable

La cadena `v091-live-refresh` reconstruía correctamente el paquete de 536 checkpoints y 134 cuencas, pero rechazaba la nueva versión cuando Playwright esperaba 30 segundos a `body[data-ready='1']`. Como consecuencia, la rama `research/v091-live-data` conservaba el paquete anterior de 117 puntos. **Un job con conclusión 'success' no significaba que el paquete se hubiera publicado:** el job de publicación preservaba el paquete previo cuando fallaba el gate del navegador.

La nueva instrumentación de `qa/replay_tools/v091_live_page_check.py` registró `page_errors=[\"Invalid or unexpected token\"]`, `state=Cargando…` y `live_cycle=null`. La validación independiente `node --check` identificó el error exacto en el JavaScript embebido de `site/v09/vigilancia.html`: una comilla doble que debía ser simple en el texto de lluvia por cuenca dentro de `hyPanel`. Se corrigió sin alterar el cálculo de lluvia ni el semáforo.

## Pruebas después de la corrección

- [GitHub Actions #41661876678](https://github.com/IRFEN2026/irfen-peru/actions/runs/41661876678): reconstrucción aislada del paquete y navegación de Chromium sin errores; autocomprobación **536/536**, paridad Python/JavaScript **0 discrepancias**, vencimiento simulado **536 grises**.
- [GitHub Actions #41662753315](https://github.com/IRFEN2026/irfen-peru/actions/runs/41662753315): prueba adicional que selecciona realmente `PIU-R-PIURA-BAJO` y abre el panel **«Cinco preguntas»** para comprobar presencia de IMERG Early por cuenca y las etiquetas de acumulados 1/3/6/24/72 h; test correcto, cero errores. Captura de ventana disponible en el artefacto `irfen-private-browser-diagnostic`.
- Para evitar futuros bloqueos silenciosos, el workflow nuevo `.github/workflows/v091-private-browser-diagnostic.yml` comprueba primero sintaxis JavaScript, luego reconstruye de `main` en un runner aislado y finalmente verifica navegación, paridad y la ficha de Piura. No escribe en main.

## Diferencia entre «código probado» y «visor privado actualizado»

La rama fuente `research/v091-live-integration-20261102` ya tiene el código correcto. **Esto NO garantiza que `research/v091-live-data/current` haya sido reemplazado**; el ciclo real de reconstrucción está encadenado cada ~20 minutos con concurrencia serializada. Para confirmar la entrega final, verificar en:
- `research/v091-live-data/current/manifest.json`: `inputs` debe incluir `data/v09/rain/imerg_early_catchments_v0_1.json`;
- `research/v091-live-data/current/page_check.json`: `runs[0].selfcheck == \"536/536\"`, `errors=[]`, `runs[0].catchment_popup.rain_detail_present == true`;
- `research/v091-live-data/current/surveillance_view_v0_1.json` con 536 puntos y datos recientes o caducados etiquetados por cuenca.

Hasta que esos tres checks se confirmen, comunicar que el **código del visor está validado en una prueba aislada**, pero el paquete vivo anterior se mantiene.

## Siguientes pendientes científicos

El [PR #486](https://github.com/IRFEN2026/irfen-peru/pull/486) identifica 32 diferencias de área superiores a ±1% en el contraste HydroSHEDS/HydroRIVERS, en particular Supe alto, La Leche alto y Caplina alto. No extrapolar que existe una crecida a partir de precipitaciones IMERG. Las 398 ubicaciones ANA son poblaciones expuestas documentales, no geometrías inventadas de microcuencas.
