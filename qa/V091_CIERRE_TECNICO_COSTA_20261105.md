# IRFEN v0.9.1 — cierre técnico reproducible de la costa

**Revisión:** 5 de noviembre de 2026. **Cobertura:** Tumbes–Tacna, 11 departamentos y cuencas que desembocan en la costa, incluidas cabeceras extranjeras relevantes. Excluidas las vertientes amazónica y Titicaca.

**Estado de activación:** RESEARCH_ONLY / TEST_ONLY; activation_gate=BLOCKED; sin alertas, semáforo predictivo, mensajes ni publicación general.

## Implementación realizada

1. Nuevo auditor offline (scripts/v09_coast_closeout.py) sobre archivo IMERG Early ya archivado para 134 áreas aportantes. Comprueba secuencia de media hora, geometría de cobertura, valores nulos, fecha futura, duplicados, antigüedad y validez de ventanas observacionales 1/3/6/12/24/72 horas. **No descarga NASA, no imputa ceros y no pronostica caudales.**
2. Genera un archivo privado temporal de evidencias **derivadas** del último gránulo de cada área, usando el ledger de temporada ya existente (#491/#492). Cada registro conserva identificación de muestra, tasa, cobertura, fuente y SHA; la hora de incorporación es actual y nunca retrodatada. La hora de recuperación archivada representa una cota conservadora de disponibilidad conocida, no publicación oficial. El QC queda UNVERIFIED y no se permite convertir estimación de precipitación en verdad-terreno hidrológica.
3. Un evaluador opcional rechaza filas con datos futuros o sin observación independiente y ofrece MAE descriptivo frente a línea base solo con al menos 30 pares subdiarios bien fechados. Nunca declara skill operativo; aún faltarían evaluación independiente por eventos y falsas alarmas. Sin datos, NO_EVALUABLE.
4. Auditor de diferencias geográficas por sección con distribución de puntos en los 11 departamentos, discrepancias HydroSHEDS/HydroRIVERS y puntos sin cuenca. **No corrige geometría sin evidencia.**
5. CI de cierre en GitHub Actions que recupera únicamente el archivo existente en main (lectura), ejecuta pruebas y construye reporte temporal con guardas obligatorias. No sube el paquete ni modifica main.

## Hallazgos comprobados previamente en main

- 134 cuencas y 181 intervalos archivados. Último inicio disponible 2026-11-05 01:30 UTC; escrito a las 06:59 UTC.
- Hueco entre 00:30 y 01:30 UTC del 5 de noviembre: falta la media hora de 01:00. Por tanto, las ventanas terminadas en el último gránulo que cruzan ese hueco son incompletas, aun si la cobertura espacial es 100%.
- Auditoría independiente #486: 32 discrepancias de área >1%, entre ellas Supe Alto (-34,8%), La Leche Alto (-19%) y Caplina Alto (-12,3%). Cuatro puntos fluviales sin cuenca asociada evaluable. Concordar con HydroRIVERS no equivale a validación independiente.
- PR #487 contiene asociaciones históricas diarias descriptivas en Chira/Piura, no demostración de anticipación en tiempo real ni desbordes.
- No hay series subdiarias independientes y fechas de publicación verificadas para demostrar habilidad de predicción a 1/3/6/12/24 horas. Tampoco evaluación de activaciones reales de quebradas ni falsas alarmas.

## Uso privado

Ejecutar desde la raíz de la rama:

1. python -m unittest -v tests/test_v09_coast_closeout.py tests/test_v09_coastal_season_ledger.py
2. python scripts/v09_coast_closeout.py --archive data/v09/rain/imerg_early_catchments_v0_1.json --hydrology data/v09/research/semaforo/checkpoint_hydrology_v0_1.json --ledger-dir /tmp/irfen-derived-ledger --report /tmp/irfen-closeout.json --as-of FECHA_ACTUAL_UTC_CON_Z

El JSON contiene las ventanas completas/incompletas, edad de observaciones, diferencia geográfica, estado causal de evaluación y blockers. El directorio /tmp es privado y efímero, no un despliegue. No considerar el ledger un almacenamiento WORM certificado.

## Puertas para cerrar los cinco frentes

| Frente | Hecho | Falta para darlo por concluido |
| --- | --- | --- |
| Continuidad de lluvia | Identificación programática de huecos y bloqueo de ventanas | Recuperar el verdadero gránulo NASA 01:00 UTC, si existe legalmente, o conservar SIN DATO. No inventar series. |
| Archivo de observaciones | Conector offline de valores NASA derivados, trazables y no retrodatados | Reconstrucción de temporadas completas, versión de fuente y mediciones independientes verificadas; automatización supervisada. |
| Predicción | Evaluador causal y comparador de línea base preparado | Validar por eventos con niveles/caudales/activaciones independientes; errores, falsas alarmas y anticipación efectiva a cada horizonte. |
| Geografía | Clasificación de las 32 discrepancias y cuatro excluidos | Comprobación documental/espacial de sección y red fluvial, comenzando por tres >10%. |
| Visor | Hereda integración privada #472 y suma auditoría de entrega | Smoke test de todo el artefacto consolidado, acceso privado seguro y aprobación técnica. No publicación pública. |

**Dictamen:** la ingeniería puede entregarse como prototipo experimental con incertidumbre visible, pero NO se aprueba cierre predictivo hasta demostrar habilidad frente a observaciones y líneas base independientes. Mantener activation_gate=BLOCKED.
