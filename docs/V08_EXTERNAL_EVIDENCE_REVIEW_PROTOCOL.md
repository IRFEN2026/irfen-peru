# IRFEN v0.8 — Protocolo de revisión de evidencia externa

Estado: **TEST_ONLY / cierre bloqueado**

## Propósito

Este protocolo controla la revisión humana de la evidencia científica e
hidráulica exigida por `config/v08_external_validation_contract.json`. No
modifica umbrales, factores hidráulicos, recomendaciones ni la v0.7.1.

## Regla fundamental

`CANDIDATE_REVIEW` y `PARTIAL_CANDIDATE_REVIEW` son insumos para revisar, no
evidencia aceptada. Un elemento solo puede pasar a `ACCEPTED` cuando una
persona identificada confirma que el requisito completo está satisfecho por
fuentes oficiales trazables. Una brecha parcial, falta de acceso o ausencia de
datos nunca equivale a evidencia favorable ni a bajo riesgo.

## Decisiones permitidas

- `ACCEPTED`: las fuentes cubren íntegramente el requisito exacto del contrato.
- `REJECTED`: la evidencia revisada no lo cubre. El bloqueo permanece.

No existe aceptación automática. Para `ACCEPTED`, el comando exige la bandera
explícita `--confirm-requirement-fully-satisfied`, un revisor identificado,
fecha con zona horaria, justificación técnica y al menos una URL institucional
oficial. La confirmación no debe utilizarse si queda cualquier brecha descrita.

## Procedimiento

1. Verificar el `evidence_id` exacto en el contrato y revisar todas las fuentes.
2. Confirmar vigencia, ámbito espacial, unidades, configuración de la obra y
   relación con el piloto, según corresponda.
3. Registrar una decisión con `scripts/review_v08_external_evidence.py`.
4. Revisar el diff: solo debe cambiar el registro de evidencia externa.
5. Ejecutar la suite completa y tramitar el cambio por rama y pull request.

Ejemplo de rechazo conservador:

```bash
python scripts/review_v08_external_evidence.py \
  --zone-id catacaos \
  --evidence-id official_numeric_river_state_channel \
  --decision REJECTED \
  --reviewer "Nombre / institución" \
  --notes "La fuente no expone estación, unidad y hora trazables." \
  --reviewed-at 2026-08-16T06:00:00Z
```

Una revisión existente no se sobrescribe por defecto. Toda corrección exige
`--replace-existing-review`, un instante posterior y conserva la revisión
anterior en `review_history`.

## Límites

La aceptación de todos los elementos solo resuelve la puerta de evidencia
externa. No activa zonas ni alertas, no eleva por sí sola la scorecard a 100% y
no sustituye la muestra en sombra, la regresión, el smoke test ni la auditoría
final.
