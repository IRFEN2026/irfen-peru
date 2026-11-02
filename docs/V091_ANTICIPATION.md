# IRFEN v0.9.1 · Anticipación experimental (NARANJA): arquitectura, validación histórica y estado (02-11-2026)

**RESEARCH_ONLY / TEST_ONLY.** `production_use=false`, `activation_gate=BLOCKED`, `public_alerting=false`, `notifications_enabled=false` y `predictive_skill_claimed=false`.

Rama `research/v091-live-integration-20261102` (PR #472), sin fusionar en `main`.

## Respuesta corta

**La capacidad de anticipación no está demostrada. Ninguna regla puede habilitarse todavía.**

- Las dos reglas candidatas para ríos se fijaron antes de ver ningún resultado, en el commit `3bbf70044`. En la validación histórica cada una detectó **2 de 4** eventos documentados.
- Solo hay 4 eventos con fecha dentro de la zona con lluvia archivada. El protocolo exige al menos 10, y además una estimación de lluvia que exista en tiempo real, revisión independiente y autorización del propietario.
- Para las **quebradas** no existe ningún evento con fecha y lugar en esa zona: no se pueden evaluar.

Consecuencias:
- **NARANJA** existe en el código. Solo se activa con una regla que haya superado la validación; hoy no hay ninguna.
- Las señales candidatas se muestran únicamente en un **panel y una capa de simulación**. No colorean el mapa operativo y no envían correos.
- **AMARILLO nunca envía correo.**
- **ROJO** envía correo solo por un evento reportado y verificado. Aun así, el envío real está **deshabilitado** hasta que lo autorices.

## 1. Arquitectura

| Pieza | Archivo | Qué hace |
|---|---|---|
| Protocolo previo | `config/v091_anticipation_protocol_v0_1.json` | Fija las reglas candidatas, las unidades (cuenca para ríos, celda para quebradas), la climatología sin fuga, los eventos documentados, las métricas, la línea base de azar y los criterios de aceptación. Lo prohibido: ajustar a la vista de los datos, usar IMERG Final como predictor, tratar lo ausente como 0 y usar la lluvia sobre el punto del río para inferir desbordes |
| Módulo | `scripts/v091_anticipation.py` | Calcula las medias areales de IMERG Final diario por cuenca HydroSHEDS, los acumulados A1/A3/A10, los percentiles de cada unidad dejando fuera la temporada evaluada, las alarmas, los aciertos, los plazos, los episodios sin evento, el caudal PECHP de contraste y 999 desplazamientos circulares como línea base. Da un veredicto por regla, una simulación en vivo por punto y la reproducción histórica de un día. `--check` reproduce el resultado archivado |
| Resultado | `data/v09/research/anticipation/v091_anticipation_validation_v0_1.json` | Incluye el SHA-256 del protocolo y de cada entrada |
| Estado NARANJA | `scripts/v09_build_semaforo.py` y `site/v09/vigilancia.html` | Precedencia ROJO > NARANJA > AMARILLO > VERDE > GRIS. NARANJA exige que la regla esté en `validated_rules` y una señal de menos de 12 h. Python y JS evalúan igual |
| Paquete y vista | `anticipation` en `surveillance_view_v0_1.json` | Panel «Anticipación (investigación)» en la pestaña Semáforo y capa «Precaución experimental NARANJA (simulación, no validada)», apagada por defecto |
| Correos | `scripts/v091_red_alerts.py` y `config/v091_owner_notifications.json` | NARANJA solo con una regla validada **a la vez** en el paquete y en la validación local. Un único destinatario (huella SHA-256). Envío real deshabilitado |

## 2. Fuentes y capacidad real de actualización

| Fuente | Uso posible | Estado real (02-11-2026) |
|---|---|---|
| IMERG Early, 30 min, 22 zonas del norte | Acumulados de 1–72 h en tiempo real | Captura de main cada 3–8 h. **El 02-11 a las 10:04 falló** (`DownloadFailure` 400) y bloqueó GOES-19; el arreglo está propuesto en #474. Solo se conservan **96 h**, así que el antecedente de 10 días no puede calcularse en vivo |
| GOES-19 RRQPE por zona | Intensidad instantánea | Funciona cuando se ejecuta. Sin climatología, por lo que no sirve para percentiles |
| Avisos SENAMHI vía INDECI/COEN | Contexto territorial (departamento o provincia) | Conectados. Nunca cambian el color |
| IMERG Final diario 2015-16 a 2022-23 (dic–abr) | Climatología y validación | Archivado para el recuadro −6,5…−3,3 / −81,3…−79,1: Tumbes, Piura y el norte de Lambayeque. No existe en tiempo real |
| Cuencas HydroSHEDS | Lluvia aguas arriba | Validadas experimentalmente: Sánchez Cerro, Ñácara, El Ciruelo, desembocaduras del Tumbes y del Chira. **No hay ninguna para los ríos de Lambayeque** |
| Pluviómetros | Contraste y climatología local | **No hay ningún acceso automatizado legítimo identificado.** SENAMHI no se consulta de forma automatizada. Los pluviómetros del PECHP solo están en informes PDF mensuales históricos, e INAMHI no está identificado |
| Caudal y nivel | Objetivo hidrológico | Solo existen las medias diarias del PECHP (24 meses). Las series horarias son de pago (SENAMHI) o requieren solicitud (#460) |

## 3. Reglas candidatas, separadas por fenómeno

| Regla | Fenómeno | Unidad | Definición (percentiles de la propia unidad) | Estado |
|---|---|---|---|---|
| `RIO_A3_P99` | Crecida o desborde de río | Cuenca de aportación | A3 ≥ P99 de la temporada dic–abr | Evaluada |
| `RIO_A1P99_A10P90` | Crecida o desborde de río | Cuenca de aportación | A1 ≥ P99 **y** A10 ≥ P90 (cuenca húmeda) | Evaluada |
| `QDA_A1_P995` | Activación de quebrada | Celda del punto expuesto | A1 ≥ P99,5 | **No evaluable**: no hay eventos fechados |
| `QDA_I3H` | Activación de quebrada | Celda o microcuenca | Intensidad de 3 h extraordinaria | **No evaluable**: no hay climatología subdiaria |

Ninguna regla usa un umbral universal en milímetros. Los milímetros equivalentes de cada unidad y temporada están en el JSON; por ejemplo, el P99 de A3 en Sánchez Cerro sin 2016-17 es 56,4 mm.

## 4. Validación histórica (IMERG Final diario, 1 177 días evaluables, 8 temporadas)

| Evento documentado | `RIO_A3_P99` | `RIO_A1P99_A10P90` |
|---|---|---|
| Piura, desborde del 27-03-2017 (Sánchez Cerro) | **Detectado, 3 días antes** | **Detectado, 2 días antes** |
| Piura, pico de caudal del 15-03-2023 (Yaku; en el Bajo Piura no consta desborde) | No detectado | No detectado |
| Chira, El Ciruelo, pico del 31-03-2017 | Detectado el **mismo día** (sin anticipación) | **Detectado, 2 días antes** |
| Tumbes, umbral hidrológico naranja del 02-03-2019 | No detectado | No detectado |
| **Total** | 2/4 (IC Wilson 90 %: 0,18–0,82); plazo mediano 1,5 días | 2/4 (0,18–0,82); plazo mediano 2 días |
| Episodios sin evento documentado (unidades con eventos) | 21/23 | 17/19 |
| Línea base de azar (p) | Sánchez Cerro 0,22 · El Ciruelo 0,024 · Tumbes 1,0 | 0,19 · 0,026 · 1,0 |

**Lectura**
- Con 4 eventos, cualquier proporción tiene un intervalo de 0,18 a 0,82. **No se puede distinguir una regla útil de una inútil.**
- Solo en el Chira la regla supera al azar (p ≈ 0,02), y con un único evento.
- Los «episodios sin evento» son una **cota superior**. Varios coinciden con caudales altos del PECHP:
  - Sánchez Cerro, 9–11/03/2017: máximo de 1 686 m³/s, con una mediana mensual de 1 273;
  - Sánchez Cerro, 31/03–01/04/2017: 1 909 m³/s;
  - Sánchez Cerro, 5–7/04/2023: 1 247 m³/s, con una mediana de 641;
  - El Ciruelo, 20/02/2018: 352 m³/s, con una mediana de 82;
  - El Ciruelo, 27/02/2020: 398 m³/s, con una mediana de 97.

  El catálogo de eventos está incompleto, así que la tasa de falsas alarmas **no se puede medir** todavía.
- **Cota superior en todos los casos:** IMERG Final no existe en tiempo real, e IMERG Early dio más lluvia que Final en marzo de 2017 (#460). Además, el día UTC cierra a las 19:00 de Perú: con IMERG Early, la señal del día d llegaría hacia las 23:00.
- **Coherente con #459:** con datos diarios, la lluvia explica bien el caudal a posteriori, pero anticipa poco más de lo que ya dice el caudal observado.

## 5. Qué se puede activar ya, qué requiere validación y qué falta

| Criterio | Estado |
|---|---|
| ROJO por correo (evento verificado y localizado) | **Listo**, con la deduplicación, el rearme y la recuperación probados. **Pendiente de tu autorización** para el envío real (`config/v091_owner_notifications.json`) y de una prueba controlada (`--test-email`) |
| AMARILLO, VERDE y GRIS | Nunca envían correo (probado) |
| NARANJA, ríos (`RIO_A3_P99`, `RIO_A1P99_A10P90`) | **No activable.** Falla en número de eventos, POD, intervalo de POD, tasa de falsas alarmas, producto en tiempo real, línea base, revisión independiente y autorización |
| NARANJA, quebradas | **No evaluable** |
| NARANJA en Lambayeque | **No evaluable.** No hay cuencas delimitadas, el recuadro IMERG Final solo cubre el 0–88 % de las zonas de Lambayeque y no hay eventos fechados. En vivo, los 39 puntos dan NO_EVALUABLE, con el motivo de cada uno en el panel |

**Evidencia adicional necesaria, por orden de rendimiento**
1. **Catálogo de eventos con fecha, lugar y fuente:** desbordes, umbrales hidrológicos oficiales y activaciones de quebrada en Tumbes, Piura y Lambayeque entre 2001 y 2023. Incluir también **controles documentados sin impacto**, como el Bajo Piura en 2023. Fuentes posibles: reportes de emergencia de INDECI (SINPAD), avisos hidrológicos de SENAMHI archivados, boletines COE-Vivienda, INGEMMET, ANA y municipalidades. Es manual, sin consultas automatizadas a SENAMHI. Hacen falta al menos 10 eventos por fenómeno y región.
2. **IMERG Early histórico** (HHE V07, no Final) para las ventanas de esos eventos, de modo que el plazo medido sea el real. Son unos 45 GB y 25 min de runner por ventana de 4 meses (#460).
3. **Lambayeque:** ampliar el archivo diario hacia el sur hasta unos 7,4° S y delimitar con HydroSHEDS las cuencas de La Leche, Chancay-Reque y Zaña hasta puntos documentados.
4. **En vivo:** conservar al menos 10 días de IMERG Early y calcular las ventanas por cuenca HydroSHEDS dentro del workflow de captura existente. Eso cambia `main`, así que requiere autorización. También el arreglo #474.
5. **Quebradas:** microcuencas de los puntos ANA y una climatología subdiaria (varios años de IMERG de 30 min por celda, o pluviómetros con acceso legítimo).
6. **Caudal o nivel horario** (solicitudes preparadas en #460). Es el único objetivo que permite medir una anticipación de horas.
7. **Revisión independiente** del protocolo y de los resultados, y **autorización** expresa del propietario.

## 6. Simulacros con datos históricos reales (sin valores inventados)

`python3 scripts/v091_red_alerts.py --example` genera dos hojas PNG de 1080×1350 y dos correos `.eml`, marcados como SIMULACRO. El envío real está bloqueado mientras no se autorice.

- **NARANJA, 26/03/2017.** Río Piura en Puente Sánchez Cerro, regla candidata `RIO_A3_P99`, con los valores reales de IMERG Final de la cuenca: A1 44,4 mm, A3 81,3 mm y A10 218,8 mm. El P99 de A3 sin 2016-17 es 56,4 mm. Confianza BAJA, porque la regla no está validada.
- **ROJO, 27/03/2017.** Desborde documentado del río Piura en La Legua (Catacaos), con fuente ANA/SIGRID. La hora no está documentada y no se inventa. La lluvia solo aparece como contexto.
