# IRFEN · Piloto Piura de calibración pluviómetro vs. IMERG (solo investigación)

Inicio: 2026-10-21. Aprobación del propietario: **iniciar piloto de correlación SENAMHI–IMERG y evaluar redes alternativas con datos reales de lluvia**.

**Estado:** fase preparatoria. **No** se han obtenido aún pares reales de lluvia estación–IMERG co-localizados y no hay métricas de mejora. Mantener `RESEARCH_ONLY / TEST_ONLY`, `production_use=false`, `operational_alerting_enabled=false`; no unir con motor de pronóstico línea B; **no publicar, fusionar o crear cron de consulta**.

## Descubrimientos verificados y límites

### A. WIS 2.0 / OMM (SENAMHI como productor)
- Metadatos públicos: https://wis.senamhi.gob.pe/oapi/collections/discovery-metadata/items/urn%3Awmo%3Amd%3Ape-senamhi%3Asynop-hourly?f=html
- Colección de estaciones (31 según índice público): https://wis.senamhi.gob.pe/oapi/collections/stations/items?f=html
- Colección de observaciones horarias: https://wis.senamhi.gob.pe/oapi/collections/urn%3Awmo%3Amd%3Ape-senamhi%3Asynop-hourly?f=html
- Registros de estaciones visibles en catálogo: CHULUCANAS (WIGOS `0-604-1-08602104`), LANCONES (`0-604-1-07610101`), PAIMAS (`0-604-1-09615102`) y TONGORRAPE (`0-604-1-09582002`). **Catálogo operativo no garantiza sensor de precipitación ni lectura actual**. Los ejemplos indexados de observaciones son de julio de 2025.
- Consultas de exploración web al endpoint realizadas el 21-oct no respondieron antes de timeout: **NO VERIFICADA** disponibilidad de registros recientes. El acceso puede requerir concertación con SENAMHI para volumen y frecuencia, aunque los metadatos se declaren `wmo:dataPolicy=core`.
- Por decisión de seguridad previa IRFEN, **NO habilitar llamadas automáticas a dominio SENAMHI, ni el de WIS2**, hasta autorización expresa y acuerdo sobre cumplimiento de restricciones. Una ruta WIS2 independiente de la interfaz visual NO deja de ser acceso a SENAMHI.

### B. WeatherLink / Davis (estaciones de terceros)
- Documentación de API v2: https://weatherlink.github.io/v2-api/
- Lecturas reales si la estación tiene pluviómetro habilitado, ubicación/horario y permiso explícito del dueño o plan aplicable. NO asumir existencia ni acceso a estación en Piura. Probar una vez identificados propietarios y permisos, sin credenciales en repositorio.

### C. Proyecto Especial Chira-Piura / Gobierno Regional
- Datos abiertos https://www.datosabiertos.gob.pe/dataset/datos-hidrometereol%C3%B3gicos-gobierno-regional-piura
- Portal https://servicios.regionpiura.gob.pe/datosh y diarios https://servicios.regionpiura.gob.pe/datosh/detalle
- Registro público incluye precipitaciones, pero es principalmente **diario**, no evidencia de API horaria o entrega real-time. Corroborar fecha más reciente, licencia y centros de medición.

### D. Aeropuerto Piura / METAR (independiente de infraestructura SENAMHI)
- Portal estadounidense de METAR global: https://aviationweather.gov/data/api/ ; estación SPUR/Piura, con archivo de IEM https://mesonet.agron.iastate.edu/sites/hist.phtml?network=PE__ASOS&station=SPUR
- La tabla IEM de octubre 2026 indica `Precip: M` (missing) para el 19-oct, **no hay mm confirmados** vía este medio. METAR puede mostrar "RA" sin acumulado físico; NO convertir RA en milímetros ni 0.
- No sustituye a series pluviométricas verificadas, pero puede marcar episodios para control cruzado.

### E. Satélites auxiliares
- NASA IMERG Early/Late y JAXA GSMaP son estimaciones, no otra referencia de pluviómetro. JAXA confirma cambio de versión en 2026; NO usar v7 para estimaciones actuales, consultar v8/catálogo oficial. No usar satélites como verdad terreno.

## Contrato mínimo de un par válido de observaciones
- Estación id/WIGOS, nombre, fuente autorizada, lat/lon, altura, clase de sensor, hora real de observación, intervalo de acumulación (UTC), mm, fecha de recepción y calidad/flag.
- IMERG V07 Early/Late identificando gránulos HDF5, versión, SHA, centro y contorno **de la celda 0.1° que contiene la estación**, tiempo UTC de cada granulo, mm por cada media hora, cobertura completa del intervalo y fecha de disponibilidad.
- Un registro de estación puntual **no** es comparable automáticamente al promedio de toda la provincia. La celda satelital (~10 km) tampoco describe exactamente el pluviómetro; informar soporte y representatividad.
- Distinguir dato en cero (observación válida 0 mm), `MISSING` y `NOT_REPORTED`; controles de rango y duplicados; ventanas de 60 min deben sumar 2 medias horas.
- En observaciones SYNOP, *comprobar* que el campo `precipitation` especifica acumulación, periodo y unidades; algunos reportes no incluyen precipitación.

## Diseño piloto y decisiones
1. Seleccionar estaciones: ciudad Piura (si hay acceso), Chulucanas, Lancones, Paimas y estaciones PECHP (según datos disponibles). Inventariar coordenadas, instrumento, periodicidad y fecha del último dato real; sin suposiciones.
2. Autorizar proveedor(es) y consumo bajo límites documentados; prueba manual o fuente aportada por propietario antes de automatización. Reservar salida en un área de archivo científico privada cuando proceda; repositorio público **solo metadatos y código, nunca credenciales ni datos no licenciados**.
3. Obtener datos de estaciones de **al menos distintas semanas con lluvia y sin lluvia**; archivo IMERG de celda co-localizada con doble comprobación de hora y de fuente.
4. Evaluar IMERG crudo con MAE, RMSE, sesgo, r de Pearson solo si varianza suficiente, POD, FAR en umbrales, cobertura y latencia. Separar escenarios sin lluvia / lluvia moderada / lluvia fuerte.
5. Calibración experimental: ajuste simple de sesgo y un segundo método regularizado; entrenar únicamente en semanas/temporadas anteriores, bloquear prueba por fechas y (si hay estaciones suficientes) evaluar estación no vista. Exigir mejora de MAE y detección sin aumentar falsas alarmas. No prometer ratio.
6. Si no se obtiene lluvia real fechada, **estado BLOQUEADO_POR_FUENTE**, no entrenar ni presentar correlación ficticia. Si se obtiene solo PECHP diario, validar a día hidrológico 07:00–07:00 PET, no mezclarlo con acumulaciones hora UTC distintas.

## Entregable y criterios
Un inventario de fuentes con latencia y condiciones, tabla de pares válidos, métricas `IMERG_CRUDO` vs. `CORREGIDO` con datos de test temporal y análisis del episodio 19-oct. Siempre mostrar n estaciones, n días, n lluvias y CI para evitar falsos avances.

**Estado de ejecución inicial:** catálogo de fuentes contrastado; rama de código independiente preparada. A 21-oct no se ha establecido feed de pluviómetros con mm actuales ni mediciones coincidentes. No han sido efectuadas solicitudes HTTP a ningún host SENAMHI desde workflows.
