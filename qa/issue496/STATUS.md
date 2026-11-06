# Estado de ejecución autónoma · #496 · 6 noviembre 2026

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
