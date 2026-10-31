# IRFEN v0.9 · Protocolo de validación histórica de crecidas fluviales (v0.1, 31-10-2026)

RESEARCH_ONLY / TEST_ONLY. **Sin umbrales, sin alertas, sin modelos predictivos.** Este protocolo se fija **antes** de mirar los resultados de cada episodio. Cualquier cambio posterior se registra como versión nueva, con su motivo.

**Pregunta:** ¿contienen los acumulados de precipitación por satélite (IMERG Final V07) señales temporalmente útiles para explicar crecidas observadas en estaciones de aforo? No se pregunta si las predicen.

## 1. Líneas de análisis (no se mezclan)
| Línea | Río / estación | Unidad de lluvia | Estado |
|---|---|---|---|
| **A · Piura** | Puente Sánchez Cerro (ciudad de Piura) y Puente Ñácara (Chulucanas, aguas arriba) | Cuenca Piura (UH ANA 1378), hoy **más extensa** que el área que drena a la estación (ver §4) | Primera validación (2017) |
| B · Chira | El Ciruelo (frontera) y presa Sullana | Catamayo-Chira completa, **con la cabecera ecuatoriana** | Pendiente: falta un polígono binacional y caudales de Ecuador. Regulado por Poechos |
| C · Tumbes | El Tigre | Puyango-Tumbes completa, **con la cabecera ecuatoriana** | Pendiente: faltan polígono binacional y serie de caudales (SENAMHI/PEBPT) |
| D · Huaicos / flujos de detritos | Quebradas | Microcuencas, intensidades de 1 a 3 h | Línea distinta: no se valida con caudales de ríos principales |

## 2. Episodios y periodos de control
- **Episodio principal:** Niño Costero, enero–abril de 2017. Desborde del río Piura en la ciudad el 27-03-2017.
- **Controles** (misma estación del año, mismo tratamiento):
  - enero–abril de 2016: año Niño 2015-16 sin crecida comparable en el bajo Piura;
  - enero–abril de 2018: año sin Niño.
- **Más adelante:**
  - 2019 (umbral naranja en El Tigre el 02-03-2019, línea C);
  - 2023 (ciclón Yaku, líneas A–C);
  - años secos, para medir respuestas en ausencia de crecida.
- **Lluvia antecedente:** se incluye diciembre del año anterior, para disponer de 30 días de antecedente desde el 1 de enero.

## 3. Datos y unidades
- **Caudal:** informes hidrometeorológicos mensuales del PECHP (gob.pe), archivados con SHA-256.
  - Se distinguen el **caudal medio diario** (tablas diarias) y el **máximo instantáneo** (texto o resumen, con día y, si existe, hora). No se mezclan.
  - Los valores se extraen con dos lectores de texto independientes y solo se aceptan si coinciden. Las incoherencias de la fuente se registran sin corregirlas.
- **Lluvia:** IMERG Final V07 diario (GPM_3IMERGDF), en mm/día.
  - El día es UTC (00–24 UTC = 19–19 h de Perú). La convención de día de las estaciones PECHP no está declarada, así que todo desfase de ±1 día es **ambiguo**.
  - Una celda o un día sin dato es **desconocido**, nunca 0.
- **Huella observada:** Copernicus EMS EMSR199, delimitaciones vectoriales con fecha de adquisición, sensor y resolución. Sirve para comprobar que la crecida desbordó y dónde, no para calibrar.

## 4. Representatividad del polígono (condición previa a cualquier lectura causal)
El área de lluvia debe ser la que **drena hasta la estación**:
- La UH ANA 1378 (Cuenca Piura, 10 872 km²) incluye el Bajo Piura **aguas abajo** de Sánchez Cerro (hasta Sechura).
- No hay coordenadas oficiales de las estaciones ni una cuenca delimitada hasta ellas.
- El caudal en Sánchez Cerro está **alterado por obras**: la presa derivadora Los Ejidos, justo aguas arriba, y el trasvase Chira→Piura por el canal Daniel Escobar desde Poechos, que aporta agua de otra cuenca.

Mientras no se resuelva:
- los resultados se expresan como **asociación temporal**, no como relación causal ni balance hídrico;
- toda cifra que use la UH completa lleva la marca `POLIGONO_NO_EQUIVALENTE_A_LA_CUENCA_DE_LA_ESTACION`.

