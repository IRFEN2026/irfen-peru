# ISAAC Pedregal — manual capture sessions v0.1

Status: **NON_SCIENTIFIC_PROCEDURE_VALIDATION / TEST_ONLY**.

This directory preserves two reproducible manual-capture sessions for the SENAMHI ISAAC `Pedregal Koica` procedure. The files validate the capture, integrity, manifest and validator workflow only. They are **not accepted scientific rainfall observations**, do not form rain–outcome pairs, and must not feed EVENT/NONE classification, scorecard credit, threshold calibration, IMERG bias correction, production use or operational alerting.

## Canonical guard state

- reproducible sessions: 2
- accepted scientific observations: 0
- accepted rain–outcome pairs: 0
- EVENT: 0
- NONE: 0
- `rainfall_candidate=false`
- `scientific_observation_accepted=false`
- `outcome_label=null`
- `automatic_outcome_classification=false`
- `automatic_bias_correction=false`
- `bias_correction_applied=false`
- `threshold_changes=false`
- `production_use=false`
- `production_ready=false`
- `operational_alerting_enabled=false`
- `missing_data_rule=UNKNOWN_NOT_ZERO`

## Persistent limitations

Both sessions show the dashboard update header `02/06/2026 07:00 PM`, so the captures demonstrate procedure/interface reproducibility, not a fresh August 2026 observation. Both tooltip captures show `Promedio de Precip = 0,43` together with `Resaltado = 0,30`; neither value is scientifically accepted. ISAAC's displayed timestamp timezone, exact hourly-window semantics and observation-level QA/QC remain unknown. `Normal` and `Operativo` are station context, not reading QA/QC.

Session `isaac-pedregal-20260823-0425` uses operator-declared capture times and timezone. Session `isaac-pedregal-20260823-031147Z` uses `FILE_MTIME` as technical file metadata only; operator identity, operator-declared local capture time and timezone were not provided. The individual schema v0.1 requires non-empty `capture.operator` and time fields, so the second session records `UNKNOWN_NOT_PROVIDED` and a clearly labeled FILE_MTIME UTC technical value while keeping the semantic session-level operator metadata null.

The original PNG bytes are preserved byte-for-byte under standardized repository names. Name mappings are recorded in each session manifest.
