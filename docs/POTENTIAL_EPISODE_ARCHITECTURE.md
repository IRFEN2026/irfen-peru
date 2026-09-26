# IRFEN Potential Episode Architecture v0.1

## Estado

`SHADOW_ONLY` / `TEST_ONLY` / `production_use=false` / `production_ready=false`.

El Potential Episode Detector es el primer componente del pipeline por excepción. Consume el estado científico experimental y sólo identifica candidatos que merecen evaluación posterior. No crea alertas, niveles de riesgo, decisiones de evacuación ni publicaciones.

## Frontera arquitectónica vigente

```text
fuentes científicas
      |
      v
IRFEN scientific core
      |
      v
site/data/experimental_state.json
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
                  |
                  +--> NO_CANDIDATE
                  +--> UNDER_SCIENTIFIC_REVIEW
                  +--> SCIENTIFIC_BLOCKED
```

El detector permanece estrictamente consumidor del estado experimental. No modifica `build_experimental_state.py`, umbrales, scorecard, RC, evidencia externa ni el contrato operativo heredado.

## Alcance del detector

Sólo evalúa los tres pilotos v0.8:

- `san_ildefonso`;
- `chosica`, como contenedor experimental legado de Lima Este;
- `catacaos`.

Las zonas de fase 2 y el Independent Basin Validation Framework permanecen fuera de este componente.

## Estados del detector

### `NO_EPISODE`

No existe una recomendación `TEST_ONLY` configurada para abrir un episodio potencial, o la señal fue bloqueada por una guarda fail-closed.

### `POTENTIAL_EPISODE`

Una recomendación `TEST_ONLY` ya producida por el núcleo científico coincide con una regla explícita del contrato y supera las guardas mínimas de entrada.

`POTENTIAL_EPISODE` **no significa** alerta, riesgo alto, evento confirmado, `SCIENTIFIC_PASS`, elegibilidad de comunicación ni autorización de publicación.

## Mapeo v0.1

- `TEST_NO_TRIGGER` -> `NO_EPISODE`;
- `TEST_WATCH` -> `NO_EPISODE` con `watch_only=true`;
- `TEST_FORECAST_REVIEW` -> candidato;
- `TEST_OBSERVED_THRESHOLD_CROSSING` -> candidato;
- `TEST_STRONG_OBSERVED_SIGNAL` -> candidato;
- `TEST_RIVER_MODEL_SIGNAL` -> candidato.

Una recomendación desconocida falla cerrada.

## Gate mínimo de candidato

Una señal mapeada a candidato sólo puede producir `POTENTIAL_EPISODE` si:

1. la zona mantiene `test_ready=true`;
2. `production_use=false`;
3. la recomendación mantiene `mode=TEST_ONLY`;
4. `operational_alert=false`;
5. `thresholds_modified=false`;
6. no existe una marca explícita `STALE`, `EXPIRED` u `OUTDATED` en campos de estado/frescura.

La v0.1 no inventa un umbral temporal de frescura.

## Reproducibilidad

Cada ejecución conserva el SHA-256 de `experimental_state.json`, su `generated_at`, la recomendación TEST_ONLY, razón upstream y bloqueadores. El `episode_id` es determinista por zona, timestamp fuente y hash fuente.

Runtime output:

`site/data/episodes/shadow/latest.json`

La salida mantiene obligatoriamente:

```text
mode=SHADOW_ONLY
production_use=false
production_ready=false
operational_alert=false
public_social_publishing=false
scientific_pass=false
```

El resumen siempre registra `alerts_created=0` y `publications_created=0`.

## Separación del Scientific Episode Gate v0.1

La evaluación científica posterior está implementada en `scripts/evaluate_scientific_episode_gate.py` y documentada en `docs/SCIENTIFIC_EPISODE_GATE_V01.md`.

El Gate no modifica la semántica del detector. En particular:

- San Ildefonso entra al carril `debris_flow_flash_runoff`;
- Catacaos entra al carril `river_floodplain`;
- el candidato legado `chosica` **no se atribuye automáticamente** a ninguno de los dos submodelos de Lima Este;
- Huaycoloro principal y las quebradas locales/Pedregal requieren cada uno una futura señal explícita de su propio mecanismo.

El Gate v0.1 tampoco implementa `SCIENTIFIC_PASS`: sólo abre revisión o bloquea por mecanismo.

## Fuera de alcance de esta PR

- `DISMISSED` por revisión humana;
- `SCIENTIFIC_PASS`;
- replay histórico del pipeline de episodios;
- persistencia de un ledger de episodios;
- generación pública de reporte, mapa o tarjeta;
- Communication Gate;
- integración con Facebook, Instagram u otros canales.

## Siguiente incremento

Una vez validado el Gate v0.1, el siguiente paso debe definir el expediente de revisión humana por episodio/mecanismo y la semántica auditable de `DISMISSED` / eventual `SCIENTIFIC_PASS`. No se debe implementar publicación antes de cerrar ese contrato.
