# IRFEN — coastal evidence gates, 2026-11-08

**RESEARCH_ONLY / TEST_ONLY.** No merge, publication, alert, semáforo or deployment.

## Coverage
Exactly 11 departments: Tumbes, Piura, Lambayeque, La Libertad, Áncash,
Lima, Callao, Ica, Arequipa, Moquegua, Tacna. Relevant foreign headwaters
belong to their Pacific-draining catchments. Amazonian/Titicaca basins excluded.
Administrative coast mask is a **display clipping constraint**, not a substitute
for full upstream hydrological catchment geometry.

## SILVIA
User-provided 2026-11-04 national shapefile inventory: 771 polygons, 2 invalid,
NIVEL codes 2/3/4; SHA256 `0bb60908160eb9931341140f4c13cf9eb5afe7b336f0b4b7dbf017ed7f092d33`.
The code audits metadata ONLY. It does not invent an official mask, level
legend, license or geometry repair; does not copy the ZIP; never renders polygons.
Before enabling a separate private overlay: obtain official full 11-department
boundary dataset, provenance/license/CRS/date/hash; confirm all 11 geometries,
clip national SILVIA, repair 2 invalid geometries with QA, validate intersection
areas and no out-of-mask fragments, and review redistribution terms.
Susceptibility != observed mass movement != river overflow.

## Forecast
All 1/3/6/12/24 h horizons remain NO_EVALUABLE without independent
time-stamped observed flow/level and event labels, available-at-issue timestamps,
persistence baseline, held-out events, errors, false positives and effective lead.
IMERG/GOES are context, not independent hydrometric truth. TENDHIS/PISCO are
historical climate context, not hourly predictions. PHISIS/Observatorio ingestion
requires a verified authorized access path. No automated scraping.

## P0 #496
The reported Tumbes 04–05 Nov station totals cannot be divided by IRFEN basin
means. Pixel-vs-station comparisons require NASA V07 Early original HDF5 and
official SENAMHI source with coordinates, QC and identical time windows.
No global factor or accuracy claim. See draft #497 and #498.

Run: `python -m unittest discover -s tests -p 'test_v09_coast_evidence_gates.py' -v`.
This document records requirements, not completed scientific validation.
