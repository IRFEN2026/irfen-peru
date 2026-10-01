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
  archivo geométrico reproducible enlazado. Ese era el punto de partida 0/18.
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

## W1 materializada · Santa Eulalia–Rímac

`site/data/phase2/geometries/w1_santa_eulalia_rimac.geojson` contiene cinco
unidades separadas, todas `RESEARCH_ONLY` y `REVIEW_ONLY`:

| Unidad | Representación | Confianza geométrica | Limitación dominante |
|---|---|---|---|
| Cashahuacra | Cuenca candidata Copernicus GLO-30 + D8; 15.088 km² derivados del DEM | `MEDIUM_CANDIDATE` | Outlet y área no aprobados oficialmente; no es el área del ortomosaico CENEPRED |
| Shingolay | Cuenca candidata Copernicus GLO-30 + D8; 0.243 km² derivados del DEM | `LOW_CANDIDATE` | RPAS identifica el conjunto; no es el área del ortomosaico y no existe outlet oficial |
| Santa Eulalia | Polígono oficial de faja marginal, tramo 6.08 km | `HIGH_SOURCE_GEOMETRY_MEDIUM_CURRENTNESS` | Resolución 2004; vigencia material por confirmar |
| Rímac | Polígono oficial de faja marginal, 58.30 km | `HIGH_SOURCE_GEOMETRY_MEDIUM_CURRENTNESS` | La modificación 2022 no se fusiona automáticamente |
| Rímac 2022 | `MultiLineString` de 20 hitos oficiales de margen izquierda | `HIGH_SOURCE_GEOMETRY_PARTIAL_COVERAGE` | Dos partes: 39+950–40+050 y 44+200–46+900; sin enlace entre ellas |

Los 15.088 km² de Cashahuacra y 0.243 km² de Shingolay son áreas de
microcuenca derivadas mediante Copernicus GLO-30, D8 y recorrido explícito de
celdas aguas arriba. No son áreas oficiales de cuenca ni áreas de cobertura de
los ortomosaicos CENEPRED. Esos polígonos documentales se usan únicamente para
restringir la búsqueda del outlet. En Shingolay se selecciona el máximo de
acumulación D8 dentro del pequeño ámbito RPAS y de la banda reproducible
0.05–1.0 km². El resultado de 0.243 km² es sensible a la resolución del DSM y
al drenaje urbano; al no existir confirmación oficial de outlet o área,
permanece `LOW_CANDIDATE` y `REVIEW_ONLY`.

La RD N.° 0058-2022-ANA-AAA.CF se reconcilia como 15 hitos principales más
cinco intermedios, 20 filas de coordenadas en total. El primer componente
contiene MI-185, MI-185-A y MI-185-B (39+950–40+050); el segundo contiene
MI-204 a MI-221, incluidos MI-208-A, MI-215-A y MI-220-A
(44+200–46+900). Las menciones `MI-2016` y `MI-2015-A` del texto son erratas
por `MI-216` y `MI-215-A`. Para códigos y coordenadas prevalecen el cuadro
oficial de la página 5 y el Mapa N.° 1 del anexo cartográfico de la página 7.
La geometría no contiene el segmento artificial MI-185-B–MI-204 y no altera
ninguna coordenada oficial.

El snapshot de fuentes conserva URL, institución, año, método, WKT o hitos,
hashes y fecha de recuperación. El DEM está fijado por SHA-256. Los controles
confirman geometrías válidas, coordenadas WGS84 dentro del ámbito esperado,
0 solapamiento entre Cashahuacra y Shingolay, coincidencia exacta entre celdas
de acumulación y recorrido aguas arriba, y conexión de ambas salidas con la
faja Santa Eulalia. También exigen exactamente 20 códigos/coordenadas Rímac,
dos componentes y ausencia expresa del segmento MI-185-B–MI-204. Esto no
valida la hidráulica, el área oficial ni un umbral.

El catálogo pasa a 1/18 sistemas con archivo cartografiable; los otros 17
siguen retenidos sin puntos aproximados. La capa W1 está apagada por defecto.

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

## Consolidación semántica · cuenca / quebrada / colector / nodo

`scripts/build_map_semantic_layers.py`, invocado por el builder canónico
`scripts/build_map_layer_catalog.py`, añade a `site/data/map_layers.json` el
bloque `map_semantics`. No crea geometrías: clasifica, feature por feature, los
archivos que el catálogo ya admitió con SHA-256 y registra en inventario lo que
no puede dibujarse.

