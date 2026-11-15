# IRFEN — precipitation shadow calibration (research only)

Scope: 11 coastal departments Tumbes–Tacna; relevant foreign headwaters only.
No Amazonian/Titicaca expansion. No merge, deployment, alert or threshold change.

## P0 #496 gate
The 4–5 Nov 2026 SENAMHI values reported by media are **not** independently
verified station records. The basin-average IMERG values are **not** station pixels.
Therefore no observational pairs may be fabricated from those figures.
Await authorized SENAMHI station records (IDs, coordinates, QC, time window)
and original NASA V07 IMERG Early half-hourly HDF5. Audit #497 first.

## Shadow protocol
1. Extract collocated station-pixel accumulations with matched windows and verified
   granule completeness, units, SHA256, availability and QC. Keep raw data immutable.
2. Use distinct meteorological events as holdout units; never split a storm across
   training and test. The example module uses leave-one-event-out, a **diagnostic**
   rather than prospective evidence. Evaluate separately by coastal department
   once adequate independent event counts exist; no northern factor transfer.
3. Report raw vs shadow MAE, RMSE and bias; negative improvement is a failure.
   Correlation, event detection, false alarms, uncertainty intervals and prospective
   lead time require more events and independent observations; do not claim them.
4. Realtime shadow corrections must only use records actually available at
   snapshot freeze time. A historical verification result cannot be used to
   generate an earlier forecast. Rainfall estimation != river discharge forecast.
5. Missing source, incomplete window, station ID/coordinate mismatch, missing
   quality verification, or insufficient independent events => NO_EVALUABLE.

Run synthetic tests: `python -m unittest discover -s tests -p 'test_v09_precip_bias_shadow.py'`.
Run evaluator: `python scripts/v09_precip_bias_shadow.py verified_pairs.json`.
This branch contains no real station pairs, no calibrated multiplier, no model
performance claim, and no change to operational visor or semaphores.
