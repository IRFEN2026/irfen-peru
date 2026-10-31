# IRFEN v0.9 · Viabilidad de una anticipación experimental de crecidas fluviales (31-10-2026)

**RESEARCH_ONLY / TEST_ONLY.** Sin umbrales, sin alertas, sin cambios en el motor, sin publicación y sin fusión en `main`. Las conclusiones y limitaciones de #459 se mantienen tal como están documentadas.
Rama: `research/v09-flood-anticipation-feasibility-20261031`, apilada sobre #459.

## Respuesta corta

**Hoy no se puede medir si la lluvia mejora la anticipación en 3, 6, 12 o 24 h.** No hay en el archivo de IRFEN ninguna serie de caudal o nivel con paso horario. Las medias diarias del PECHP no permiten evaluar esos horizontes y no se han desagregado.

El resultado del arnés v0.3 sobre los datos archivados es `NO_EVALUABLE` para todos los objetivos. Por tanto, la mejora **ni está demostrada ni está refutada**.

Lo que sí se ha resuelto: las series horarias existen, se sabe quién las tiene y cuánto cuestan; la lluvia de 30 minutos está completa y es reproducible; y el protocolo, los episodios y el código se fijaron antes de abrir cualquier dato. El siguiente experimento está listo para ejecutarse en cuanto lleguen las series oficiales.

## 1. Datos hidrométricos de mayor resolución

Ninguna serie es pública como descarga. En la tabla, *Sí* indica serie horaria documentada, *Probable* indica indicios y *?* indica desconocido.

| Estación | Operador | Serie horaria | Evidencia (fuente comprobada) | Coordenada y área documentadas | Hora de lectura |
|---|---|---|---|---|---|
| El Tigre (Tumbes) | SENAMHI | **Sí** | Estación automática horaria (Metzger y Xuan 2010). SENAMHI calibró un modelo horario en 2014/15–2018/19 (EGU2020-12927) | 3,72 S; 80,47 O (0,01°). Área: 4 710 / 4 802 / 4 750 km² | — |
| Puente Ñácara (47E0415A) | SENAMHI | **Sí** | Caudal horario en PHISIS: 2 lecturas válidas de 613 consultas de IRFEN en 2026 | 5,11 S; 80,17 O (Lavado 2012). 05°07′ S; 80°10′ O (UDEP 2020). Área: 4 765 km² | 08:00 |
| Los Ejidos | PECHP | **Sí** | UDEP modela «caudales horarios» en Los Ejidos (Farías et al. 2020) | 05°10′ S; 80°37′ O (al minuto de arco). Área: no documentada | — |
| Tambogrande | SENAMHI / PECHP | Probable | UDEP: desfase de unas 18 h hasta Los Ejidos | 04°57′ S; 80°19′ O (UDEP). Área: solo indirecta | — |
| Puente Sánchez Cerro | PECHP | ? | Limnímetro; el COER difunde lecturas con hora durante la avenida | Coordenada y área en #459 | **07:00** |
| El Ciruelo (Chira) | PECHP / SENAMHI | ? | Informes con media diaria y máximo instantáneo por día, sin hora | 4,30 S; 80,15 O. Área: 7 760 km² | 08:00 |
| Puente Internacional (río Macará), La Ardilla | PECHP / SENAMHI | ? | Medias diarias | Sin coordenada | 08:00 |
| Puyango (INAMHI, Ecuador) | INAMHI | ? | No se encontró ninguna fuente pública | Sin coordenada | — |

**Datum y hora**
- Ninguna fuente declara el datum.
- La hora de lectura (07:00 en Sánchez Cerro y 08:00 en las demás) procede del reporte SENAMHI Nº029-DZ01-PIURA de 2026. Es un indicio de la convención de día, pero no define qué es la media diaria del PECHP, así que la convención **sigue sin resolverse**.

**Acceso**
- SENAMHI cobra los datos horarios validados por la tarifa TUSNE 2024, servicio 5: S/ 861,38 por estación y año para caudal y S/ 348,45 para nivel.
- El PECHP y el INAMHI requieren una solicitud formal.

**Solicitudes preparadas, no enviadas:** `research/v09/requests/SOLICITUDES_DATOS_HIDROMETRICOS_BORRADOR_20261031.md`, dirigidas a PECHP, SENAMHI, INAMHI y ANA o el ministerio ecuatoriano. Coste orientativo en SENAMHI: S/ 5 168 por el núcleo (3 estaciones × 2 años) y S/ 4 307 más por la calibración de El Tigre (2015–2019).

