# IRFEN v0.9.1 · Primera evaluación histórica lluvia–respuesta fluvial

**Estado:** RESEARCH_ONLY · TEST_ONLY · `activation_gate=BLOCKED`. Prohibida su utilización para alertas, colores, umbrales, publicación pública o afirmaciones de habilidad predictiva.

## Materiales y método reproducibles

- Lluvia: **IMERG Final V07B diaria** por cuenca experimental HydroSHEDS. No es un producto disponible en tiempo real.
- Caudales: promedios diarios extraídos de informes del **PECHP** (2016–2023), utilizando únicamente filas con `DOS_LECTORES` y valores no negativos. En el río Piura se utiliza `R_PIURA_1` solo cuando el informe identifica expresamente su sección como **Puente Sánchez Cerro**.
- Referencias por punto: río **Chira / El Ciruelo** y río **Piura / Puente Sánchez Cerro**. **Tumbes queda NO EVALUABLE** por ausencia de serie diaria de caudal compatible; se prohíbe utilizar caudales de Chira/Piura como sustitutos.
- Rejilla de hipótesis fijada antes de examinar la evaluación final: acumulados IMERG de **1, 3, 5 o 7 días** y desfases `P(t−lag)` vs `Q(t)` de **0 a 7 días**.
- Selección: máximo coeficiente de Spearman positivo en **2016–2020**, siempre que existan al menos 30 pares. Comprobación en temporadas **2021–2023**, no usadas para la selección.
- Todos los días sin observación completa de IMERG o sin caudal se descartan; **ausencia de datos ≠ lluvia de 0 mm**. Se conservan fechas de calendario y no se extrapolan resultados a otros ríos.

## Primer resultado (CI #41688267529 y #41688617468)

| Río/estación | Hipótesis seleccionada antes del periodo de comprobación | n entrenamiento | Spearman entrenamiento | n 2021–2023 | Spearman 2021–2023 | Spearman tras eliminar medias mensuales |
|---|---|---:|---:|---:|---:|---:|
| Chira / El Ciruelo | Acumulado 7 días; lag 0 días | 302 | 0,641 | 360 | **0,660** | **0,609** |
| Piura / Sánchez Cerro | Acumulado 7 días; lag 5 días | 305 | 0,601 | 360 | **0,675** | **0,212** |
| Tumbes | NO EVALUABLE | — | — | — | — | — |

Una correlación estadística no es un pronóstico. Para **Chira el desfase 0** impide anticipar el flujo con esa hipótesis. Para **Piura**, la caída tras corregir la media mensual sugiere estacionalidad compartida y obliga a una validación mucho más exigente. Ninguno de estos resultados demuestra capacidad para detectar desbordes o predecir impactos.

### Controles de falsificación histórica

El control no causal con lluvia **posterior** al caudal obtiene una correlación en el periodo reservado de **0,284 (Chira)** y **0,403 (Piura)**, lo cual respalda la necesidad de no interpretar la correlación de Piura como causal o predictiva. Los controles de desfase circular entre pares observados se consideran descriptivos (los días faltantes impiden tomarlos como desplazamientos reales del calendario).

Se añadió también una comparación con la **persistencia del caudal del día anterior**, construida sobre los mismos días de prueba; sus resultados quedan en el artefacto JSON de CI y requieren revisión antes de cualquier pretensión de pronóstico.

## Limitaciones decisivas

1. **Convención diaria PECHP desconocida**, frente a la ventana UTC IMERG (en Perú, el día UTC no coincide con el día civil). Diferencias de ±1 día podrían alterar el desfase estimado.
2. **Infraestructura hidráulica y trasvase Chira→Piura**, más operación de Los Ejidos/Curumuy y otras derivaciones: la relación lluvia–caudal no es puramente natural.
3. El promedio de lluvia por cuenca depende de un área HydroSHEDS **experimental**, con fuentes geoespaciales que no constituyen validación oficial.
4. **No hay caudales y niveles históricos uniformes para Tumbes** en este conjunto, ni umbrales calibrados de desborde.
5. Un periodo reservado reduce el sobreajuste, pero hay **autocorrelación, eventos poco frecuentes y dependencia entre estaciones**. Los coeficientes Spearman descriptivos no pueden convertirse en probabilidad de alarma.
6. No se han calculado errores de predicción fuera de muestra comparables con un modelo ingenuo operativo, ni confiabilidad, incertidumbre por bloque ni validación prospectiva.

## Siguientes tareas científicas (sin activar alertas)

1. Conseguir series verificables de caudal/nivel para Tumbes, Chira y Piura; armonizar estación, referencia hidráulica, fecha, zona horaria y cobertura.
2. Separar efectos de lluvia meteorológica y gestión de embalses/canales, con reportes PECHP y evidencia hidrológica trazable.
3. Validar por **eventos independientes** y temporadas completas, con controles de no evento y persistencia, antes de proponer criterios de activación.
4. Enlazar de forma explícita con los 32 puntos HydroSHEDS/HydroRIVERS que siguen bajo revisión en el [PR #486](https://github.com/IRFEN2026/irfen-peru/pull/486).

**Ningún color ni alerta de IRFEN se modifica en este PR.**
