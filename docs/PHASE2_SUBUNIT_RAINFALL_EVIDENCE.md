# Claude G — Phase-2 Subunit Rainfall Evidence v0.1

**Status:** `RESEARCH_ONLY / TEST_ONLY`.

Claude G accelerates rainfall acquisition for four hydrologic research units authorized by Claude F:

- `cashahuacra`
- `shingolay`
- `lambayeque_chancay_lambayeque_chongoyape`
- `lambayeque_zana_oyotun`

Cashahuacra and Shingolay remain local research subunits of
`lima_este_santa_eulalia_rimac`.

The Lambayeque units are official whole ANA hydrologic units (13776 and
137754) retained under the historical non-activable grouper
`lambayeque_chongoyape_oyotun_zana`. Their rainfall is basin-scale context,
not rainfall for a named local quebrada or event footprint.

## Two observation tracks

### IMERG Early — fast track

The existing `imerg-early-probe.yml` runs at minutes **18 and 48 of every hour**.

Claude G adds the Phase-2 research subunits to the same GPM `GPM_3IMERGHHE V07` half-hourly sampling pass. The v0.8 core targets remain unchanged; Phase-2 subunits are dynamically added only to the current research continuity contract.

Rolling windows:

- 1 h
- 3 h
- 6 h
- 12 h
- 24 h

A window is published only when the required 30-minute samples are continuous. Missing samples produce `INSUFFICIENT_EVIDENCE`, never zero rainfall.

When recent archived granules do not yet contain the new subunit targets, the probe temporarily increases its bounded download cap from 4 to 8 granules per run. It automatically returns to normal mode once the backlog is repaired.

### IMERG Late Daily — accumulated context

The same 30-minute workflow calls a second collector for `GPM_3IMERGDL`.

It refreshes at most every 6 hours and initially requests enough daily history to calculate:

- 24 h
- 72 h
- 7 d

A daily value is normalized only if all IMERG cells intersecting the research polygon have finite data and collectively cover the geometry. Partial spatial data are retained only as a non-decisional diagnostic.

A multi-day window is available only when every required consecutive date is present.

## Shared geometry resolver

Both Early and Late use `scripts/phase2_subunit_sampling.py`, which resolves all eligible research targets directly from:

`site/data/phase2/spatial_observation_contracts_v0_1.json`

This avoids hard-coding the geometry twice. Future subunits that pass the Claude F contract can enter both rainfall pipelines through the same resolver.

## Consolidated artifact

`site/data/phase2/subunit_rainfall_evidence_v0_1.json`

keeps Early and Late evidence separate. It does not merge them into a score.

The artifact contains no:

- activation score;
- risk score;
- alert score;
- rainfall threshold;
- promotion decision;
- candidate-wide rainfall claim.

## Scientific boundary

Observed rainfall is evidence of rainfall only.

It is **not**, by itself, evidence that a quebrada activated, that debris flow occurred, that hydraulic capacity was exceeded, or that an alert should be issued.

All Phase-2 activation gates remain `BLOCKED`.

## Lambayeque semantics

For ANA 13776 and 137754, a valid IMERG value means area-weighted satellite rainfall over the entire official hydrologic unit. It must not be downscaled by interpretation into Juana Ríos, Cuculí, Río Yaipón, Río Nanchoc or any other local tributary without a separate spatial contract.