| Grupo | Categoría | Tipos admitidos | Nunca es |
|---|---|---|---|
| A | `CATCHMENT` cuenca / subcuenca | Polygon, MultiPolygon | footprint, inundación, unión compuesta del padre |
| B | `LOCAL_CHANNEL` quebrada / cauce local | LineString, MultiLineString | cuenca, outlet, confluencia, colector |
| C | `COLLECTOR` río colector | LineString, MultiLineString propios | faja marginal, cauce local, capacidad |
| D | `NODE` outlet / confluencia / nodo | Point | evento, alerta, ubicación aproximada |
| contexto | `REGULATORY_FAJA_MARGINAL` | Polygon/Line | cuenca, cauce, footprint, extensión de inundación |
| contexto | `ENGINEERED_OR_CRITICAL_REACH_CONTEXT` | Line/Point | capacidad hidráulica histórica, evento |
| contexto | `DOCUMENT_CONTEXT` | Polygon | cuenca, peligro, inundación |

Reglas:

- Cada categoría es una capa distinta en ambos mapas; los colores identifican el
  tipo de entidad y excluyen la gama roja/naranja/amarilla de riesgo.
- Los nodos declaran `EXACT_OFFICIAL`, `REPRODUCIBLE_DERIVED`,
  `MONITORING_ANCHOR`, `NEAR_CONFLUENCE` o `UNRESOLVED`. Los `UNRESOLVED` no se
  dibujan y sólo `EXACT_OFFICIAL` puede rotularse como confluencia exacta.
- Los colectores se registran aunque no tengan eje reproducible, separando
  `tributary_coupling` / `tributary_activation_evidence` de
  `collector_response`, con `tributary_activation_implies_collector_response=false`.
- Los contenedores territoriales (candidatos Phase-2, agrupadores discovery,
  grupos de capas) nunca se dibujan como polígono propio; sus hijos sí, por
  separado.
- Toda geometría de `site/data/phase2/geometries/` que no entra al mapa necesita
  una decisión explícita en `WITHHELD_REPOSITORY_GEOMETRY_POLICY`; un archivo
  nuevo sin decisión hace fallar el builder.
- Los resultados nuevos de Rímac/Jicamarca (#310) y Zorritos (#340) no se
  consolidan hasta `INDEPENDENT_QA_ACCEPTED`.
- Casma (#335→#346, integrada en #347) está en `ACCEPTED_INDEPENDENT_QA_LINES`
  (alcance: captura Gate A y topología Gate C; Gate B `NOT_ESTABLISHED`). Sólo
  sus 9 unidades N7 `CURRENT_INSTITUTIONAL_N7_RESEARCH_CONTEXT` se clasifican,
  como `CATCHMENT` / `CURRENT_INSTITUTIONAL_N7_HYDROGRAPHIC_UNIT`, apagadas por
  defecto y con fuente declarada por feature. El builder verifica el registro
  de aceptación y el hash del informe Gate C; si no verifican, falla cerrado.
  El padre N6 137596 no se dibuja y la captura congelada Gate A queda retenida
  (`WITHHELD_FROZEN_GATE_A_EVIDENCE`) para no duplicar entidades.
- Todos los conteos (`map_semantics.summary` y `summary.map_semantic_*`) se
  derivan de las filas; los tests los recalculan en lugar de fijarlos.

## Línea Rímac/Jicamarca (#310) · reconciliación sin promoción

`config/phase2_rimac_jicamarca_map_semantic_reconciliation_v0_1.json` clasifica
cada elemento de la línea con el vocabulario de este modelo. La línea sigue en
`PENDING_INDEPENDENT_QA_LINES`: no se dibuja ningún elemento nuevo y
`map_layers.json` no cambia.

- Ya dibujado en `main`, sin cambios: cuenca Huaycoloro (CATCHMENT), líneas IGP
  Canto Grande y Media Luna (LOCAL_CHANNEL), Cashahuacra y Shingolay (CATCHMENT),
  fajas Santa Eulalia/Rímac (contexto) y nodos D8 Quirio/Pedregal
  (`REPRODUCIBLE_DERIVED`, nunca `EXACT_OFFICIAL`).
- Topología documental parcial Colca / El Silencio → Río Seco → Huaycoloro →
  Rímac: los cuatro nodos quedan `UNRESOLVED` (sólo inventario).
- Único elemento dibujable tras QA independiente: QHuay1 como `NEAR_CONFLUENCE`
  (requiere bytes del PDF ANA con hash y un Point congelado con guardas).
- Colector Rímac: sin eje reproducible; las fajas no lo sustituyen.
- Tambo de Viso 1998: contexto histórico del Rímac alto, no entidad cartográfica
  ni parámetro hidráulico transferible.
