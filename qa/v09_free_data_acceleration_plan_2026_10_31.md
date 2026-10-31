# IRFEN v0.9 · Ruta sin pagos para versión avanzada (31 octubre 2026)

**Decisión del propietario:** no pagar datos hidrométricos, avanzar hacia una versión de investigación mejorada para el 1 de noviembre de 2026. No confundir aproximación con observación. RESEARCH_ONLY / TEST_ONLY; no alertas, no publicación, sin cambios en main.

## Entregado de inmediato

- `research/v09/north_flood_lab_free_data.html`: una vista autocontenida de laboratorio sobre el norte, con 24/72 h IMERG archivado de #457, resultados diarios PECHP verificados de #459, límites de la anticipación #460, y enlaces a las tres vistas existentes. Ningún caudal GloFAS se presenta aún como extraído.
- Fuentes gratuitas seleccionadas: Copernicus GloFAS histórico (caudal **modelado** diario, escorrentía y humedad); GloFAS forecast (pronóstico modelado diario, no servicio crítico de EWDS); JRC Monthly Water History (agua detectada mensualmente, no huella certificada de un episodio); NASA IMERG.
- La vista no se coloca en `site/`, no se publica, no dispara consultas a SENAMHI, y no añade umbrales o alarmas.

## Integración GloFAS de siguiente prioridad

1. **Autenticación gratuita** a Copernicus EWDS, si ya existe una cuenta compatible; no asumir credenciales y no utilizar tokens ajenos.
2. **Recorte pequeño y limitado**: ventana marzo–abril de 2017 y febrero–abril de 2023 para Piura, Puyango-Tumbes y Catamayo-Chira; producto `cems-glofas-historical`, descarga de variable caudal medio diario, con versión exacta, configuración y licencia. La interfaz fue actualizada en julio de 2026: inspeccionar esquema actual antes de usar API. No pedir toda América ni décadas completas de inicio.
3. Archivar bytes, SHA-256, fecha y metadatos. Asociar celdas de río solo cuando el área upstream y la topología sean consistentes con la estación; no elegir la celda cuya serie simplemente correlacione mejor.
4. Comparar serie GloFAS diaria con caudales PECHP diarios como dos clases distintas: observado (PECHP) y simulado (GloFAS). Medir sesgo, desfase y sensibilidad; no evaluar horizontes horarios con datos diarios.
5. Si GloFAS no se puede descargar por falta de credenciales o limitaciones de API, conservar `DATA_UNAVAILABLE`; no crear valores sintéticos presentados como caudal real.
6. Para vista avanzada sumar indicadores descriptivos de lluvia antecedente de 3/7/15 días y distribución espacial por subcuenca usando IMERG ya archivado; no convertir en probabilidades ni alertas.
7. Para huellas, inspeccionar JRC MonthlyHistory como contexto del agua visible 2017, con señal de agua estacional/normal y no inferir el polígono de inundación del 27 marzo de una observación mensual.
8. Para pronóstico histórico genuino, distinguir un pronóstico emitido antes del evento de una reanálisis publicada después; `GloFAS historical` **no es** pronóstico ex ante.

## Incertidumbres no negociables

- Falta caudal horario observado; horizontes de anticipación 3/6/12/24 h siguen `NO_EVALUABLE` conforme al protocolo v0.3. No interpolar medias diarias para fabricar horas.
- GloFAS es simulación hidrológica, no referencia independiente equivalente a un limnímetro.
- La operación de Poechos y el trasvase Chira–Piura no se reconstruyen a partir de precipitación.
- EWDS advierte que su servicio de descarga no está diseñado para usos críticos en tiempo real. En investigación no se afirma que un futuro aviso derive del EWDS de manera operativa.
- `production_use=false`, `activation_gate=BLOCKED`, `map_publishable=false`, `UNKNOWN_NOT_LOW_RISK`.

## Fuentes originales verificadas

- https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=overview
- https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview
- https://confluence.ecmwf.int/spaces/CEMS/pages/242067419/EWDS
- https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory
- https://www.gob.pe/21711-plataforma-hidrologica-phisis

## Criterio de entrega

Esta fase **sí entrega ahora** una vista avanzada de investigación que integra resultados existentes; **no** entrega caudal horario observado, nueva descarga GloFAS ni previsión validada. Quedan tareas de integración con fuentes gratuitas, revisables independientemente.
