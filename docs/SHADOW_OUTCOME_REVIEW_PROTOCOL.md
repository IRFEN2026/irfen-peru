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

La fotografía elegible se toma al comienzo de la jornada. El workflow intenta
capturarla a las 00:10 UTC y repite a las 00:50 y 01:30 UTC para cubrir demoras
de GitHub Actions. Los intentos se serializan y solo el primero que logra crear
la fotografía puede publicarla; los demás conservan el registro inmutable y no
ordenan despliegues redundantes. La ventana admite como máximo dos horas de
demora desde el comienzo del día. Una ejecución posterior se omite sin crear ni
reemplazar el registro. Las capturas históricas realizadas fuera de esa ventana
permanecen auditables, pero no cuentan para el cierre, aunque más tarde reciban
una etiqueta `EVENT` o `NONE`.

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

La captura de INDECI/COEN sigue, de forma acotada, la paginación oficial que
la propia página anuncia para la fecha revisada. Los enlaces repetidos se
deduplican y cada página adicional conserva URL, estado HTTP y huella de
contenido. Una página que no responde deja la cobertura como
`PARTIAL_UNKNOWN_NOT_ZERO`; nunca convierte la falta de coincidencias en
`NONE`.

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

Las anotaciones se aplican con `scripts/review_shadow_outcome.py` o, de forma
preferente para reducir errores manuales, con el workflow **IRFEN - Revisar
resultado diario en sombra v0.8** (`review-shadow-outcome.yml`). En GitHub
Actions se selecciona la jornada cerrada y una etiqueta conservadora; se pega
una URL oficial por línea y se explica la cobertura temporal y espacial. El
workflow identifica al revisor mediante su cuenta de GitHub, conserva
`automatic=false`, publica el commit exacto y recalcula la scorecard. `EVENT`
exige describir el evento verificado; `NONE` exige marcar explícitamente que la
cobertura oficial fue integral. El valor predeterminado es `UNCERTAIN`.

El comando y el workflow
rechazan fuentes fuera de dominios institucionales, exigen evidencia positiva
para `EVENT`, un revisor identificado y una confirmación explícita de cobertura
para `NONE`. La scorecard vuelve a comprobar estos campos aunque el JSON se
edite por fuera de la herramienta. Una
revisión `UNCERTAIN` queda auditada, pero no cuenta para el cierre.

## Regla de promoción

Completar esta muestra no autoriza por sí solo una alerta operativa. El 100%
también exige resolver los bloqueos científicos e hidráulicos y cerrar el
documento final con el marcador explícito `Release status: COMPLETE`.
