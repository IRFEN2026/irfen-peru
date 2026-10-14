# IRFEN v0.9 — Correspondencia espacial y temporal entre ECMWF, IMERG y SENAMHI

RESEARCH_ONLY / TEST_ONLY. Este documento fija qué se compara con qué al verificar el pronóstico de lluvia de la
costa norte, y qué **no** se puede concluir de esa comparación.

## 1. Las tres fuentes

| Fuente | Soporte espacial | Resolución temporal | Latencia aproximada | Qué representa |
| --- | --- | --- | --- | --- |
| ECMWF IFS ENS, datos abiertos | Celda de 0,25° (~27,7 × 27,6 km ≈ 765 km² a 5° S) | Acumulado desde el inicio, pasos de 3 h | Horas tras la hora de inicio | Lluvia media de la celda simulada por cada miembro |
| IMERG Late V07 (`GPM_3IMERGHHL`) | Celda de 0,1° (~11 km, ≈ 123 km²) | 30 min | ~14 h | Estimación satelital de la lluvia media de la celda |
| Estación convencional SENAMHI | Punto (pluviómetro) | 24 h, lectura a las 07:00 | Variable; requiere captura | Lluvia en un punto |

IMERG es una estimación, no una medición: en la costa desértica y en laderas andinas puede fallar en lluvias cálidas
de poca altura y en chubascos muy locales. Por eso se usa IMERG Late (no Early) para verificar, y las estaciones
SENAMHI se incorporan como contraste en cuanto exista su captura diaria.

## 2. Correspondencia temporal: un único día pluviométrico

Todo se lleva al **día pluviométrico D = 12:00 UTC de D−1 → 12:00 UTC de D (07:00 → 07:00 en Perú)**, el cierre
de lectura de las estaciones convencionales.

- ECMWF: ventanas de 24 h que cierran a las 12 UTC; con corrida de 00 UTC son los pasos 12–36, 36–60 y 60–84 h; con
  12 UTC, 0–24, 24–48 y 48–72 h. Se registra `valid_date_peru = D`.
- IMERG: suma de los 48 gránulos cuyo inicio cae en `[D−1 12:00, D 12:00)` UTC; tasa (mm/h) × 0,5 h. Un día con menos
  de 48 gránulos queda **incompleto** y no se verifica.
- SENAMHI: el total diario de las estaciones va de las 07:00 locales de un día a las 07:00 del siguiente
  ([SENAMHI](https://www.senamhi.gob.pe/load/file/03619SENA-24.pdf)), la misma ventana de 24 h. **La fecha con que se
  etiqueta ese total no es uniforme entre productos** (fecha de cierre en los reportes "a las 07 horas del día D";
  algunas planillas históricas pueden usar la fecha de inicio). Por eso:
  - la captura de estaciones debe guardar la fecha de **cierre** de la ventana (`fecha_peru` = día de la lectura de
    las 07:00), y si un archivo trae lecturas separadas de 07 h y 19 h, el día D se arma como 19 h de D−1 + 07 h de D;
  - antes de usar una fuente nueva se comprueba el desfase: correlación de su serie con IMERG Late en desfases de
    −1, 0 y +1 día; si el máximo no está en 0, la etiqueta está corrida y la fuente no se usa hasta corregirla.

Regla anti-mirada al futuro: un pronóstico solo se verifica para ventanas que cierran después de su archivo
(`archived_at_utc ≤ end_utc`). La lista de corridas archivadas no se filtra por resultado.

## 3. Correspondencia espacial: tres escalas que no deben mezclarse

| Escala | Variable | Cómo se calcula | Uso |
| --- | --- | --- | --- |
| **Máximo provincial a escala de modelo** | `imerg_025.lluvia_max_mm` vs `p_max` | IMERG promediado por área sobre cada celda de 0,25° de ECMWF; máximo sobre las celdas que el pronóstico asigna a la provincia | Verificación justa de `p_max`: mismo soporte y mismas celdas |
| **Media provincial a escala de modelo** | `imerg_025.lluvia_media_mm` vs `p_mean` | Media de esas mismas celdas | Verificación justa de `p_mean` |
| **Máximo provincial a 0,1°** | `imerg_nativo.lluvia_max_nativo_mm` vs `p_max` | Máximo de celdas IMERG de 0,1° dentro de la provincia | Contraste de soporte: mide cuánto subestima una celda de 27 km un chubasco de 11 km |
| **Lluvia puntual** | Estaciones SENAMHI vs `p_max` | Máximo entre pluviómetros de la provincia | Contraste de soporte; con pocas estaciones el máximo provincial queda subestimado |

### Máximo provincial ≠ lluvia en una quebrada

Una probabilidad provincial de ECMWF **no es** la probabilidad de que una quebrada se active:

- Una celda de ECMWF (~765 km²) es unas 26 veces la microcuenca de San Ildefonso (28,9 km²). El modelo no resuelve la
  lluvia dentro de la quebrada; da la lluvia media de una superficie mucho mayor.
- En lluvia convectiva, el máximo puntual en 24 h puede ser bastante mayor que la media de una celda de 27 km, y una
  quebrada vecina puede quedar casi seca. La relación punto/área en la costa norte aún no está medida en IRFEN; no se
  usa ningún factor supuesto.
- La activación depende además de la lluvia de las horas previas, de la intensidad horaria y del estado hidráulico,
  que IRFEN v0.8 trata por cuenca y no se infiere aquí.

Pasar de la escala provincial a la puntual exige una relación estadística aprendida con pluviómetros (o radar)
dentro de las quebradas, comparada con IMERG de las mismas fechas. Hasta tenerla, el modelo solo dice: "es probable
que llueva fuerte en alguna parte de esta provincia".

## 4. Qué falta para cerrar la correspondencia

- Captura diaria automatizada de estaciones SENAMHI (el formato de entrada ya está definido en
  `docs/V09_ECMWF_ENS_SHADOW.md`).
- Contraste IMERG Late vs. estaciones en el norte para estimar el sesgo de IMERG en esta temporada.
- Relación punto/área con pluviómetros dentro de quebradas piloto (San Ildefonso, Bocapán).
