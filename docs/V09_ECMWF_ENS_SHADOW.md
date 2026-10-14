# IRFEN v0.9 — ECMWF ENS por provincia, costa norte (TEST_ONLY)

Fase 0 del modelo predictivo de lluvia a 72 h para el escenario El Niño 2026–2027. Corre **en modo sombra**:
archiva probabilidades para verificarlas contra lluvia observada; no alimenta alertas, el mapa ni GitHub Pages.

## Qué produce

Para cada corrida del ensamble ECMWF (51 miembros, datos abiertos CC BY 4.0) y cada una de las 26 provincias INEI
de Tumbes, Piura, Lambayeque y La Libertad:

| Campo | Significado |
| --- | --- |
| `p_max["10"]`, `["25"]`, `["50"]` | Fracción de miembros con **alguna celda** de la provincia ≥ 10 / 25 / 50 mm en el día |
| `p_mean[...]` | Fracción de miembros con la **media provincial** ≥ umbral |
| `q50_mean_mm` | Mediana del ensamble de la lluvia media provincial |
| `q90_max_mm` | Percentil 90 del ensamble de la lluvia máxima por celda |
| `cells`, `method` | Celdas de 0,25° usadas y cómo se eligieron (no se inventa resolución) |

Los días son ventanas de 24 h que cierran a las 12 UTC (07:00 en Perú), el cierre del día pluviométrico de las
estaciones de SENAMHI. `valid_date_peru` es la fecha de ese cierre.

Archivos (en `data/v09/forecast/`):

- `ecmwf_ens_provinces_north_v0_1.json`: última corrida, con las guardas `TEST_ONLY` y el estado (`AVAILABLE` /
  `UNAVAILABLE`). Una falla de descarga nunca se registra como lluvia cero.
- `ecmwf_ens_provinces_ledger_v0_1.jsonl`: una línea por corrida, solo agregado; es la base de la verificación.
- `ecmwf_ens_verification_v0_1.json`: puntajes, cuando existe el archivo de observaciones.

## Observaciones para verificar

`data/v09/forecast/observaciones_provincia_v0_1.csv`, una fila por provincia y día pluviométrico:

```csv
fecha_peru,idprov,lluvia_max_mm,lluvia_media_mm,fuente,n
2026-10-15,2001,12.4,5.1,SENAMHI estaciones,4
```

`idprov` es el código INEI de 4 dígitos. Una celda vacía o negativa es dato faltante y se excluye del par.
El máximo de pocas estaciones subestima el de la provincia, por lo que la detección medida es conservadora.

## Métricas

Por día de anticipación (1–3), umbral y definición (`max`/`mean`): Brier y BSS frente a la frecuencia base de la
muestra, POD/FAR/CSI para probabilidades de alerta 0,1 a 0,7 y tabla de fiabilidad. Con menos de 30 pares o sin
eventos, `enough_sample` es `false` y los puntajes son solo indicativos.

## Lo que esta fase no hace

No corrige sesgos con datos peruanos ni usa los índices E y C ni la TSM relativa: eso es la fase siguiente
(regresión logística sobre reforecasts). Esta fase fija la línea base a superar y acumula verificación de la
temporada en curso desde el primer día.
