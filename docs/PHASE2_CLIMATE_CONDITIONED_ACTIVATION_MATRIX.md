# Phase-2 Climate-Conditioned Activation Matrix (v0.1)

**Status:** `RESEARCH_ONLY` / `TEST_ONLY`. `production_use=false`,
`production_ready=false`, `operational_alerting_enabled=false`,
`decision_thresholds=null`, `activation_gate=BLOCKED`.

> Climate-Conditioned Activation Matrix is a research framework and must not
> be interpreted as an operational activation, warning, emergency trigger, or
> production decision system.

## Purpose

IRFEN's Phase-2 zone contracts and case validations answer "did this system
activate" for specific, bounded historical events. They do not yet answer a
different, prior scientific question: **under which combination of rainfall,
antecedent-moisture, persistence, seasonal and large-scale-climate
conditions would a hydrologic response be more or less physically plausible
for a given candidate** — independent of whether that combination has ever
actually occurred and been observed.

This matrix is a reproducible, auditable structure for that question. It
produces a `physical_plausibility_assessment` category per candidate, never
an `ACTIVATED = TRUE` verdict, and it is built to fail closed: any
conditioning dimension without a verifiable, mechanically-derived value is
`INSUFFICIENT_EVIDENCE` / `UNKNOWN`, never guessed.

## Inputs

- `config/phase2_candidate_inventory_v0_2.json` — the 18 registered Phase-2
  candidates (read-only; never modified, never re-counted).
