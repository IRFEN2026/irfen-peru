# IRFEN v0.9 · `uh_rain_context`: lluvia IMERG Early por unidad hidrográfica ANA (31-10-2026)

**Guardas:** RESEARCH_ONLY / TEST_ONLY, `production_use=false`, `activation_gate=BLOCKED`, `decision_thresholds=null`, `predictive_skill_claimed=false`.

Es un producto científico independiente: el motor de lluvia, la priorización y el mapa no lo leen, y no tiene umbrales ni alertas. Va apilado sobre #456 (polígonos ANA archivados).

```bash
python scripts/v09_build_research_uh_units.py --check      # unidades (≈70 s, sin red)
python scripts/v09_build_uh_rain_context.py --check        # producto + vista (≈20 s, sin red)
python -m unittest tests.test_v09_uh_rain_context          # 19 pruebas
# captura (runner, EARTHDATA_TOKEN): python scripts/v09_uh_rain_capture.py --hours 120
```
Vista experimental autocontenida, sin recursos externos y fuera de `site/`: `research/v09/uh_rain_context.html`.

## 1. Unidades de investigación (`data/v09/research/uh_units_v0_1.json`)
Son 10 polígonos ANA archivados en #456, sin simplificar.
- Para cada uno se registran: código Pfafstetter, superficie (atributo ANA y cálculo esférico; difieren un 1,0–1,1 %), celdas IMERG de 0,1° con su fracción interior, cabecera fuera del Perú, centros poblados contenidos y grado de incertidumbre territorial.
- **Regla del grado de incertidumbre territorial:**
  - **ALTA** si la resolución IMERG es insuficiente (0 celdas enteras dentro) o si más del 25 % de los centros poblados están a menos de 1 km del límite.
  - **MEDIA** si la resolución es marginal (1–9 celdas), si la cabecera está fuera del Perú o si algún centro poblado está a menos de 1 km.
  - **BAJA** en el resto de casos.

