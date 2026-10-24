# IRFEN Scientific Episode Gate v0.1

## Estado

`SHADOW_ONLY` / `TEST_ONLY` / `production_use=false` / `production_ready=false` / `operational_alerting_enabled=false`.

El Gate v0.1 consume candidatos del Potential Episode Detector y los enruta a carriles científicos separados. **No implementa `SCIENTIFIC_PASS`** y no puede emitir alertas, niveles de riesgo ni publicaciones.

## Frontera

```text
experimental_state.json
        |
        v
Potential Episode Detector
        |
        +--> NO_EPISODE
        |
        +--> POTENTIAL_EPISODE
                  |
                  v
        Scientific Episode Gate v0.1
          |        |        |
          |        |        +--> SCIENTIFIC_BLOCKED
          |        +----------> UNDER_SCIENTIFIC_REVIEW
          +-------------------> NO_CANDIDATE
```

La v0.1 termina antes de cualquier decisión de comunicación. `UNDER_SCIENTIFIC_REVIEW` sólo significa que existe un candidato correctamente atribuido y con contexto mínimo para revisión; no es una confirmación de evento.

## Mecanismos

### San Ildefonso — `debris_flow_flash_runoff`

Se conserva el artefacto histórico `san_ildefonso_test_rule.json` como contexto científico existente. El Gate **no copia ni recalcula sus valores umbral**. Para admitir un candidato a revisión requiere que:

- el candidato corresponda a `san_ildefonso`;
- el estado experimental siga `test_ready`;
- el artefacto histórico permanezca `TEST_ONLY`;
- el mismo carril subdiario IMERG Early esté actualmente disponible y no marcado stale.

Si el carril subdiario no está disponible, el candidato falla cerrado como `SCIENTIFIC_BLOCKED`. Esto no interpreta el último dato válido como lluvia cero ni inventa una ventana de frescura.

### Catacaos / Bajo Piura — `river_floodplain`

La revisión exige un estado fluvial disponible en el estado experimental. Puede conservarse un proxy categórico TEST_ONLY si el núcleo lo considera disponible, pero el Gate no lo convierte a caudal numérico ni infiere nivel crítico.

Los seis requisitos del ledger de evidencia externa se proyectan únicamente como estado de cierre pendiente. Un estado distinto de `ACCEPTED` nunca se promueve.

### Lima Este — Huaycoloro principal

No hereda automáticamente un `POTENTIAL_EPISODE` del contenedor legado `chosica`. El artefacto canónico de descomposición declara que ese contenedor agrupa mecanismos distintos; por tanto, Huaycoloro queda `SCIENTIFIC_BLOCKED` hasta que upstream produzca una señal candidata explícita y trazable del submodelo de cuenca/cauce principal.

### Lima Este — quebradas locales / Pedregal

Tampoco hereda un `POTENTIAL_EPISODE` de `chosica`. El submodelo local queda `SCIENTIFIC_BLOCKED` hasta que upstream produzca una señal candidata explícita y trazable del mecanismo local. Esta guarda evita convertir una señal agregada de Lima Este en evidencia de activación de Huaycoloro, Pedregal u otra quebrada sin atribución científica.

## Evidencia externa

El Gate sólo lee `site/data/validation/v08_external_evidence.json`. No escribe en ese ledger y no puede originar `ACCEPTED`.

Para cada mecanismo expone:

- requisitos aplicables;
- estado exacto del ledger;
- número aceptado;
- requisitos no aceptados.

Incluso si todos los requisitos llegaran a `ACCEPTED`, v0.1 mantiene `scientific_pass=false`. La futura habilitación de un pase científico requiere un contrato explícito de revisión humana, separado y auditable.

## Guardas

La salida mantiene:

- `production_use=false`;
- `production_ready=false`;
- `operational_alerting_enabled=false`;
- `public_social_publishing=false`;
- `thresholds_modified=false`;
- `scientific_acceptance_modified=false`;
- `scientific_pass_implemented=false`;
- `scientific_pass_count=0`;
- `alerts_created=0`;
- `publications_created=0`.

No se modifica el scorecard, el RC, v0.7.1, los umbrales científicos, la corrección de sesgo ni los workflows de publicación.

## Salida runtime

`site/data/episodes/scientific/shadow/latest.json`

Es un artefacto runtime. El Gate registra SHA-256 canónico de todas sus entradas para reproducibilidad.

## Próximo incremento permitido

Después de validar esta v0.1, el siguiente paso científico no debe ser la publicación. Debe definirse primero un expediente de revisión humana por episodio/mecanismo y los criterios de `DISMISSED` / eventual `SCIENTIFIC_PASS`, conservando la aceptación científica externa en su ledger canónico.
