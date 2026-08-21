# IRFEN Perú

Plataforma experimental de alerta y priorización hidrometeorológica para zonas vulnerables frente a lluvias intensas, activación de quebradas e impactos asociados a El Niño en Perú.

**Núcleo operativo protegido:** v0.7.1
**Carril científico actual:** v0.8 experimental en validación en sombra

La integración técnica v0.8 supera las pruebas automáticas y permite ejecutar
los tres pilotos en modo `TEST_ONLY`. La promoción a producción permanece
bloqueada hasta completar evidencia de lluvia local en Pedregal, validación
hidráulica posterior a las obras recientes, estado fluvial primario para
Catacaos y un periodo suficiente de observación operativa.

Sitio público: `https://irfen2026.github.io/irfen-peru/`

## Principio de diseño

IRFEN separa tres conceptos:

1. **Amenaza actual:** señal meteorológica basada en lluvia observada.
2. **Impacto potencial:** exposición/vulnerabilidad estructural de la zona.
3. **Prioridad operativa:** combinación de amenaza e impacto.

Las mejoras de v0.8 se prueban **en paralelo** y no reemplazan la lógica operativa hasta superar controles espaciales, históricos e hidráulicos.

## Datos meteorológicos

- NASA GPM IMERG Late Daily para operación diaria.
- NASA GPM IMERG Final para análisis histórico posterior a junio de 2000.
- Reintentos automáticos y modo contingencia si Earthdata no responde.
- El último dataset válido se conserva y la web sigue publicándose aunque falle una actualización.

## Zonas piloto

- Quebrada San Ildefonso — La Libertad.
- Chosica / Huaycoloro — Lima.
- Catacaos / Bajo Piura — Piura.

Los tres pilotos cierran el método v0.8; no representan el límite territorial
de IRFEN. La fase posterior se seleccionará por riesgo, recurrencia, rapidez de
activación, aislamiento y brecha de respuesta, no por tamaño de ciudad. La
preparación comprende quebradas y sistemas críticos de Lima norte y sur chico,
Ica/Pisco, Lambayeque y otras zonas prioritarias de la costa norte, central y
sur, incluidas comunidades pequeñas y rurales. Véanse
`docs/PHASE2_EXPANSION_STRATEGY.md` y el inventario preliminar
`config/phase2_candidate_inventory_v0_2.json` (solo investigación, sin zonas
activadas). La trazabilidad del mapa y el orden de preparación se documentan en
`docs/PHASE2_MAP_LAYER_MODEL.md`; una zona sin archivo geométrico reproducible
no se representa mediante puntos aproximados.

## Estado científico v0.8

### San Ildefonso

Se construyó una microcuenca candidata con **Copernicus DEM GLO-30**, flujo D8 y acumulación de drenaje.

- Referencia externa: 28.9 km².
- Área DEM: 28.34 km².
- Error de área: 1.94%.
- Control espacial externo: consistente.
- IMERG Final 15/03/2017:
  - caja antigua: 19.63 / 39.22 / 48.98 mm (24h / 72h / 7d)
  - microcuenca: 20.77 / 42.77 / 53.15 mm
  - diferencia: +1.14 / +3.55 / +4.17 mm

**Aún no es producción.** En 2026 entraron en operación obras de retención, captación y derivación que modifican la relación lluvia-caudal-impacto histórica.

### Huaycoloro

Se está construyendo un polígono DEM independiente usando como referencias:

- área aproximada publicada del sistema Huaycoloro: ~492 km²;
- punto ANA QHuay-1 cerca de la confluencia con el río Rímac;
- contexto hidráulico actual: canalización de 10.5 km inaugurada en 2025.

### Catacaos / Bajo Piura

No se tratará como una microcuenca simple. La siguiente fase debe representar el sistema **cuenca del río Piura + aportes aguas arriba + intercuenca Bajo Piura + llanura de inundación + defensas**.

## Archivos principales

- `.github/workflows/update-and-deploy.yml` — actualización IMERG y publicación.
- `.github/workflows/history.yml` — histórico IMERG Final.
- `.github/workflows/build-san-ildefonso-v08.yml` — delineación San Ildefonso.
- `.github/workflows/build-huaycoloro-v08.yml` — delineación Huaycoloro.
- `.github/workflows/shadow-validation.yml` — registro diario de validación en sombra.
- `scripts/fetch_imerg.py` — operación diaria.
- `scripts/fetch_history.py` — histórico.
- `scripts/compare_san_ildefonso_history_polygon.py` — comparación histórica caja vs. polígono.
- `scripts/build_san_ildefonso_remote.py` — delineación DEM San Ildefonso.
- `scripts/build_huaycoloro_dem.py` — delineación DEM Huaycoloro.
- `site/data/latest.json` — dataset operativo publicado.
- `site/data/history.json` — catálogo histórico.
- `site/data/scientific_status.json` — estado de validación científica.
- `site/data/validation/shadow_runs.json` — evidencia diaria TEST_ONLY, contingencias y bloqueos.
- `docs/SHADOW_OUTCOME_REVIEW_PROTOCOL.md` — criterios auditables para que un resultado diario cuente en el cierre.
- `scripts/review_shadow_outcome.py` — aplica una revisión posterior con URLs oficiales sin alterar la fotografía previa.
- `.github/workflows/review-shadow-outcome.yml` — interfaz manual auditable para etiquetar una jornada cerrada; usa la cuenta GitHub del revisor y falla de forma cerrada para `EVENT`/`NONE`.
- `.github/workflows/review-v08-external-evidence.yml` — revisión humana trazable de requisitos científicos e hidráulicos; `REJECTED` por defecto y confirmación explícita para `ACCEPTED`.
- `site/data/v08_scorecard.json` — scorecard auditable de cierre (25/50/75/100), calculada solo con evidencia y sin porcentajes intermedios subjetivos.
- `config/v08_closeout_contract.json` — condiciones fijas de cada hito, muestras mínimas y guardas de seguridad.
- `site/data/watersheds/` — polígonos y reportes de validación.

## Seguridad

El token NASA Earthdata se almacena únicamente como secret de GitHub Actions bajo el nombre `EARTHDATA_TOKEN`. **Nunca debe incluirse en archivos del repositorio.**

## Advertencia científica

IRFEN es experimental. No sustituye avisos, pronósticos ni decisiones oficiales de SENAMHI, ANA, INDECI, CENEPRED, INGEMMET, IGP u otras autoridades competentes. Los umbrales actuales son provisionales y no se convertirán en umbrales de activación oficiales sin calibración y validación adicionales.