- `site/data/validation/phase2_zone_contracts/*.json` — for each candidate's
  `assets.geometry.path`, to check real file presence (via
  `scripts/build_phase2_catalog.py`'s `data_presence`), never to alter the
  contract.
- `site/data/validation/phase2_case_validations/*.json` — linked
  mechanically (exact `zone_id` or asset-`path` match) using the exact same
  linkage helpers PR-C built and tested for `asset_readiness`
  (`load_case_validations` / `resolve_linked_case_validation` in
  `scripts/build_phase2_catalog.py`, imported rather than duplicated).
- `config/phase2_climate_conditioned_research_priority_v0_1.json` — the
  existing scenario-corridor overlay, reused **only** as qualitative regional
  context (`large_scale_climate_context.source`), never as a numeric
  ENSO/SST index and never as an activation input.
- No new external network dependency is introduced. IMERG/GOES/GEOS-CF
  access already exists elsewhere in the repository (e.g.
  `scripts/fetch_imerg.py`, `scripts/verify_geos_against_imerg.py`) but is
  not wired into Phase-2 candidates today; see Limitations.

## Conditioning variables

Per candidate, per generation:

| Dimension | Representation | Current state on the 18 candidates |
|---|---|---|
| Rainfall | 8 windows (1h/3h/6h/12h/24h/48h/72h/7d), each with `accumulated_mm`, `max_mm`, `intensity_mm_per_hr`, `climatological_percentile`, `anomaly_mm` and a typed `observations[]` list (`source`, `station`, `observation_type`, `spatial_relation`, `event_pairing`, `transfer_validated`) | `INSUFFICIENT_EVIDENCE` for all windows, all 18 candidates — no committed, source-attributed rainfall series is wired per candidate yet |
| Antecedent moisture | `DRY`/`NORMAL`/`WET`/`VERY_WET`/`UNKNOWN` | `UNKNOWN` / `INSUFFICIENT_EVIDENCE` for all 18 |
| Persistence | `NONE`/`SHORT`/`MODERATE`/`PROLONGED`/`UNKNOWN` (documented definitions in the generator) | `UNKNOWN` / `INSUFFICIENT_EVIDENCE` for all 18 |
| Season | `DRY_SEASON`/`TRANSITION`/`WET_SEASON`/`UNKNOWN`, with `date_precision` | `UNKNOWN` / `INSUFFICIENT_EVIDENCE` for all 18 (no live "current date" concept in this non-operational framework; see Limitations) |
| Large-scale climate (ENSO) | `enso_phase` enum, always `is_trigger_alone=false` | `UNKNOWN` / `INSUFFICIENT_EVIDENCE`; `source` cites the scenario-corridor overlay when the candidate is listed in one |
| Physical factors | drainage area, slope, concentration time, drainage density, soil, land cover, imperviousness, geomorphology, known susceptibility, ephemeral channels | All `null`, explicitly listed in `data_gaps`; no candidate has committed numeric catchment characteristics today, and none are inferred |
| Historical evidence | `linked_case_validation`, `link_method`, `documented_realizations[]` (event date, classification, primary source, whether rainfall evidence exists in the case file) | Populated wherever a case validation mechanically links (same linkage as PR-C); values are copied verbatim, never interpreted |
| Uncertainty | `confidence_tier` plus six sub-dimension statuses (temporal coverage, spatial resolution, source agreement, historical-observation availability, geometry quality, meteorological-data quality) | `INSUFFICIENT_EVIDENCE` overall for all 18, with `historical_observation_availability_status` / `geometry_quality_status` promoted to `HISTORICAL_EVIDENCE_ONLY` where real linked evidence exists |

## Scientific position of v0.1

Claude D v0.1 establishes:

- **A. WHAT variables are required** — rainfall (8 windows), antecedent
  moisture, persistence, season, large-scale climate (ENSO), physical
  catchment factors, and historical evidence.
- **B. HOW they must be represented** — the typed, per-dimension shapes
  documented in *Conditioning variables* below, identical for every
  candidate regardless of what data currently exists for it.
- **C. WHAT provenance must accompany them** — `evidence_status`,
  `source`/`observations[]`, and (for historical evidence)
  `linked_case_validation` / `link_method`, on every dimension, always.
- **D. HOW uncertainty and missing data are represented** — explicitly,
  multi-dimensionally, and fail-closed (`INSUFFICIENT_EVIDENCE` / `UNKNOWN`
  is a first-class value, never a fabricated default; see *Uncertainty*
  below).
- **E. HOW the 18 Phase-2 candidates are associated with the framework** —
  one record per candidate, generated from
  `config/phase2_candidate_inventory_v0_2.json` and cross-checked against
  `site/data/phase2/catalog.json`, with the two Lambayeque hydrologic child
  units referenced (never duplicated, never counted) outside the 18-record
  matrix (see *Hydrologic child unit integrity* below).

It does **not** yet assert that the correct mathematical combination of
those variables is scientifically known. That calibration is a subsequent,
separately reviewed stage that requires real historical event/non-event
evidence — not synthetic fixtures. This is an important distinction: v0.1
builds the **Climate-Conditioned Activation Matrix contract and evidence
architecture**. It does not validate a universal **Climate-Conditioned
Activation Function**.

## Methodology

`scripts/build_phase2_climate_matrix.py::compute_physical_plausibility` is
documented and unit-tested, but in v0.1 it is **not a calibrated scoring
function** — it is a fixed, fail-closed placeholder:

1. `methodology.classification_method_status` (root level) and
   `physical_plausibility_assessment.classification_method_status`
   (per-record) are always `NOT_YET_CALIBRATED` in this generator version.
2. Whenever `classification_method_status == NOT_YET_CALIBRATED`, the
   schema (`config/phase2_climate_conditioned_activation_matrix.schema.json`,
   via an `if`/`then` conditional on `$defs.physical_plausibility_assessment`)
   *requires* `category == "INSUFFICIENT_EVIDENCE"` and
   `physical_response_plausibility_score == null` and
   `score_components == null` — this is a schema-level invariant, not just a
   generator convention.
3. `compute_physical_plausibility()` accepts all five conditioning inputs
   (rainfall, antecedent moisture, persistence, season, large-scale climate)
   and records a human-readable audit trail of what was passed in
   (`rationale`), but **no input value — including an extreme rainfall
   percentile, a `VERY_WET` antecedent state, or a strong ENSO phase — can
   change the output.** There is no code path in v0.1 by which any
   combination of inputs produces a differentiated category
   (`VERY_LOW_PLAUSIBILITY` … `VERY_HIGH_PLAUSIBILITY`). This is what makes
   the required guarantee — **ENSO alone can never create or upgrade a
   plausibility category** — true *by construction*, rather than by
   argument about score weights and breakpoints.

A previous revision of this function combined per-dimension weights
(rainfall, antecedent moisture, persistence, season, ENSO) into a numeric
score against documented category breakpoints. That model is **removed** in
this revision: the weights and breakpoints were documented but never
calibrated or validated against real IRFEN historical evidence, and
documenting an arbitrary weighting does not make it scientifically
defensible. It also had a real logical defect — a fixed combination of the
other (undifferentiated) dimension weights could itself sit near a category
breakpoint such that adding the ENSO contribution alone crossed it,
contradicting the "ENSO alone is never a trigger" guarantee the
documentation claimed. Removing the scoring model removes that defect at
the root rather than patching around it.

The categories `VERY_LOW_PLAUSIBILITY` … `VERY_HIGH_PLAUSIBILITY` remain
defined in the schema as **future-allowed values**: a later, separately
reviewed and calibrated methodology stage may populate them from real
historical event/non-event evidence. v0.1 must not, and structurally cannot,
emit them today.

Persistence's conceptual states (`NONE`/`SHORT`/`MODERATE`/`PROLONGED`) are
retained, but their **quantitative day-count boundaries are `UNRESOLVED`** —
no cited, IRFEN-validated methodology yet ties a specific number of
antecedent rain days to each state. Assigning numeric boundaries without
that citation would itself be an uncited, arbitrary threshold of exactly the
kind this revision removes elsewhere.

On the **real, committed data today**, every one of the 18 candidates
legitimately resolves to `physical_plausibility_assessment.category ==
"INSUFFICIENT_EVIDENCE"` for two independent, reinforcing reasons: no
candidate has a committed rainfall percentile/anomaly series, **and** v0.1
has no calibrated scoring path in the first place. This is the honest,
scientifically preferable output of the current architecture, not a
placeholder — `tests/test_phase2_climate_matrix.py` proves this
*software* behavior (no crash, no fabricated score, fail-closed under
extreme synthetic inputs) without using those fixtures to establish any
hydrological weight or threshold.

Historical case-validation linkage is deliberately **not** fed into the
plausibility assessment at all. `historical_evidence_summary` reports what
is factually documented about a linked case (event date, classification,
primary source) as a separate, descriptive field — it is not, and in v0.1
cannot be, converted into a plausibility category or an activation rule,
because doing so from a single documented realization would be an
unjustified generalization from n=1. `CONFIRMED_NO_ACTIVATION`-grade claims
remain the responsibility of the existing, reinforced-validation gate in
`scripts/build_phase2_catalog.py` (`evaluate_negative_control_leg` /
`compute_historical_events_gate`, built in PR-C); this matrix never asserts
or overrides that gate.

## Hydrologic child unit integrity

`hydrologic_child_units_reference` (root-level, outside the 18-record
`records` array) is a read-only, verified pointer to the two Lambayeque
hydrologic child units and their historical grouper — it never duplicates
their authoritative contracts:

- `lambayeque_chancay_lambayeque_chongoyape` (ANA hydrologic-unit code
  `13776`)
- `lambayeque_zana_oyotun` (ANA hydrologic-unit code `137754`)
- both `parent_candidate_id`-linked to `lambayeque_chongoyape_oyotun_zana`,
  which stays `entity_role: "HISTORICAL_NON_ACTIVABLE_GROUPER"` with
  `geometry_policy: "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR"` and
  `activation_gate: "BLOCKED"`.

`build_hydrologic_child_units_reference()` fails closed
(`phase2_catalog.ContractError`) at generation time if either child is
missing from `config/phase2_candidate_inventory_v0_2.json`, if either ANA
code has changed, or if the grouper's `entity_role`/`geometry_policy` has
changed — so a silent change to any of these upstream facts breaks the
build rather than being silently carried forward. Both children explicitly
declare `counts_as_additional_phase2_candidate: false` and
`counts_as_operational_candidate: false`; the 18-candidate Phase-2 count is
unaffected by their presence in this reference.

## Independent authoritative-state validation

`scripts/validate_phase2_climate_matrix.py` does not trust the generated
matrix's own summary constants (e.g. `summary.operational_candidate_count`)
as proof that Phase-2 remains unchanged — a generator that always writes
zero proves nothing about the real catalog. Instead, the validator
independently reads `site/data/phase2/catalog.json` and
`config/phase2_candidate_inventory_v0_2.json` and recomputes, from those
authoritative sources alone: 18 registered candidates, 0 approved contracts,
0 operational candidates, 0 zones with `promotion_gate.promotion_gate_met ==
true`, every `activation_gate == "BLOCKED"`, `RESEARCH_ONLY`,
`production_use == false`, `production_ready == false`, alerting disabled,
and both hydrologic children present with their correct ANA codes. Only
after establishing that independent state does it cross-check the matrix's
own claims (e.g. `relationship_to_phase2.candidate_count`,
`hydrologic_child_units_reference`) against it. Any mismatch — in either
direction — is a validator `ERROR`, and the validator exits non-zero.

## Uncertainty

Uncertainty is represented explicitly and multi-dimensionally
(`uncertainty.confidence_tier` plus six named sub-statuses), never hidden
inside a single combined score. `confidence_tier` cannot rise above
`INSUFFICIENT_EVIDENCE` for any of the 18 candidates today, because no
candidate has a committed, dated rainfall/antecedent observation series —
this mirrors, rather than contradicts, the plausibility category.

## Limitations

- **No live rainfall/antecedent/persistence data wired per candidate.** This
  is the dominant limitation: IMERG/GOES/GEOS-CF access exists elsewhere in
  the repository but is not yet extracted into a per-candidate,
  per-window, source-attributed series with climatological percentiles. Until
  that exists, `rainfall`, `antecedent_moisture` and `persistence` stay
  `INSUFFICIENT_EVIDENCE` for all 18 candidates by design.
- **No live "current date" concept.** This matrix is a reproducible
  framework generated at build time, not an operational, continuously-updated
  service; `season_context` and `large_scale_climate_context` are therefore
  not evaluated "as of now" and stay `UNKNOWN` at the top level. A future
  per-event extension could compute season for a specific historical
  `documented_realization` date using standard Peru coastal/Andean
  climatology conventions, but that is out of scope for v0.1 to avoid
  conflating a descriptive historical fact with a live assessment.
- **No numeric physical/catchment characteristics are committed** (drainage
  area, slope, drainage density, soil type, land cover, …) for any of the 18
  candidates. `physical_factors` is `null` everywhere with an explicit
  `data_gaps` list; nothing is inferred from geometry files even where a
  geometry asset exists, because the tooling to compute those values
  correctly (e.g. `shapely`) is not available in every environment that runs
  this generator, and because most candidates' geometry assets are not
  `READY` in the first place.
- **Historical rainfall context fields are heterogeneous and not
  cross-file-comparable.** A survey of `phase2_case_validations/*.json`
  found at least three different shapes carrying rainfall-adjacent data:
  an observed event-day rainfall value (`cashahuacra_santa_eulalia_2015`), a
  design-return-period value from an IDF study
  (`lima_sur_malanche_2023` — a fundamentally different quantity, not an
  observed event value), and a purely descriptive block with no number at
  all (`lurin_cieneguilla_pachacamac_2017`). `documented_historical_realizations`
  therefore only records **whether** rainfall evidence exists in the linked
  case (`rainfall_evidence_available` + `rainfall_evidence_field_ref`
  pointing at the source field name), and never extracts or compares the
  numeric values themselves. Building a safe, normalized cross-candidate
  rainfall-evidence projection is future scope, not this PR's.
- **ENSO phase is never populated with a real, dated value** in v0.1 — only
  the existing qualitative scenario-corridor membership is surfaced as
  context. Wiring a real ENFEN/ONI/SST-anomaly time series with a documented
  as-of date is future scope.
- **`lambayeque_chongoyape_oyotun_zana`** (the historical non-activable
  grouper, `entity_role: "HISTORICAL_NON_ACTIVABLE_GROUPER"`) receives a
  record like any other of the 18 for count-preservation purposes, but never
  a geometry-backed `physical_factors.source_asset_ref` (per
  `geometry_policy: "NO_COMPOSITE_GEOMETRY_NO_ARTIFICIAL_CONNECTOR"` in the
  inventory) — its two hydrologic children
  (`lambayeque_chancay_lambayeque_chongoyape`,
  `lambayeque_zana_oyotun`) are tracked separately in
  `site/data/phase2/catalog.json` and referenced (never duplicated or
  counted) via the root-level `hydrologic_child_units_reference`; see
  *Hydrologic child unit integrity* above.
- **No scientifically calibrated combination function exists yet.** This is
  by design, not an oversight: see *Scientific position of v0.1* above.
  `classification_method_status` will move beyond `NOT_YET_CALIBRATED` only
  in a later, separately reviewed revision that cites real historical
  event/non-event evidence for its weights and breakpoints — never from
  synthetic test fixtures.

## Operational boundary

> Climate-Conditioned Activation Matrix is a research framework and must not
> be interpreted as an operational activation, warning, emergency trigger, or
> production decision system.

Concretely: this matrix never sets `activation_gate` to anything other than
`BLOCKED`; never sets `promotion_gate_met` (it does not even define that
field — that remains `scripts/build_phase2_catalog.py`'s alone, from PR-C);
never changes `production_use`/`production_ready`/
`operational_alerting_enabled`/`decision_thresholds`; never changes the
18/0/0 Phase-2 candidate/operational/approved counts; and never merges or
replaces a case validation's or zone contract's own findings.
