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
