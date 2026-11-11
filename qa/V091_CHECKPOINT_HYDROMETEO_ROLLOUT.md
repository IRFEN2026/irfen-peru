# IRFEN v0.9.1 — Ejecución hidro-meteorológica por checkpoint (03-11-2026)

**Trabajo realizado ahora:** `scripts/v091_audit_checkpoint_hydrometeo.py` y pruebas aisladas. Auditoría de referencias declaradas en los 117 puntos; sin mutar `main`, modelos, alertas o datos científicos. Ejecución de CI todavía pendiente.

## Cobertura ya conocida
- Lambayeque: 39 puntos, con cuencas del panel para Chancay-Reque y Zaña, y proxy Motupe (no equivalente al área aportante del río La Leche).
- Tumbes: 24 puntos; cuenca transfronteriza Tumbes/Puyango experimental, Zarumilla sin delimitación validada.
- Piura: 54 puntos; cuenca Piura/Sánchez Cerro y Chira/Catamayo experimental, sin integración al capturador recurrente.
- Restantes departamentos: aún pendientes de materializar checkpoints.
- Sin coordenadas inventadas; punto ANA ≠ estación de lluvia/aforo ni línea de cauce.

## Contrato científico necesario para conectar lluvia de cuenca
1. Geometría por sistema con identificador estable, versión, fuente y hash; área y porcentaje transfronterizo con procedimiento de reproducción. Zona de lluvia no es provincia.
2. Para cada ventana 1/3/6/24/72h registrar cobertura espacio-temporal real, intervalos faltantes, fin de observación UTC, producto IMERG Early, número de celdas, reglas de pesos/área. No usar suma de gránulos incompletos como acumulado completo.
3. Fallback ante fallo: observación última validada con su hora; estado STALE/UNKNOWN y checkpoint GRIS si caduca. Nunca lluvia 0 ni verde por falta de datos.
4. No convertir lluvia de cuenca en caudal, crecida o desborde sin modelo validado. El naranja seguirá bloqueado; rojo solo evidencia reportada verificada. Sin emails reales.
5. Para ríos regulados y cuencas Ecuador/Perú registrar explícitamente límites: Poechos/Los Ejidos/trasvase; precipitación ecuatoriana incluida en el polígono si el producto y su cobertura lo permiten.
6. Construir en **rama de investigación** tres referencias candidatas TUMBES_DESEMBOCADURA, CHIRA_DESEMBOCADURA y PIURA_SANCHEZ_CERRO sobre geometrías existentes y comprobar reproducibilidad. Zarumilla permanece pendiente hasta tener cuenca reproducible. Prohibido apuntar estas referencias a zonas provinciales.
7. Integrar luego las series por cuenca en el capturador IMERG *solo mediante PR separado a main*; la ejecución actual de este PR no solicita ni autoriza esa fusión.
8. QA de extremo a extremo con observación NASA real: comparar una ventana completa del capturador contra una reconstrucción independiente de gránulos, verificar límites y fecha, ejecución sin Earthdata y pérdida progresiva de frescura.
9. Expandir resto de costa desde La Libertad a Tacna en lotes con IDs IGN, puntos ANA y clasificación explícita de no evaluabilidad, max 60 por departamento sin ocultar puntos por saturación.

## Próximo entregable verificable
Un inventario `data/v09/research/semaforo/checkpoint_hydrometeo_audit_v0_1.json` generado desde el paquete actual, CI verde, luego 3 cuencas conectadas a capturas recurrentes en PR independiente y puntos del norte mostrando fuentes concretas. El inventario presente es únicamente *diagnóstico de asociaciones*, no validación hidrológica.

## Tiempo
No prometer fecha de finalización ni trabajos futuros ejecutándose fuera de una tarea programada. La extensión de 117 a toda la costa depende de verificar identificadores y geometrías y de ejecución/QA; una estimación de 12 horas no está demostrada.
