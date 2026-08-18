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
retrospectivas para completar la muestra. La primera fotografía archivada de
cada día UTC es inmutable: una reejecución del workflow no reemplaza entradas,
pronósticos o recomendaciones ni siquiera mientras la revisión está pendiente.
Esto impide incorporar retrospectivamente información aparecida después de la
captura original.

La fotografía elegible se toma al comienzo de la jornada: el workflow apunta a
las 00:10 UTC y admite como máximo dos horas de demora. Una ejecución posterior
se omite sin crear ni reemplazar el registro. Las capturas históricas realizadas
fuera de esa ventana permanecen auditables, pero no cuentan para el cierre,
aunque más tarde reciban una etiqueta `EVENT` o `NONE`.

La revisión solo puede comenzar después de las 00:00 UTC del día siguiente.
Una etiqueta aplicada antes de cerrar la jornada sería parcial y no es válida,
aunque exista ya una noticia o un aviso oficial durante el día.

Un día solo es elegible si, en el momento de la fotografía:

1. estaban presentes los tres pilotos;
2. la fotografía se archivó dentro de la ventana pre-resultado de dos horas;
3. todas las recomendaciones eran `TEST_ONLY` y no operativas;
4. GEOS estaba disponible y tenía al menos 30 pares por piloto;
5. IMERG Early estaba disponible con latencia registrada;
6. la regresión estaba en `PASS`;
7. la entrada conservaba `production_use=false`.

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
de consulta, identidad del revisor humano, marca `automatic=false`, instante de
cierre de la ventana UTC y nota que explique cobertura temporal y espacial.
`NONE` conserva además la confirmación explícita de cobertura integral. Una
revisión existente no se sobrescribe por defecto. Toda
corrección exige el indicador explícito `--replace-existing-review`, un
`reviewed_at` posterior y conserva íntegramente la versión reemplazada en
`outcome_verification_history`, además del commit y pull request que documenten
el cambio.

Las anotaciones se aplican con `scripts/review_shadow_outcome.py`. El comando
rechaza fuentes fuera de dominios institucionales, exige evidencia positiva
para `EVENT`, un revisor identificado y una confirmación explícita de cobertura
para `NONE`. La scorecard vuelve a comprobar estos campos aunque el JSON se
edite por fuera de la herramienta. Una
revisión `UNCERTAIN` queda auditada, pero no cuenta para el cierre.

## Regla de promoción

Completar esta muestra no autoriza por sí solo una alerta operativa. El 100%
también exige resolver los bloqueos científicos e hidráulicos y cerrar el
documento final con el marcador explícito `Release status: COMPLETE`.
