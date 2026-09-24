# North Peru Sep-2026 forecast/reference experiment

Status: **RESEARCH_ONLY / TEST_ONLY**. This package cannot alter v0.7.1,
activate Phase-2 candidates, set thresholds, infer hydraulic capacity or issue
operational alerts.

## Scientific purpose

The package isolates the Piura/Tumbes rainfall episode of 23-25 September 2026
from the legacy three-pilot daily GEOS-IMERG verification. It provides a separate
append-only lane for forecast-versus-reference comparisons without claiming that
rainfall verifies huaico activation or river overflow.

The official CENEPRED SIGRID scenario for 23-24 September 2026 explicitly cites
SENAMHI Aviso 376 and lists Cajamarca, La Libertad, Lambayeque, Piura and Tumbes.
That official derivative is recorded as provenance context only. Exact original
SENAMHI notice bytes and exact issue timestamp remain unresolved until they are
frozen from the primary source. Social captures and previously mentioned values
for Pananga, Chulucanas, Morropón and Santo Domingo are excluded from numeric
evidence until a primary report with interval, date and units is frozen.

## Separation from legacy data

- `site/data/latest.json` is a historical DEMO artifact and is prohibited.
- `site/data/forecast/latest.json` is mutable and is not a historical cycle file.
- `generated_at` from IRFEN is not model `issue_time`.
- Existing `imerg_verification_history.json` is a daily ledger for three legacy
  pilots; it does not validate subdaily northern units.
- This package does not change the protected v0.8 verification/scorecard path.

## Frozen forecast contract

A GEOS record is admissible only after a cycle-specific immutable source payload
is frozen and the record includes model/version, cycle ID, retrieved time,
verified issue time (or explicit unresolved state), exact valid bounds, mm
accumulation, native/documented spatial support, sampling method, source-payload
SHA-256 and record SHA-256.

Only 1 h, 3 h, 6 h, 12 h and 24 h GEOS accumulations are pairable. The current
GEOS hourly product is never presented as a native 30-minute forecast.

A forecast is *prospective* for a window only when its independently verified
model issue time is at or before that window start. A genuine historical
forecast recovered later may be analyzed retrospectively, but does not become
prior anticipation by using retrieval time or IRFEN `generated_at`.

## Observed-reference contract

Reference classes remain separate:

- SENAMHI station: point reference with representativeness limitations.
- IMERG Early.
- IMERG Late.
- GOES-19 RRQPE.

Satellite comparisons are product discrepancies, not ground truth. Daily values
cannot be divided into subdaily values. Rates require explicit time bounds and
integration interval. Incomplete windows, mixed-source accumulations and silent
coarse-to-fine interpolation are rejected.

Revisions are append-only and retain independent record hashes. A dry measured
period remains a rainfall observation; it is never a negative activation control.

## Pairing and metrics

Pairs require the same valid start, valid end, duration and preregistered
comparison support. Signed error is `forecast - observed`; positive means
overestimate. Percent error is reported only for observed accumulation at least
0.1 mm. The denominator rule is preregistered in the contract.

Bias, MAE and RMSE are grouped by comparison support, reference source, duration,
lead bucket and model version. Counts include periods and unique episodes, and
the output flags overlapping windows because they are not independent samples.
Dry-zero hits do not establish skill for rainfall extremes.

## Current safe state

The two new ledgers are intentionally empty until admissible source bytes arrive.
This is a scientific state, not a data failure: missing evidence remains
`UNKNOWN_NOT_LOW_RISK`. The generator therefore cannot manufacture a
forecast/reference row from mutable latest data, unresolved issue times, names,
social captures, city centroids or approximate hydrologic geometry.
