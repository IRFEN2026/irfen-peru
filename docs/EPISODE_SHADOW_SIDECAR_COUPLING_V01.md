# IRFEN — Acoplamiento persistente del sidecar de episodios v0.1

## Estado

`SHADOW_ONLY` · `TEST_ONLY` · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `scientific_candidate_forwarding_enabled=false`

Este documento define el primer acoplamiento técnico del `Potential Episode Detector` y del `Episode Continuity and Regional Saturation Controller` al pipeline real de IRFEN. El acoplamiento permanece contenido en una PR borrador: no funciona en `main` y no comenzará a producir checkpoints hasta que exista una autorización separada de merge y finalice posteriormente una ejecución satisfactoria del workflow upstream.

No se acopla todavía la salida del controlador al `Scientific Episode Gate`. Tampoco se habilitan alertas, publicaciones, correos, prioridades operativas ni decisiones de evacuación.

## Arquitectura

```text
IRFEN — Actualizar IMERG y publicar
                │ workflow_run SUCCESS
                ▼
IRFEN - Actualizar continuidad de episodios en sombra
                │
                ├── descarga experimental_state.json publicado
                ├── descarga latest.json publicado
                ├── construye un sobre de fuente trazable
                ├── ejecuta Potential Episode Detector v0.1
                ├── ejecuta Continuity Controller v0.1
                ├── valida latest + continuity + history
                ├── persiste únicamente tres archivos en main
                └── despacha el publicador existente con SHA exacto
                                 │
                                 ▼
IRFEN - Publicar datos experimentales archivados
                                 │ workflow_run SUCCESS
                                 ▼
IRFEN - Verificar continuidad de episodios publicada
                ├── exige paridad byte a byte main ↔ Pages
                ├── valida cadena de hashes
                ├── valida monotonicidad e idempotencia
                └── confirma 0 alertas, 0 publicaciones y 0 mensajes
```

El workflow sidecar es el único escritor canónico del estado de continuidad. Su grupo de concurrencia está serializado y no cancela ejecuciones en curso.

## Sobre de fuente

Cada ciclo se basa en dos componentes publicados conjuntamente por IRFEN:

1. `site/data/experimental_state.json`: recomendaciones y señales integradas `TEST_ONLY`.
2. `site/data/latest.json`: identidad y estado de adquisición del dataset NASA IMERG.

El sidecar congela en su trazabilidad:

- SHA-256 exacto de ambos componentes;
- `generated_at` del estado experimental;
- `generated_at` del dataset;
- `last_update_attempt`;
- fuente `NASA GPM IMERG Late Daily`;
- producto `GPM_3IMERGDL` y versión;
- `operational_status=updated|stale`;
- `dataset_freshness_status=FRESH|STALE`.

No se admite una fuente `DEMO`, una versión demostrativa, un estado desconocido ni un documento sin zona horaria.

## Tratamiento de una caída de NASA

El workflow upstream puede terminar satisfactoriamente conservando el último dataset válido y publicando:

```text
operational_status=stale
```

Ese caso no se interpreta como un día seco ni como ausencia de activación. El sidecar añade una marca explícita `STALE` a cada carril de decisión antes de ejecutar el detector. El resultado se registra como entrada bloqueada:

- conserva el `continuity_episode_id` anterior;
- conserva `ACTIVE`, `PERSISTENT` o `RECOVERY` según corresponda;
- no incrementa `clear_streak`;
- no cierra el episodio;
- no aumenta la racha candidata;
- no crea alertas, publicaciones ni mensajes;
- deja evidencia auditable del bloqueo en el historial.

Así se evita que una indisponibilidad de IMERG produzca una falsa recuperación o cierre.

## Persistencia durable

`main` es la única fuente durable de verdad. GitHub Pages funciona sólo como réplica publicada.

El sidecar persiste, en un único commit, exclusivamente:

```text
site/data/episodes/shadow/latest.json
site/data/episodes/continuity/shadow/latest.json
site/data/episodes/continuity/shadow/history.json
```

El historial es `APPEND_ONLY` y usa como clave de deduplicación:

```text
(potential_source_sha256, source_generated_at)
```

Cada registro conserva hashes de los dos componentes de entrada, hashes del detector y del controlador, estados y transiciones por zona, bloqueadores de entrada, simultaneidad y saturación regional.

