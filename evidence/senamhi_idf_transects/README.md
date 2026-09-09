# SENAMHI IDESEP IDF transects — research evidence

This package preserves the distinct raw payloads and query-point mapping for three SENAMHI IDESEP IDF transects: Malanche, Pedregal/Chosica and San Ildefonso. It is strictly `RESEARCH_ONLY` / `TEST_ONLY`; `production_use=false`, `production_ready=false`, and `operational_alerting_enabled=false`.

The `.xls` downloads are UTF-8 HTML tables returned by the SENAMHI IDESEP IDF portal. Duplicate captures with identical SHA-256 share one canonical raw payload in the repository while the manifest preserves every queried coordinate and original capture filename.

These are spatially queried IDF frequency estimates, not observed event rainfall time series and not rain-gauge observations at the query coordinates. Equal IDESEP payloads at different coordinates mean only that the service returned identical values at those points; they do not establish physical rainfall uniformity.

Captured equality patterns are: Malanche lower=middle and upper differs; Pedregal lower differs and middle=upper; San Ildefonso all three are identical. These are descriptive properties of this capture only.

Forbidden uses include operational threshold transfer, automatic outcome labeling, production alerting, and calibration of IRFEN to force agreement with the IDF product. Missing event observations remain missing and may not be imputed from IDF curves.