**Antecedentes que conviene conocer**
- **UDEP (Farías et al. 2020)** afirma 12 h de anticipación en los picos de Los Ejidos usando **estaciones aguas arriba**: Tambogrande unas 18 h antes y Ñácara unas 24 h. Es encaminamiento hidrométrico, que es justo la línea base B2 del protocolo; no demuestra que la lluvia aporte algo más.
- **SENAMHI (EGU2020)**, en El Tigre, con lluvia IMERG Early y GSMaP: NSE de 0,6 a 0,8, pero los picos quedan subestimados entre un 22 % y un 38 %.

## 2. IMERG cada 30 minutos

| Producto V07 | Papel en el protocolo v0.3 | Cobertura 2017-01-01 → 04-30 | Cobertura 2023-02-01 → 05-31 |
|---|---|---|---|
| HHE (Early) | **Predictor admisible**, con 4 h de latencia | 5 760 / 5 760 | 5 760 / 5 760 |
| HHL (Late) | Predictor admisible, con 14 h de latencia | 5 760 / 5 760 | 5 760 / 5 760 |
| HH (Final) | **Solo como «oráculo»**: prohibido como predictor | 5 760 / 5 760 | 5 760 / 5 760 |

**Coste medido en el piloto (2017-03-26, 96 gránulos)**
- Cada gránulo global pesa unos 7,9 MB y se descarga en 0,25–0,28 s.
- Por producto y ventana de 4 meses: unos **45 GB** de transferencia y **23–27 min** de runner. Se conservan unos 5,4 millones de valores del recuadro.
- Es viable, pero **no se ha descargado** porque todavía no hay caudal subdiario con el que compararlo.

**Coherencia interna:** la suma de las 48 medias horas Final coincide con el diario Final del mismo día en 704 celdas (diferencia máxima de 0,0 mm).

**Early frente a Final, solo el 2017-03-26**
- Early da más lluvia que Final en todas las cuencas validadas: Sánchez Cerro 57,7 frente a 44,4 mm, Ñácara 53,6 frente a 41,5, El Ciruelo 27,1 frente a 17,6 y Tumbes 24,0 frente a 17,1 mm.
- Es un solo día y no se generaliza. Pero confirma que **evaluar la anticipación con IMERG Final sobreestimaría lo que se puede saber en tiempo real**.

**Limitación:** el V07 Early reprocesado no es idéntico al producto publicado en 2017 (V04). Es una aproximación de lo que estaba disponible entonces.

## 3. Cuencas transfronterizas

Las delimitaciones son experimentales, con HydroSHEDS v1 de 15″ y las mismas reglas que #459. Son **no oficiales** y no sustituyen ninguna UH ANA.

| Cuenca | Estado | Área HydroSHEDS | Áreas documentadas | HydroRIVERS | Fuera de las UH ANA (≈ Ecuador) |
|---|---|---|---|---|---|
| Puyango-Tumbes completa (salida derivada en la desembocadura) | Validada experimental | **5 395 km²** | 5 488 (ADT GEF: ANA 2017 + SENAGUA 2017); 5 638 | 5 394 | **67,7 %** |
| Catamayo-Chira completa (salida derivada) | Validada experimental | **17 761 km²** | 17 810 (ADT); 17 199 (AECI) | 17 760 | **41,3 %** (documentado: 40,5–41,9 %) |
| El Ciruelo | Validada experimental, **con cautela** | 7 064 km² | 7 760 (9 % menos) | 7 085 | 85,6 % |
| El Tigre | **No validada** | — | 4 710–4 802 | — | — |
| Puente Ñácara | Validada experimental | **4 712 km²** | 4 765; 4 731 indirecta | 4 734 | 0,4 % |
| Tambogrande | Consistente con el área indirecta, no validada | 6 310 km² | 6 174 (suma de subcuencas) | 6 323 | 0,3 % |
| Los Ejidos | Sin área documentada | 7 562 km² | — | — | — |

