# IRFEN v0.9.1 — Integración de observaciones actualizadas (RESEARCH_ONLY)

**Objetivo:** reemplazar las instantáneas congeladas del visor de investigación por observaciones recientes verificables, sin necesitar sesiones abiertas de Claude y sin activar alertas públicas ni un modelo de peligro no validado.

## Lo que ya existe en main (verificado 02-11-2026)

- `.github/workflows/v09-rain-north.yml`: captura IMERG norte con cron `22,52 * * * *`; ya genera datos de zonas y bundle de dashboard.
- `.github/workflows/v09-senamhi-avisos-capture.yml`: noticias/avisos vía INDECI/COEN (no consultas robotizadas directas a SENAMHI) con cron `7,37 * * * *`.
- `.github/workflows/goes19-rrqpe-probe.yml`: una captura NOAA GOES-19 por hora, TEST_ONLY; los archivos de la rama principal son datos de investigación.
- Comprobación de GitHub Actions: había ejecuciones programadas exitosas en 01-11 y 02-11. Las ejecuciones programadas pueden retrasarse o fallar; un cron no garantiza una actualización en tiempo real.

**Problema real:** `research/v09/private_demo/` contiene datos incrustados y congelados. No consulta los archivos nuevos de main. Claude Code no es un proceso 24/7 y sus mensajes no alimentan automáticamente el sitio.

## Primer módulo ejecutable de este PR

`scripts/v091_build_observation_feed.py`:

- Consume 4 fuentes archivadas y anota `RECENT_ARCHIVED`, `STALE`, `SNAPSHOT_ONLY`, `INVALID_TIME`, `INVALID_GUARD` o `UNKNOWN`.
- Usa la **fecha de observación o último éxito**, no la fecha de apertura de la página.
- Los productos costeros de captura única se marcan siempre `SNAPSHOT_ONLY`, incluso si están recientes.
- No transforma fuentes sin datos en lluvia cero, ni asigna verde/amarillo/rojo a checkpoints.
- Permite `--as-of` para pruebas con tiempo fijo y `--check` para asegurar reproducibilidad.
- `.github/workflows/v091-observation-feed-research.yml`: prueba aislada en la rama de investigación; genera un artefacto de estado sin desplegar, sin escribir main y sin enviar notificaciones.
- `tests/test_v091_observation_feed.py`: archivos válidos, caducados, futuros, inconsistentes y faltantes.

Este feed es **una pieza de la infraestructura, no el sistema continuo terminado**.

## Siguiente integración necesaria para la versión privada viva

1. **Mantener los capturadores ya activos**. No duplicar solicitudes a SENAMHI, INDECI o NOAA; respetar robots, TOS, pausas y listas blancas de fuentes oficiales. Para pluviómetros públicos de Perú/Ecuador, solo usar servicios permitidos y con metadatos de horario/cota/QA.
2. **Armar un snapshot de publicación research** tras cada captura: bajar exclusivamente archivos de origen permitidos y recientes, reconstruir dashboard/semaforo/feed, validar timestamps y procedencia, publicar **atómicamente** sólo cuando pasa QA. Si falla, conservar último paquete y marcar `STALE` claramente.
3. **Habilitar actualización de toda la costa** con IMERG Early: aprovechar procedimiento que ya produjo 2.215 celdas costeras y priorizar lotes incrementales acotados. No asumir que la captura aislada del 01-11 es continua ni inventar ventanas incompletas; completar y auditar cobertura y tiempo de ejecución en runner.
4. **Nubosidad NOAA GOES-19**: obtener un producto público NOAA ABI-L2-MCMIPF/CMIPF para el área de Perú, georreferenciar y superponer como producto separado (nubes no equivalen a lluvia). Conservar fuente, banda, DQF, hora de escaneo y caducidad. No proclamar que una imagen satelital sea un radar meteorológico terrestre.
5. **Publicación privada autenticada**: la página de Claude sigue siendo una demo estática; una vista realmente cambiante necesita un hosting protegido que consulte el paquete validado en intervalos definidos. No activar repositorio Pages público ni distribuir información personal. El dueño debe autorizar el destino y sus controles de acceso. Diseñar de modo que los datos puedan ser públicos pero la interfaz de investigación siga privada, cuando corresponda y según licencia.
6. **Contratos del mapa**: cada fuente lleva `observed_at`, `ingested_at`, `valid_until`, producto, cobertura, calidad, permiso/licencia, hash y `status`. Desconocido, caída de servicio, falta de cobertura o latencia excesiva → GRIS/DATO FALTANTE; nunca cero o verde.
7. **No unir semáforo con alertas de peligro**: 
   - Regional: avisos meteorológicos mostrados como área administrativa y separados del checkpoint.
   - Local: observaciones de lluvia satelital o pluviómetro como señal meteorológica, no condición hidráulica confirmada.
   - Evento confirmado: fuente oficial o evidencia revisada, fenómeno/localización/horario, diferenciando `ocurrió` de `sigue activo`. La ausencia de confirmación NO significa ausencia de evento.
   - Los checkpoints de centros poblados ANA NO son pluviómetros ni puntos en la quebrada.
   - En La Leche, Motupe es un proxy de lluvia: documentar que no corresponde necesariamente a su cuenca efectiva.
   - Sin estaciones de caudal/nivel, NO inferir desborde ni tiempos de anticipación 3/6/12/24 h. Deshabilitar red/amarillo como estados de peligro automáticos hasta revisión científica.
8. **Verificación end-to-end**: ejecutar dos ciclos consecutivos con entrada real y distinta; demostrar cambio de fecha y observación en navegador privado, sin recargar manually, sin JS errors, sin verde indebido, sin mensajes de confirmación inventados; probar cierre de conexión/fuente caducada y rollback de bundle; respaldar paquete anterior.

## Operación sin Claude permanentemente conectado

Claude = responsable de programar/depurar conectores y revisar fallos. GitHub Actions / cron externo autorizado = reloj; fuente oficial y NASA/NOAA = datos; pipeline determinista = verificación; alojamiento privado con control de acceso = entrega visual. No se necesitan sesiones permanentes de IA para el ciclo normal. Investigaciones nuevas pueden ejecutarse aparte, no en cada iteración.

**Límite de GitHub Actions:** los cron se ejecutan en el workflow de la rama por defecto; los cron pueden retrasarse y workflows de repositorios públicos pueden deshabilitarse por inactividad. No pretender que la rama PR por sí sola se programe constantemente. Cloudflare Workers Free tiene límites de CPU que impiden procesar grandes archivos científicos allí; si se usa Worker, dejarlo exclusivamente como disparador/verificador, manteniendo procesamiento en runner.

## Puertas de habilitación

- Sin fusión a main ni despliegue general en esta etapa.
- Confirmar licencias/atribuciones, uso de fuentes y autenticación del hosting.
- El propietario debe aprobar un despliegue privado y una modificación mínima del reloj GitHub o cron externo cuando el ciclo de investigación pase la prueba end-to-end.
- `RESEARCH_ONLY / TEST_ONLY / activation_gate=BLOCKED / public_alerting=false / missing_data_rule=UNKNOWN_NOT_LOW_RISK`.
