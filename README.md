# IRFEN v0.9 — Resultados del motor de pronóstico (RESEARCH_ONLY / TEST_ONLY)

Rama huérfana: no comparte historia con `main`. La escriben solo los jobs `persist` de `v09-forecast-engine.yml` y
`v09-own-model-train.yml` de la rama `v09/forecast-engine` (ver `docs/V09_FORECAST_AUTOMATION.md` en esa rama), con
reglas de solo agregar: no se borra nada salvo `data/v09/obs_imerg/partial/` y los registros `*.jsonl` solo crecen.
Nada de aquí es una alerta ni se publica.

- `data/v09/forecast/`: registros de pronóstico de solo agregado (ECMWF ENS crudo, modelo propio) y evaluación.
- `data/v09/obs_imerg/`: lluvia observada IMERG Late por provincia y día pluviométrico (07:00–07:00 Perú).
