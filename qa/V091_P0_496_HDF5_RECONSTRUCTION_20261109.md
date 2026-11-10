# P0 #496 · Reconstrucción IMERG Early desde los HDF5 originales (09-11-2026)

RESEARCH_ONLY / TEST_ONLY. No se calibra, no se corrige, no se cambian umbrales y no se colorea nada.

**Evidencia:**
- Ejecución de GitHub Actions [42638351230](https://github.com/IRFEN2026/irfen-peru/actions/runs/42638351230). Descargó de NASA GES DISC, con el token del proyecto, las 48 medias horas de la ventana.
- Informe `data/v09/research/p0_496/imerg_hdf5_reconstruction_v0_1.json`, con nombre y SHA-256 de cada HDF5. Los HDF5 no se redistribuyen.
- Mapa `imerg_24h_tumbes_hdf5_v0_1.png`.

## 1. ¿Hay un error de procesamiento en IRFEN? No

| Control | Resultado |
|---|---|
| Medias horas originales 04-11 12:00Z → 05-11 12:00Z | 48 de 48, de `3B-HHR-E…S120000…0720.V07C` a `…S113000…0690.V07C` |
| Producto y versión | GPM_3IMERGHHE, Early, **V07C** en todos los archivos |
| Variable | `Grid/precipitation`, unidades `mm/hr`, `_FillValue` −9999,9, `DimensionNames` = `time,lon,lat` |
| Ejes | Rejilla global de 0,1°, centros de −179,95 a 179,95 y de −89,95 a 89,95, crecientes |
| Orientación | La lectura de producción (`probe_imerg_early_live.read_grid`) y una lectura h5py independiente, que sigue `DimensionNames`, coinciden **celda a celda** en las 48 medias horas (diferencia máxima 0; ningún desacuerdo en datos ausentes) |
| Acumulado | Σ tasa × 0,5 h por media hora; una media hora ausente deja el valor como desconocido |
| Medias areales | Recalculadas desde los HDF5 con el código de producción para 156 objetivos (134 áreas aportantes y 22 zonas o provincias del norte). **Diferencia máxima frente a lo archivado en main (`d214e8b9`): 0,0002 mm** |
| Gránulos | Los nombres de los 48 gránulos coinciden con los registrados en ambos archivos de main |

Valores reconstruidos (iguales a los archivados): Tumbes alto 1,33 mm, medio 3,57 mm y bajo 5,78 mm; Zarumilla alto 2,96 mm y bajo 3,50 mm; Bocapán 31,05 mm; provincia de Tumbes 17,65 mm; Contralmirante Villar 24,61 mm; provincia de Zarumilla 10,08 mm.

**Conclusión:** no se encontró ningún error de variable, unidades, ×0,5, orientación, huecos ni ponderación geométrica. Los valores de IRFEN son los que contiene IMERG Early V07C.

## 2. ¿Por qué la cuenca del Tumbes da tan poco?

- El 73 % del área aportante del Tumbes bajo está en Ecuador (cabecera del Puyango).
- Según IMERG, el núcleo de lluvia estuvo en la franja costera y en el mar, al noroeste: el máximo del recorte es 88,3 mm en −80,65 / −3,15. Sobre la cabecera, IMERG da 0–5 mm.
- La media de la cuenca diluye la lluvia costera. **No es comparable con un pluviómetro.**

## 3. Píxel frente a estación (diagnóstico, no validación)

Los valores de estación proceden de **prensa y no están verificados**. Las coordenadas son las del anexo del Atlas Climático SENAMHI, redondeadas a 0,1°. Por eso cada punto cae en una esquina de la rejilla y es compatible con 2×2 celdas: se da el rango.

| Estación | Reportado (mm) | IMERG, celdas compatibles (mm) | IMERG 3×3 media / máx (mm) | Emparejamiento |
|---|---:|---:|---:|---|
| Rica Playa | 112,5 | 16,5 – 36,9 | 18,8 / 36,9 | Ambiguo (2×2); con la coordenada citada en #496: 36,9 |
| Aeropuerto Tumbes | 112,2 | — | — | **No emparejable**: sin coordenada documentada del pluviómetro |
| Cabo Inga | 90,1 | 2,9 – 18,7 | 10,5 / 19,0 | Ambiguo (2×2) |
| Cañaveral | 88,9 | 29,9 – 59,6 | 36,8 / 59,6 | Ambiguo (2×2) |
| Huásimo | 82,0 | — | — | **No emparejable** |
| La Cruz | 75,0 | 25,1 – 35,0 | 31,5 / 48,1 | Ambiguo (2×2) |
| Puente Tumbes | 49,0 | — | — | **No emparejable** |
| Matapalo | 10,4 | 0,8 – 8,7 | 9,3 / 23,9 | Ambiguo (2×2) |

Indicadores para las 5 estaciones emparejables (un único evento: no son estadística de sesgo):

| Variante | Sesgo | MAE | RMSE | Σ IMERG / Σ reportado |
|---|---:|---:|---:|---:|
| Celda compatible más favorable | −43,6 mm | 43,6 mm | 51,5 mm | 0,42 |
| 3×3 máximo | −37,9 mm | 43,3 mm | 50,1 mm | 0,50 |

**Cabo Inga, 16–19 PET (21–24Z):**
- reportado: 74,4 mm;
- IMERG: 12,8 mm, tanto en la celda compatible como en el máximo 3×3.

**Momento del máximo según IMERG:**
- la celda de Rica Playa tiene su máximo entre las 01:00 y las 02:00Z (20–21 PET), con 20–23 mm/h;
- eso es entre 2 y 4 h después de la subventana que la prensa atribuye a Cabo Inga;
- es compatible con un desfase de IMERG Early en convección (morphing IR), pero no está demostrado.

**Índice de calidad medio** en las celdas de las estaciones: ≈ 0,42.

**Dictamen:**
- **Procesamiento de IRFEN:** correcto.
- **Píxel:** IMERG Early subestima de forma marcada la lluvia puntual reportada en 4 de las 5 estaciones emparejables. Solo Matapalo (10,4 mm) es coherente.
- **Tiempo:** el máximo de IMERG llega con retraso respecto a la hora reportada.
- **Validez:** la lluvia IMERG Early de cuenca **no es válida** como indicador de lluvia intensa costera en Tumbes. No se calibra con un solo evento ni con valores de prensa.

## 4. Consecuencias que el visor debe reflejar (para la línea de ChatGPT)

- Un `VERDE` o un amarillo bajo derivado de IMERG en Tumbes **no** implica ausencia de lluvia intensa. Recomendación: no mostrar `VERDE` («sin señal de lluvia») a partir de IMERG Early en puntos con eventos convectivos costeros documentados sin contraste instrumental. Como mínimo, una nota visible: «IMERG Early subestimó ~50–80 % la lluvia puntual en Tumbes el 04–05/11/2026 (#496)».
- Distinguir en la ficha: lluvia areal estimada (IMERG), lluvia puntual instrumental (SENAMHI, pendiente de verificación), aviso oficial y desconocido.

## 5. Qué falta para cerrar #496

1. Registros instrumentales originales SENAMHI DZ1 (ID, coordenadas exactas, hora de inicio y fin, control de calidad). Sin ellos, las cifras de la tabla siguen siendo diagnósticas.
2. Coordenadas documentadas de Aeropuerto Tumbes, Huásimo y Puente Tumbes.
3. IMERG Final V07 de la ventana cuando NASA lo publique (unos 3,5 meses después) y repetición de este mismo análisis.
4. Otros eventos independientes y estaciones de toda la costa antes de estimar cualquier sesgo (#498 lo plantea en modo «shadow»).

**Reproducir:** `python3 scripts/v091_p0_496_hdf5_reconstruction.py --download --archived-catchments <catchments.json de d214e8b9> --archived-north <north.json de d214e8b9>`, con `EARTHDATA_TOKEN`. También se puede ejecutar el workflow de esta rama.
