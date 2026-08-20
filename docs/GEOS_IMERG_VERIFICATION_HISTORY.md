# Histórico científico GEOS–IMERG v0.8

## Propósito

`site/data/forecast/imerg_verification_history.json` es la única fuente de
observaciones aceptada por `verify_geos_against_imerg.py`. La ventana móvil de
`site/data/latest.json` puede aportar candidatos nuevos mediante el actualizador
dedicado, pero nunca se usa para reconstruir evidencia acumulada.

Antes de extraer candidatos, el actualizador rechaza expresamente cualquier
`latest.json` con marca `DEMO`, `STATIC_FALLBACK`, `fallback_used=true`, producto
distinto de `GPM_3IMERGDL` o sin procedencia NASA IMERG y fecha de generación.
El rechazo ocurre antes de escribir el histórico.

El histórico permanece en `TEST_ONLY`: no cambia umbrales, no habilita alertas,
no modifica v0.7.1 y no activa candidatos de fase 2.

## Contrato de retención

- Clave única: `zone_id + sampling_method + valid_date_utc`.
- Modo: `APPEND_ONLY` con retención indefinida.
- Duplicado idéntico: se deduplica y se registra en `change_log`.
- Valor distinto para una clave existente: la corrida falla antes de escribir.
- Retirada: solo mediante un tombstone añadido por commit manual revisado, con
  `approval_reference`, aprobador, motivo, fechas, SHA-256 canónico de la
  observación y SHA-256 canónico de su evidencia de procedencia.
- `automatic_tombstone_creation=false`: ningún workflow ni actualizador posee
  una ruta de creación automática de retiradas.
- Dato ausente: permanece desconocido; nunca equivale a cero o riesgo bajo.

## Persistencia durable y restauración

La fuente de verdad durable es el archivo versionado en Git, no GitHub Pages.
Cada adquisición directa que añade observaciones supera primero las pruebas y
después crea un commit dedicado de ese único archivo en `main`. Pages es sólo
una réplica publicable.

`restore_imerg_verification_history.py` parte siempre del ledger del checkout
Git. Una réplica de Pages sólo se acepta si conserva, sin alterar, todas las
observaciones, evidencias, tombstones y entradas de `change_log` durables. Si
Pages no está disponible, contiene JSON inválido o presenta una regresión, se
restauran exactamente los bytes del ledger Git y se emite un recibo con rutas,
hashes y modo `GIT_VERSIONED_DURABLE_RESTORE`.

## Backfill del 7 de agosto de 2026

La semilla conserva la evidencia del artefacto Pages de `update-and-deploy`
run #170 (run id `32300707086`, commit de origen
`5082bc526a3023e141bf5b1a0fb3ad6c451ec1c7`).

- SHA-256 del artefacto: `88c0cd15ebbde7a9b789cacf4720c81e946e31d46f60546275fcac1dad851d9b`.
- Ruta interna: `data/forecast/verification.json`.
- SHA-256 de verification: `f4a79332710e8531e588b1f56222933e710439f38627c28a988ee7d11970ae1b`.
- Observaciones candidatas: 33; 30 ya estaban en la ventana de diez días y
  tres corresponden al 7 de agosto, una por piloto.
- Pares maduros recuperados en ese backfill: 12, cuatro por piloto.

Los conteos del evento son evidencia histórica, no constantes del pipeline. El
smoke exige como contrato un mínimo por piloto y coherencia interna; el total
puede crecer a medida que maduran nuevos forecast.

## Cadena verificable

1. `verification.json` registra las rutas y SHA-256 de forecast horario,
   forecast diario e histórico IMERG, junto con workflow, run, commit, modo de
   adquisición, retención, rango temporal y estado de monotonicidad.
2. `v08_scorecard.json` incorpora el SHA-256 completo de `verification.json`.
3. `v08_rc_status.json` valida ese enlace e incorpora el SHA-256 completo de la
   scorecard, preservando también el hash de verification.
4. El smoke remoto recalcula ambos hashes desde los bytes publicados.

## Actualización y monotonicidad

`update_imerg_verification_history.py` añade únicamente adquisiciones NASA
directas con `fallback_used=false`. Después, el verificador compara el resultado
con la verification publicada anterior. Cualquier disminución total o por piloto
sin una retirada aprobada y vinculada por hashes a la observación exacta hace
fallar el workflow antes del despliegue.
