# IRFEN v0.9 — Investigación de retención NASA/NOAA (paso 1, NO ACTIVADO)

**RESEARCH_ONLY / TEST_ONLY.** Esta propuesta no cambia el contrato de captura, datos científicos, guardas, geometrías, pronósticos ni la publicación de v0.9. No recupera intervalos ni descarga gránulos IMERG o escaneos GOES.

## Evidencia documental conocida (20-10-2026)

- **NASA GPM, IMERG Early half-hourly v07:** la página oficial del producto identifica GES DISC y la resolución de 30 minutos: https://gpm.nasa.gov/node/2525 .
- **NASA, documentación técnica IMERG (2023):** describe el archivo IMERG (incluido Early) en PPS/GES DISC: https://gpm.nasa.gov/sites/default/files/2023-07/IMERG_TechnicalDocumentation_final_230713.pdf .
- **CMR GES_DISC:** colección `C2723758340-GES_DISC`; la sonda consulta metadatos de colección y el gránulo más antiguo enumerado, *sin solicitar contenido del gránulo*: https://cmr.earthdata.nasa.gov/search/concepts/C2723758340-GES_DISC.html .
- **NOAA NODD / Registro de datos abiertos:** identifica el bucket público `noaa-goes19` con metadatos GOES-19: https://registry.opendata.aws/noaa-goes/ . La sonda lista la primera clave lexicográfica disponible bajo `ABI-L2-RRQPEF/2025/` y `/2026/` mediante `ListObjectsV2` y `max-keys=1`.

## Interpretación limitada

1. Que el catálogo muestre un archivo antiguo solo prueba que ese archivo estaba listado al consultar. **No prueba una garantía contractual de retención o disponibilidad continua.**
2. La cobertura temporal de la colección NASA no garantiza que cada intervalo esté publicado; el listado más antiguo tampoco prueba que ese sea el archivo más antiguo físicamente conservado.
3. Un año/prefijo NOAA vacío, un fallo HTTP, una redirección o un resultado malformado no prueban eliminación, caducidad ni inexistencia. Se reporta `UNKNOWN`.
4. La **retención mínima garantizada sigue `NOT_VERIFIED`** para ambos productos. Por tanto, `UNRECOVERABLE` sigue deshabilitado.
5. Las 34 medias horas IMERG que figuran `MISSING_RETRYING` en la instantánea de #394 se podrán considerar candidatas únicamente mientras CMR las siga listando; el diseño de recuperación requiere otra autorización antes de descargarlas.

## Implementación revisable

- `qa/replay_tools/v09_source_retention_readonly.py`: acepta solamente HTTPS de CMR (colecciones/gránulos) y S3 público de GOES-19. Rechaza redirecciones. Usa solicitudes de catálogo pequeñas y limitadas, sin enlaces de descarga, e informa SHA-256 de la respuesta y momento de consulta.
- `.github/workflows/v09-source-retention-manual.yml`: exclusivamente `workflow_dispatch`, permisos `contents: read`, timeout 15 minutos, sin credenciales, artefacto temporal fuera del repositorio.
- `qa/replay_tools/test_v09_retention_readonly.py`: pruebas offline de allowlist, respuestas CMR/S3 y conservación de UNKNOWN ante errores.
- La ejecución de este workflow **no está autorizada por el simple merge**; el propietario debe autorizar el disparo manual de forma separada. CI de PR no hace consultas a NASA ni NOAA.

## Decisión pendiente

Para pasar de observación puntual a `retention.status=VERIFIED` haría falta documentar una **política oficial verificable de conservación temporal**, con alcance exacto, duración y producto, además de evidencia reproducible de catálogo. Hasta entonces: `NOT_VERIFIED`, sin intervalos `UNRECOVERABLE` y sin capturas nuevas.
