# Validación independiente del modelo propio (RESEARCH_ONLY / TEST_ONLY)

Scripts con que se midieron los resultados del informe científico del 15-10-2026. No forman parte del motor ni
de `main`; solo leen una copia de la rama de resultados y escriben JSON locales.

| Script | Qué mide |
| --- | --- |
| `analisis.py` | Probabilidades fuera de muestra (dejando fuera una temporada sep–ago) a 24, 48 y 72 h para ≥ 10, 25 y 50 mm, frente a una **climatología calibrada** por provincia × mes (estimada solo con las temporadas de entrenamiento). BSS con IC 90 % por bootstrap de temporadas, ROC, detección y falsas alarmas, fiabilidad; subconjuntos todas / Niño / costa / sierra / costa en Niño. |
| `ablacion.py` | Aporte de cada bloque de variables: aumento del Brier fuera de muestra al quitarlo, con IC 90 % pareado por temporadas. |
| `mismas_fechas.py` | Modelo propio vs ECMWF ENS crudo vs ECMWF calibrado en las mismas corridas, provincias y observación IMERG Late. El modelo propio se emite de forma retrospectiva solo con insumos fechados antes de cada emisión. |

## Cómo reproducir

```bash
git fetch origin v09/forecast-data
mkdir -p _data && git archive origin/v09/forecast-data data/v09 | tar -x -C _data
python3 analysis/v09_validacion/analisis.py
python3 analysis/v09_validacion/ablacion.py
python3 analysis/v09_validacion/mismas_fechas.py
```

Variables de entorno: `IRFEN_FC_DATA` (por defecto `_data`) y `IRFEN_REPORT_OUT` (por defecto `.`). Cada script
reutiliza el código del motor (`scripts/v09_own_model.py`) para construir las variables, así que mide exactamente lo
que el motor usaría. Tiempo aproximado con PISCO 1981–2016: 25–35 min por variante en un núcleo.
