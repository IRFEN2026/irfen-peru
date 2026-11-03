# IRFEN v0.9.1 — Hallazgos de auditoría científica independiente (03-11-2026)

**Estado:** RESEARCH_ONLY / TEST_ONLY. No se han modificado el capturador, el semáforo, las reglas de peligro, la publicación ni los correos.

**Evidencia reproducible:** [GitHub Actions #41657305009](https://github.com/IRFEN2026/irfen-peru/actions/runs/41657305009). Se ejecutó el auditor en el inventario experimental de 536 checkpoints de la rama v0.9.1 y contra los datos IMERG y la geometría SHA-bloqueada de `main`: 134 cuencas, 170 gránulos, último inicio 2026-11-03 04:30 UTC. Diez contrapruebas superadas, cero errores bloqueantes y **32 asociaciones con diferencias >1% en el contraste de área HydroSHEDS/HydroRIVERS**.

## Interpretación científica

La validación informática y el anidamiento D8 no equivalen a una validación hidrológica observacional. El cociente `area_km2 / hydrorivers.UPLAND_SKM` compara una delimitación HydroSHEDS en el checkpoint con un área publicada en un tramo HydroRIVERS seleccionado por proximidad. La proximidad no demuestra identidad de sección hidráulica, y ambas capas comparten linaje científico: **no son dos evidencias completamente independientes**. Por ello, las discrepancias son señales para revisión, no pruebas automáticas de error ni justificación de un aviso de crecida.

La afirmación previa «134 puntos coinciden ±1 % con HydroRIVERS» queda **rectificada**: 32 difieren más de ese margen (24 %). Los otros 102 tampoco quedan científicamente validados solo por concordar en área.

## Prioridad alta: diferencia de área superior al 10 %

| Checkpoint | Cociente HydroSHEDS / HydroRIVERS | Diferencia aproximada |
| --- | ---: | ---: |
| LIM-R-SUPE-ALTO | 0,652 | −34,8 % |
| LAM-R-LA_LECHE-ALTO | 0,810 | −19,0 % |
| TAC-R-CAPLINA-ALTO | 0,877 | −12,3 % |

Revisar en primer término si el `HYRIV_ID` usado corresponde a la misma confluencia y sector, si el ajuste al cauce modelado desplazó el checkpoint aguas arriba, si hay bifurcaciones/trasvases o discrepancias de escala. Conservar la asociación como **experimental pendiente de revisión**, no corregir el área arbitrariamente.

## Otras discrepancias para revisión

| Checkpoint | Cociente |
| --- | ---: |
| LAM-R-ZANA-ALTO | 0,939 |
| TUM-R-ZARUMILLA-ALTO | 0,941 |
| LIB-R-VIRU-MEDIO | 0,988 |
| LIB-R-HUAMANZANA-MEDIO | 0,974 |
| ANC-R-NEPENA-BAJO | 0,982 |
| ANC-R-SECHIN-MEDIO | 0,977 |
| ANC-R-CULEBRAS-MEDIO | 0,969 |
| ANC-R-HUARMEY-ALTO | 0,975 |
| ANC-R-HUARMEY-MEDIO | 0,976 |
| ANC-R-PATIVILCA-ALTO | 0,958 |
| LIM-R-FORTALEZA-ALTO | 0,981 |
| LIM-R-SUPE-BAJO | 0,950 |
| LIM-R-CHANCAY_HUARAL-ALTO | 0,920 |
| LIM-R-CHILLON-ALTO | 0,980 |
| LIM-R-CHILLON-MEDIO | 0,966 |
| LIM-R-LURIN-BAJO | 0,988 |
| LIM-R-MALA-ALTO | 0,963 |
| LIM-R-CANETE-ALTO | 0,972 |
| ICA-R-SAN_JUAN-ALTO | 0,981 |
| ARE-R-ACARI-MEDIO | 0,986 |
| ARE-R-CHAPARRA-MEDIO | 0,988 |
| ARE-R-ATICO-ALTO | 0,988 |
| ARE-R-ATICO-MEDIO | 0,963 |
| ARE-R-CHILI_VITOR_QUILCA-ALTO | 0,984 |
| MOQ-R-OSMORE-MEDIO | 0,985 |
| MOQ-R-TAMBO-ALTO | 0,989 |
| TAC-R-LOCUMBA-ALTO | 0,986 |
| TAC-R-CAPLINA-MEDIO | 0,905 |
| TAC-R-CAPLINA-BAJO | 0,987 |

## Asociación de lluvia IMERG

El auditor comprueba:
- Correspondencia exacta y orden de los identificadores del archivo y de la configuración.
- SHA-256 de la geometría contra la configuración de `main`.
- Ventanas como secuencias UTC de media hora; cobertura por cuenca; valores nulos no se convierten en ceros.
- Validación espacial y temporal de los vectores (rate_mm_hr, covered_pct), duplicados y rangos físicamente imposibles.
- Conteo de cuencas con ventanas completas de 1, 3, 6, 24 y 72 horas (nuevo chequeo).
- Rechazo de parámetros de producción/alertas o de un checkpoint no fluvial sin área aportante delimitada.

**No prueba:** correlación meteorología–caudal, desfases de propagación de onda, operación real de embalses, exactitud absoluta del satélite, habilidad predictiva, falsos positivos/negativos ni observación de crecida. El criterio de solape 80 % / 80 % es geométrico, **no un umbral calibrado de peligro**.

## Casos específicos que siguen pendientes

- `TUM-R-ZARUMILLA-MEDIO`: distancia IGN al cauce modelado >1 km.
- `LIM-R-RIMAC-ALTO`: distancia IGN al cauce modelado >1 km.
- `ARE-R-TAMBO-BAJO`: distancia IGN al cauce modelado >1 km.
- `ICA-R-SAN_JUAN-BAJO`: brazo de delta no conectado al conjunto aguas arriba.
- Orientación de la línea IGN del Piura bajo: no sustituir con un supuesto de dirección sin contraste adicional.
- Los 398 checkpoints de población ANA describen exposición documental y NO implican geometría verificada de una quebrada.

## Siguiente ciclo de investigación

1. Inspección por sección de los tres casos >10 %: puntos IGN, celda D8, cauce HydroRIVERS, `HYRIV_ID` y confluencias.
2. Selección de muestra estratificada de las otras 29 discrepancias y de tres asociaciones de control que sí coinciden.
3. Reproducir IMERG desde gránulos HDF5 y ponderaciones poligonales, incluyendo controles nulos y de cobertura parcial.
4. Evaluar respuesta histórica independiente (eventos, caudal/nivel, fecha, tiempos de tránsito, negativas) antes de cualquier regla naranja.

**Ninguna de estas tareas autoriza activar semáforo predictivo, alertas, correos o exposición pública.**
