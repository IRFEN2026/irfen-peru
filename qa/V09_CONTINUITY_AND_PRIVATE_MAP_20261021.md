# IRFEN v0.9 — Continuidad de fuentes y mapa experimental (revisión 21-10-2026)

**RESEARCH_ONLY / TEST_ONLY; production_use=false; operational_alerting_enabled=false; activation_gate=BLOCKED.**
No hay activación, nuevas descargas, cambios de cron, publicación Pages ni operaciones sobre fuentes SENAMHI.

## Evidencia de puntualidad de GitHub Actions

Inspección de las ejecuciones **schedule** visibles entre el 20 y 21-10-2026 en GitHub Actions. Es una muestra acotada a los resultados recientes listados, **no** una auditoría exhaustiva de todos los intervalos.

| Flujo | Ejecuciones programadas observadas | Separaciones entre ejecuciones UTC | Mayor separación |
|---|---:|---|---:|
| v0.9 IMERG Early norte | 4 | 255, 185 y 139 min | 255 min |
| GOES-19 RRQPE test | 2 | 232 min | 232 min |
| INDECI/COEN avisos v0.9 | 3 | 201 y 178 min | 201 min |

Estas ejecuciones consultadas terminaron en `success`. **Eso solo valida el estado de ejecución del trabajo, NO demuestra que se hayan recibido nuevas observaciones, que todos los gránulos se encuentren en NASA o que las ventanas temporales estén completas.** Es incorrecto declarar `ABSENT_AT_SOURCE` por el mero hecho de no disponer de un registro local.

### Causa y alcance

El cron configurado en los workflows no se traduce en una cadencia garantizada de entrega por GitHub Actions. La causa concreta de estas separaciones no está demostrada con los logs. La corrección no consiste en asumir que se capturó información cuando el workflow aparece verde.

La evidencia anterior de #394 detectó 34 medias horas IMERG existentes entonces en NASA sin capturar por IRFEN. Fueron recuperadas en una rama de investigación (#396), auditadas estructuralmente (#397); su cierre científico sigue abierto (#398/#399) por dos identidades CMR no reproducibles. **Esa historia no justifica usarlas como observaciones operativas ni para el visor.**

## Cambio preparado en el mapa v0.9

Solo en el visor **privado** `site/v09/index.html`:

1. Una línea independiente resume la cobertura de 24 h **tal como figura en el paquete actual de lluvia por zona**: completas, incompletas y desconocidas.
2. El Centro de seguimiento incorpora el detalle de cobertura IMERG que antes solo aparecía en la pestaña de lluvia.
3. El rótulo aclara que **cobertura del archivo y puntualidad del programador son fenómenos diferentes**.
4. Cobertura ausente, malformada, mayor que el total o incompleta se trata como evidencia desconocida/incompleta, nunca se suma al conjunto completo.
5. No cambia prioridades R1–R6, niveles oficiales, avisos, umbrales, fuente científica, geometrías, archivos de lluvia, alertas ni publicación. No se presenta la cobertura como riesgo o como probabilidad de lluvia.

**Limitación:** la interfaz muestra la cobertura informada en el paquete vigente de v0.9; no calcula de forma autónoma atrasos de Actions ni pretende diagnosticar todas las ejecuciones históricas. Si el propio paquete está obsoleto, esta visualización tampoco representa continuidad actual.

## Siguiente fase recomendada, para autorización independiente

1. Desarrollar una auditoría de continuidad **por intervalo esperado UTC** que compare el registro de NASA/NOAA y las capturas locales con su timestamp, SHA-256 y estado, sin rellenar datos ni inventar valores.
2. Generar informe de observabilidad con dos métricas separadas: cadencia de ejecuciones GitHub (workflows) y cobertura real por producto.
3. Solo si la instrumentación de lectura es adecuada, evaluar un disparador externo independiente de GitHub; sin crear token ni elegir infraestructura todavía.
4. Antes de cualquier publicación de v0.9, resolver autenticación, permisos, georreferencias y requisitos de privacidad. El visor sigue experimental.

No hacer merges sin autorización específica y CI verde. No activar servidor, publicador, alertas, modelo predictivo ni capturas adicionales.

## Corrección 22-10-2026: cobertura verificada y sin falsos estados verdes

**Causa raíz.**
- **A.** El visor clasificaba la cobertura con los recuentos autodeclarados de `coverage_24h` (`available_half_hours` / `required_half_hours`), sin mirar la serie:
  - antes de `2b929b8d`, 1/1 o 24/24 contaban como «completas»;
  - después, 48 registros con un intervalo duplicado, un intervalo fuera de la ventana, o 48 intervalos registrados sin valor válido, seguían contando como «completos» si declaraban 48/48.
- **B.** El indicador se calculaba sobre conjuntos vacíos: con 0 zonas no había nada «incompleto» ni «desconocido» y salía verde. Además, el texto no explicitaba la falta de evidencia.

**Corrección** (`site/v09/index.html`, solo presentación):
- `imergCoverageState` deriva el estado de la propia serie `series_24h_half_hourly_mm`.
  - Cuenta los intervalos distintos, alineados a 30 min, dentro de `[window_end_utc − 24 h, window_end_utc)` y con valor numérico válido ≥ 0.
  - Los intervalos registrados sin valor no cuentan. Los duplicados y los que caen fuera de ventana se detectan aparte.
- Los intervalos esperados se derivan de la ventana y del paso (`expectedSlots`, 24 h / 30 min = 48); el 48 no está fijado en el código.
- `COMPLETE` exige todos los intervalos esperados, sin duplicados, dentro de la ventana y con una cobertura declarada coincidente.
- En los demás casos: `PARTIAL`, `NO_DATA` o `UNKNOWN`.
- El indicador global solo es verde si **todas** las zonas están `COMPLETE` y hay al menos una. Con 0 zonas muestra `NO_DATA` («el paquete no contiene zonas: no hay evidencia»), y el resumen dice que eso no significa ausencia de lluvia ni riesgo bajo.
- El motor (`scripts/v09_zone_rain_engine.py`) ya calculaba bien la cobertura y no cambia. No cambian datos, reglas, prioridades, umbrales, alertas ni la puerta de publicación.

**Pruebas:** `qa/replay_tools/test_v09_continuity_evidence.py`, 18 pruebas.
- Los 9 casos obligatorios con la lógica real de la página ejecutada en node.
- La concordancia con la salida real del motor.
- Un navegador (Playwright) que comprueba el indicador, la tabla del Centro de seguimiento y la ficha de zona.
- Se ejecutan en el workflow de navegador, que falla si alguna se omite.