**Para resolverlo hacen falta:**
- coordenadas oficiales de las estaciones (SENAMHI/PECHP, por solicitud);
- delimitación hasta cada estación con un modelo digital del terreno reproducible (HydroSHEDS o MERIT Hydro, declarados como no oficiales), contrastada con el área de drenaje que publique la institución;
- serie del trasvase y operación de Los Ejidos.

## 5. Métricas fijadas de antemano
1. **Series diarias:**
   - P(d), media de la unidad ponderada por la fracción de cada celda dentro del polígono;
   - acumulados antecedentes A_k(d), con k = 1, 3, 5, 7, 10, 15 y 30 días;
   - Q(d), caudal medio diario.
2. **Desfase:**
   - correlación de Spearman y de Pearson (esta, sobre log(Q+1)) entre P(d) y Q(d+L), para L = 0…10 días;
   - el mismo cálculo entre Q_Ñácara(d) y Q_SánchezCerro(d+L), para L = 0…5 días.
   - Se informa la curva completa, **no solo el máximo**, con n y la advertencia de autocorrelación serial (no se calculan valores p ingenuos).
3. **Cronología del episodio:** fecha del máximo de Q; fecha del máximo de cada A_k; diferencia en días.
4. **Comparación con los controles:** las mismas métricas en 2016 y 2018. Una señal solo se considera «temporalmente útil» si:
   - (a) aparece con un desfase físicamente plausible (≥ 0 días);
   - (b) se mantiene en al menos un control con crecidas menores;
   - (c) no depende de un único día extremo. Se comprueba **excluyendo ±3 días alrededor del pico**.
5. **Prohibido:**
   - ajustar umbrales;
   - elegir k o L a la vista de 2017 y aplicarlos a 2017 como si fueran una prueba;
   - presentar la correlación de un único episodio como capacidad predictiva.

## 6. Resultado admisible de esta fase
- La resolución temporal es diaria, y la convención de día no está declarada.
- Si las métricas cumplen 4(a)–(c), el resultado admisible es: «hay o no hay una **señal temporal** de acumulados antecedentes que precede al caudal observado, con un desfase de L días, en esta estación y estos años».
- Siempre se acompaña de las limitaciones del §4.

---

## Versión 0.2 (31-10-2026, después de #458): añadidos fijados en el código **antes** de la primera ejecución

Las reglas se fijaron en el commit `cc64da9fa` (`scripts/v09_piura_robustness.py`), antes de ejecutarlo por primera vez, y se documentan aquí después.
Motivo: la revisión de #458 identificó cuatro riesgos de interpretación. La autocorrelación y la estacionalidad inflan ρ. Elegir el desfase con el máximo de ρ sesga el resultado. La convención de día es incierta. Y la correlación se confundía con anticipación.

1. **Polígono:** la comparación lluvia–caudal solo se recalcula con una cuenca **validada hasta la estación**:
   - coordenada documentada;
   - área de la delimitación dentro de ±10 % del área documentada;
   - topología D8 sin ciclos y sin cortes por el recorte;
   - contraste independiente de área (HydroRIVERS) dentro de ±15 %.

   Una cuenca experimental se etiqueta como no oficial y no sustituye a la UH ANA.
2. **Régimen:** se define R = (Curumuy + canal Ejidos)/(Q_SC + canal Ejidos) y se clasifica cada mes:
   - regulado: mediana de R > 0,5 o mediana de Q_SC < 5 m³/s;
   - natural: mediana de R < 0,1;
   - mixto: el resto.

   Solo los meses naturales o mixtos son controles hidrológicamente comparables.
3. **Autocorrelación:** se calcula con diferencias diarias y con preblanqueo AR(1).
4. **Selección del desfase:** la significación del máximo sobre L = 0…10 se mide con todos los desplazamientos circulares de la lluvia de al menos 7 días. Es determinista: p = (k+1)/(N+1).
5. **Convención de día:** se prueba la lluvia desplazada −1, 0 y +1 días, y la aproximación 12–12 UTC.
6. **Tres preguntas distintas:**
   - correlación;
   - explicación retrospectiva: ρ parcial(Q(d), A3(d) | Q(d−1));
   - anticipación: ρ parcial(Q(d+L), A3(d) | Q(d)), con L = 1–3.
7. **Réplica:** un desfase observado en 2017 solo se considera replicado si aparece en otro episodio de régimen natural no usado para elegirlo (2023). Nunca se fijan umbrales con 2017.

