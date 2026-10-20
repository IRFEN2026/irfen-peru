# Consulta del inventario nacional de quebradas documentadas (solo lectura)

`scripts/query_phase2_national_inventory.py` consulta las 400 identidades de
`config/phase2_national_inventory_completeness_audit_v0_1.json`. No hace falta geometría: las filas sin contorno
aparecen como cualquier otra. RESEARCH_ONLY / TEST_ONLY. No escribe, no promueve identidades ni eventos y no crea
geometrías ni outlets.

```
python scripts/query_phase2_national_inventory.py --name quitasol
python scripts/query_phase2_national_inventory.py --department Tumbes --without-geometry
python scripts/query_phase2_national_inventory.py --provenance SIN_VERIFICAR --format json
```

## Estado de procedencia (calculado al consultar)

| Estado | Significado |
|---|---|
| VERIFICADA_SHA256 | El `verification_record` de la fuente apunta a un archivo de este repositorio cuyo SHA-256, recalculado al consultar, coincide con `archived_sha256`, **y** el ítem tiene `locator` + `verified_statement`. |
| SHA256_DISTINTO | El archivo existe, pero su SHA-256 no coincide con el registro. |
| ARCHIVO_AUSENTE | El registro nombra una ruta del repositorio que no existe. |
| REGISTRO_SIN_ARCHIVO_LOCAL | Hay registro, pero su ubicación no es un archivo seguro del repositorio: URL, ruta absoluta, ruta fuera de `data/` o `site/data/`, `..`, `.` o segmentos vacíos, barras invertidas, caracteres de control, o un enlace simbólico que sale de la raíz de archivo. También si el hash está mal formado. No está verificado. |
| SIN_VERIFICAR | No hay registro de verificación: es una pista, no una evidencia. |
| FUENTE_NO_CATALOGADA | El ítem cita un `source_id` que no está en el catálogo de fuentes de la auditoría. |

Con la auditoría actual de `main`, las **400 filas están en SIN_VERIFICAR**, porque ninguna fuente tiene texto
verificado, y **397 no tienen geometría reproducible**. Las revisiones r3–r7 (#365, #366, #381, #385, #378) no
están en `main` y no aparecen. Por ejemplo, Banchero/Mariátegui (#385) devuelve 0 filas.

## Seguridad de rutas
Solo se leen archivos bajo `data/` o `site/data/`, y solo para calcular su SHA-256 en modo binario. Primero se resuelve
la ruta real, siguiendo los enlaces simbólicos, y se exige que quede dentro de esa raíz. La consulta no escribe nada
ni accede a la red.
