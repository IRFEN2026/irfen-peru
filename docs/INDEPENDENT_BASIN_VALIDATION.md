# IRFEN Independent Basin Validation Framework — Phase A

**Status:** `RESEARCH_ONLY` · `TEST_ONLY` · `production_use=false` · `production_ready=false` · `operational_alerting_enabled=false`.

This track is isolated from v0.8 closeout. It does not alter the v0.8 scorecard, RC, release, thresholds, bias correction, pilot decisions, canonical `EVENT/NONE`, or operational geometry.

## Phase-A selection

Current `main` materializes two local research features that can be investigated without inventing new basin polygons:

- **Cashahuacra** — Copernicus GLO-30/D8 catchment candidate, 15.088 km², `MEDIUM_CANDIDATE`; outlet and area are not officially confirmed.
- **Shingolay** — existing `REVIEW_ONLY`/low-confidence candidate; fail closed if hydrologic geometry or exact event dating cannot be defended.

Santa Eulalia and Rímac features in the same W1 file are faja/territorial geometries, not basin polygons. Chillón, Lurín, Punta Hermosa/Malanche, Mala and Cañete remain blocked for this framework until a defensible hydrologic basin geometry is materialized and reviewed.

## Data availability

- **IMERG V07:** half-hourly global precipitation; official V07 period of record begins June 2000. The requested 1998–May 2000 interval is an explicit coverage gap.
- **SMAP Enhanced L3, SPL3SMP_E V6:** daily surface soil moisture, 9 km, 31 March 2015–present. For small ravines it is regional antecedent context, not basin truth.
- **Sentinel-1:** operational/open archive from October 2014; preferred pre/post SAR source.
- **Sentinel-2:** optical support from 2015, with systematic supply from December 2015; cloud/QA screening is mandatory.
- **Copernicus DEM GLO-30:** global 30 m DSM; vegetation/buildings, fill masks and release must be retained as limitations/provenance.

## Evidence and labels

The E0–E6 chain is encoded in the contract. E0–E4 remain research-only. Target-basin records keep `training_target=null` unless a future documented human research adjudication makes them eligible. The framework never writes canonical v0.8 `EVENT`/`NONE`.

Cashahuacra has a strong exact-date territorial positive for **23 March 2015**: DS 019-2015-PCM states that intense rainfall activated the quebrada and generated huaicos affecting homes and roads. Shingolay currently has official RPAS/orthomosaic context but no exact-date activation established from the verified source, so it remains `INSUFFICIENT_EVIDENCE`.

## First experiment

The executable model is deliberately a **pipeline smoke experiment**, not a scientific performance claim. It uses three already-versioned San Ildefonso reference cases and their 3 h, 6 h and 24 h IMERG values with L2 logistic regression and leave-one-out evaluation. It neither retrains nor reinterprets v0.8; `research_target` is internal to this experiment.

With only three samples, one basin, and differing infrastructure phases, metrics are non-inferential. Current output: ROC-AUC 0.0, PR-AUC 0.5833, Brier 0.4354, sensitivity 0.5, specificity 0.0, one false negative and one false positive. This poor out-of-sample smoke result is itself a guard against premature Phase-B expansion.

## Required next acquisition before Phase B

1. Version exact IMERG V07 Final granules for event/control windows with granule IDs and checksums.
2. Version SMAP SPL3SMP_E V6 files for ±7 days where available, preserving QA flags and pixel/basin support.
3. Query Sentinel-1 GRD same-orbit pre/post pairs and record product IDs, acquisition times, orbit, polarization, processing baseline and checksums.
4. Use Sentinel-2 L2A only when cloud/quality masks permit; missing optical data remains missing.
5. Acquire/version exact Copernicus DEM GLO-30 tiles and masks, then compute morphometrics and the research-only Basin Susceptibility Index.
6. Archive territorial source snapshots/hashes where access and licensing permit.
7. Build defensible negative controls; absence of reports is never a negative.

No missing layer is interpreted as zero and no automatic classifier can create a scientific `EVENT`/`NONE`.
