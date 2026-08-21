# Migración hidrológica Chongoyape–Oyotún–Zaña

**Versión:** `chongoyape-oyotun-zana-hydrologic-migration-v1`

**Fecha de investigación:** 2026-08-20 (America/Mexico_City)

**Estado:** `RESEARCH_ONLY` / `REVIEW_ONLY` / `activation_gate=BLOCKED`

## Resultado ejecutivo

El identificador `lambayeque_chongoyape_oyotun_zana` no representa una unidad
hidrológica reproducible: mezcla Chongoyape, que la evidencia oficial sitúa en
el sistema Chancay-Lambayeque, con Oyotún, que la evidencia oficial sitúa en la
cuenca Zaña. Se conserva únicamente como agrupador histórico no activable para
no cambiar silenciosamente el universo de 18 candidatos de Phase 2.

La capa institucional ANA/IDEP `Unidades Hidrográficas` permite materializar
dos unidades hijas independientes:

| candidate_id | sistema | código ANA | geometría | estado |
|---|---|---:|---|---|
| `lambayeque_chancay_lambayeque_chongoyape` | Chancay-Lambayeque | 13776 | polígono oficial completo | `RESEARCH_ONLY`, `BLOCKED` |
| `lambayeque_zana_oyotun` | Zaña | 137754 | polígono oficial completo | `RESEARCH_ONLY`, `BLOCKED` |

Los polígonos tienen interiores disjuntos. Su intersección tiene área 0 m² y
corresponde a una divisoria compartida (`MultiLineString`, aproximadamente
109.976 km); no se creó disolución, corredor, puente o polígono compuesto.

## Diagnóstico por subentidad

### Chongoyape

