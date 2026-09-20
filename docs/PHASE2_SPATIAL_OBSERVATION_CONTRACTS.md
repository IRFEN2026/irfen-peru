# Phase-2 Spatial Observation Contracts (Claude F) — v0.1

**Status:** `RESEARCH_ONLY` / `TEST_ONLY`.

Claude F answers a spatial question that must be resolved before NASA climate evidence can be attributed to a Phase-2 candidate:

> Which exact geometry may be used to sample gridded IMERG / GOES / GEOS data, and what scientific role does that geometry represent?

It does **not** decide activation, risk, thresholds, hydraulic response, or production readiness.

## Current classification

Across the 18 registered Phase-2 candidates:

- **0** candidates have a candidate-wide geometry ready for area-based sampling.
- **2** candidates/groupers expose research-only hydrologic subunits:
  - `lima_este_santa_eulalia_rimac`
    - `cashahuacra`
    - `shingolay`
  - `lambayeque_chongoyape_oyotun_zana` (historical non-activable grouper)
    - `lambayeque_chancay_lambayeque_chongoyape` — ANA 13776
    - `lambayeque_zana_oyotun` — ANA 137754
- **1** candidate has a reproducible file but no catchment/watershed geometry suitable for rainfall-area sampling:
  - `lima_este_lurin_cieneguilla`
- **15** candidates remain blocked because no reproducible sampling geometry is available under the current contract.

This classification is fail-closed. A `PARTIAL` asset label does not count as file presence.

## Santa Eulalia–Rímac

The committed geometry file contains five different scientific/administrative units.

### Eligible research subunits

`cashahuacra` and `shingolay` are DEM-derived D8 catchment candidates with explicit polygon geometries, pinned geometry hashes and declared areas.

They are accepted only as:

`HYDROLOGIC_SUBUNIT_RESEARCH_ONLY`

They do **not**:

- complete the parent candidate geometry;
- count as operational geometry;
- validate an outlet;
- validate activation;
- establish thresholds;
- validate routing or hydraulic response.

Their outlets remain without official confirmation.

### Explicitly excluded geometries

The Santa Eulalia and Rímac faja-marginal geometries are reproducible, but they are not drainage basins.

They remain excluded from precipitation area-sampling contracts even where represented as polygons.

The 2022 Rímac left-margin update is a `MultiLineString` and is also not an area-sampling geometry.

## Lambayeque hydrologic children

The legacy `lambayeque_chongoyape_oyotun_zana` identifier remains a
`HISTORICAL_NON_ACTIVABLE_GROUPER`. It receives no composite geometry and is
never activated.

Two official ANA hydrologic units may be sampled independently for research:

- `lambayeque_chancay_lambayeque_chongoyape` — Cuenca Chancay-Lambayeque, ANA **13776**, official area **4022.2645 km²**.
- `lambayeque_zana_oyotun` — Cuenca Zaña, ANA **137754**, official area **1745.3989 km²**.

Both geometries come from the official ANA hydrologic-unit service and passed
the committed migration validation as `PASS_RESEARCH_ONLY`. They remain
separate, have no artificial connector and do not increase the 18-candidate
Phase-2 count.

Their contract scope is:

`OFFICIAL_HYDROLOGIC_CHILD_UNIT_RESEARCH_ONLY`

Rainfall sampled over these polygons is **whole-basin context**. It is not
rainfall for a specific local quebrada, municipal boundary, event footprint,
inundation polygon or hydraulic model.

## Lurín–Cieneguilla

The committed Lurín file contains:

- official right-margin connected hitos;
- official left-margin connected hitos;
- a derived regulatory corridor polygon.

These geometries describe river-margin/regulatory space, not a drainage basin.

Therefore:

`spatial_contract_status = NON_CATCHMENT_GEOMETRY_ONLY`

The corridor polygon is never reinterpreted as a watershed merely because it is a polygon.

## Sampling method

All four research-subunit contracts define:

`AREA_WEIGHTED_GRID_CELL_INTERSECTION`

with geometry in `EPSG:4326`.

No arbitrary minimum coverage percentage is introduced in v0.1.

Instead the contract requires coverage metadata to be preserved and partial coverage to fail closed until a source-specific method is independently reviewed.

## Source semantics

### IMERG

A subunit contract may be used for research-only IMERG extraction when timestamped gridded precipitation values are available.

### GOES RRQPE

Spatial geometry alone does not make the current GOES archive usable. Claude E established that the committed GOES archive currently preserves source availability/freshness metadata rather than candidate precipitation values.

GOES therefore remains blocked until candidate-level precipitation values are persisted.

### GEOS-CF

The same geometry can support forecast sampling, but GEOS remains forecast evidence and is never relabeled as observed rainfall.

## Guardrails

Claude F never:

- opens `activation_gate`;
- changes `promotion_gate`;
- changes the 18-candidate count;
- changes v0.8 scope;
- treats faja marginal or regulatory corridors as catchments;
- transfers a subunit geometry to another candidate;
- creates activation/risk/plausibility scores;
- introduces rainfall or coverage thresholds;
- treats missing geometry as low risk.

## Current data-ingestion scope

Claude G may now sample four research-only spatial units automatically:

- Cashahuacra
- Shingolay
- Chancay-Lambayeque / Chongoyape (ANA 13776)
- Zaña / Oyotún (ANA 137754)

The first two are local DEM-derived catchment candidates. The Lambayeque
polygons are official whole hydrologic units. Their rainfall semantics must
remain distinct and none of the four may be reported as activation evidence.
