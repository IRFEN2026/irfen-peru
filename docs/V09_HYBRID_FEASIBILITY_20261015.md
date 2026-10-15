# IRFEN — experimento acotado para pronóstico híbrido a 24/48/72 h
Fecha de apertura: 2026-10-15. Estado: PLAN DE INVESTIGACIÓN; NO es una mejora validada.
Rama aislada: `research/v09-hybrid-feasibility-20261015` (creada desde `v09/forecast-engine`).
**No fusionar en main; no tocar site/, no publicar probabilidades ni activar alertas o variables.**

## Diagnóstico documentado a partir del código y de los resultados existentes

1. En `scripts/v09_own_model.py`, `feature_row()` usa el estado atmosférico de `issue - 1 día`; no consume pronósticos de humedad, circulación o convección para cada día de validez futura.
2. `TRAIN_ORDER = ("no_atmos", "no_atmos_no_rain", "full", "no_rain")` prioriza variantes sin atmósfera en la predicción; el propio código declara que NCEP/NCAR R1 ya no es una entrada operacional útil.
3. El entrenamiento global `mu, sd = X.mean(axis=0), X.std(axis=0)` antecede a `_oof(...)` por temporada. Hay riesgo de *data leakage* en los puntajes de CV. Además, las climatologías se calculan para un intervalo completo y la selección del mejor conjunto (todos / Niño) se efectúa sobre resultados de CV de las mismas temporadas: hay que usar validación anidada y temporal antes de comparar modelos.
4. A partir del archivo `data/v09/model/modelo_propio_validacion_v0_1.json` en `v09/forecast-data`, en las 18 combinaciones de `max/mean × día 1/2/3 × umbral 10/25/50` y variante `no_atmos`, el BSS histórico evaluado **en temporadas Niño** es superior para `training_set=todas` frente a `training_set=nino`. No son 18 experimentos estadísticamente independientes: comparten fechas y etiquetas.
5. Los reforecasts NOAA GEFSv12 públicamente documentados en AWS cubren 2000–2019; la publicación científica describe un tramo 1989–1999 cuya disponibilidad y homogeneidad deben verificarse antes de usarlo. Nunca tratar una reanálisis de la fecha objetivo como un pronóstico emitido antes de esa fecha.

## Hipótesis contrastables (no asumir resultados)

- H1 — Pronósticos atmosféricos fechados **antes de emitir** (agua precipitable, humedad a 850/700 hPa, u/v 850 hPa y su convergencia de humedad, omega 500 hPa, CAPE/CIN cuando estén disponibles) mejoran el pronóstico 72 h frente al actual.
- H2 — Entrenar en todos los años y usar ENSO como predictor/regímen con interacción local supera entrenar exclusivamente en tres temporadas Niño.
- H3 — Calibración regional por costa baja/estribaciones y agregación con soporte espacial comparable mejora FAR sin perder POD.
- H4 — El efecto de MJO/ZCIT/TSM es incremental sobre el pronóstico meteorológico futuro; solo incluir esos índices si una ablación anidada demuestra beneficio.

## Contrato de datos e integridad

Una fila de pronóstico experimental debe incluir: `issued_at_utc`, `valid_start_utc`, `valid_end_utc`, `lead_hours`, `idprov` o subzona, `threshold_mm`, `support_grid`, `source_run_id`, `baseline_probability`, `candidate_probability`, `observation_mm`, `observation_source`, `observation_available_at_utc` y `features_manifest` con hora real de disponibilidad de cada predictor. El instante `available_at_utc` de cada predictor debe ser anterior o igual a `issued_at_utc`. La observación puede conocerse después pero **no** alimentar las variables del pronóstico. Descargas fallidas o muestras no comparables son `UNAVAILABLE`, nunca cero.

- Respetar día pluviométrico 07:00–07:00 PET (12–12 UTC), sin adelantar gránulos ni correr fechas de estaciones.
- Comparar siempre probabilidades y observaciones de **la misma celda/soporte**, ventana, provincia/subzona y umbral.
- Conservar versiones de descarga, licencia, fechas de corte y SHA del conjunto de datos.
- No usar `ERA5` del día objetivo como predictor futuro: sirve para diagnóstico o verificación, no simula el pronóstico disponible a la fecha de emisión.
- Los máximos provinciales `p_max` no equivalen a lluvia puntual ni activación de quebradas.

## Experimento de esfuerzo acotado (5 jornadas técnicas, sin garantía de finalización/calidad)

1. **Auditoría y referencias:** reproducir métricas históricas; recalcular escalado, imputación y calibración **dentro** de cada fold temporal; separar entrenamiento, ajuste de hiperparámetros y prueba independiente.
2. **Disponibilidad/homogeneidad:** confirmar acceso a GEFSv12 reforecast 2000–2019 y variables atmosféricas; levantar muestra pequeña de múltiples temporadas con sus horas de emisión, y probar correspondencia de GEFS/IMERG/PISCO. Si no hay datos comparables, registrar bloqueo y detener.
3. **Baseline justa:** regresión actual revalidada, climatología provincia×mes y GEFS/ECMWF crudos y calibrados cuando exista un hindcast comparable, siempre sobre los mismos pares. No comparar score de 1981–2016 con score de 4–11 octubre.
4. **Candidato:** regresión logística regularizada y, solo si aporta, árboles potenciados conservadores; H1/H2 primero, H3/H4 solo con datos suficientes. Calibración entrenada sin observar datos de test.
5. **Decisión:** tabla para leads 24/48/72 y ≥10/25/50 mm de Brier/BSS, POD, FAR, CSI, eventos y temporadas; intervalos bootstrap por *temporada completa*, análisis de fallo y regla CONTINUAR / CONGELAR / INCONCLUSO.

## Regla de decisión preregistrada

- **CONTINUAR** únicamente si el candidato mejora al baseline **calibrado** en Brier/BSS fuera de muestra sobre los mismos pares, y mejora la relación POD/FAR para lluvia intensa sin pérdida relevante de detección; exigir intervalos por temporada y suficiente número de eventos independientes.
- **CONGELAR** si no supera baselines o los avances son pequeños/inestables; redirigir esfuerzo a la línea A (mapa IRFEN v0.9).
- **INCONCLUSO** si faltan hindcasts comparables, episodios intensos o datos de estaciones; no presentar ese resultado como mejora ni como fracaso confirmado.
- Umbrales exploratorios de producto: 50 mm, POD ≥0.60 y FAR ≤0.40; 10 mm, POD ≥0.80 y FAR ≤0.30. **No** declararlos alcanzados; umbrales finales requieren decisión científica y operativa.

## Fuentes verificables

- NOAA GEFSv12 reforecast público (2000–2019): https://registry.opendata.aws/noaa-gefs-reforecast/
- Estudio NOAA de GEFSv12 (1989–2019, contrastar disponibilidad por fase): https://repository.library.noaa.gov/view/noaa/53301
- ECMWF Open Data, catálogo de variables de pronóstico: https://www.ecmwf.int/en/forecasts/datasets/open-data
- IRFEN: `scripts/v09_own_model.py` y `data/v09/model/modelo_propio_validacion_v0_1.json` en sus ramas aisladas.

## Estado de ejecución
15-oct: revisión de código y lectura de puntuaciones históricas realizadas. **No se han descargado reforecasts ni recalculado métricas corregidas**, y aún no hay una mejora cuantitativa nueva. El experimento no tiene cron ni trabajos automáticos.