- La [ANA identifica Chongoyape dentro del monitoreo de la cuenca
  Chancay-Lambayeque](https://www.gob.pe/institucion/ana/noticias/138840-la-ana-analiza-calidad-del-agua-de-la-cuenca-chancay-lambayeque).
- El [PGRH Chancay-Lambayeque aprobado por R.J. 365-2023-ANA](https://www.gob.pe/institucion/ana/normas-legales/4910620-365-2023-ana)
  ubica el corredor del río Chancay, Tinajones y el valle encañonado en el
  sistema y trata como aportes las quebradas Juana Ríos, Montería, Pampagrande
  y Pacherrez.
- Las fichas ANA/SIGRID 2021 documentan tres tramos con extremos WGS84/UTM 17S:
  Vega Tabacal y Santa Rosa-Huaca Blanca sobre el río Chancay-Lambayeque, y el
  sector Montería sobre la quebrada Montería. Se publican sólo como cuerdas
  lineales de referencia, no como eje de cauce ni límite de cuenca.
- El inventario INGEMMET/SIGRID 692 añade los sectores Puntilla-Chongoyape,
  Montería-Tabazos, Wadington-Huayto, Magín-Juana Ríos, Chiriquipe, Pampa
  Grande y quebrada Campana. Esta lista es defendible como inventario nominal,
  pero no basta para delimitar cada subcuenca.

**Diagnóstico:** se materializa la unidad ANA 13776 completa con Chongoyape
como referencia territorial. No se recorta por distrito. Las subcuencas de
Juana Ríos, Montería, Pampagrande, Pacherrez, Magín, Chiriquipe y Campana quedan
bloqueadas hasta contar con geometría oficial o delimitación DEM separada,
outlet documentado y sensibilidad.

### Oyotún

- La [ANA enumera Oyotún entre las localidades de la cuenca
  Zaña](https://www.gob.pe/institucion/ana/noticias/137713-docentes-de-cuenca-zana-se-comprometieron-a-promover-la-cultura-del-agua-en-sus-instituciones-educativas).
- Las fichas ANA/SIGRID 2019 identifican tramos del **río Zaña** en
  Bebedero-Potrero, Sorronto-Campana-Gramadal, Santa Rosa/Virú-Espinal y
  Espinal-Polvareda. Sus once cuerdas se materializan `REVIEW_ONLY` dentro de
  la unidad ANA 137754.
- El [mapa ANA/SIGRID 4542](https://sigrid.cenepred.gob.pe/sigridv3/documento/4542)
  identifica en Oyotún las quebradas Algarrobal, Nueva Esperanza y Germán
  Muñoz y publica puntos de referencia UTM 17S; el [mapa ANA/SIGRID
  5670](https://sigrid.cenepred.gob.pe/sigridv3/documento/5670) vincula la
  quebrada La Compuerta con el río Zaña. Son puntos/zonas de exposición, no
  límites de subcuenca.
- INGEMMET/SIGRID 692 registra Querpán-Sector Seis-Macuaco, Las
  Delicias-Santa Rita y La Compuerta como sectores críticos de Oyotún.

**Diagnóstico:** se materializa la unidad ANA 137754 completa con Oyotún como
referencia territorial. Las quebradas nominales y sus zonas de exposición no
se convierten en polígonos de cuenca. La topología tributaria individual y la
relación hidráulica con el río receptor siguen `BLOCKED`.

### Zaña y tributarios fuera de Oyotún

El mapa ANA/SIGRID Cojal 2016, en Cayaltí, muestra el río Zaña y nombres como
Agua Salada, Seca, Huallacal, El Alumbral y Songoy. Sirve para inventario
contextual de la cuenca, no para asignar esas quebradas a Oyotún ni para
construir una geometría continua entre distritos. No se materializaron.

### Gobiernos regionales y locales

Se revisaron los portales oficiales indexados del Gobierno Regional de
Lambayeque, municipalidades y el catálogo SIGRID. El catálogo contiene el
[PPRRD 2026-2030 de la Municipalidad Provincial de
Chiclayo](https://sigrid.cenepred.gob.pe/sigridv3/documento/biblioteca?c=MP+CHICLAYO)
y EVAR territoriales para Chongoyape/Oyotún. Son evidencia de gestión de riesgo
y exposición; no se encontró allí una descarga oficial que sustituya la capa
ANA como límite de cuenca. Ningún límite administrativo fue usado como límite
hidrológico.

## Contrato de migración

Se eligió la alternativa de **conservar el ID compuesto como agrupador
histórico no activable**:

1. `phase-2-candidate-inventory-v0.1` queda intacto como antecedente.
2. `phase-2-candidate-inventory-v0.2` conserva las mismas 18 filas históricas.
3. El padre recibe `entity_role=HISTORICAL_NON_ACTIVABLE_GROUPER`, no recibe
   geometría compuesta y mantiene `activation_gate=BLOCKED`.
4. Dos contratos hijos se informan en una colección separada. No cuentan como
   candidatos adicionales ni como candidatos operativos.
5. Una futura sustitución del padre en el conteo necesitará otra versión del
   catálogo y revisión explícita; no está autorizada por esta migración.

| métrica | antes | después |
|---|---:|---:|
| candidatos históricos Phase 2 | 18 | 18 |
| agrupadores históricos no activables | 0 | 1 |
| unidades hijas informadas por separado | 0 | 2 |
| candidatos operativos Phase 2 | 0 | 0 |

## Método geométrico y topología

- Fuente: capa 8 `Unidades Hidrográficas` del servicio institucional ANA/IDEP.
- Consulta: selección exacta por `NOMBRE` de `Cuenca Chancay-Lambayeque` y
  `Cuenca Zaña`, con `returnGeometry=true` y `outSR=4326`.
- CRS de salida: EPSG:4326. El servicio declara EPSG:3857, pero la consulta
  solicita explícitamente la reproyección a EPSG:4326.
- No se usó Copernicus DEM GLO-30 ni otro DEM. Por ello `outlet=null`,
  `outlet_required=false` y la validación D8 se marca no aplicable, nunca
  aprobada implícitamente.
- Área geodésica de control: 4.042,7612 km² para Chancay-Lambayeque y
  1.754,5158 km² para Zaña. La diferencia respecto de `AREA_KM2` de la capa es
  0,5096% y 0,5223%, respectivamente.
- Las dos geometrías son válidas, no vacías, de tipo `Polygon`; sus interiores
  no se solapan.

## Inventario reproducible de fuentes

El inventario completo, con URL, identificador, fecha UTC de captura, tamaño y
SHA-256, está en
`site/data/phase2/sources/lambayeque_hydrologic_migration/source_inventory.json`.
Los tres snapshots necesarios para reconstruir la geometría se versionan en el
mismo directorio. Los documentos PDF/HTML de contexto se fijan por metadatos y
hash sin incorporar decenas de megabytes al repositorio.

Fuentes geométricas principales:

| fuente | tamaño | SHA-256 |
|---|---:|---|
| ANA/IDEP consulta GeoJSON | 210.302 B | `008e4ba2f6dc76c716a984cf8b19f34734aa3785617dc17a3562836d563eb578` |
| ANA/IDEP metadatos capa 8 | 286.932 B | `cc2f0e96926770f3edfb66c0b85aa68f7b98c0ec0d7b60f9109d08dd039a5dc9` |
| ANA/IDEP metadatos servicio | 5.866 B | `765c43c97e36e3640ba2f48544f52076efc644f16c83d7db2167add21a2c118e` |

GeoGPS figura sólo como `DISCOVERY_ONLY_PRIVATE`; no aporta geometría, no
cuenta para validación y no es evidencia principal.

## Unidades y activos materializados

Materializados:

1. `lambayeque_chancay_lambayeque_chongoyape`: polígono ANA 13776.
2. `lambayeque_zana_oyotun`: polígono ANA 137754.
3. Colección de 14 cuerdas de tramos críticos oficiales: 3 Chongoyape y 11
   Oyotún, `REVIEW_ONLY`, apagada por defecto y fuera del mapa general.
4. Dos contratos hijos fail-closed, inventario v0.2, snapshots, validación y
   catálogo Phase 2 v2.

Bloqueados:

1. El agrupador histórico `lambayeque_chongoyape_oyotun_zana` para cualquier
   activación o geometría.
2. Ambas unidades hijas para producción, alertas, umbrales, factores
   hidráulicos y promoción.
3. Toda subcuenca tributaria individual sin geometría reproducible suficiente.
4. Las zonas de exposición o puntos críticos como sustitutos de límites de
   cuenca.
5. Cualquier unión artificial entre Chancay-Lambayeque y Zaña.

## Estado público usado como línea base dinámica

La consulta de GitHub Pages del 2026-08-20 confirmó:

- `forecast/verification.json`: 177 pares (59 por piloto), estado de
  monotonicidad `NO_DECREASE`; SHA-256
  `80fd18ed35a1507494bb219b9a6294c7ec49256c7d1b1032ad3c7e96306b6d58`.
- `v08_scorecard.json`: hito acumulado 75%; SHA-256
  `1cdf74cad1b9d2d8c74c9ef5607b94969965fc48624f1e775745ce4a0b5fc0ae`.
- `v08_rc_status.json`: `RC_AVAILABLE_TEST_ONLY`, `production_use=false`,
  `production_ready=false`, `operational_alerting_enabled=false`, Phase 2 con
  18 registrados y 0 operativos; SHA-256
  `c0a322fce3c19314783d4f44353e73e9ba5bb274231e63a2447d645f2f5d2324`.

La regresión debe comparar GEOS contra ese artefacto público inmediatamente
anterior; 177 se registra como observación de línea base, no como constante del
código.

## Recomendación

Aceptar la migración sólo como corrección de identidad hidrológica en
investigación. No activar ninguna unidad. La siguiente etapa defendible es
delimitar y revisar por separado las subcuencas tributarias prioritarias,
empezando por Montería/Juana Ríos en Chancay-Lambayeque y La Compuerta/
Algarrobal-Nueva Esperanza-Germán Muñoz en Zaña, con fuente oficial o DEM por
cuenca, outlet y sensibilidad documentados.
