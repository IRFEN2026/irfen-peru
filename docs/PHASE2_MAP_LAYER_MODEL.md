# IRFEN · expansión geográfica y capas del mapa

Estado: `RESEARCH_ONLY` / `TEST_ONLY`. Este documento no modifica v0.7.1,
los umbrales, las guardas de producción ni la fase 2 operativa.

## Auditoría del punto de partida

- El mapa general calcula y muestra únicamente los tres pilotos de `latest.json`:
  San Ildefonso, Chosica/Huaycoloro y Catacaos/Bajo Piura.
- `v08-experimental.js` ya superponía las cuencas DEM de San Ildefonso y
  Huaycoloro, además de referencias documentales y tramos de Catacaos cuando
  estaban disponibles.
- La geometría `chosica_local_candidate_sets.geojson` existía, pero no estaba
  incorporada al selector de capas.
- Los 18 contratos fase 2 existían en `RESEARCH_ONLY`. Santa Eulalia–Rímac
  tenía metadatos de geometría `CANDIDATE`, pero ningún contrato tenía un
  archivo geométrico reproducible enlazado. Por tanto, 0/18 eran cartografiables.
- No se encontraron otras geometrías históricas eliminadas: el historial
  reciente contiene los mismos cuatro GeoJSON persistentes del repositorio.

## Inventario priorizado para desarrollo

La prioridad siguiente es un orden de trabajo, no un ranking de peligro,
impacto o urgencia operativa. El detalle reproducible y la razón de cada puesto
están en `config/phase2_map_priority_v0_1.json`.

| Ola | Objetivo | Sistemas |
|---|---|---|
| W1 | Normalizar geometría desde fuentes relativamente focalizadas | Santa Eulalia–Rímac; Huerta Vieja; Malanche; Chongoyape–Oyotún–Zaña; Acarí–San Agustín |
| W2 | Desagregar sistemas compuestos antes de delimitar | Arahuay–Chillón; Lampián; Chilca–Pucusana; Pisco–San Andrés; Palpa–Changuillo; Motupe–La Leche–Pítipo |
| W3 | Extraer unidades verificables desde corredores amplios | Lurín–Cieneguilla; Chillón bajo; Chancay–Huaral; Huaura–Huacho–Sayán; Mala; Asia–Omas; Cañete |

La primera entrega recomendada es materializar, por separado, la geometría de
Cashahuacra/Shingolay y los tramos Santa Eulalia–Rímac citados por el contrato.
El sistema compuesto no debe convertirse en una sola cuenca ni mezclarse con
el piloto v0.8 Chosica/Huaycoloro.

## Modelo mínimo reproducible por zona

`site/data/map_layers.json` expone, para cada candidato:

1. `geometry`: estado contractual, ruta del archivo, fuentes y elegibilidad
   cartográfica. Sin archivo reproducible la zona no se dibuja y no se inventa
   un punto representativo.
2. `sources`: identificadores oficiales y ruta exacta del contrato.
3. `confidence`: confianza geométrica y general. `UNASSESSED` o `CANDIDATE`
   nunca significan validación.
4. `coverage`: ámbito territorial, cobertura geométrica y cobertura temporal.
5. `variables_available`: activos no ausentes y su estado (`CANDIDATE`,
   `PARTIAL` o `READY`).
6. `validation`: estado del contrato, mecanismo, puerta de activación,
   revisiones obligatorias, evidencia revisada y bloqueos.
7. `development_priority`: ola, orden y razón, con
   `is_risk_or_operational_priority=false`.

## Capas técnicas registradas

| Capa | Estado | Visibilidad | Uso permitido |
|---|---|---|---|
| Microcuenca San Ildefonso | TEST_ONLY | Encendida | Geometría DEM; hidráulica pendiente |
| Subcuenca Huaycoloro | TEST_ONLY | Encendida | Geometría DEM; capacidad as-built pendiente |
| Alternativas locales Chosica | TEST_ONLY | Apagada | Comparar outlets/áreas; no seleccionar automáticamente |
| Ámbitos documentales Catacaos | TEST_ONLY | Apagada | Contexto de documentos; no peligro/inundación |
| Tramos críticos ANA Catacaos 2026 | TEST_ONLY | Apagada | Líneas de referencia; no polígonos de inundación |

Cada entrada conserva ruta, hash SHA-256 cuando el archivo está versionado,
fuentes, cobertura, variables, confianza, validación y una advertencia visible.
Ninguna capa entra a `calc(z)`, lleva valores de alerta ni usa colores de riesgo.

## Regla de incorporación cartográfica

Una zona fase 2 solo puede aparecer como geometría cuando su contrato enlaza
un archivo GeoJSON/JSON existente y el activo de geometría deja de estar
`MISSING`. Aun entonces conserva `RESEARCH_ONLY`, `production_use=false`,
`alerting_enabled=false`, umbrales nulos y puerta `BLOCKED` hasta completar sus
revisiones específicas.
