# IRFEN v0.9.1 · Procedimiento de reversión de la integración #504 + #505

Rama candidata: `research/v091-integration-main-20261110`. Estado: RESEARCH_ONLY / TEST_ONLY.

Este procedimiento no está autorizado a fusionar ni a activar nada. Describe cómo deshacer la integración si en el futuro se autoriza fusionarla en `main`.

## 1. Qué entraría en `main` y en qué estado

| Componente | Archivo | Estado tras fusionar |
|---|---|---|
| Registro de frescura tras cada captura | `scripts/v091_capture_freshness.py`, pasos nuevos en `.github/workflows/v09-rain-north.yml` | Pasivo: se registra la decisión como `SIMULADO` en `data/v09/rain/freshness_ledger_v0_1.json`. No se pide nada |
| Petición de reconstrucción tras captura | Paso «Request ONE private-viewer rebuild» en `v09-rain-north.yml` | **Apagado.** Solo se ejecuta si la variable del repositorio `IRFEN_V091_AFTER_CAPTURE_DISPATCH` vale `true` (no está definida) |
| Destino de la petición | `research/v091-viewer-after-capture-20261110` (constante en el paso `gate`) | Admite `mode=after_capture`. Su propia configuración tiene `after_capture.enabled=false` |
| Reconstrucción del visor | `.github/workflows/v091-live-refresh.yml`, `scripts/v091_live_refresh.py`, `config/v091_live_refresh.json` | Sin `schedule`. En `main` solo se dispararía a mano. Cadena de 20 min con `enabled=false` (caducidad vencida el 09-11, no renovada) y `after_capture.enabled=false` |
| Visor privado | `site/v09/vigilancia.html`, `site/data/v09/surveillance_view_v0_1.json`, `scripts/v09_build_surveillance_view.py` | Sin desplegar. Resumen por cuenca, histórico separado, advertencia #496, 4 puntos sin cuenca nombrados |
| Paso «Territorial view bundle» | `v09-rain-north.yml`, `v09-senamhi-avisos-capture.yml` | Solo visualización, con `continue-on-error`. No bloquea la captura |
| Flujos de prueba | `research-v091-after-capture-test.yml`, `research-v091-integrated-e2e.yml` | Inertes en `main`: solo se disparan con un `push` a sus ramas `research/*` |

Hay **tres interruptores independientes**. Los tres están apagados y hacen falta los tres para que una captura produzca una reconstrucción real:
1. `IRFEN_V091_AFTER_CAPTURE_DISPATCH=true` en el repositorio. Sin él, nada se envía.
2. `after_capture.enabled=true`, con una caducidad explícita, en la configuración de la rama destino. Sin él, la reconstrucción pedida se niega.
3. La cadena de 20 min tiene su propio `enabled`, hoy en `false`. No interviene en `after_capture`.

## 2. Reversión por niveles (de menor a mayor impacto)

### Nivel 0 · parada inmediata, sin tocar código (segundos)

1. Borrar la variable del repositorio, o ponerla a `false`: Settings → Secrets and variables → Actions → Variables → `IRFEN_V091_AFTER_CAPTURE_DISPATCH`. La captura siguiente registrará `after-capture rebuild request: false`.
2. Si hubiera reconstrucciones en curso:
   ```
   gh workflow disable v091-live-refresh.yml -R IRFEN2026/irfen-peru
   ```
   Esto desactiva el flujo en todas las ramas, incluida la rama destino.

### Nivel 1 · rama destino

En `research/v091-viewer-after-capture-20261110`, poner `after_capture.enabled=false` en `config/v091_live_refresh.json` (es el valor actual). Una petición que llegue se rechazará en el paso de control con la razón `after_capture.enabled=false`.

### Nivel 2 · revertir la fusión en `main`

Con un PR, nunca con un `push --force`:
```
git switch -c revert/v091-integration main
git revert -m 1 <SHA del merge de la integración>
git push -u origin revert/v091-integration
gh pr create --base main --draft --title "Revertir integración v0.9.1 (#504 + #505)"
```
- `-m 1` conserva el lado de `main`. Se eliminan el script de frescura, los pasos nuevos de las capturas, el flujo de reconstrucción, los cambios del visor y los flujos de prueba.
- Los commits de datos que las capturas de `main` hayan hecho después de la fusión **no se revierten**: son datos reales de NASA, SENAMHI e INDECI.
- `data/v09/rain/freshness_ledger_v0_1.json` puede quedar como registro o borrarse en el mismo PR. No lo lee ningún otro componente.

### Nivel 3 · limpieza de ramas de prueba

Opcional, con autorización. Son ramas aisladas con evidencia de pruebas; ninguna está programada:
- `research/v091-e2e-capture-20261110m-*`, `research/v091-e2e-capture-20261110-*`, `research/v091-e2e-capture-20261109`
- `research/v091-live-data-test-20261110-main`, `research/v091-live-data-test-20261110`, `research/v091-live-data-test-20261109`
- `research/v091-wfcheck-20261109` (diagnóstico de Actions)

## 3. Comprobaciones tras revertir

1. La siguiente ejecución de `v09-rain-north.yml` en `main` termina en `success` y su registro **no** contiene `V091_FRESHNESS` (nivel 2) o muestra `after-capture rebuild request: false` (niveles 0 y 1).
2. No aparecen nuevas ejecuciones de `v091-live-refresh.yml`:
   ```
   gh run list -R IRFEN2026/irfen-peru --workflow v091-live-refresh.yml -L 5
   ```
3. Las capturas de `main` (IMERG, GOES, avisos) siguen actualizando sus archivos como antes de la integración.
4. Los archivos originales no cambian por la reversión. Comprobarlo con `git diff --stat <merge>^1 HEAD -- data/` y revisar que solo aparezcan los archivos de datos posteriores a la fusión.

## 4. Qué no hace la reversión

- No borra datos capturados ni modifica archivos originales.
- No toca la rama de datos real `research/v091-live-data` ni el lanzamiento congelado RP1.
- No afecta a SILVIA, calibración, umbrales ni semáforos (la integración no los cambia).
