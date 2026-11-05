# IRFEN v0.9.1 — incorporación experimental de SILVIA y evaluación de otras fuentes SENAMHI

**Revisión:** 2026-11-05. **Ámbito obligatorio:** toda la costa peruana Tumbes–Tacna, 11 departamentos, cuencas aportantes incluso extranjeras si drenan al Pacífico. **Fuera:** Amazonía/Titicaca.

**Puertas:** RESEARCH_ONLY · TEST_ONLY · activation_gate=BLOCKED · sin cambio del semáforo, alertas, pronósticos hidrológicos ni publicación abierta.

## Evidencia proporcionada por el usuario

1. Imagen SENAMHI fechada **2026-11-04**: zonas que superan umbrales de **lluvia antecedente de 7 días**. Es un mapa de categorías, NO una medición cuantitativa puntual en milímetros ni un pronóstico de lluvia.
2. Imagen SENAMHI fechada **2026-11-04**: **peligro potencial de movimientos en masa**. NO significa activación observada ni desborde de río.
3. ZIP Shapefile **peligros_mm/SILVIA.shp + shx + dbf + prj + cpg** con SHA256 **0bb60908160eb9931341140f4c13cf9eb5afe7b336f0b4b7dbf017ed7f092d33**:
   - **771 polígonos** con fecha de registro **2026-11-04**.
   - Campo **NIVEL**: código 2 = 346 polígonos; código 3 = 344; código 4 = 81.
   - BBOX: longitudes −80.7464 a −71.3417, latitudes −14.2083 a −2.9467. Contiene zonas no costeras y **NO debe cargarse entero en IRFEN**.
   - Geometrías: 758 Polygon, 13 MultiPolygon; **2 geometrías inválidas** en comprobación de Shapely. La capa es WGS84 geográfico; PRJ del usuario marca GCS_unknown con datum D_WGS_1984.
   - La correspondencia exacta de códigos numéricos a etiquetas oficiales amarillo/naranja/rojo **NO se encuentra en el DBF** y debe verificarse en leyenda/metadatos antes de nombrar categorías. No deducir amenazas de códigos por sí solos.
4. GIF GOES-19 de fecha 2026-11-05, imagen 640×524, **solo un fotograma**: canal infrarrojo 13, longitud de onda 10,33 µm, temperatura de brillo (°C). Es imagen de nubes/temperatura de brillo; no mide directamente precipitación en superficie ni pronostica desbordes y no prueba trayectoria sin una secuencia temporal.

**Regla de procedencia:** las capturas aportadas constituyen evidencia puntual fechada, no un servicio continuo ni una autorización para raspar portales. La propiedad/licencia para redistribución automática permanece sin verificar.

## Capacidad implementada en este PR

Nuevo **scripts/v09_silvia_coast_import.py**:
- Procesa offline el ZIP Shapefile legalmente suministrado y produce auditoría sin hacer ningún acceso de red.
- Para **exportar GeoJSON exige máscara explícita con los 11 departamentos costeros** (polígonos administrativos independientes). Rechaza la exportación si falta uno; interseca las geometrías nacionales con cada departamento y elimina territorio fuera del alcance.
- Repara geometrías inválidas para operaciones SIG mediante `make_valid` y mantiene el conteo de errores original.
- Conserva fecha, código NIVEL, departamento, fuente y salvaguardas `event_observed=false` / `hydrological_prediction_validated=false`; deja etiqueta de nivel desconocida hasta verificación.
- Genera reporte QA: SHA256, fechas, niveles y conteos por departamento. **No genera alertas ni actualiza capas operativas.**
- Pruebas sintéticas cubren salida segura sin máscara, recorte exacto, máscara costera incompleta, geometría inválida y proyección desconocida.

**No se adjunta el ZIP a GitHub**, ni se publica una capa nacional. El CLI requiere el ZIP legítimo del usuario y la máscara costera autenticada, todavía pendiente de selección.

## Fuentes web y su utilidad

- [SILVIA](https://www.senamhi.gob.pe/?p=monitoreo-silvia): aporta peligro de **activación de quebradas/movimientos en masa**, lluvia previa de siete días y potencial contraste externo con IRFEN. No equivale a caudal o desborde de río, ni es una verdad-terreno independiente de ocurrencias.
- [TENDHIS](https://www.senamhi.gob.pe/tendenciashistoricas/): tendencias históricas de precipitación y temperatura, datos de estaciones y PISCO; útil para climatología de referencia y anomalías, no para pronósticos subdiarios 1–3 h. Portal agotó tiempo de espera durante revisión.
- [Observatorio Nacional](https://observatorio.senamhi.gob.pe/): reúne visualizaciones de precipitación, satélite/radar, avisos meteorológicos e hidrológicos; **prioridad alta para ubicar fuentes oficiales de niveles/caudales y predictores**, sujeto a accesibilidad, licencia y marcas temporales verificables. Portal interactivo agotó tiempo de espera en lector; **no se ha verificado API/autorización de extracción**.
- [PHISIS](https://www.senamhi.gob.pe/servicios/?p=monitoreo-hidrologico): fuente complementaria de estaciones de nivel/caudal que requiere una vía legal estructurada; publicaciones de avisos no equivalen a mediciones independientes.
- [GEOQUEBRADAS MINAM](https://geoservidorperu.minam.gob.pe/geoquebradasestadistica/): referencia de exposición/impactos para **validación territorial**, no sustituto de activación observada.

## Orden de incorporación recomendado sin bloquear el cierre anterior

1. Adoptar **SILVIA como capa oficial referencial separada** para peligro potencial de quebradas: mapa del 04-11, fecha, fuente, códigos y opacidad, siempre con máscara costera y advertencia de no equivalencia a evento.
2. Comparar superposición SILVIA con puntos/zonas de quebradas costeras y lluvia IMERG Early 1/3/6/24/72 h, **sin asumir independencia** (ambas fuentes pueden utilizar lluvia satelital o datos comunes).
3. Incorporar TENDHIS/PISCO como línea base histórica, priorizando percentiles y estacionalidad para **cada cuenca costera**.
4. Investigar acceso *autorizado* a Observatorio/PHISIS para datos de caudales/niveles con hora de medición, publicación y control de calidad; sin eso seguirá `NO_EVALUABLE` la predicción de desbordes 1/3/6/12/24 h.
5. Mantener SILVIA y modelos experimentales separados; un aviso institucional puede incorporarse como **referencia oficial** con vigencia y enlace, nunca como una predicción propia de IRFEN.

**Entregable científico todavía no cumplido:** disponer de eventos verdaderamente ocurridos de quebradas/desbordes y mediciones hidrométricas independientes para evaluar alertas con anticipación y falsas alarmas.
