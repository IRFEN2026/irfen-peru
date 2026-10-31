# IRFEN v0.9 · Río Piura: cuencas de aportación, evidencia histórica y robustez (31-10-2026)

RESEARCH_ONLY / TEST_ONLY. Sin umbrales, sin alertas, sin cambios en el motor, en `site/` ni en `main`. Apilado sobre #458.

```bash
python scripts/v09_pechp_extract.py --check          # PECHP 2016–2023, dos lectores + sumas impresas
python scripts/v09_piura_catchments.py --check       # cuenca experimental HydroSHEDS (≈ 70 s)
python scripts/v09_piura_robustness.py --check       # régimen, autocorrelación, desfases, tres preguntas
python scripts/v09_render_piura_catchments_view.py --check
python -m unittest tests.test_v09_piura_catchments_robustness tests.test_v09_piura_2017_validation
```
Vista experimental: `research/v09/piura_catchments_robustness.html`.

## 1. Cuencas de aportación (prioridad 1)
**Coordenadas y áreas documentadas.** Se archivaron con SHA-256 y capa de texto:
- PNUD 98/018 – CTAR Piura, *Estudio para el Tratamiento Integral del Río Piura, Apéndice D*, 2000;
- *Plan de gestión de los recursos hídricos de la cuenca Chira-Piura* (ANA).

| Estación | Coordenada | Área documentada | Resultado |
|---|---|---|---|
| **Puente Sánchez Cerro** («sección de la presa Los Ejidos») | 5°11′55″ S, 80°37′20″ O, 23,3 msnm (PNUD-CTAR 2000, §3.1). **Datum no declarado** | 7 790 km² (PNUD-CTAR 2000) y 7 742 km² (Garbrecht 1981, citado en el mismo documento). Las subcuencas de su Tabla 1 suman 7 789,4 km² | ✅ **VALIDADA_EXPERIMENTAL** |
| Puente Ñácara | **No encontrada** en las fuentes archivadas | — (la correspondencia con las subcuencas de la Tabla 1 no es explícita) | ⛔ No se delimita |
| Tambogrande | **No encontrada** | — | ⛔ No se delimita |

**Delimitación experimental de Sánchez Cerro (HydroSHEDS v1, 15″; WWF/USGS a partir de SRTM; no oficial):**
- **Datos:** dirección de drenaje y acumulación recortadas y archivadas con SHA-256, más HydroRIVERS como contraste independiente.
- **Topología:** 0 ciclos D8 en el recorte. La cuenca no toca el borde del recorte.
- **Salida:** ajustada a la celda de máxima acumulación a 1,64 km del punto documentado. Es compatible con un datum PSAD56 no declarado, pero no lo demuestra.
- **Estabilidad del ajuste:** con ajuste de 1, 2 o 3 celdas el área es 7 756,5–7 758,5 km². Sin ajuste (el píxel bruto) cae en un afluente: 7 571 km².
- **Área:** **7 758,5 km²**, es decir, 0,996 × 7 790 y 1,002 × 7 742. HydroRIVERS da 7 760,4 km² en el tramo más cercano, a 0,65 km.
- **Solape:** el 98,8 % de la cuenca cae dentro de la UH ANA 1378.
- **Diferencia con la UH:** la UH 1378 (10 872 km²) añade unos 3 100 km² de Bajo Piura, aguas abajo de la estación. Así queda cuantificado el sesgo del polígono usado en #458.
- **Estado:** la geometría vigente **no se sustituye**. La cuenca HydroSHEDS es un candidato experimental validado contra áreas documentadas y solo se usa en este análisis de investigación.

**Aportación natural, regulación y trasvase en Sánchez Cerro:**
- **Fórmula:** Qn ≈ Q_SC + canal Ejidos − Curumuy. Es un balance diario sin tiempos de viaje ni otras extracciones.
- **Peso de la regulación:** R = (Curumuy + Ejidos)/(Q_SC + Ejidos).
- **Infraestructura:** según el Plan de gestión, el canal Daniel Escobar trasvasa agua del Chira al Medio y Bajo Piura (la C.H. Curumuy capta 38 m³/s), y la presa Los Ejidos deriva por el canal Biaggio Arbulú.
- **Meses naturales** (R < 0,1): marzo de 2017 (mediana de Q_SC 1 273 m³/s, R 0,05) y marzo–abril de 2023 (525–641 m³/s, R 0,07–0,10).
- **Meses mixtos:** abril de 2017 y marzo de 2021.
- **Los 18 meses restantes con datos** (enero–abril de 2018 a 2022, enero–febrero de 2023, enero de 2019) están **dominados por la regulación**. El río está casi seco en la ciudad mientras el trasvase sigue entrando.
- **Consecuencia:** 2018 no era un control hidrológicamente comparable.

