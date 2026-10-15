# IRFEN Episode Continuity and Regional Saturation Controller v0.1

## Estado y alcance

`SHADOW_ONLY` · `TEST_ONLY` · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `scientific_candidate_forwarding_enabled=false`

Este componente es un **sidecar de prueba** situado después de `Potential Episode Detector v0.1`. No modifica el detector, no alimenta todavía el `Scientific Episode Gate`, no cambia umbrales, no asigna niveles de riesgo y no envía mensajes. Su objetivo es comprobar que IRFEN no pierda utilidad cuando varias zonas permanecen activas durante ciclos consecutivos o se reactivan después de pausas breves.

## Problema que controla

Un detector instantáneo genera un identificador distinto cada vez que cambia el snapshot de entrada. En una temporada prolongada esto puede representar un mismo episodio como muchas aperturas, cierres y reaperturas independientes. El controlador añade continuidad sin afirmar que exista una validación científica de activación.

## Máquina de estados

`NORMAL → WATCH → ACTIVE → PERSISTENT → RECOVERY → NORMAL`

- `WATCH`: señal interna sin apertura de episodio.
- `ACTIVE`: primer candidato de episodio aceptado por las guardas del detector.
- `PERSISTENT`: tercer ciclo candidato consecutivo en el contrato de prueba.
- `RECOVERY`: desaparece temporalmente el candidato, pero el episodio permanece abierto.
- cierre: tercer ciclo claro consecutivo.
- reactivación durante `RECOVERY`: conserva el mismo `continuity_episode_id`.
- reactivación después del cierre: abre un identificador nuevo.

Los conteos de ciclos son **parámetros mecánicos de prueba**, no umbrales hidrológicos ni meteorológicos. El piloto deberá evaluar su equivalencia temporal según la frecuencia real de actualización.

## Histéresis y datos faltantes

Una entrada bloqueada, obsoleta, contradictoria o fuera de orden nunca se interpreta como señal clara. El controlador conserva el estado anterior y marca `BLOCKED_RETAINED_PREVIOUS`. Un snapshot duplicado es idempotente y no incrementa rachas ni duración.

## Evidencia temporal

La salida expone, sin interpolar ni completar con cero:

- lluvia de 1 h, 3 h, 6 h, 24 h, 72 h y 7 días;
- racha húmeda;
- humedad antecedente;
- tasa de respuesta disponible aguas arriba;
- confianza declarada por la fuente.

Actualmente `experimental_state.json` aporta de forma general 24 h, 72 h y 7 días. Las ventanas subdiarias ausentes se marcan `MISSING_NOT_INFERRED`. La fracción de completitud es sólo una métrica de disponibilidad; no es un riesgo ni una confianza calculada.

## Episodios locales y coordinación regional

Cada zona conserva su propio episodio local. El controlador puede agrupar episodios abiertos en un `coordination_cluster_id` para resumir concurrencia, pero declara siempre:

`shared_hydrologic_event=false`

San Ildefonso y Catacaos pertenecen al grupo de coordinación de costa norte únicamente para ensayar carga regional. No se afirma que compartan una misma cuenca, respuesta hidráulica o episodio científico.

## Modo de saturación

El contrato de prueba entra en `REGIONAL_SATURATION_TEST` cuando al menos dos de los tres pilotos están en `ACTIVE`, `PERSISTENT` o `RECOVERY` y representan al menos 66 % del conjunto. `RECOVERY` se cuenta para evitar parpadeos durante pausas breves.

La salida sólo produce una vista previa de comunicación por excepción:

- una síntesis regional en vez de mensajes repetidos por punto;
- transiciones nuevas, persistentes, reactivadas, en recuperación o cerradas;
- cero alertas, cero publicaciones y cero correos creados por el componente;
- ninguna prioridad operativa.

## Reproducción y piloto

El script admite dos modos:

```bash
python scripts/control_episode_continuity.py
python scripts/control_episode_continuity.py \
  --replay-sequence ruta/secuencia.json \
  --output /tmp/episode-continuity-replay.json
```

Una secuencia de replay contiene `frames[]`, cada uno con `potential`, `experimental` y `generated_at`. El reporte calcula aperturas, cierres, reactivaciones, transiciones persistentes, cambios de ID aguas arriba absorbidos, máxima concurrencia y ciclos de saturación.

## Criterios para el piloto posterior

El piloto debe usar primero snapshots históricos o sintéticos sellados y evaluar dos modos por separado:

1. **Ordinario:** una zona, apertura, persistencia, pausa, reactivación y cierre.
2. **Extremo:** varias zonas simultáneas durante varios días, pausas breves, entradas faltantes y recuperación escalonada.

Antes de conectar este sidecar al `Scientific Episode Gate` deben fijarse la cadencia de actualización, la equivalencia horas/ciclos, las reglas por mecanismo y los criterios de revisión humana. Hasta entonces `scientific_candidate_forwarding_enabled=false` es obligatorio.