---

## Versión 0.3 (31-10-2026): anticipación real. Fijada **antes** de cualquier comparación subdiaria

Las reglas que se pueden ejecutar están en `config/v09_anticipation_protocol_v0_3.json`; el arnés `scripts/v09_anticipation_harness.py` las lee y no admite otras.
Motivo: el objetivo deja de ser explicar el caudal a posteriori y pasa a medir si la lluvia **disponible en el instante de emisión** mejora la anticipación del caudal o nivel **medido**.

1. **Pregunta:** en un instante de emisión t, con todo lo publicado hasta t, ¿mejora la lluvia observada la predicción de Q o H en t + h, para h = 3, 6, 12 y 24 h, frente a una línea base que solo usa caudales y niveles?
2. **Cuatro categorías que no se mezclan:**
   - lluvia registrada;
   - caudal o nivel medido;
   - caudal aproximado, que nunca es objetivo ni predictor de la línea base;
   - operación hidráulica (Poechos, Los Ejidos, Curumuy, canal Daniel Escobar), que solo entra como predictor si estaba publicada en t.
3. **Resolución mínima del objetivo:** serie con un paso de 1 h o menos, con hora y zona horaria declaradas.
   - Las medias diarias del PECHP **no permiten** evaluar ningún horizonte de 3 a 24 h. Su resultado es `NO_EVALUABLE`.
   - No se desagregan medias diarias.
4. **Latencias de disponibilidad:**
   - IMERG Early: 4 h; IMERG Late: 14 h; telemetría de estación: 1 h por defecto, que se sustituye por la latencia documentada del operador cuando exista. Sensibilidad: +0 y +2 h.
   - **IMERG Final queda excluido como predictor.** Se publica meses después y su calibración mensual con pluviómetros usa información posterior a t. Solo se admite como cota superior etiquetada `ORACULO_NO_OPERATIVO`.
5. **Modelos fijados:**
   - B0: persistencia.
   - B1: tendencia hidrométrica local.
   - **B2: B1 más la estación aguas arriba.** Es la línea base de referencia.
   - M: B2 más ln(1 + R_k), con k = 6 y 24 h. Se informan las dos acumulaciones y la multiplicidad se corrige con Holm.
6. **Episodios:**
   - se definen con ventanas de calendario antes de abrir los datos;
   - validación dejando un episodio fuera, con 7 días de separación si comparten temporada;
   - ningún parámetro ni escalado se calcula con el episodio de evaluación;
   - los desfases diarios descritos en #458 y #459 no sirven para elegir hiperparámetros.
7. **Decisión:** la mejora solo es **demostrable** si se cumplen las cuatro condiciones siguientes. En caso contrario se informa como `RESULTADO_NEGATIVO_O_NO_CONCLUYENTE`.
   - el IC 95 % de ΔMSE = MSE_B2 − MSE_M, por bootstrap de bloques de 48 h, es mayor que 0 en dos o más episodios de evaluación independientes y en los dos sentidos de la validación cruzada;
   - supera el percentil 95 de un placebo de lluvia desplazada al menos 7 días;
   - se mantiene con +2 h de latencia;
   - el p ajustado por Holm es menor que 0,05.
8. **Chira:**
   - el objetivo natural es El Ciruelo, aguas arriba de Poechos, con Puente Internacional Macará como estación aguas arriba;
   - todo lo que queda aguas abajo de Poechos depende de las descargas del embalse y queda **fuera de alcance** como problema lluvia–caudal.
9. **Tumbes:** el objetivo es El Tigre. La estación aguas arriba en Ecuador (Puyango, INAMHI) está por confirmar.
10. **Prohibido:** umbrales, alertas, uso operativo, mezclar caudal aproximado con caudal medido y reconstruir series horarias.
11. **Episodios fijados el 31-10-2026, antes de disponer de ningún dato subdiario de caudal o nivel** (detalle en `episodes_fixed_before_data`):
    - Piura: 2017 (15-01 a 30-04), 2019 (01-02 a 31-03) y 2023 (15-02 a 15-05).
    - Chira en El Ciruelo: 2017 y 2023, con las mismas ventanas que Piura.
    - Tumbes en El Tigre: temporadas 2015 a 2019, del 15-01 al 30-04, y 2023, del 01-02 al 31-05.
    - Una ventana solo se acorta si la serie oficial no la cubre, y lo que falte es desconocido.
