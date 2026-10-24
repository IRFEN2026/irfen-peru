# IRFEN · Episodios de lluvia en costa norte, 21–22 de octubre de 2026

**Corte y propósito.** Casos de investigación meteorológica documentados a partir de noticias, avisos oficiales y un mismo estado archivado de IMERG/GOES. Se archivan **sin** usar como mediciones de estaciones ni integrarlos automáticamente al mapa. `RESEARCH_ONLY / TEST_ONLY`; sin alertas, cambios de umbral, contactos nuevos a SENAMHI ni motor predictivo.

**Archivo de referencia:** [north_rains_2026-10-21_to_22_v1.json](../validation_cases/north_rains_2026-10-21_to_22_v1.json). Incluye 22 zonas, procedencia y SHA por cada fuente, tres reportes meteorológicos, dos avisos oficiales y cuatro cortes temporales de 30 minutos. Datos extraídos del árbol `main` mediante API GitHub, sin repetir capturas.

## Qué se pudo corroborar y qué no

| Región | Hecho en noticias | Comparación IMERG Early | Limitación |
|---|---|---|---|
| Sullana, Piura | 21-oct, 19:15 PET: lluvias y descargas eléctricas comunicadas | 21-oct 18:00–21:00 PET: **4,114 mm de media de superficie provincial**; 6/6 medias horas | La franja es **exploratoria**, el reportero no da inicio y fin exactos. Una estimación anunciada de **15 mm/h** era **pronóstico**, no intensidad observada |
| Zarumilla, Tumbes | Noche 21→22-oct con lluvia y tormenta eléctrica | 21-oct 20:00–22-oct 06:00 PET: **6,636 mm de media provincial**; 20/20 medias horas | Sin medición de pluviómetro; no demuestra cuánto cayó en el casco urbano |
| Tumbes, provincia | Noche 21→22-oct con aniegos comunicados para la región | Mismo intervalo: **7,348 mm de media provincial**; 20/20 medias horas | El reporte regional no define todas las localidades de afectación |
| Contexto Piura, provincia | No es el punto de la noticia de Sullana | 21-oct 18:00–21:00 PET: **2,056 mm de media provincial** | Provincia distinta: control contextual, **no** validación cruzada de Sullana |

**Acumulados 24 h** (21-oct 14:00→22-oct 14:00 PET): Tumbes provincia 13,83 mm; Zarumilla 12,82 mm; Sullana 6,51 mm; Piura provincia 2,54 mm; Zaña/Oyotún 2,88 mm; Chancay-Lambayeque/Chongoyape 1,54 mm; Motupe 0,03 mm. Todos **estimados por satélite** sobre superficie, no medidas de estación. El perímetro de la provincia y el de una cuenca difieren. No extrapolar ni sumar superficies superpuestas.

**Avisos:** n.º 426, previsión del 20 al 22-oct de 2–16 mm/día en costa norte según INDECI/SENAMHI; n.º 430, para 23–25-oct, aviso de lluvias previsto en Piura y Tumbes, con cantidades periodísticas previstas de hasta 14, 15 y 17 mm/día en costa norte en cada día. Son **pronósticos**, no acumulaciones ya medidas, y no justifican cambiar prioridades/umbrales o generar avisos IRFEN. En el archivo v0.9 se conserva `official_level=null` del 430 por discrepancia sobre si el nivel constaba explícitamente en el contenido oficial parseado.

## Fuentes trazables
- [El Comercio, seguimiento del 21-oct](https://elcomercio.pe/peru/piura-y-el-norte-del-peru-bajo-lluvias-intensas-ultimas-noticias-alerta-por-el-nino-e-informe-del-coen-en-vivo-lbposting-noticia/?outputType=amp) — lluvia en Sullana y hora del reporte.
- [Gestión, 22-oct](https://gestion.pe/peru/fenomeno-el-nino-lluvias-intensas-inundan-calles-de-tumbes-noticia/) — lluvias y tormenta nocturna en Zarumilla; aniegos en Tumbes.
- [INDECI, aviso 426 publicado 19-oct](https://www.gob.pe/institucion/indeci/noticias/1459288-indeci-recomienda-medidas-de-preparacion-ante-las-precipitaciones-en-la-costa-norte-y-sierra) — previsión oficial y duración, no pluviómetro.
- [El Comercio, aviso 430 reportado 22-oct](https://elcomercio.pe/peru/piura/piura-lluvias-intensas-con-descargas-electricas-seguiran-desde-hoy-hasta-el-domingo-25-de-octubre-segun-senamhi-apuesplan-ultimas-noticia/?outputType=amp) — valores previstos 23–25.
- `data/v09/surveillance/zone_rain_state_v0_1.json` y archivos v0.9 de IMERG/GOES de `main`, congelados por SHA en el JSON, evaluados **2026-10-23T00:13:59 UTC**. En ese corte, IMERG `AVAILABLE`, 48/48 medias horas por zona, última ventana hasta **22-oct 14:00 PET**; el escaneo GOES más reciente hasta **22-oct 19:09 PET**. Ese escaneo posterior no refuta lluvias nocturnas.

## Decisiones y siguiente comprobación
1. Guardar noticia como **reporte de lluvia**, no pluviómetro y no etiqueta de riesgo hidráulico.
2. Usar estos intervalos como candidatas de validación temporal frente a información instrumental de Zarumilla/Sullana con hora/periodo conocidos.
3. Exigir pares estaciones–IMERG de **misma ventana y celda** antes de cuantificar error o entrenar sesgo.
4. Para verificar si GOES-19 ayuda al *nowcast*, congelar escaneos que **coincidan** con las horas de lluvia y no compararlos con un único escaneo varias horas posterior.
5. Comprobar frescura y acceso continuado NASA: `AVAILABLE` una vez no acredita continuidad permanente; el fallo previo no se debe confundir con cero lluvia.
6. Mantener el PR #403 y el mapa sin integración de esta evidencia hasta completar QA editorial/visual y decisión expresa del propietario.

**Resultado:** corroboración de señal satelital temporal en dos episodios de lluvia informados por medios; **ninguna** medición instrumental validada, **ninguna** estimación calibrada nueva y **ninguna** modificación operativa.
