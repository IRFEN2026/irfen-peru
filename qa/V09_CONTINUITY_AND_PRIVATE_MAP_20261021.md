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
