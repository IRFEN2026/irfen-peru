# IRFEN v0.8-RC1: modo de disponibilidad controlada

IRFEN v0.8-RC1 separa dos conceptos que no deben confundirse:

- **Disponibilidad técnica**: el núcleo de los tres pilotos alcanzó al menos el hito auditable de 75%, la regresión pasa y las guardas de seguridad permanecen cerradas. Esto habilita pruebas controladas.
- **Cierre científico v0.8**: continúa medido exclusivamente por `site/data/v08_scorecard.json`. Solo llega a 100% con evidencia en sombra, revisión humana, bloqueos científicos e hidráulicos resueltos y auditoría final.

## Usos permitidos de la RC

- adquisición y visualización de datos;
- ejecución y archivo de corridas en sombra;
- revisión por una persona experta identificada;
- preparación de paquetes de nuevas zonas bajo `RESEARCH_ONLY`.

## Usos prohibidos

- alertas operativas autónomas o decisiones de producción;
- promoción de umbrales o factores hidráulicos sin evidencia;
- activar una zona de fase 2;
- interpretar un dato ausente como riesgo bajo;
- modificar o sustituir la versión protegida v0.7.1.

## Contrato automático

`scripts/build_v08_rc_status.py` genera `site/data/v08_rc_status.json`. La salida es *fail-closed*: si el hito formal cae por debajo de 75%, falla la regresión o una guarda RESEARCH_ONLY se relaja, el estado cambia a `RC_BLOCKED`.

La interfaz pública muestra simultáneamente el estado RC y el porcentaje formal. Por tanto, “RC disponible” nunca se presenta como “v0.8 cerrada” ni como autorización operacional.

## Flujo eficiente hacia nuevas zonas

1. Mantener diariamente IMERG, GEOS, smoke test y regresión para los tres pilotos.
2. Acumular evidencia en sombra y revisión humana hasta el 100% formal sin frenar el trabajo documental.
3. Completar en paralelo un contrato por zona: geometría, exposición, eventos, observaciones, forecast, contexto hidráulico y mecanismo de peligro.
4. Conservar cada candidato en `RESEARCH_ONLY` y con `activation_gate=BLOCKED` hasta que todas sus puertas específicas estén aprobadas.
5. Proponer la activación de cada zona en un cambio separado y auditable; nunca por herencia de los pilotos v0.8.