## 2. Evidencia histórica (prioridad 2)
**Archivado:** 32 informes PECHP (enero–abril de 2016 a 2023). Las tablas diarias de ríos se extrajeron en **24 meses**: marzo–abril de 2017, enero–abril de 2018, enero de 2019, y enero–abril de 2020 a 2023.
- **Dos lectores:** todas las filas coinciden en ambos.
- **Nuevo control:** en los 24 meses, la suma de las medias diarias coincide con la fila **SUMA / Total mensual impresa** en todas las columnas (tolerancia de redondeo de 0,05 × días).
- **Formatos:** se añadieron los de 2019 (día al final) y 2020–2023 (día con una cifra).

**Meses que no son recuperables:** 2016, enero–febrero de 2017 y febrero–abril de 2019 **no traen tablas diarias**. Solo incluyen **gráficos de líneas** del caudal del río Piura; enero de 2017 ni siquiera trae el del Piura. Se revisaron visualmente las imágenes de febrero de 2017, enero de 2017 y marzo de 2019.
- No hay nada que pasar por OCR.
- Digitalizar una curva produciría valores aproximados con error no acotado, así que **no se digitalizan como observaciones**. Quedan como desconocidos.
- **Siguiente paso:** pedir la serie diaria de Sánchez Cerro, Ñácara y Tambogrande al PECHP o a SENAMHI.

**Ñácara y Tambogrande:** las tablas en texto solo llegan hasta marzo–abril de 2018. Desde 2019 los informes ya no las incluyen en texto.

**IMERG Final V07B diario:** 1 195 días (diciembre–abril de 2015-16 a 2022-23). Siguen ausentes los 15 días de enero de 2016, declarados como desconocidos.

**Episodios con aportación natural y datos completos:** 2017 (desborde del 27-03, 2 754,5 m³/s) y **2023 (ciclón Yaku, 1 561,5 m³/s el 15-03)**. Los periodos secos o regulados (2018–2022) quedan como **periodos de regulación**, no como controles naturales.

## 3. Robustez (prioridad 3)
Lluvia IMERG Final media sobre la cuenca HydroSHEDS hasta Sánchez Cerro. Caudal observado y aproximación natural. ρ es la correlación de Spearman; p sale de desplazamientos circulares que conservan la autocorrelación y tienen en cuenta la elección del máximo entre 11 desfases.

| Año (régimen) | Serie | Niveles: ρ máx. (L) · p | Diferencias diarias: ρ (L) · p | Preblanqueo AR(1): ρ (L) | Retrospectiva: ρ parcial(Q(d), A3(d) \| Q(d−1)) | Anticipación: ρ parcial(Q(d+1…3), A3(d) \| Q(d)) |
|---|---|---|---|---|---|---|
| **2017** (natural, mixto) | observado | 0,85 (1) · 0,02 | 0,36 (1) · 0,19 | 0,65 (1) | **0,52** | **0,02 / 0,03 / −0,01** |
| **2017** | natural aprox. | 0,86 (1) · 0,02 | 0,44 (1) · 0,04 | 0,67 (1) | 0,54 | 0,03 / 0,01 / −0,04 |
| **2023** (natural en marzo–abril) | observado | 0,67 (1) · 0,02 | 0,47 (1) · 0,04 | 0,43 (1) | **0,42** | 0,20 / 0,21 / 0,23 |
| 2023 | solo meses comparables | 0,75 (1) · 0,04 | 0,60 (1) · 0,04 | 0,60 (1) | 0,58 | 0,21 / 0,24 / 0,22 |
| 2021 (mixto en marzo) | solo meses comparables (n = 31) | 0,71 (2) · 0,03 | 0,59 (2) · 0,03 | 0,62 (2) | 0,76 | 0,71 / 0,68 / 0,58 |
| 2018–2022 (regulados, enero–abril completo) | observado y natural aprox. | 0,18–0,45, con L de 4 a 10 sin patrón | 0,16–0,42 (L 2–9) | 0,10–0,41 | −0,40 a 0,24 | −0,74 a 0,44 (inestable) |

**Convención de día:**
- Con día UTC, el mejor desfase es **1 día** en 2017 y en 2023.
- Desplazando la lluvia −1/+1 días el desfase pasa a 2/0 días.
- La aproximación 12–12 UTC da 1 día (2017) o 2 días (2023), con ρ ligeramente mayor.
- Por tanto, el desfase verdadero en Sánchez Cerro está entre 0 y 2 días. La convención del PECHP decide la cifra exacta, y sin la hora de lectura no se puede afinar.