## 2. Resultados reales
Captura: [run 41143397810](https://github.com/IRFEN2026/irfen-peru/actions/runs/41143397810).
- 228 gránulos GPM_3IMERGHHE **V07C**, del 25-10 23:00 UTC al 30-10 17:00 UTC (corte), 1,6 GB leídos en 167 s.
- **228 de 228 medias horas** disponibles. NASA republicó la caída del 28 al 30-10, así que no quedan huecos.
- 0 duplicados, 0 ausentes.
- Cada gránulo queda registrado con su SHA-256.

| Unidad | Clase | 1 h | 3 h | 6 h | 24 h | 72 h (mm) | Máximo en bloques de 6 h (mm, UTC) | Celdas IMERG enteras / que tocan | Centros poblados (a < 1 km del límite) | Avisos vigentes en el corte | Incertidumbre territorial |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cuenca Piura (1378) | prioritaria | 0,0 | 0,0 | 0,0 | 1,31 | 7,46 | 2,44 (29-10 05→11) | 59/119 suficiente | 51 (0) | ACP-LLUVIAS-302, ACP-QUEBRADAS-302, AVISO-MET-443, 445 | BAJA |
| Cuenca Chira (138) | prioritaria | 0,0 | 0,0 | 0,0 | 5,57 | 14,36 | 4,93 (27-10 05→11) | 56/121 suficiente | 9 (0) | ídem | MEDIA (cabecera en Ecuador) |
| Cuenca Cascajal (13778) | prioritaria | 0,0 | 0,0 | 0,0 | 0,20 | 8,13 | 5,26 (29-10 05→11) | 14/54 suficiente | 3 (0) | ídem | BAJA |
| Intercuenca 13779 | prioritaria | 0,0 | 0,0 | 0,0 | 0,00 | 0,19 | 0,16 (26-10 17→23) | 18/62 suficiente | 3 (3) | ídem | ALTA (3 de 3 cerca del límite) |
| Cuenca Tumbes (1394) | exploratoria | 0,0 | 0,0 | 0,0 | 5,86 | 10,76 | 19,11 (27-10 05→11) | 4/31 marginal | 21 (0) | ídem | MEDIA (cabecera en Ecuador) |
| Cuenca Zarumilla (13952) | exploratoria | 0,0 | 0,0 | 0,0 | 25,57 | 34,67 | 26,19 (27-10 05→11) | 0/9 insuficiente | 11 (5) | AVISO-MET-443, 445 | ALTA |
| Intercuenca 13935 | exploratoria | 0,0 | 0,0 | 0,0 | 0,04 | 0,95 | 4,92 (27-10 05→11) | 0/10 insuficiente | 2 (2) | ídem | ALTA |
| Intercuenca 13939 | exploratoria | 0,0 | 0,0 | 0,0 | 0,40 | 3,61 | 30,91 (27-10 05→11) | 0/6 insuficiente | 6 (6) | ídem | ALTA |
| Intercuenca 13951 | exploratoria | 0,0 | 0,0 | 0,0 | 14,23 | 44,21 | 38,36 (27-10 05→11) | 0/6 insuficiente | 4 (1) | ídem | ALTA |
| Cuenca Bocapán (13936) | control | 0,0 | 0,0 | 0,0 | 0,19 | 1,42 | 7,36 (27-10 05→11) | 3/14 marginal | 0 | ídem | MEDIA |

**Cómo leer estas cifras:**
- Todas las ventanas están completas, al 100 % de datos y 100 % de cobertura espacial.
- **0,0 mm es un cero observado por IMERG**, no un dato ausente.
- Son estimaciones satelitales: no son medidas de pluviómetro y no tienen error caracterizado frente a estaciones en estas cuencas.
- Los avisos se relacionan por las provincias o departamentos que enumeran, no por su huella. Los avisos meteorológicos solo listan departamentos.

## 3. Validación científica
| Comprobación | Resultado |
|---|---|
| Lectura directa de 3 gránulos con h5py, sin el lector existente | ✅ 3/3. Dimensiones `time,lon,lat` [1, 3600, 1800]; unidades `mm/hr`; relleno −9999,9; centros −89,95 / −179,95 con paso 0,1° (float32) |
| Marca temporal | ✅ La variable `Grid/time` usa la **época GPS** (`seconds since 1980-01-06 00:00:00 UTC`) y coincide con el inicio S del nombre en los 3 gránulos. **Error detectado y corregido:** la captura convertía con época 1970 y daba fechas de 2016. El error no afectaba a las medias (el intervalo sale del nombre); ya está corregido en el script de captura y el informe usa la época declarada |
| Unidades e intervalos | ✅ Todos `mm/hr`. Duración de intervalo: 1800 s en los 228. Acumulado por media hora = tasa × 0,5 h, comprobado en cada valor |
| Intervalos duplicados | ✅ 0 en el catálogo y 0 en la serie. La deduplicación conserva la versión más alta |
| Medias recalculadas desde las celdas crudas | ✅ Coinciden en las 4 unidades prioritarias (diferencia máx. 0,0009 mm/h) |
| Muestreador existente frente a método de control | La mediana de la diferencia relativa es 0,2 % y el p95 es 1,1 %, sobre 615 valores > 0,1 mm/h. Máximo 15,6 % en Zarumilla (0,108 mm/h): en unidades de menos de 10 celdas, el tratamiento de las celdas parciales importa |
| Consistencia con el archivo operativo | ✅ Bocapán, mismo polígono que la zona `tumbes_bocapan`: 180 medias horas, diferencia máx. 0,00005 mm/h (redondeo) |
| Estaciones | ❌ **Sin comparación defendible.** No hay serie de pluviómetro de 2026 archivada en estas cuencas: El Salto (Zarumilla, #447) solo tiene 1968–2015, y no se consulta SENAMHI de forma automatizada. No se declara precisión |

**Muestreador existente** (`probe_imerg_early_live.polygon_mean`):
- **Celdas parciales:** se ponderan por el área de intersección celda ∩ polígono, en grados².
- **Celdas sin dato:** se excluyen y bajan `covered_pct`. Una media hora se acepta solo si `covered_pct` ≥ 95.
- **Ponderación en latitud:** no aplica cos(lat). El efecto se mide con el método de control.

## 4. Reorientación científica: crecidas y desbordes
En Tumbes y en buena parte de Piura el peligro prioritario es la **crecida y el desborde de los ríos principales**. Lo producen lluvias intensas o acumuladas en las cuencas altas, incluidas las cabeceras ecuatorianas de Puyango-Tumbes y Catamayo-Chira. Los huaicos y flujos de detritos de quebradas siguen siendo una línea **diferenciada**: no se da por hecho que sean el peligro predominante en el norte.

Consecuencias para `uh_rain_context`:
1. **La lluvia que importa está aguas arriba.**
   - En Tumbes y Chira, el polígono ANA solo cubre la parte peruana (cuenca media y baja). La lluvia de la cabecera ecuatoriana no está representada.
   - Para validar crecidas hace falta una **cuenca completa hasta la estación de aforo**, que es una unidad distinta de la UH ANA. Para el Tumbes, en El Tigre (área de drenaje por confirmar con la fuente). Para el Chira, en El Ciruelo, en la frontera.
2. **Tiempos de propagación.**
   - El acumulado debe compararse con el caudal **desfasado** según el tiempo de viaje entre la cabecera y la estación.
   - No se ha encontrado una cifra oficial de tiempo de viaje para crecidas en ningún río. El único estudio localizado (Peña-Cáceres et al., REDER 2025) mide el tramo urbano del río Piura con flotadores y en caudales bajos: no sirve para crecidas.
   - El tiempo de propagación debe **estimarse con datos**: correlación cruzada lluvia–caudal y desfase entre estaciones aguas arriba y aguas abajo, por ejemplo Ñácara → Sánchez Cerro o El Ciruelo → Ardilla/Sullana. No se asume ninguna cifra.
3. **Sin umbrales ni modelos predictivos** hasta tener evidencia suficiente.

### Disponibilidad de datos históricos (investigación del 31-10; nada se ha descargado de forma automatizada)
| Necesidad | Fuente candidata | Qué ofrece | Estado / acceso |
|---|---|---|---|
| Caudales diarios Chira y Piura | **Proyecto Especial Chira-Piura (PECHP)**, «Informes técnicos hidro» mensuales en gob.pe ([marzo 2017](https://cdn.www.gob.pe/uploads/document/file/3274125/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000003-2017.pdf), [marzo 2018](https://cdn.www.gob.pe/uploads/document/file/3274145/Informes%20T%C3%A9cnicos%20hidro%20N%C2%B0%2000003-2018.pdf), 2011–2018 localizados) | Tablas de caudal medio diario y máximos instantáneos en El Ciruelo (frontera), Macará, Paraje Grande (Quiroz), Poechos, Presa Sullana, Puente Ñácara, Puente Sánchez Cerro, Los Ejidos y Tambogrande. Marzo de 2017: Sánchez Cerro con un máximo de caudal medio diario de **2 754,5 m³/s el día 27**; El Ciruelo con un instantáneo máximo de **2 286,2 m³/s el día 31** | PDF públicos y estáticos en gob.pe. Se pueden archivar con SHA-256 y transcribir con el mismo método de doble lectura que ANA 2016-17. Faltan coordenadas de estación y metadatos de método, y hay incoherencias internas en los totales (registradas). **Es la fuente más prometedora para validar Chira y Piura** |
| Caudal y nivel del río Tumbes | SENAMHI, estaciones hidrológicas **El Tigre** y **Puente Tumbes** (citadas en el [boletín COE-Vivienda n.º 033-2019](https://ww3.vivienda.gob.pe/grd/documentos/Bolet%C3%ADn%20Aviso%20Hidrol%C3%B3gico%20N%C2%BA%20033-2019%20Situaci%C3%B3n%20del%20caudal%20del%20r%C3%ADo%20Tumbes%20-%2002Mar%29.pdf), con umbral hidrológico naranja); Proyecto Especial Binacional Puyango-Tumbes | Estados de umbral y caudales en boletines. Hay series históricas en SENAMHI | **No se consulta SENAMHI de forma automatizada** (restricción vigente). Hay que pedir la serie a SENAMHI o a PEBPT, o archivar a mano boletines PDF concretos |
| Cabecera ecuatoriana | INAMHI (Ecuador): estaciones de Macará y Puyango. Delimitación binacional de cuencas | Caudal y lluvia aguas arriba | Sin servicio verificado en esta sesión. Para el polígono de la cuenca completa, la alternativa reproducible es HydroBASINS/HydroSHEDS (WWF; **no oficial**; solo para investigación y declarado así) |
| Zonas inundadas observadas | **Copernicus EMS [EMSR199](https://mapping.emergency.copernicus.eu/activations/EMSR199)**, «Floods in Peru», activado el 22-03-2017 | Delimitaciones vectoriales (.zip) de áreas inundadas en Piura (norte, este, oeste), Sullana y Los Ejidos, entre el 23-03 y el 22-05-2017 | Descarga pública. Es **huella observada por satélite** de 2017, útil para validar el episodio. No es mapa de peligro |
| Susceptibilidad a inundación | INGEMMET, informe A6792 «Peligros geológicos y geo-hidrológicos… Niño Costero 2017 en la región Tumbes» ([SIGRID 3975](https://sigrid.cenepred.gob.pe/sigridv3/documento/3975/descargar)) | Mapa de susceptibilidad a inundación y erosión fluvial, cuenca baja del Tumbes | Solo PDF, sin capa vectorial. Según la política vigente, no se digitaliza |
| Huellas de inundación en Tumbes | ANA, MapServer `Inundacion_Tumbes` (plan archivado en el repositorio: capas 2, 66 y 67, cuenca del Tumbes y huellas de 2023) | Huellas de inundación de 2023 | Servidor ANA (`geosnirh`) inaccesible desde los runners (#456). Hace falta una vía alternativa |
| Faja marginal | Resoluciones ANA de delimitación de faja marginal | Límite legal del cauce | Una faja marginal **no** es una zona inundable ni una huella de inundación |

### Episodios candidatos para la validación histórica
| Episodio | Río | Evidencia localizada | Cobertura de lluvia por satélite |
|---|---|---|---|
| Niño Costero, marzo de 2017 (desborde del río Piura el 27-03-2017) | Piura, Chira | PECHP marzo 2017 (caudales diarios); EMSR199 (huella); INGEMMET (Tumbes) | IMERG Final/Late V07, desde 2000 |
| Febrero–marzo de 2019 (umbral naranja en El Tigre el 02-03-2019) | Tumbes | Boletín COE-Vivienda 033-2019 (sin cifra de caudal) | IMERG |
| Ciclón Yaku y lluvias de marzo de 2023 | Tumbes, Piura | Huellas ANA `Inundacion_Tumbes` (inaccesible por ahora) | IMERG |
| Niño 1997-98 y 1983 | Todos | Literatura (U. de Chile, cuenca baja Puyango-Tumbes) | IMERG solo desde 2000: **1983 y 1998 quedan fuera**. Haría falta CHIRPS o PERSIANN-CDR, con otra resolución |

## 5. Problemas detectados
1. **Época temporal del HDF5.** IMERG V07 usa la época GPS (1980-01-06). La relectura directa convertía con época 1970. No afectaba a las medias; ya está corregido y probado.
2. **Unidades pequeñas.** Las intercuencas de Tumbes, Zarumilla y la 13935 no tienen ninguna celda IMERG entera dentro. Sus valores dependen de 6 a 10 celdas compartidas con unidades vecinas y del criterio para las celdas parciales (hasta un 15 % entre métodos). **No sirven para distinguir lluvia entre unidades vecinas.**
3. **Cabeceras ecuatorianas.** Tumbes y Chira solo representan la parte peruana. Es la limitación principal para el objetivo de crecidas: el caudal de El Tigre o de El Ciruelo responde sobre todo a la lluvia de Ecuador, que no está en estos polígonos.
4. **Avisos.** Los avisos meteorológicos solo listan departamentos, así que su relación con una cuenca es meramente administrativa. Los ACP sí listan provincias, lo que permite indicar qué parte de la unidad cubren.
5. **Sin verdad de terreno en esta ventana.** Sin estaciones no se puede caracterizar el sesgo de IMERG Early en estas cuencas.
6. **Coste de la prueba de reproducibilidad.** Reconstruir las unidades tarda unos 70 s en Python puro. Es aceptable en CI, pero conviene vectorizarlo si se añaden más unidades.

## 6. Condiciones para iniciar la validación histórica del comportamiento de las lluvias
1. **Cuenca completa hasta la estación de aforo**, incluida la parte ecuatoriana: Puyango-Tumbes hasta El Tigre y Catamayo-Chira hasta El Ciruelo. Se necesita un polígono reproducible, oficial binacional o HydroBASINS declarado como no oficial. Sin él, la lluvia que se compare con el caudal está truncada.
2. **Series de caudal o nivel observadas** con horario conocido:
   - PECHP (Chira y Piura), archivando los PDF con SHA-256 y transcribiendo con doble lectura.
   - SENAMHI o PEBPT para Tumbes, mediante solicitud formal, no por consulta automatizada.
   - Hay que registrar las coordenadas de cada estación y la definición de «máximo instantáneo» frente a «medio diario».
3. **Lluvia histórica coherente:** IMERG **Final** V07 (2000–presente) para el análisis de episodios. Early es casi en tiempo real y tiene más sesgo. Los episodios de 1983 y 1998 requieren otro producto.
4. **Catálogo de episodios con fecha y hora:** 27-03-2017 (Piura), marzo de 2019 (Tumbes), marzo de 2023 (Yaku). Cada uno con su evidencia independiente: caudal, huella EMSR199 y avisos de la época.
5. **Propagación medida, no supuesta:** desfase lluvia–caudal y desfase entre estaciones, estimados por episodio y con su incertidumbre.
6. **Protocolo previo a mirar los resultados:** qué acumulados y qué desfases se comparan, sin ajustar umbrales a los episodios. Ningún umbral ni modelo predictivo antes de tener esa evidencia.
7. **Huaicos y flujos de detritos como línea aparte:** usan otras escalas (quebradas pequeñas, intensidad de 1 a 3 h) y otra evidencia, y no se mezclan con la validación de crecidas de ríos.
