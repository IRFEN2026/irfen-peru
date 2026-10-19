# Inventario maestro r6 — regiones activas (ANA DU 015-2023 Anexo II/III) y vínculo de Huarangal

RESEARCH_ONLY · TEST_ONLY · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false` · `activation_gate=BLOCKED` · `missing_data_rule=UNKNOWN_NOT_LOW_RISK` · `decision_thresholds=null` · `hydraulic_factors=null`

Registro: `config/phase2_inventory_r6_active_regions_du015_v0_1.json` · validador: `scripts/validate_phase2_inventory_r6_active_regions_du015.py` · pruebas: `tests/test_phase2_inventory_r6_active_regions_du015.py`.

## Qué se añade

- **19 filas** en `config/phase2_national_inventory_completeness_audit_v0_1.json` (revisión r6). Todas son `IDENTITY_ONLY`, con `map_eligible=false`, sin geometría, sin outlet o confluencia y sin cuenca padre.
- **Huarangal (Huáncano, Pisco)** es una *fila de vínculo* hacia la unidad que `main` ya registra (`ica_huarangal_pisco`, linaje del PR #313). No se crea una segunda unidad. Sus homónimos se mantienen separados: `lima_mala_huarangal` y `arequipa_huarangal`.
- **Catambo (Parcona, Ica)** es también una fila de vínculo, hacia `ica_catambo` en `main`.
- Las fuentes son ANA DU 015-2023: el Anexo II (puntos críticos para limpieza y descolmatación) y el Anexo III (quebradas a ser intervenidas). Son copias byte a byte del archivo del PR #364, en `data/phase2/source_archive/ana_du015_2023/`, con estos SHA-256:
  - ANA-DU-015-2023-ANEXO-II: `c00095672208cb0afbd368aa02fe8172c2661d0df629385fb91b9f464db883b9`
  - ANA-DU-015-2023-ANEXO-III: `5963b140cd49b8ee6599044ab094e7a511a77d5ad0d9efdebcad35f633ac1cad`
- Cada cita es una línea de la capa de texto archivada, y el validador la vuelve a leer. Los números Este/Norte del Anexo III se copian solo como `source_reference_point` (la fuente no imprime datum ni zona): no son outlet ni geometría.

## Filas r6

| Fila | Nombre documental | Distrito · provincia | Corredor | Evidencia | En IRFEN | Prio. | Fuente (fila) |
|---|---|---|---|---|---|---|---|
| `lima_chaclacayo_u3_y_p_p1` | U3 y P-P1 | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.6 |
| `lima_chaclacayo_huascata` | Huascata | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.7 |
| `lima_chaclacayo_panorama` | Panorama | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.8 |
| `lima_lurigancho_caraponguillo` | Caraponguillo | Lurigancho-Chosica · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.9 |
| `lima_chaclacayo_condores_2` | Condores 2 | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.11 |
| `lima_chaclacayo_condores_1` | Condores 1 | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.13 |
| `lima_chaclacayo_ines_1` | Ines 1 | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.14 |
| `lima_lurigancho_nana` | Ñaña | Lurigancho-Chosica · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.15 |
| `lima_lurigancho_laguna` | Laguna | Lurigancho-Chosica · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.16 |
| `lima_lurigancho_milagros` | Milagros | Lurigancho-Chosica · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.19 |
| `lima_chaclacayo_ines_2` | Ines 2 | Chaclacayo · Lima | CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA | WORKS | no está | P2 | ANEXO-III f.22 |
| `ica_parcona_catambo` | Catambo | Parcona · Ica | PISCO_ICA | CRITICAL_POINT | main: unidad registrada `ica_catambo` | EXISTING | ANEXO-II f.73 |
| `ica_salas_rio_seco` | Rio Seco | Salas · Ica | PISCO_ICA | CRITICAL_POINT | solo rama/PR (#366), sin confirmar | P3 | ANEXO-II f.75; ANEXO-II f.76; ANEXO-II f.77 |
| `ica_llipata_rio_seco` | Rio Seco | Llipata · Palpa | PISCO_ICA | CRITICAL_POINT | no está | P3 | ANEXO-II f.78 |
| `ica_llipata_piedras_gordas` | Piedras Gordas | Llipata · Palpa | PISCO_ICA | CRITICAL_POINT | main: nombrada como quebrada | P3 | ANEXO-II f.79 |
| `ica_grocio_prado_topara` | Topara | Grocio Prado · Chincha | PISCO_ICA | CRITICAL_POINT | main: nombre como contexto (cuenca) | P3 | ANEXO-II f.80 |
| `ancash_yautan_bombon_poctao` | Bombon-Poctao | Yaután · Casma | SANTA_CASMA | CRITICAL_POINT | no está | P3 | ANEXO-II f.89 |
| `ancash_pampas_grande_sen_sen` | Sen Sen | Pampas Grande · Huaraz | ANCASH_INTERIOR | CRITICAL_POINT | no está | P4 | ANEXO-II f.88 |
| `ica_huancano_huarangal` | Huarangal | Huancano · Pisco | PISCO_ICA | IDENTITY | main: unidad registrada `ica_huarangal_pisco` | EXISTING | ANA-PISCO-HUARANGAL-RA060-2018 |

## Filas de la fuente que ya estaban en el inventario (sin cambios)

ANEXO-II f.74 → `ica_tinguina_cansas`, ANEXO-II f.81 → `ica_huancano_quitasol`, ANEXO-II f.82 → `ica_huancano_paracas`, ANEXO-II f.90 → `ancash_yautan_tomeque`, ANEXO-III f.1 → `lima_lurigancho_la_ronda`, ANEXO-III f.2 → `lima_lurigancho_quirio`, ANEXO-III f.3 → `lima_santa_eulalia_cashahuacra`, ANEXO-III f.4 → `ica_palpa_saramarca`, ANEXO-III f.5 → `lima_cieneguilla_rio_seco`, ANEXO-III f.10 → `lima_chaclacayo_huascaran`, ANEXO-III f.12 → `lima_chaclacayo_cusipata`, ANEXO-III f.17 → `lima_lurigancho_chacrasana`, ANEXO-III f.18 → `lima_lurigancho_yanacoto`, ANEXO-III f.20 → `lima_ricardo_palma_cupiche`, ANEXO-III f.21 → `lima_santa_eulalia_huayaringa`.

## Correcciones al ledger de revisión #378

- `rev20261014_a2_ica_la_tinguina_cansas`: Anexo II fila 74 names Qda. Cansas in La Tinguiña (Ica), the district of the existing row ica_tinguina_cansas (main unit ica_cansas). No new row; existing row unchanged.
- `rev20261014_a2_ica_salas_rio_seco`: Filas 75, 76 and 77 all name Qda. Rio Seco in Salas (sectors Villacuri 1/2/3); one row ica_salas_rio_seco carries all three.
- `rev20261014_a2_ica_parcona_catambo`: main registers the unit ica_catambo; the master row is a link row (priority EXISTING), not a new unit.

## Bloqueos reales

- Geometry, outlet and confluence: UNKNOWN for every row; Anexo III coordinates are source-printed reference numbers (datum/zone not printed), not outlets or geometry.
- Equivalences UNRESOLVED (curated_relationships, added_in_revision r6): Condores 1/2 vs Los Cóndores; Milagros vs Señor de los Milagros; Ines 1 vs Ines 2; Huascata vs U3 y P-P1.
- Source text not promoted: source_text_verified stays false on every source; promotion is left to independent QA.
- **Huarangal**: la fuente (R.A. 060-2018-ANA-AAA.CHCH-ALA.P) **no se pudo archivar**. La URL oficial agotó el tiempo de espera 3 veces desde el runner y el Internet Archive no tiene captura (404); el intento queda en `data/phase2/source_archive/pisco_huarangal_ra060_2018/capture_record_v0_1.json`. La fila cita el registro de `main` y no declara SHA-256.
- Topará (Lima, Cañete) y los nombres de Tumbes no se añaden aquí: el primero está fuera de las regiones activas y los segundos los cubre el PR #365 (r3).
- Las etiquetas de revisión r3, r4 y r5 las usan los PR #365, #366 y #363, que aún no están en `main`. Al integrarlos habrá conflictos mecánicos en `summary`, `derived_views` y `sources`. Las fuentes `ANA-DU-015-2023-ANEXO-II/III` coinciden en contenido con las del PR #365, salvo la ruta del archivo.