## 4. Lectura
**Resuelto:**
1. **Polígono:** ya existe una cuenca hasta Sánchez Cerro validada experimentalmente contra dos áreas documentadas y una tercera estimación independiente (diferencia < 0,5 %). El sesgo de la UH 1378 está cuantificado: unos 3 100 km² de Bajo Piura aguas abajo de la estación.
2. **Regulación:** está medida mes a mes. La mayoría de los meses están dominados por la operación (trasvase y derivación). Solo marzo de 2017 y marzo–abril de 2023 tienen aportación natural dominante.
3. **Réplica:**
   - El desfase de **1 día** en Sánchez Cerro observado en 2017 **se repite en 2023**, un episodio independiente que no se usó para elegirlo. Se repite en niveles, en diferencias y con preblanqueo.
   - Resiste el control de selección del desfase (p de 0,02 a 0,04 frente a desplazamientos circulares).
   - En diferencias, para el caudal observado de 2017, p = 0,19: ahí la señal se apoya sobre todo en el nivel.
4. **Correlación, explicación y anticipación:** la lluvia de 3 días **explica retrospectivamente** cambios del caudal más allá de la persistencia (ρ parcial 0,42–0,58 en episodios naturales). En cambio, la **anticipación** más allá del caudal ya observado es **nula en 2017** (≈ 0) y **débil en 2023** (≈ 0,2). Con datos diarios, la lluvia de un día no dice mucho más sobre el caudal de mañana que el caudal de hoy.

**Sigue abierto:**
1. **Ñácara y Tambogrande:** no tienen coordenadas documentadas. Son las estaciones de aportación natural, aguas arriba del trasvase, pero no se pueden delimitar sin inventar coordenadas.
2. **Datos diarios del PECHP:** faltan en 2016, enero–febrero de 2017 y 2019 (solo hay gráficos), y en las tablas de Ñácara y Tambogrande desde 2019.
3. **Convención de día del PECHP y datum de la coordenada:** desconocidos.
4. **Resolución sub-diaria:** la propagación (0–2 días) no se resuelve con datos diarios. Hacen falta IMERG por media hora y niveles horarios.
5. **Pocos episodios naturales:** dos (2017 y 2023), más uno mixto (2021). Con tan pocos casos no se puede estimar el error ni la estabilidad de ninguna relación.
6. **Aportación natural:** es aproximada. No incluye tiempos de viaje entre Curumuy y Los Ejidos ni otras extracciones del Medio Piura.
7. **Huella EMSR199:** sigue bloqueada (403/404).
8. **Cabeceras ecuatorianas:** Chira y Tumbes, que siguen como líneas aparte.

**¿Hay base suficiente para diseñar una validación retrospectiva con varios episodios?**
- **Para diseñarla, sí.** Ya existen:
  - una cuenca validada hasta Sánchez Cerro;
  - 24 meses de caudal diario verificado con tres controles: dos lectores, sumas impresas y volumen declarado;
  - una clasificación de régimen que separa episodios naturales de periodos regulados;
  - lluvia IMERG Final íntegra para 8 temporadas;
  - un protocolo con controles de autocorrelación y de elección de desfase.
- **Para ejecutarla con conclusiones generalizables, todavía no:**
  - hay solo dos o tres episodios naturales;
  - las estaciones de aportación natural (Ñácara, Tambogrande) no tienen coordenadas;
  - falta la resolución sub-diaria;
  - falta la convención de día.
- **Para pasar a una validación con varios episodios hace falta:**
  1. pedir la serie diaria, y si existe horaria, de Ñácara, Tambogrande y Sánchez Cerro (1990–2023), con coordenadas, datum y hora de lectura;
  2. ampliar los episodios naturales con más años, incluidos 1998 con CHIRPS o PERSIANN-CDR, ya que IMERG empieza en 2000;
  3. usar IMERG por media hora para los episodios;
  4. fijar el protocolo v0.3 (episodios, controles y métricas) antes de abrir esos datos.

## 5. Cambios respecto al plan, declarados
- **Añadidos tras la primera ejecución del análisis de robustez**, sin cambiar las reglas de régimen ni los desfases:
  - la serie «solo meses comparables»;
  - la regla p = (k+1)/(N+1), para que p nunca sea 0;
  - el cálculo de los acumulados con toda la serie de lluvia, para no truncar el antecedente en el inicio de la ventana.
- **Estación cambiada:** HydroBASINS nivel 12 no se encontró entre los enlaces de descarga, así que el contraste independiente de área se hizo con HydroRIVERS (UPLAND_SKM).
