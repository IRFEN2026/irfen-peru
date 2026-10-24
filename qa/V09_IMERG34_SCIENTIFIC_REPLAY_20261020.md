# IRFEN v0.9 — Reproducción científica independiente, muestra de IMERG Early v07

**Estado:** `PARTIAL_CATALOG_UNAVAILABLE` — NO APROBADO para integración científica. RESEARCH_ONLY / TEST_ONLY, `activation_gate=BLOCKED`.

Fuente de la ejecución: https://github.com/IRFEN2026/irfen-peru/actions/runs/39502276728

## Alcance y método

- Referencia: archivo de 34 gránulos recuperados (15 y 16-10-2026) en rama documental de #397.
- Selección reproducible: primer intervalo, último intervalo y dos con máxima tasa de lluvia por zona.
- Se efectuaron nuevas consultas a NASA CMR y descargas de los gránulos EXACTAMENTE identificados; no se sustituyó un HDF5 por otro.
- Para cada objeto descargado se contrastaron SHA-256 y tamaño con los del archivo congelado.
- Se recalcularon las estadísticas de las 22 zonas mediante un segundo algoritmo de media ponderada por superficie de intersección de cada celda, sin llamar a la función de agregación original `probe.polygon_mean`.
- No se utilizaron nuevas observaciones en el mapa, motor, alertas ni en archivos en vivo.

## Resultado verificable

| Intervalo UTC | Resultado |
|---|---|
| 15-10 09:30 | HDF5 recuperado de nuevo, SHA-256 idéntico (`bbe554ba…`), 22/22 zonas coinciden, 0 diferencias |
| 15-10 22:30 | HDF5 recuperado de nuevo, SHA-256 idéntico (`7b13d324…`), 22/22 zonas coinciden, 0 diferencias |
| 16-10 13:00 | Gránulo exacto `3B-HHR-E.MS.MRG.3IMERG.20261016-S130000-E132959.0780.V07C.HDF5` no identificado de manera única por consulta actual de CMR; consulta acotada devolvió 1 candidato sin coincidencia exacta. NO se descargó ni sustituyó |
| 16-10 23:30 | Gránulo exacto `3B-HHR-E.MS.MRG.3IMERG.20261016-S233000-E235959.1410.V07C.HDF5` no identificado de manera única por consulta actual de CMR; consulta acotada devolvió 1 candidato sin coincidencia exacta. NO se descargó ni sustituyó |

**Cobertura:** 2/4 HDF5 reproducidos; 44/44 estadísticas zona-intervalo coinciden para los dos reproducidos; 0 diferencias numéricas observadas. **La muestra 4/4 NO está validada**.

### Interpretación científica

Los 44 resultados confirmados respaldan la equivalencia de cálculo sobre dos gránulos, pero NO permiten declarar validados los 34 intervalos ni los dos gránulos que no se identificaron. La discrepancia restante es **identidad/disponibilidad de catálogo**, no una diferencia de precipitación demostrada. Una coincidencia en la marca temporal sin coincidencia exacta de título/gránulo no autoriza sustitución.

### Próximas comprobaciones, sin activar más procesos automáticamente

1. Investigar los metadatos de esos dos intervalos: `concept_id`, título exacto, versión y fecha de actualización en CMR; registrar la respuesta y su SHA-256.
2. Determinar si el catálogo presenta una nueva revisión del archivo o una discrepancia temporal de indexación. No descargar un candidato distinto sin validarlo documentalmente.
3. Si se demuestra identidad de bytes/versiones, completar la muestra 4/4; de otro modo conservar `UNKNOWN`.
4. Solo después considerar una muestra más amplia para concluir sobre los 34 intervalos.

**Evidencias:** artefacto `scientific-replay-four-HDF5` del run enlazado. No se guardan HDF5 y no hay ninguna activación de producción.
