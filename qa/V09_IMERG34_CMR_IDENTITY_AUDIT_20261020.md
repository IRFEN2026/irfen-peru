# IRFEN v0.9 — Auditoría CMR de dos gránulos IMERG Early (20-10-2026)

**Resultado:** dos gránulos históricos NO LISTADOS EN CMR EN EL MOMENTO DE CONSULTA; causa física y administrativa **UNKNOWN**. RESEARCH_ONLY / TEST_ONLY; sin descargas HDF5, sin cambios a datos vivos, alertas, motor ni publicación.

## Alcance y evidencias originales

| Hora UTC | Concept-ID histórico | Productor / versión | SHA-256 HDF5 recuperado previamente |
|---|---|---|---|
| 2026-10-16 13:00 | `G4374452323-GES_DISC` | `3B-HHR-E.MS.MRG.3IMERG.20261016-S130000-E132959.0780.V07C.HDF5` | `7925067c32055c30a23f2c6c8d01d687218d9cb217f443dcf4a8b6eb17f9f047` |
| 2026-10-16 23:30 | `G4374376915-GES_DISC` | `3B-HHR-E.MS.MRG.3IMERG.20261016-S233000-E235959.1410.V07C.HDF5` | `3274414c48a5c1c4e27b493c81647caa861e8e95bbbb789b2ce7bdf7bf67bc6c` |

Los SHA proceden de la recuperación del 20-10; **no** fueron contrastados de nuevo contra HDF5 en esta auditoría.

## Consultas NASA CMR de solo metadatos

Script reproducible: `qa/replay_tools/v09_imerg34_cmr_metadata_audit.py`. Evidencia JSON final: `qa/evidence/imerg34_cmr_identity_20261020_v2.json` (con fecha/hora, URL, SHA-256 del cuerpo, recuento CMR-Hits y metadatos).

La primera versión de la consulta de nombre devolvía HTTP 400 por falta del filtro de colección. Queda archivada en `qa/evidence/imerg34_cmr_identity_20261020.json`. La segunda emplea los parámetros documentados de NASA `short_name=GPM_3IMERGHHE&version=07&producer_granule_id[]=...`.

**En los dos casos, cada una de las tres búsquedas completas resultó HTTP 200 y CMR-Hits concordante:**

1. `concept_id=<G histórico>`: **0 coincidencias**.
2. Nombre original exacto, acotado a `GPM_3IMERGHHE` versión `07`: **0 coincidencias**.
3. Ventana temporal del mismo producto y versión: **2 registros vecinos**, sin el intervalo investigado.

| Hora buscada | Registro anterior en CMR | `updated` anterior | Registro posterior | `updated` posterior |
|---|---|---|---|---|
| 16-10 13:00 UTC | 12:30, `G4372394651-GES_DISC` | 2026-10-16 17:24:03 UTC | 13:30, `G4373829349-GES_DISC` | 2026-10-16 18:24:04 UTC |
| 16-10 23:30 UTC | 23:00, `G4373235926-GES_DISC` | 2026-10-17 04:24:29 UTC | 17-10 00:00, `G4373723737-GES_DISC` | 2026-10-17 05:24:43 UTC |

Los cuatro vecinos son `GPM_3IMERGHHE.07` / `V07C`. No existe valor `updated` actual para los dos originales porque sus registros no fueron encontrados. Las fechas de los vecinos **no son** fechas de actualización de los archivos faltantes.

## Interpretación permitida

- Los dos gránulos estuvieron disponibles y se descargaron en la recuperación anterior, pero **no figuran en el catálogo CMR durante estas consultas**.
- El catálogo no permite distinguir con esta evidencia entre desindexación, retiro, cambio de visibilidad o incidencia temporal. No hay prueba de borrado ni de sustitución.
- **No se reemplazaron** por los registros vecinos ni se infirió precipitación.
- El estado científico de la muestra sigue `PARTIAL_CATALOG_UNAVAILABLE`; se mantienen 2/4 HDF5 reproducidos y 44/44 resultados de zona coincidentes para esos dos.
- `UNRECOVERABLE` no se asigna; no hay retención garantizada verificada.
- Los 34 resultados recuperados y su auditoría estructural siguen archivados en la rama documental de #397; el motor, visor y sistema de alertas no los consumen.

## Decisión pendiente

No procede dar por cerrado el control científico de los 34 gránulos. Un paso posible, sujeto a revisión, sería investigar el historial de revisiones o registros eliminados de CMR y buscar evidencia institucional sobre esos dos gránulos, **sin acceso operativo ni nuevas descargas meteorológicas**.

Documento de API NASA CMR: https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html .