**Notas**
- **El Tigre:** el punto publicado (0,01°) cae en un afluente y el cauce principal está a 2,1 km, fuera del ajuste de 3 celdas. No se ha cambiado la regla, así que hace falta la coordenada oficial.
- **Delimitación oficial binacional:** no hay una geometría pública descargable. El ADT cita ANA 2017 y SENAGUA 2017, y se ha pedido en la solicitud 4.
- **Capa ANA de Tumbes:** la única consulta agotó el tiempo y no se reintentó.
- **Poechos:** El Ciruelo está aguas arriba del embalse y es el objetivo natural del Chira. Aguas abajo (Sullana y Bajo Chira) el caudal depende de las descargas del embalse, por lo que queda **fuera de alcance** como problema lluvia–caudal. Solo podría estudiarse con las descargas publicadas, como operación hidráulica.
- **Estación ecuatoriana aguas arriba:** ninguna está identificada con coordenada. El Puente Internacional (río Macará) tiene medias diarias del PECHP, pero no tiene coordenada.

## 4. Evaluación de anticipación: protocolo v0.3

El protocolo se fijó en el commit `ea1fcad9a` y los episodios en `46b3fdcc8`, ambos **antes** de cualquier dato subdiario. Tiene una parte ejecutable en `config/v09_anticipation_protocol_v0_3.json` y se describe en el §0.3 de `qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md`.

- **Cuatro categorías separadas:** lluvia registrada, caudal o nivel medido, caudal aproximado y operación hidráulica.
- **Objetivo:** caudal o nivel medido con un paso de 1 h o menos. Con medias diarias el resultado es `NO_EVALUABLE`.
- **Línea base B2:** tendencia local más la estación aguas arriba, con datos disponibles en t (latencia de telemetría de 1 h y sensibilidad de +2 h).
- **Modelo M:** B2 más ln(1 + lluvia IMERG Early acumulada en 6 y 24 h, disponible en t − 4 h).
- **Episodios:** validación dejando un episodio fuera; bootstrap por bloques de 48 h; placebo de lluvia desplazada al menos 7 días; corrección de Holm.
- **Regla de decisión:** «mejora demostrable» exige que se cumpla en al menos dos episodios. Si no, se informa `RESULTADO_NEGATIVO_O_NO_CONCLUYENTE`.
- **Arnés `scripts/v09_anticipation_harness.py`:**
  - comprueba fila a fila que ningún predictor usa datos posteriores a t;
  - rechaza IMERG Final y las medias diarias;
  - trata la lluvia incompleta como desconocida.
  - Las pruebas con series **sintéticas de juguete** (solo prueban el código; no son observaciones) muestran que detecta una señal real y da un resultado negativo cuando la lluvia es ruido.
- **Resultado sobre los datos reales archivados** (`anticipation_evaluation_v0_1.json`): **NO_EVALUABLE** en los cuatro horizontes para Sánchez Cerro, El Tigre y El Ciruelo. Aguas abajo de Poechos queda fuera de alcance.

## 5. Bloqueos

1. No hay series horarias públicas de SENAMHI ni del PECHP. PHISIS agota el tiempo desde GitHub y no se le hacen consultas automatizadas.
2. Falta el datum y faltan las coordenadas oficiales de El Tigre, Puente Internacional, La Ardilla y la estación del Puyango.
3. La convención de la media diaria del PECHP sigue sin declarar.
4. No hay datos hidrométricos ecuatorianos (INAMHI) identificados.
5. No hay una geometría oficial binacional descargable, y el servicio ANA de Tumbes no respondió.
6. La serie de operación de Poechos y del trasvase solo existe como medias diarias.

## 6. Siguiente experimento reproducible (E1)

1. **Enviar las solicitudes.** Lo decide y firma la persona solicitante. Mínimo útil: caudal horario de Ñácara, Tambogrande, Los Ejidos y Sánchez Cerro en 2017 y 2023.
2. **Archivar** cada serie recibida con su SHA-256, sus metadatos (hora, zona horaria, datum, curva de gasto) y la latencia de publicación.
3. **Capturar IMERG HHE V07** solo para los episodios con caudal disponible (unos 45 GB y 25 min por ventana) y calcular las medias areales sobre las cuencas validadas.
4. **Ejecutar `evaluate_pair()`** sin cambiar nada del protocolo:
   - Sánchez Cerro (objetivo) con Ñácara como estación aguas arriba;
   - después El Tigre y El Ciruelo cuando haya datos.
   - Informar el veredicto por horizonte y acumulación, **incluido el negativo**.
5. Comparar con la cota «oráculo» de IMERG Final solo como referencia, nunca como resultado.

## Fuentes comprobadas

La lista completa, con el resultado de cada consulta, está en `config/v09_anticipation_sources_checked_v0_1.json`.
