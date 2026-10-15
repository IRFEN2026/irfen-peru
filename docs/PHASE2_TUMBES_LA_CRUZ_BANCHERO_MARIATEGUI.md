# La Cruz (Tumbes): quebradas Banchero, Mariátegui y Banchero Rossi — inventario r7

RESEARCH_ONLY · TEST_ONLY · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `activation_gate=BLOCKED` · `missing_data_rule=UNKNOWN_NOT_LOW_RISK` · `decision_thresholds=null` · `hydraulic_factors=null`

Registro: `config/phase2_tumbes_la_cruz_banchero_mariategui_v0_1.json` · validador: `scripts/validate_phase2_tumbes_la_cruz_banchero_mariategui.py` · pruebas: `tests/test_phase2_tumbes_la_cruz_banchero_mariategui.py`.

## Corrección

Supersedes the 15-10 executive report statement that no official source named Banchero, Banchero Rossi or Mariátegui as quebradas: that search had not read INDECI RC 1951 (2024), the MVCS 2021 note or MD La Cruz R.A. 128-2023. PR #378's verdict NOT_A_QUEBRADA_IN_SOURCES_READ remains correct for the sources it read (INDECI RC 3755-2025 lists 'Banchero Rossi' among cleaned streets; ANA 2016 Piura names the settlement 'AH José Carlos Mariátegui').

## Fuentes archivadas (capturadas en el runner de GitHub, fuera de `site/`)

| Id | Documento | Fecha | SHA-256 |
|---|---|---|---|
| `INDECI-RC-1951-2024-TUMBES` | Reporte Complementario N.° 1951 - 27/2/2024 / COEN-INDECI / 15:30 horas (Reporte N.° 3): Lluvias intensas en el departamento de Tumbes | 2024-02-27 | `2fa3621f0b7c13456c277d65f5393c1c8a372c2ac5d9f7bf9e2dc18eb80fa005` |
| `MVCS-NOTA-569204-2021` | Tumbes: Ministerio de Vivienda inicia limpieza y descolmatación de la quebrada Banchero Rossi (nota de prensa) | 2021-12-11 | `bd4861084f5a9747a3db6876c6ed72f8902db3efe6516023caa1b63396aa03c7` |
| `MDLC-RA-128-2023` | Resolución de Alcaldía N.° 128-2023/MDLC-ALC | 2023-04-05 | `49cf55092c5e0cc451586aedbf978fd7b0049ad46effa41139b125cbdf1b264e` |
| `MDLC-RA-128-2023` (PDF escaneado) | https://cdn.www.gob.pe/uploads/document/file/5276927/4742023-resolucion-de-alcaldia-128-2023.pdf?v=1697216421 | 2023-04-05 | `98032fcfcd1bd316993e3e6d9ad4c3b5af9217fcd3366e105bc6e46b45f6d373` |

## Texto exacto

- **INDECI, RC N.° 1951, 1. HECHOS, Distrito de La Cruz, 11/01/2024, 22:00 h:** «Inundación y huaico por la activación de las quebradas Banchero y Mariátegui, ocasionando daños a la infraestructura de transporte en la calle Banchero, sector Mariátegui y calle Palmeras.» (en el PDF, la columna de fecha y hora está intercalada con la descripción).
- **MVCS, nota de prensa del 11/12/2021:** «Tumbes: Ministerio de Vivienda inicia limpieza y descolmatación de la quebrada Banchero Rossi» … «inició los trabajos de limpieza y descolmatación de la quebrada Banchero Rossi, en el distrito de La Cruz, en la provincia y región de Tumbes.» Es una obra preventiva y no menciona ningún evento.
- **MD La Cruz, R.A. N.° 128-2023/MDLC-ALC, 05/04/2023:** aprueba el expediente técnico de la «ACTIVIDAD DE EMERGENCIA "LIMPIEZA Y DESCOLMATACION DEL CAUCE DE LA QUEBRADA LUIS BANCHERO ROSSI DEL DISTRITO DE LA CRUZ, PROVINCIA DE TUMBES, DEPARTAMENTO DE TUMBES"». La cita se comprueba sobre la ficha oficial de gob.pe. El PDF es un escaneo sin capa de texto y se leyó visualmente.

## Filas del inventario (r7)

| Fila | Identidad | Evento | Estado | Geometría · outlet |
|---|---|---|---|---|
| `tumbes_la_cruz_banchero` | INDECI RC 1951 (quebrada) | pista 11/01/2024 (INDECI), sin verificar | `EVENT_LEAD_UNVERIFIED` · P2 | desconocidos |
| `tumbes_la_cruz_mariategui` | INDECI RC 1951 (quebrada) | pista 11/01/2024 (INDECI), sin verificar | `EVENT_LEAD_UNVERIFIED` · P2 | desconocidos |
| `tumbes_la_cruz_banchero_rossi` (variante «Luis Banchero Rossi») | MVCS 2021 y R.A. 128-2023 (obras) | ninguno | `IDENTITY_ONLY` · P3 | desconocidos |

## Lo que no se afirma

- Banchero / Banchero Rossi: **UNRESOLVED**. Different sources and labels; no georeferenced evidence that they are the same channel.
- Banchero (quebrada) / calle Banchero: **DIFFERENT_FEATURES**. INDECI names both; the street is damaged infrastructure, not the channel.
- Mariátegui (quebrada, La Cruz, Tumbes) / AH José Carlos Mariátegui (Sullana, Piura): **NOT_EQUIVALENT**. Different department; the Piura source names a settlement.
- Banchero Rossi (quebrada) / Banchero Rossi in INDECI RC 3755-2025 street list: **UNRESOLVED**. RC 3755 (PR #364 archive) lists 'Calles, Palmeras, Banchero Rossi' as cleaned roads; not used as channel evidence here.

## Bloqueos

- Geometry and outlet UNKNOWN for all three: no source gives coordinates, length or confluence.
- EVENT_EVIDENCE not assigned: the INDECI text is archived and quote-tested but promotion requires independent QA (verification_record).
- R.A. 128-2023 PDF is a scan without text layer: its content was reviewed visually; OCR (Spanish) was not available in the review environment.

