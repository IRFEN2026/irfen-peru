# IRFEN v0.9.1 · Auditoría científica independiente (09-11-2026)

RESEARCH_ONLY / TEST_ONLY. Esta auditoría no modifica el visor, el actualizador, el semáforo ni el capturador. **Ninguna asociación queda validada científicamente porque sus pruebas de software pasen.**

**Ramas:**
- `research/v091-scientific-audit-20261109`: esta auditoría, sobre la rama de integración `27aa0c80`.
- `research/v091-p0-496-hdf5-reconstruction-20261109`: incidente #496, sobre main.

**Reproducir:**
- Hidrología:
  ```
  python3 scripts/v091_audit_checkpoint_catchments.py \
    --catchment-archive <main:data/v09/rain/imerg_early_catchments_v0_1.json> \
    --geometry-config <main:config/v091_catchment_rain_targets_v0_1.json> \
    --evaluated-at 2026-11-09T15:00:00Z
  ```
  Salida: `data/v09/research/audit/checkpoint_catchment_audit_v0_1.json`.
- #496: `scripts/v091_p0_496_hdf5_reconstruction.py` (ejecución [42638351230](https://github.com/IRFEN2026/irfen-peru/actions/runs/42638351230)).

## Matriz de hallazgos

| ID | Sev. | Hallazgo | Evidencia | Causa raíz | Acción | Estado |
|---|---|---|---|---|---|---|
| A1 | **P0** | IMERG Early subestima la lluvia puntual de Tumbes del 04–05/11. La media de cuenca no representa la lluvia costera | 48 HDF5 V07C originales. Píxel (celda compatible más favorable) frente a lo reportado: Rica Playa 36,9/112,5 · Cabo Inga 18,7/90,1 · Cañaveral 59,6/88,9 · La Cruz 35,0/75,0 · Matapalo 8,7/10,4 mm. Σ IMERG/Σ reportado = 0,42 (n = 5; los valores son de prensa) | Limitación del producto (convección localizada, morphing IR; máximo de IMERG 2–4 h después) y soporte espacial: el 73 % de la cuenca del Tumbes está en Ecuador, con 0–5 mm | Documentado. Sin calibración (un solo evento, datos de prensa). Recomendación al visor (línea de ChatGPT): no presentar la lluvia IMERG baja como ausencia de lluvia intensa y separar lo estimado, lo instrumental, los avisos y lo desconocido | Diagnosticado; mitigación en el visor **pendiente** |
| A2 | — | ¿Error de procesamiento de IRFEN en #496? **No** | Lectura de producción = lectura h5py independiente en las 48 medias horas (diferencia 0). Recálculo de 156 medias areales frente a lo archivado: Δ máx 0,0002 mm. Mismos nombres de gránulo. Unidades `mm/hr`, ×0,5 y orientación `time,lon,lat` verificadas | — | Prueba de regresión sintética de orientación y unidades, más la ejecución real | **Cerrado: correcto** |
| A3 | P1 | Frescura del archivo IMERG por cuenca | Último gránulo el 09-11 a las 01:30Z; a las 15:00Z tiene 12,9 h, es decir, **caducado**. Escrituras en main desde el 03-11: mediana cada 5,6 h, máximo 15,3 h (04-11 03:23Z → 18:41Z, justo al inicio del evento de #496). Retraso al escribir: 4,5–10,1 h | El cron de GitHub no respeta los 30 min | Reloj externo (#373) o encadenar la actualización tras la captura: **requiere autorización** | Bloqueado (autorización) |
| A4 | P1 | Ciclo en vivo del visor detenido | Último ciclo en `research/v091-live-data`: 08-11 20:48Z. A las 15:00Z del 09-11 lleva unas 18 h sin ciclo | La cadena de 20 min estaba autorizada hasta el 09-11 | Decidir si se prorroga (usuario) | Pendiente de decisión |
| A5 | P1 | Validación de PR fallida en #498 y #499 | `verify_phase2_test_collection`: 19 y 8 identificadores de prueba nuevos no figuran en el manifiesto | Faltó regenerar el manifiesto en el runner fijado | Regenerarlo en el runner (procedimiento documentado), sin tocar las pruebas | Corregible; PR de corrección aparte |
| H1 | P2 | La afirmación «HydroRIVERS ±1 %» era imprecisa (#486: 32 de 134 superan el 1 %) | Áreas D8 en los extremos de cada tramo HydroRIVERS:<br>• 122 puntos dentro de su tramo;<br>• 4 aguas arriba del inicio del tramo asociado (`LIM-R-SUPE-ALTO` 0,65, `TAC-R-CAPLINA-ALTO` 0,88, `LAM-R-ZANA-ALTO`, `ANC-R-PATIVILCA-ALTO`);<br>• 8 sin tramo a ≤ 1 km;<br>• **0 en otro río y 0 incoherentes** | UPLAND_SKM es el área en la salida del tramo. Comparar con un punto a mitad de tramo, o aguas arriba de la confluencia que abre el tramo, da cocientes menores que 1 | Clasificación por posición incorporada. HydroSHEDS e HydroRIVERS comparten linaje: es consistencia interna, no validación | Explicado |
| H2 | P3 | Conectividad aguas arriba → aguas abajo | 89 de 89 pares consecutivos: el camino D8 desde cada punto pasa por la celda del siguiente | — | Prueba de regresión | Correcto |
| H3 | P2 | `TUM-R-ZARUMILLA-MEDIO` sin área | Cauce principal modelado a 1,37 km (840 km²). El 49 % de los vértices IGN del tramo se separan más de 0,5 km | Río fronterizo: la línea IGN 1:500.000 y el cauce SRTM divergen | Mantener `NO_VERIFICADA`. Opción: elegir otro vértice IGN del sector medio que esté sobre el cauce modelado, con revisión | Abierto (decisión de método) |
| H4 | P2 | `LIM-R-RIMAC-ALTO`: posible **falso negativo** | A 0,15 km del vértice hay un cauce modelado de 171 km² que drena al Rímac medio. El criterio de «cauce dominante» eligió uno de 414 km² a 1,54 km | La regla de ajuste prefiere el cauce mayor de la ventana | Mantener `NO_VERIFICADA` hasta revisión experta: identificar qué cauce es el Rímac en IGN y en la cartografía ANA | Abierto (revisión experta) |
| H5 | P2 | `ARE-R-TAMBO-BAJO` sin área | Cauce principal a 1,09 km (12 881 km²), apenas por encima del umbral de 1,0 km. Mediana de desvío de la línea IGN en ese tramo: 1,08 km | Generalización 1:500.000 en un valle ancho | Mantener. No relajar el umbral para un caso concreto | Abierto |
| H6 | P2 | `ICA-R-SAN_JUAN-BAJO` inconsistente | El vértice (brazo Matagente) está a 4,75 km del cauce principal modelado | Delta bifurcado | Correctamente marcado | Confirmado |
| H7 | P2 | Tramo inferior del Piura | El punto bajo está sobre el cauce principal (0,08 km). El extremo inferior de la línea IGN 3504 está a 30 km de la salida D8 (Sechura); el 23 % de los vértices de la línea se separan más de 0,5 km | La línea 1:500.000 no sigue la desembocadura modelada en el bajo Piura | Orientación por línea: no verificada. El anidamiento este ⊂ centro ⊂ oeste está comprobado. Renombrar los sectores solo tras revisión | Abierto |
| H8 | P3 | 398 poblaciones ANA | 0 con área, celda D8, contorno o referencia de lluvia `catchment:`. Su lluvia es `cell` (335), `zone` (50) o ninguna (13) | — | Prueba de regresión | **Correcto** |
| D1 | P3 | Integridad del archivo IMERG por cuenca (main, `c72b4ad9`) | 182 gránulos; sin duplicados, huecos ni fechas futuras; 134 objetivos = configuración SHA-bloqueada; cobertura del 100 %; sin nulos. Desde el 30-10 16:00Z, ninguna media hora perdida de forma permanente | — | Pruebas adversariales sintéticas (duplicado, hueco, futuro, fila malformada, nulo con cobertura, caducidad) | Correcto (salvo la frescura, A3) |
| D2 | P2 | Coordenadas de estaciones a 0,1° | Atlas SENAMHI: cada punto cae en una esquina de la rejilla IMERG (2×2 celdas posibles) | Metadatos públicos redondeados | Se informa el rango y no se elige una celda. Hacen falta los metadatos originales | Bloqueado (datos) |

## Cobertura costera (último ciclo en vivo, 08-11 20:48Z)

| Departamento | Puntos | Ríos con área aportante / ríos | Ríos con lluvia de cuenca en vivo | Poblaciones ANA | Lluvia ANA | Validación instrumental |
|---|---:|---:|---:|---:|---|---|
| Tumbes | 24 | 5/6 | 5 | 18 | celda o ninguna | **NO** (#496: IMERG subestima) |
| Piura | 54 | 6/6 | 6 | 48 | celda o ninguna | NO |
| Lambayeque | 39 | 9/9 | 9 | 30 | zona o celda | NO |
| La Libertad | 63 | 10/10 | 10 | 53 | zona o celda | NO |
| Áncash | 68 | 24/24 | 24 | 44 | celda o ninguna | NO |
| Lima | 100 | 29/30 | 29 | 70 | celda | NO |
| Callao | 2 | 2/2 | 2 | 0 | — | NO |
| Ica | 46 | 11/12 | 11 | 34 | celda o ninguna | NO |
| Arequipa | 83 | 23/24 | 23 | 59 | celda o ninguna | NO |
| Moquegua | 29 | 6/6 | 6 | 23 | celda | NO |
| Tacna | 28 | 9/9 | 9 | 19 | celda | NO |

- **Cobertura administrativa:** 11 de 11 departamentos.
- **Cobertura hidrográfica:** 134 de 138 ríos (experimental).
- **Cobertura de datos:** 134 ríos con IMERG por cuenca. En el momento de esta auditoría el dato está caducado (A3).
- **Validada:** 0. No hay caudal o nivel, ni eventos contrastados, ni estaciones verificadas.

## Qué falta para considerar validada una asociación

1. Una sección hidrométrica (ANA o SENAMHI) en o cerca del punto, con su área oficial publicada.
2. Contraste con las unidades hidrográficas oficiales ANA al nivel del punto.
3. Eventos fechados (crecida o no crecida) con lluvia de cuenca y respuesta medida.
4. Para la lluvia: pluviómetros originales con control de calidad e independientes por evento, y un período de evaluación separado del de cualquier ajuste.