No existen borrado automático, tombstones automáticos, force-push ni sobrescritura silenciosa.

## Idempotencia, orden y concurrencia

### Snapshot exacto repetido

Produce:

```text
NOOP_DUPLICATE_SOURCE
```

No incrementa contadores, no modifica archivos, no crea commit y no ordena una nueva publicación.

### Snapshot anterior al estado durable

Falla cerrado. No rebobina el episodio ni modifica el historial.

### Estado durable parcial o manipulado

Si falta uno de los tres archivos, no coinciden los hashes o se rompe la secuencia monotónica, la ejecución termina sin mutación.

### Escritura concurrente

Antes de persistir se compara el estado sidecar validado con el `main` remoto más reciente. Una escritura ajena en otros archivos puede reintentarse. Cualquier modificación concurrente de uno de los tres archivos de episodios detiene el proceso sin adoptar, fusionar ni sobrescribir ese cambio. Como el escritor canónico está serializado, una modificación de este tipo se trata como una anomalía que exige revisión.

## Semántica temporal

Un ciclo no equivale todavía a una hora ni a un día. La unidad actual es:

```text
ONE_DISTINCT_PUBLISHED_SOURCE_ENVELOPE
```

El workflow upstream tiene una ejecución rutinaria programada y también puede ejecutarse manualmente o después de otros procesos científicos. Por ello:

- tres ciclos candidatos no deben describirse todavía como tres días consecutivos;
- la transición a `PERSISTENT` sigue siendo una mecánica de prueba;
- la equivalencia ciclo–tiempo debe estimarse con el historial real de ejecuciones;
- no se ha validado una cadencia subdiaria;
- este acoplamiento no convierte IRFEN en un sistema de alerta en tiempo real.

El historial permitirá medir los intervalos reales entre sobres de fuente y preparar posteriormente reglas temporales por mecanismo.

## Publicación y smoke posterior

Después de un append válido, el sidecar despacha el publicador existente con el SHA exacto del commit persistido. El smoke posterior exige:

- que el SHA solicitado sea ancestro del `main` publicado;
- paridad byte a byte entre los tres archivos de `main` y Pages;
- hashes del último detector y controlador idénticos al historial;
- claves únicas y timestamps estrictamente crecientes;
- correspondencia `updated→FRESH` y `stale→STALE`;
- en un último ciclo `STALE`, todas las zonas retenidas y ninguna racha de cierre incrementada;
- ausencia de campos de alerta, riesgo, publicación o prioridad operativa;
- cero mensajes, cero alertas y cero publicaciones.

## Separación respecto de la puerta científica

El flujo científico continúa separado:

```text
Potential Episode Detector → Scientific Episode Gate v0.1
```

El sidecar de continuidad no reemplaza esa señal ni la alimenta todavía. Se conserva:

```text
scientific_candidate_forwarding_enabled=false
```

Una eventual conexión requerirá otro contrato, replay histórico real, reglas temporales diferenciadas por mecanismo y autorización explícita.

## Qué valida este acoplamiento

Valida técnicamente que IRFEN puede:

- recordar un episodio entre workflows independientes;
- no abrir un episodio nuevo en cada actualización;
- resistir snapshots repetidos o fuera de orden;
- mantener estados durante pérdidas explícitas de datos;
- conservar un historial auditable;
- publicar una réplica verificable;
- operar el controlador sin alterar scorecard, RC o puertas científicas.

No valida todavía:

- capacidad predictiva hidrológica;
- umbrales de lluvia o caudal;
- equivalencia correcta entre ciclos y duración física;
- activación real de quebradas o inundación fluvial;
- disponibilidad subdiaria;
- preparación operativa o alertamiento público.

## Primera observación real después de una eventual integración

Tras una autorización futura de merge, el primer workflow upstream satisfactorio inicializará el checkpoint durable. Las ejecuciones posteriores permitirán observar, sin uso operativo:

- intervalos reales entre ciclos;
- episodios abiertos y cerrados;
- permanencia en `PERSISTENT` y `RECOVERY`;
- días o ciclos con dataset `STALE`;
- máxima concurrencia entre pilotos;
- entrada y salida de `REGIONAL_SATURATION_TEST`;
- cambios de identificador aguas arriba absorbidos por continuidad.

El resultado de esa observación deberá evaluarse antes de considerar cualquier acoplamiento decisional.
