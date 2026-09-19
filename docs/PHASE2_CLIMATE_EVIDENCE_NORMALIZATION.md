# Phase-2 Climate Evidence and Normalization Layer (Claude E) — v0.1

Status: RESEARCH_ONLY / TEST_ONLY.

This layer answers a narrower question than Claude D:

What climate and hydrometeorological evidence actually exists, what does each source mean, which temporal windows can be normalized without fabrication, and what may be linked to a Phase-2 candidate?

It does not answer whether a candidate activated, how plausible activation is, or what threshold should be used.

## Scientific boundary

Claude D remains the owner of the Climate-Conditioned Activation Matrix contract. Its current state remains NOT_YET_CALIBRATED; Claude E does not modify that status, emit a plausibility category, or create a score.

Claude E is an evidence and provenance layer only.

## Existing sources normalized

### IMERG Early Phase-2 event reanalysis

site/data/phase2/event_reanalysis.json contains 30-minute event reanalysis windows. A 3 h, 6 h or 24 h accumulation is normalized only when the source marks every required half-hour interval continuous and supplies accum_mm.

Partial coverage is preserved as metadata, but the normalized accumulation remains null.

Candidate linkage requires an exact target_zone_id from the event intake. Geographic similarity, department, free text and proximity are never used.

### IMERG Late durable scientific history

site/data/forecast/imerg_verification_history.json is a durable observed-rainfall ledger for the three v0.8 pilot sampling contracts. It is not Phase-2 candidate rainfall.

Daily observations may support 24 h, 72 h and 7 d accumulation mechanics only after a new exact Phase-2 spatial contract exists. Daily data can never fabricate 1 h, 3 h, 6 h or 12 h rainfall.

### GOES-19 RRQPE

site/data/calibration/goes19_rrqpe_archive.json currently preserves source availability and freshness metadata. Its committed records do not preserve candidate-level precipitation values.

Therefore Claude E records GOES as SOURCE_AVAILABILITY_METADATA and does not convert availability into rainfall.

### GEOS-CF

site/data/forecast/historical_daily.json contains historical daily forecast records used for v0.8 verification. GEOS is forecast evidence, not observation evidence.

It may eventually be paired with exact Phase-2 observations for forecast verification, but it is not converted into observed rainfall and cannot validate activation.

## Normalization rules

- All assessment timestamps use UTC.
- Accumulated precipitation is represented in mm.
- Rates, when available in a future source contract, use mm/h.
- Missing data is UNKNOWN, never zero and never low risk.
- Partial temporal coverage never produces a normalized accumulation.
- Cross-zone transfer is forbidden.
- Exact candidate IDs are required for linkage.
- Forecasts are never relabeled as observations.
- Source availability is never relabeled as precipitation.
- Candidate-specific climatological percentiles and anomalies require a cited baseline; none is committed today for the 18 Phase-2 candidates.
- Antecedent-state thresholds DRY, NORMAL, WET and VERY_WET remain unresolved. Claude E may normalize 24 h, 72 h and 7 d accumulations in the future, but it does not turn those sums into wetness states without a separately reviewed methodology.

## Current result

The layer intentionally leaves all eight candidate rainfall windows at INSUFFICIENT_EVIDENCE because there is no explicit current or live assessment context and no exact candidate-linked observation contract suitable for those fields today.

The current Phase-2 event-reanalysis records are retained as event evidence. Their exact candidate linkage remains fail-closed: an event with no registered target_zone_id is not assigned to a candidate.

This is useful progress: the absence of candidate values is now machine-readable and scientifically explained rather than silently conflated with zero rain.

## Antecedent accumulation helper

The builder includes a pure normalization helper for 24 h, 72 h and 7 d daily sums. It returns a value only when every required consecutive day exists exactly once and contains a non-negative observation.

The helper does not classify wetness and does not define thresholds.

## Relationship to future work

A later stage may:

1. establish exact Phase-2 spatial sampling contracts;
2. persist candidate-level IMERG or GOES observation series;
3. add cited climatological baselines;
4. normalize complete antecedent 24 h, 72 h and 7 d histories;
5. independently validate forecast-observation pairing.

Only after those evidence contracts exist should a separate calibration stage consider moving Claude D beyond NOT_YET_CALIBRATED.

## Operational boundary

This layer never:

- opens an activation gate;
- sets a promotion gate;
- creates an alert;
- creates an activation, risk or plausibility score;
- infers thresholds;
- changes the 18-candidate Phase-2 scope;
- changes v0.8 pilots;
- treats missing evidence as low risk.
