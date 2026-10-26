# `research/gauge_imerg` · pluviómetro frente a IMERG, offline (RESEARCH_ONLY / TEST_ONLY)

Este paquete compara lecturas de pluviómetro con la celda IMERG de 0,1° que contiene cada estación. Reconstruye el acumulado satelital en la ventana exacta de cada lectura y lo evalúa. Una calibración experimental solo se intenta cuando la muestra real lo permite. El informe de esta iteración está en [`REPORT_2026-10-26.md`](REPORT_2026-10-26.md) y el issue de referencia es **#400**.

* Funciona **sin red**: las pruebas bloquean cualquier conexión. No descarga gránulos ni consulta SENAMHI, NASA o NOAA.
* Está **desacoplado del visor v0.9** (#388, #403): no lee ni escribe `site/` y no cambia umbrales, geometrías, probabilidades ni clasificaciones de riesgo.
* Una estimación satelital nunca se convierte en observación. Una ausencia de dato nunca se trata como cero, y un pronóstico nunca cuenta como lectura.

## Flujo

```
lecturas reales (registro JSON) ──┐
                                  ├─► pairing ─► pares + rechazos con motivo ─► evaluate ─► calibrate (con compuertas)
HDF5 IMERG locales ─► imerg_cells ┘                                    └─► station_validation_feed (contrato futuro)
historial git del archivo IRFEN ─► archive_manifest (lista exacta de gránulos de un episodio)
```

| Módulo | Función |
|---|---|
| `grid.py` | Malla V07 (centros −179,95 + 0,1·i y −89,95 + 0,1·j). Asigna la celda de cada estación con la regla semiabierta, marca las estaciones que caen en un borde (`ON_CELL_EDGE`), arma la vecindad 3×3 y comprueba los ejes leídos del archivo. |
| `granules.py` | Lee del nombre de archivo la corrida (Early, Late o Final), la versión, el intervalo de 30 min y su índice. Calcula las medias horas de una ventana. |
| `imerg_cells.py` | Lee HDF5 locales: valida `DimensionNames`, unidades mm/h, `_FillValue` y la hora interna, y registra el SHA-256 de cada archivo. La tasa × 0,5 h da el acumulado de la media hora. |
| `observations.py` | Decide si cada lectura sirve para uso **exploratorio**, de **métricas** o de **calibración** (detalle en la tabla de abajo). |
| `pairing.py` | Exige todas las medias horas de una sola familia de producto, sin rellenar huecos ni mezclar productos o subversiones. Registra latencia, vecindad 3×3, linaje y limitaciones conocidas. Exporta al CSV horario del piloto de #400 y al contrato `station_validation_feed`. |
| `evaluate.py` | Calcula sesgo, MAE, RMSE y razón de sumas. Calcula POD, FAR, CSI y FBI para la detección, la cuantificación (pares húmedos en ambas fuentes) y los extremos. Estratifica por estación, región, intensidad y duración. Da IC solo por bootstrap de días y solo cuando son defendibles. |
| `calibrate.py` | Compara la línea base cruda con un ajuste multiplicativo y un mapeo cuantílico. Divide por cronología con embargo, verifica que no haya solapes de ventanas y hace validación dejando una estación fuera. La regla de decisión está fijada de antemano. Si la muestra no alcanza, devuelve **BLOCKED**. |
| `archive_manifest.py` | Reconstruye, desde el historial git de `data/v09/rain/imerg_early_north_v0_1.json` (que solo guarda medias por polígono), qué gránulos existieron para cada media hora. |
| `run_pipeline.py` | Ejecuta todo de punta a punta y escribe un manifiesto con el SHA-256 de entradas, código y salidas (`--fixed-time` para reproducir byte a byte). |

### Clases de uso de una lectura

| Uso | Requisitos | Alcance |
|---|---|---|
| Exploratorio | Fuente atribuida al productor, ventana declarada, coordenadas verificadas y valor numérico no censurado. | Nunca entra en calibración. |
| Métricas | Además: fuente primaria u oficial, ventana exacta e identificador oficial de estación. | Evaluación de IMERG crudo. |
| Calibración | Además: control de calidad aprobado. Un valor extremo con QC solo provisional no basta. | Ajuste de correcciones. |

## Comandos

```bash
cd research/gauge_imerg
python -m pytest tests -v                      # o: cd tests && python -m unittest discover -p 'test_*.py'
python -m irfen_gauge_imerg.run_pipeline --ledger evidence/north_gauge_reports_2026-10-22_25_v1.json \
       --use calibration --out-dir /tmp/salida --fixed-time 2026-10-26T00:00:00Z
python -m irfen_gauge_imerg.archive_manifest --repo ../.. --since 2026-10-15 \
       --windows evidence/episode_windows_v1.json --out /tmp/manifiesto.json
# cuando existan HDF5 autorizados y coordenadas verificadas:
python -m irfen_gauge_imerg.imerg_cells --stations estaciones.json --out celdas.json gránulos/*.HDF5
python -m irfen_gauge_imerg.run_pipeline --ledger L.json --cells celdas.json --use metrics --out-dir salida/
```

`IRFEN_REQUIRE_H5PY=1` e `IRFEN_REQUIRE_JSONSCHEMA=1` convierten en error las omisiones de las pruebas de HDF5 y de esquemas; el CI propio (`.github/workflows/gauge-imerg-offline-tests.yml`) las activa. Las pruebas viven fuera de `tests/`, así que no alteran el manifiesto de colección de pytest de la validación de PR (`config/phase2_test_collection_manifest.json`).

## Contenido

* `evidence/`: datos **reales** con procedencia. Incluye el registro de 24 lecturas reportadas entre el 21 y el 26 de octubre, el registro de búsquedas, las ventanas del episodio y el manifiesto de gránulos IMERG Early reconstruido desde git.
* `reports/real_run_2026-10-26/`: salida de la ejecución real para cada clase de uso. Hay una prueba que la regenera y la compara.
* `examples/`: ejemplos **SINTÉTICOS** del contrato de datos, marcados con `SYNTHETIC: true`, y el script que los genera.
* `schemas/`: contratos versionados v1 en JSON Schema 2020-12. `station_validation_feed` es el formato propuesto para que un visor lo consulte en el futuro. Hoy no está activo.
