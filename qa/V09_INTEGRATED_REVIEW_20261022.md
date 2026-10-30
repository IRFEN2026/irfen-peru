# IRFEN v0.9 — Revisión de la integración privada, 22-oct-2026

**Estado:** BORRADOR / RESEARCH_ONLY / TEST_ONLY. Sin merge a main, ni sitio Pages, ni alertas operativas, ni activación del motor predictivo.

## Contenido integrado
- Panel `site/v09/index.html` de #401: indicadores de IMERG 24 h con intervalos reconstruidos y clasificación estricta COMPLETA / PARCIAL / SIN DATOS / DESCONOCIDA.
- Visor territorial `site/v09/territorio.html` de #377: costa norte y Rímac, geometrías verificadas, quebradas, zonas de vigilancia, metadatos por fuente.
- Navegación cruzada con enlaces visibles entre los dos documentos.
- Guardas territoriales específicas en `scripts/v09_pages_publication_gate.py`; las dos publicaciones están deshabilitadas.
- Flujos de captura basados en el `main` moderno. Su compilación territorial es informativa/optativa y no altera sus fuentes; no añade crons ni accesos a SENAMHI.
- Recálculo de `site/data/v09/territory_v0_1.json` desde la última lluvia `main` leída **sin ejecutar capturas** en una rama aislada.

## Evidencia de QA

- Ejecución integrada [#39812485387](https://github.com/IRFEN2026/irfen-peru/actions/runs/39812485387): éxito en dependencias, reconstrucción, pytest collection real, QA científica independiente, pruebas funcionales, navegador y congelamiento del paquete en el commit `9cc67615a4111781c462b67d8da472b4170b0cae`.
- La colección real registró **1702 tests** (1011 Phase-2), guardada en `config/phase2_test_collection_manifest.json` de esta rama.
- Prueba del navegador [#39812494781](https://github.com/IRFEN2026/irfen-peru/actions/runs/39812494781): éxito.
- Instantánea `site/data/v09/territory_v0_1.json` generada **2026-10-22T16:18:36Z**, lluvia evaluada **2026-10-22T13:14:34Z**, 22 zonas, 62 geometrías, `map_publishable=false`.
- En el paquete territorial los `imerg.windows[6h/24h]` válidos tienen `accum_mm` y no necesariamente `status=CALCULADO` (se omite intencionadamente el estado duplicado); los ausentes llevan `status=NO_DISPONIBLE`. **No** interpretar ausencia de status en un acumulado válido como cobertura perdida.

## Cómo abrir ambos mapas sin publicarlos

La vista no está desplegada en GitHub Pages (prohibición de publicación sigue vigente). Se debe ejecutar mediante servidor HTTP en `localhost`; abrir `file://` directamente suele bloquear las solicitudes internas `fetch`.

```powershell
git clone --filter=blob:none --sparse --depth=1 --single-branch --branch integration/v09-territory-private-map-20261022 https://github.com/IRFEN2026/irfen-peru.git IRFEN-Revision
cd IRFEN-Revision
git sparse-checkout set site/v09 site/data/v09
py -m http.server 8000 --directory site
```

Abrir http://localhost:8000/v09/index.html (panel), hacer clic en «Ver territorio», o abrir directamente http://localhost:8000/v09/territorio.html. Los controles permiten elegir costa norte / Rímac, seleccionar quebradas y revisar evidencia y datos ausentes.

Si Python no está disponible pero hay otra forma de servir una carpeta HTTP local, puede utilizarse. **No subir** `site/` a ningún servicio ni compartir un preview accesible por terceros para no confundir revisión local con publicación aprobada.

## Precauciones para la revisión
- Las magnitudes IMERG son **estimaciones espaciales satelitales**, no lectura de pluviómetro.
- GOES-19 RRQPE no está calibrado con estaciones de Piura.
- Geometrías derivadas/candidatas DEM no son geometrías oficiales.
- Los avisos oficiales y los códigos IRFEN de revisión no son una alerta operativa.
- La vista congelada en la rama no mantiene datos en vivo por sí misma. Requiere actualización controlada del paquete para revisar otro período.
- La cobertura 22/22 es evidencia de **completitud de las ventanas**, no de exactitud frente a precipitación real.

## Pendientes
1. QA humana de diseño y navegabilidad en computadora y móvil.
2. Revisión de seguridad de los cambios de workflows y de las exclusiones Pages.
3. Verificación de consistencia frente a un corte `main` actualizado, sin confundir fechas distintas.
4. Aprobación separada posterior de merge, y otra específica de alojamiento/publicación (si alguna vez se solicita).
