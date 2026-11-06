# P0 #496 — 06-11-2026, protocolo de comparación NASA–SENAMHI

**Estado: BLOQUEADO PARA CALIBRACIÓN, NO_EVALUABLE.** No se han recuperado en este PR los 48 HDF5 originales ni el boletín/CSV instrumental oficial con ID, coordenadas y QC de las ocho estaciones. Los valores atribuidos a SENAMHI por Correo (05-11-2026) son evidencia periodística, NO observaciones instrumentales importadas.

## Diagnóstico ya reproducible del incidente
Ventana **2026-11-04T12:00Z – 2026-11-05T12:00Z** (07:00–07:00 PET). Medias archivadas de cuencas Tumbes alto 1,32 mm, medio 3,57, bajo 5,78; Zarumilla alto 2,96, bajo 3,50. **No dividir una media areal entre un pluviómetro puntual para concluir sesgo instrumental.** La coincidencia de 48 registros de 30 minutos no demuestra validez de variables, grilla ni del origen HDF5.

## Herramienta
`scripts/v09_p0_496_pixel_gauge_audit.py` acepta SOLO archivos originales HDF5 de NASA IMERG Early V07 obtenidos por vía autorizada y JSON con las ocho estaciones (ID, coordenadas verificadas, fuente oficial y SHA256 del documento original). Verifica 48 tiempos de inicio exactos, duplicados, variable `Grid/precipitation`, unidades mm/hr, orientación de grilla, nulos, celda central y vecindario 3×3. Produce un informe congelado sin sobrescribir. Rechaza falta de metadatos o gránulos. Los máximos de vecindario son diagnósticos, no una estimación equivalente a la estación.

NASA documenta el producto GPM_3IMERGHHE V07, grilla 0,1°, intervalos de 30 minutos, latencia Early de ~4 horas y variable `precipitation` en la versión V07. La unidad debe verificarse contra atributos reales del HDF5, no presumirse. Fuente oficial: https://doi.org/10.5067/GPM/IMERG/3B-HH-E/07 y https://gpm.nasa.gov/data/directory

SENAMHI DZ1: el 05-11-2026 Diario Correo atribuyó 112,5 mm a Rica Playa, 112,2 mm al Aeropuerto de Tumbes, 90,1 Cabo Inga, 88,9 Cañaveral, 82 Huásimo, 75 La Cruz, 49 Puente Tumbes, 10,4 Matapalo. No usar para entrenamiento sin documento primario. https://diariocorreo.pe/edicion/tumbes/fenomeno-el-nino-fuertes-lluvias-inundan-tumbes-calles-hospital-minsa-resultan-afectados-noticia/

## Toda la costa
Aplicar idéntica auditoría al archivo de 134 áreas aportantes de los 11 departamentos; etiquetar cobertura temporal y espacial, sin afirmar calibración en departamentos sin pluviómetros originales. Tumbes es incidente prioritario, NO único territorio. SILVIA sigue capa de susceptibilidad (no eventos), con máscara oficial costera pendiente. Sin modificaciones a visor, semáforo, `main` ni alertas.
