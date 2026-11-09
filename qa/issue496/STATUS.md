# Actualización verificada · 9 noviembre 2026

**RESEARCH_ONLY/TEST_ONLY. La ejecución ya terminó; el bloqueo de autorización mencionado más abajo quedó resuelto con el permiso posterior del usuario.** El texto del 6 noviembre se conserva como antecedente, no como estado actual.

Run [42246018380](https://github.com/IRFEN2026/irfen-peru/actions/runs/42246018380), commit `7f6c97b54f2cab6771adac3f345638397c03e858`: 48 HDF5 IMERG Early V07C, 4 noviembre 12:00–5 noviembre 12:00 UTC. 7.488 comparaciones para 134 geometrías de cuenca/tramo y 22 zonas norte; cero diferencias superiores a 0,000051 mm/h. Máximo absoluto: 0,0000506419365 mm/h. Esto comprueba reproducción dentro de tolerancia, no exactitud pluviométrica.

Verificación independiente del 9 noviembre: 48 hashes correctos y reproducción exacta de píxel, media, máximo, p50 y p90 de los cuatro candidatos geográficos mediante h5py, sin importar lectores ni muestreadores IRFEN. Run remoto: 12 pruebas dirigidas aprobadas. Artefacto `13518036065`, SHA256 ZIP `9806f9207767ff7a44552bd476cf40c4e2c9bf7245e69a482b57dd61619838fd`; retención hasta 6 diciembre. Preservar originales antes de su expiración.

El control de reproducción abarca Tumbes, Piura, Lambayeque, La Libertad, Áncash, Lima, Callao, Ica, Arequipa, Moquegua y Tacna: 10 departamentos y Callao. No equivale a validar todas sus estaciones o cuencas.

## Evidencia documental nueva

El [boletín COEN 309](https://portal.indeci.gob.pe/wp-content/uploads/2026/11/BOLET%C3%8DN-INFORMATIVO-MONITOREO-DE-PELIGROS-Y-PERSPECTIVAS-N%C2%B0309-del-05-11-2026.pdf), página 5, reproduce datos SENAMHI para 4 noviembre 07:00–5 noviembre 07:00. Página comprobada visualmente. Se interpreta hora Perú UTC−05; la lámina no imprime zona horaria. Es evidencia institucional, **no registro instrumental original**.

| Estación candidata | Boletín mm/24 h | Celda 0,1° mm | Media 3×3 mm | Máximo 3×3 mm | Diferencia celda/boletín |
|---|---:|---:|---:|---:|---:|
| Rica Playa | 112,50 | 36,90 | 31,07 | 59,60 | −67,20 % |
| Puerto Pizarro | 40,08 | 25,15 | 29,35 | 61,12 | −37,24 % |
| Matapalo | 10,40 | 8,69 | 9,31 | 23,90 | −16,44 % |

También constan La Cruz 75, Cañaveral 88,9 y Papayal 22,4 mm. No se asigna celda sin revisar coordenadas. Coordenadas, centros de celda y procedencia están en `research/issue496/results-20261109/documentary-comparison.json`; datum aún no confirmado. El resultado NASA original conserva cero pares instrumentales.

Rica Playa mantiene discrepancia incluso respecto al máximo del vecindario. Es un indicio documental del evento, no un sesgo transferible demostrado. Los cocientes distintos no justifican un multiplicador único. Estación puntual, celda y media de cuenca tienen distinto soporte espacial.

## Limitaciones encontradas

Los sectores Tumbes alto/medio/bajo dan 1,325 / 3,565 / 5,781 mm con ponderación equivalente: no representan la lluvia puntual en Rica Playa. De 156 geometrías, 140 tienen resultado equivalente y 16 quedan nulas por cobertura calculada inferior a 0,99999. Investigar precisión geométrica y límites de celda antes de relajar el umbral. No convertir nulos a cero.

Entre los resultados evaluables, el cambio máximo frente a pesos en grados cuadrados fue 0,002877 mm (Ocoña bajo); en sectores Tumbes, inferior a 0,000341 mm. No explica la gran discrepancia del episodio. La reproducción usa geometrías y lógica de pesos históricas: no es validación independiente de la delimitación hidrológica.

## Recomendación y alcance pendiente

Cerrar solo la comprobación acotada NASA→archivo de estas 24 horas. Mantener #496 abierto para originales SENAMHI y período completo 31 octubre–6 noviembre: **se comprobó un día, no siete**. No aplicar multiplicador global ni declarar calibración. Faltan datum, calidad instrumental y más episodios para evaluación fuera de muestra.

Reproducción offline: `python scripts/verify_issue496_artifact.py /ruta/artefacto --output /ruta/verificacion.json` (requiere numpy y h5py). Resultados y verificación: `research/issue496/results-20261109/`.

No se fusionó, desplegó visor ni activaron alertas. Estimación para análisis completo: 1–2 jornadas desde disponer de originales y metadatos suficientes, según calidad/volumen. No hay fecha garantizada para obtener archivos restringidos y no se eluden login ni CAPTCHA. La recomendación actual ya está emitida.

---

# Antecedente: estado del 6 noviembre 2026 (superado por la actualización anterior)

**Cierre científico pendiente. Sin ejecución remota nueva, sin fusión, sin despliegue ni alertas.**

## Comprobaciones realizadas

- El run [42211307907](https://github.com/IRFEN2026/irfen-peru/actions/runs/42211307907), job 127870331558, terminó correctamente y sus logs informan `EARLY_HALFHOURLY_SOURCE_AVAILABLE` y `granules_downloaded: 4`. El acceso NASA existe en Actions. Esto no demuestra que los 48 originales históricos ya estén recuperados.
- Ese flujo escribe en main y ordena publicación. No se relanzó. Su lista de artefactos está vacía.
- El run offline #496 [42232660929](https://github.com/IRFEN2026/irfen-peru/actions/runs/42232660929) no tiene artefactos. El run privado 42236518491 solo lista un artefacto de 1162 bytes; no se recuperó de él ningún HDF5. No se afirma haber agotado todos los runs históricos.
- La búsqueda adicional en SENAMHI no aportó registros instrumentales del período. Las coordenadas de Rica Playa aparecen en https://www.senamhi.gob.pe/load/file/02243SENA-75.pdf ; no equivalen a un registro de lluvia de noviembre de 2026.

## Dos errores demostrados del auditor en borrador #497

1. **Máximo/p90 del vecindario acumulado incorrectamente.** Sumaba máximos y percentiles de cada media hora, aunque correspondieran a diferentes celdas. La corrección acumula primero las nueve celdas fijas y después calcula sus estadísticas. Un ejemplo sintético alternando lluvia entre dos celdas produce 120 mm de máximo acumulado; el método anterior producía 240 mm. Este es un error del auditor nuevo, no una causa demostrada de las medias bajas de cuencas.
2. **Observación fijada en el código a partir de noticias.** `STATIONS` contenía cantidades que luego se utilizaban sin leer la cantidad del documento instrumental. La corrección exige el valor, unidades, ventana, calidad, indicador de origen instrumental y documento local cuyo SHA256 coincida. No hay sustitución periodística.

También se exige datum WGS84, se permite un subconjunto de estaciones verificadas, se protege la división cuando la medición es cero y se etiqueta la diferencia como firmada.

## Ejecución preparada

Rama local: `research/issue496-nasa-replay-20261106`.
Workflow: `.github/workflows/issue496-original-replay.yml`.

- Descarga acotada a los 48 originales del 4 noviembre 12:00–5 noviembre 12:00 UTC.
- Reutiliza `EARTHDATA_TOKEN` dentro del runner, sin extraerlo ni imprimirlo.
- Solo `contents: read`; checkout sin credenciales persistentes.
- Sin escrituras a main, Pages, notificaciones, alertas o despliegues.
- Originales y resultados en artefacto con retención de 30 días.
- Compara tasas contra una referencia congelada de las 134 cuencas y las zonas norte; evalúa diferencias del peso en grados cuadrados frente a proyección equivalente.
- Guarda muestras de píxel y 3×3 como candidatos geográficos, sin inventar mediciones instrumentales.

La referencia congelada procede de main@46d68647; `research/issue496/baseline/manifest.json` enumera hashes. Se conserva separada porque el PR #497 parte de una versión anterior sin el muestreador de cuencas requerido.

## Pruebas

**53 pruebas aprobadas en esta revisión**, incluida una integración con 48 HDF5 sintéticos, cero llamadas externas y cero credenciales reales. Estos archivos sintéticos no son evidencia meteorológica.

```bash
python -m pytest -q tests/test_issue496_nasa_replay.py tests/test_v09_p0_496_pixel_gauge_audit.py tests/test_v09_imerg_north_archive.py tests/test_imerg_early_catacaos.py
```

## Bloqueo y plazo

La revisión automática rechazó subir la rama: consideró que publicar código en el repositorio público contradice la instrucción de no publicar. No se reintentó mediante otra herramienta ni mecanismo. La ejecución remota necesita que el workflow exista en GitHub; por eso quedó preparada, no iniciada.

**Decisión mínima necesaria:** permitir subir exclusivamente esta rama de investigación para ejecutar el workflow aislado, sin fusionar ni desplegar. No solicita autorización para publicar el visor ni activar alertas.

Estimación de trabajo, no garantía: **1–2 horas desde que se habilite esa ejecución**, si NASA sirve los 48 archivos y no aparecen errores nuevos. El timeout de una ejecución es de 35 minutos; revisión y posibles ajustes explican el margen adicional.

Para el cierre estación–satélite faltan registros SENAMHI originales. Estimación **1–2 horas adicionales desde su recepción**, dependiendo del formato y calidad. No puede garantizarse su obtención en cuatro horas: depende de acceso consentido o respuesta de SENAMHI. Si se entregan a tiempo, las tareas pueden solaparse.

El incidente #496 permanece abierto; no se ha estimado un factor de calibración ni validado la costa completa.
