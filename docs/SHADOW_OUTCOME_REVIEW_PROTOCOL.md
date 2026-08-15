# IRFEN v0.8 — Protocolo de revisión de resultados en sombra

Estado: **TEST_ONLY / no operativo**

## Propósito

Este protocolo define cuándo una fotografía diaria puede contar para el cierre
de v0.8. La revisión compara lo que IRFEN registró antes de conocerse el
resultado con evidencia oficial posterior. No modifica umbrales, factores
hidráulicos, recomendaciones ni la v0.7.1.

## Unidad de evidencia

La unidad es un día UTC distinto ya conservado en
`site/data/validation/shadow_runs.json`. No se crean fotografías
retrospectivas para completar la muestra y no se reemplazan las entradas,
pronósticos o recomendaciones después de observar el resultado real.

Un día solo es elegible si, en el momento de la fotografía:

1. estaban presentes los tres pilotos;
2. todas las recomendaciones eran `TEST_ONLY` y no operativas;
3. GEOS estaba disponible y tenía al menos 30 pares por piloto;
4. IMERG Early estaba disponible con latencia registrada;
5. la regresión estaba en `PASS`;
6. la entrada conservaba `production_use=false`.

## Fuentes aceptables para el resultado

La revisión debe enlazar evidencia oficial fechada y espacialmente pertinente:

- SENAMHI para precipitación observada, avisos y estaciones;
- ANA para nivel, caudal o estado fluvial;
- INDECI/COEN para emergencias e impactos verificados;
- entidades regionales o locales oficiales únicamente como corroboración.

Una noticia, una publicación social o un testimonio pueden abrir una revisión,
pero no cierran por sí solos el resultado.

## Etiquetas

- `EVENT`: existe evidencia oficial de un evento hidrometeorológico o impacto
  pertinente para al menos uno de los tres pilotos durante el periodo.
- `NONE`: la cobertura oficial revisada permite concluir que no hubo un evento
  pertinente. No equivale a “no encontré datos”.
- `UNCERTAIN`: la evidencia falta, no cubre el territorio o es contradictoria.
  No cuenta para el cierre.

La ausencia de IMERG, estación, parte oficial o señal fluvial nunca se etiqueta
automáticamente como `NONE`.

## Muestra mínima de cierre

El contrato exige 30 días distintos, elegibles y revisados, incluyendo como
mínimo un día `EVENT` y diez días `NONE`. El resto puede pertenecer a cualquiera
de esas dos clases. Los registros `UNCERTAIN` y los días técnicamente
incompletos permanecen en el archivo, pero no incrementan el hito.

## Registro de auditoría

Cada revisión debe conservar: etiqueta, evento verificado, URL oficial, fecha
de consulta y nota que explique cobertura temporal y espacial. Una corrección
posterior debe mantener trazabilidad del valor anterior mediante commit y pull
request.

## Regla de promoción

Completar esta muestra no autoriza por sí solo una alerta operativa. El 100%
también exige resolver los bloqueos científicos e hidráulicos y cerrar el
documento final con el marcador explícito `Release status: COMPLETE`.
