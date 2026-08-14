# IRFEN v0.8 — Plan de pruebas antes de temporada de lluvias

Estado: **experimental / pre-operativo**  
Principio: la v0.7.1 continúa siendo el núcleo operativo hasta que cada puerta científica de v0.8 sea validada.

## 1. Objetivo

Demostrar que IRFEN puede observar lluvia, conservar antecedentes, incorporar previsión, representar contexto hidrológico/hidráulico y mantener la plataforma disponible sin convertir datos experimentales en alertas no validadas.

## 2. Pruebas automáticas obligatorias

Cada deployment debe superar:

1. JSON/GeoJSON válidos.
2. NASA IMERG actualizado o contingencia con último dato válido.
3. `history.json` protegido frente al flujo diario.
4. Cuencas San Ildefonso y Huaycoloro con `production_ready=false`.
5. Forecast GEOS con `production_use=false`.
6. Infraestructura hidráulica con `production_modifier=null`.
7. Catacaos bloqueado si no existe estado numérico del río.
8. Función operativa `calc(z)` sin dependencias de forecast, río, hidráulica o polígonos experimentales.
9. Suite de regresión v0.8 en PASS.
10. Smoke test del sitio público después del deployment.

## 3. Prueba A — operación diaria normal

**Entrada:** ejecución programada diaria con Earthdata disponible.

**Debe ocurrir:**
- IMERG Late Daily se actualiza.
- `operational_status=updated`.
- se calculan 24h/72h/7d para las tres zonas;
- San Ildefonso y Huaycoloro calculan además IMERG por polígono en paralelo;
- la web se publica;
- ninguna señal v0.8 cambia Amenaza/Prioridad v0.7.1.

**Aceptación:** workflow y smoke test en PASS.

## 4. Prueba B — contingencia NASA

**Entrada controlada:** provocar fallo de la consulta NASA en rama/prueba o mediante un test aislado; no alterar el secreto real.

**Debe ocurrir:**
- cuatro intentos;
- restauración del último `latest.json` válido;
- `operational_status=stale`;
- la web sigue disponible;
- se visualiza CONTINGENCIA;
- no se publican ceros falsos como observación nueva.

## 5. Prueba C — San Ildefonso

### Geometría
- referencia: 28.9 km²;
- candidato DEM: ~28.34 km²;
- error esperado: ~1.94%;
- estado geométrico: PASS experimental.

### Evento histórico
Preset: 15/03/2017. Comparar caja antigua vs. cuenca DEM y verificar que la interfaz mantenga ambos valores diferenciados.

### Puerta de seguridad
Aunque lluvia/forecast superen un umbral provisional, el sistema debe informar que la respuesta urbana no puede corregirse numéricamente hasta calibrar las obras San Ildefonso/San Carlos 2026.

## 6. Prueba D — Huaycoloro / Chosica

- referencia provisional: 492.31 km²;
- candidato DEM: ~484.122 km²;
- error esperado: ~1.66%;
- topología D8: CONSISTENT.

Preset histórico: 23/03/2015. Comparar caja antigua vs. cuenca DEM.

El canal de 10.5 km no debe producir automáticamente un factor de reducción de riesgo. `production_modifier` debe permanecer `null`.

## 7. Prueba E — Forecast NASA GEOS

Verificar:
- forecast 24h y 72h visible para las tres zonas;
- etiquetado NO OPERATIVO;
- Catacaos conserva muestreo espacial provisional;
- 72h observadas + 24h previstas se muestra solo como contexto;
- forecast no entra en `calc(z)`.

`forecast/verification.json` debe comparar días UTC completos GEOS contra IMERG cuando maduren. No aplicar corrección de sesgo hasta contar como mínimo con 30 pares por zona y revisar además casos lluviosos relevantes.

## 8. Prueba F — Catacaos / Bajo Piura

Sin dato automático de nivel/caudal:
- `river_state_available=false`;
- bloqueo `numeric_river_state_required`;
- estado `METEO_TESTABLE_RIVER_GATE_BLOCKED`.

En el simulador manual, introducir un caudal de Puente Ñácara y comprobar que se compara descriptivamente con la referencia disponible, pero no cambia Amenaza/Prioridad y la interfaz advierte que Puente Ñácara no equivale al umbral de desborde de Catacaos.

Las capas 2011/2017/2026 deben aparecer apagadas por defecto y rotuladas como **ámbitos documentales — no polígonos de peligro**.

## 9. Prueba G — escenarios sintéticos

Para cada zona:
1. 0% de umbrales → amenaza 0.
2. 50% de umbrales → respuesta proporcional.
3. 100% de umbrales → amenaza ~74 por la normalización actual /1.35.
4. 135% de umbrales → amenaza 100.
5. Valores mayores → amenaza nunca >100.

Esta prueba verifica matemáticas existentes; **no valida científicamente los umbrales**.

## 10. Prueba H — protección contra promoción accidental

En una rama de prueba, confirmar que CI falla ante:
- `production_use=true` en forecast;
- `production_ready=true` en cuenca;
- `production_modifier` hidráulico distinto de null;
- remover bloqueo fluvial de Catacaos;
- hacer que `calc(z)` consuma forecast/river/hydraulics.

No ejecutar estos cambios directamente sobre `main`.

## 11. Criterios para considerar v0.8 candidata a operación

La plataforma técnica puede considerarse **candidata**, no certificada, cuando:
- operación + fallback + live smoke estén estables durante un periodo prolongado;
- San Ildefonso y Huaycoloro tengan validación hidráulica suficiente para la infraestructura actual;
- Catacaos disponga de una señal numérica automática de río y se haya homologado su relación con Bajo Piura;
- forecast haya acumulado una muestra suficiente de verificación contra observación;
- eventos y controles secos permitan estimar falsos positivos/negativos;
- los umbrales finales estén documentados y versionados;
- cualquier promoción a producción sea explícita, trazable y reversible.

## 12. Regla de cambio

Ninguna prueba aprobada por sí sola autoriza a reemplazar v0.7.1. La promoción de un componente experimental debe quedar registrada como cambio de versión, con evidencia, fuente, fecha y rollback disponible.
