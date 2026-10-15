# IRFEN — Resultados del piloto de continuidad y saturación v0.1

## Dictamen

**PASS — CONTROL_LOGIC_PASSED_NOT_HYDROLOGICAL_VALIDATION**

Fecha de ejecución: 5 de septiembre de 2026.

Este piloto valida exclusivamente la lógica de control de continuidad, histéresis, deduplicación, persistencia y saturación regional. No valida capacidad predictiva hidrológica, umbrales de lluvia, activación real de quebradas, preparación operativa ni emisión de alertas.

## Alcance ejecutado

Se ejecutaron 24 ciclos controlados y reproducibles, distribuidos en dos escenarios:

1. **Escenario ordinario:** 11 ciclos sobre una zona.
2. **Escenario extremo:** 13 ciclos con hasta tres zonas abiertas simultáneamente.

Los escenarios fueron predefinidos en `config/episode_continuity_pilot_v01.json` y ejecutados mediante `scripts/run_episode_continuity_pilot.py`.

## Resultado agregado

| Control | Resultado |
|---|---:|
| Escenarios aprobados | 2/2 |
| Comprobaciones métricas aprobadas | 24/24 |
| Puntos de control aprobados | 21/21 |
| Alertas creadas | 0 |
| Publicaciones creadas | 0 |
| Mensajes enviados | 0 |
| Promociones científicas automáticas | 0 |

## Escenario ordinario

Secuencia ensayada:

`WATCH → ACTIVE → PERSISTENT → RECOVERY → PERSISTENT → RECOVERY → NORMAL → ACTIVE`

Resultados:

| Métrica | Resultado |
|---|---:|
| Ciclos | 11 |
| Episodios abiertos | 2 |
| Episodios cerrados | 1 |
| Reactivaciones conservando el mismo episodio | 1 |
| Transiciones a `PERSISTENT` | 1 |
| Cambios de ID aguas arriba absorbidos | 2 |
| Máxima concurrencia | 1 zona |
| Ciclos de saturación regional | 0 |
| Ciclos idempotentes | 1 |

Hallazgos verificados:

- `WATCH` no abrió un episodio.
- El tercer ciclo candidato consecutivo produjo `PERSISTENT`.
- La primera pausa produjo `RECOVERY`, no cierre.
- La reactivación durante `RECOVERY` conservó el mismo `continuity_episode_id`.
- El tercer ciclo claro cerró el episodio.
- Una activación posterior al cierre recibió un nuevo identificador.
- Un snapshot duplicado fue idempotente y no incrementó rachas ni duración.

## Escenario extremo

Secuencia ensayada:

- San Ildefonso y Catacaos abren primero.
- Chosica se incorpora posteriormente.
- Las tres zonas permanecen abiertas simultáneamente.
- Se introduce una señal bloqueada para San Ildefonso.
- Se retiran las ventanas subdiarias de 1 h, 3 h y 6 h en parte de la secuencia.
- Las zonas entran en recuperación y cierre de forma escalonada.

Resultados:

| Métrica | Resultado |
|---|---:|
| Ciclos | 13 |
| Episodios abiertos | 3 |
| Episodios cerrados | 3 |
| Reactivaciones conservando el mismo episodio | 1 |
| Transiciones a `PERSISTENT` | 3 |
| Cambios de ID aguas arriba absorbidos | 12 |
| Máxima concurrencia | 3 zonas |
| Ciclos en `REGIONAL_SATURATION_TEST` | 10 |
| Observaciones bloqueadas retenidas | 1 |
| Ciclos idempotentes | 0 |

Hallazgos verificados:

- Dos zonas concurrentes activaron correctamente `REGIONAL_SATURATION_TEST`.
- El sistema sostuvo hasta tres episodios locales abiertos sin fusionarlos en un falso episodio hidrológico común.
- Todos los grupos mantuvieron `shared_hydrologic_event=false`.
- La entrada bloqueada no fue interpretada como señal clara: conservó el estado anterior y no aumentó la racha de recuperación.
- Las ventanas subdiarias faltantes quedaron como `MISSING_NOT_INFERRED`; no se sustituyeron por cero.
- `RECOVERY` se mantuvo como estado activo-like para evitar parpadeo del modo de saturación.
- La saturación terminó sólo después de la recuperación escalonada.
- Los tres episodios quedaron finalmente cerrados, con carga global `NORMAL_LOAD`.

## Validación del repositorio

La ejecución remota de la PR concluyó correctamente:

- suite completa: **364 pruebas, 364 aprobadas**;
- pruebas específicas del piloto: **6/6 aprobadas**;
- regresión IRFEN v0.8: **301/301 PASS**;
- validación científica: **PASS, 0 advertencias**;
- scorecard: **75 %**;
- RC: **RC_AVAILABLE_TEST_ONLY**.

## Barreras preservadas

Durante toda la prueba permanecieron:

```text
mode=SHADOW_ONLY
test_mode=TEST_ONLY
production_use=false
production_ready=false
operational_alerting_enabled=false
public_social_publishing=false
scientific_candidate_forwarding_enabled=false
hydrological_skill_validated=false
rainfall_thresholds_validated=false
operational_readiness_validated=false
```

No se fusionó la PR, no se desplegó el controlador y no se modificaron umbrales, scorecard, RC ni el ledger científico humano.

## Interpretación

El resultado demuestra que el controlador puede administrar, en un entorno sintético controlado:

- episodios prolongados;
- pausas breves y reactivaciones;
- múltiples zonas simultáneas;
- cambios repetidos de identificadores aguas arriba;
- información parcial o bloqueada;
- salida regional por excepción sin generar una tormenta de mensajes.

El piloto **no demuestra todavía** que IRFEN detecte correctamente activaciones reales. La siguiente validación debe reproducir series históricas reales, fijar la equivalencia entre ciclos y horas, evaluar reglas separadas por mecanismo y ampliar el análisis desde las tres unidades piloto hacia puntos o estaciones individuales.
