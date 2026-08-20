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
