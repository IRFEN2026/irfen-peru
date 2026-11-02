# IRFEN v0.9.1 · Semáforo de seguimiento (experimental) · piloto Lambayeque — 02-11-2026 (revisión 0.2)

**Estado:** RESEARCH_ONLY / TEST_ONLY · `official_alert=false` · `public_alerting=false` · `notifications_enabled=false` ·
`predictive=false` · no fusionado en `main` · no publicado. Rama `research/v09-coastal-hydrography-contrast-20261102` (PR #466).
La versión congelada Research Preview 1 (rama `release/irfen-v0.9-research-preview-1`, 25e611ac) no se ha tocado.

**No es una alerta oficial.** El color resume los **datos locales** de cada punto: lluvia estimada por satélite y eventos
verificados. Los avisos oficiales se muestran aparte, como contexto territorial. No predice crecidas ni huaicos.

## Revisión 0.2: correcciones tras la auditoría de #466

La auditoría del 02-11-2026 sobre 328cc64f señaló un problema: los 39 puntos salían amarillos porque compartían los mismos
avisos regionales, no por evidencia local.
- El aviso 448 es departamental, «precipitaciones en la sierra», y no enumera provincias.
- La lluvia mínima también producía amarillo.
- El orden alto / medio / bajo se presumía este→oeste.

Correcciones:

| # | Corrección |
|---|---|
| 1 | Los avisos son **contexto territorial**: un contorno discontinuo y una franja en el panel y en cada ventana. **Nunca cambian el color** (`territorial_context.affects_colour=false`). Se indica si el aviso es departamental (sin provincias) o provincial, y que «vigente» significa «según el texto archivado» cuando la comprobación de avisos es antigua |
| 2 | Sin datos locales recientes (IMERG > 12 h, o GOES-19 > 90 min donde existe), el punto es **gris**, aunque haya un aviso regional vigente |
| 3 | El amarillo pasa a llamarse **«Lluvia satelital detectada (no es activación)»**. La **evidencia de posible crecida o activación** (caudal, nivel, reportes de campo) se muestra aparte como **no disponible**. No hay umbrales de peligro |
| 4 | El rojo es solo **«Evento reportado y verificado»** (≤ 72 h). Muestra fecha, fuente, lugar y la advertencia «indica que el evento ocurrió; no garantiza que siga activo» |
| 5 | **● Círculo:** punto de cauce IGN (`CAUCE_IGN`). **■ Cuadrado:** población expuesta ANA (`POBLADO_ANA`), «no es un punto del cauce». Los nombres empiezan por «Poblado expuesto …» y la tabla tiene la columna «Ubicación» |
| 6 | El sentido del flujo se obtiene de evidencia física, no del orden este→oeste (ver abajo). Los nombres pasan a «tramo alto / medio / bajo **en Lambayeque**» |
| 8 | Se probó expresamente el caso «aviso regional vigente + datos locales antiguos»: 226 casos, todos grises, con paridad Python/JS |

## Orientación de los ríos (punto 6)

`chain()` ya no orienta los tramos. `orient()` acepta un sentido solo con alguna de estas evidencias:
- **(A) Desembocadura:** un extremo a ≤ 5 km de la costa (Natural Earth, sin fronteras terrestres) y el otro a ≥ 30 km.
- **(B) Red de flujo:** la acumulación HydroSHEDS 15" que ya está en el repositorio, muestreada en los vértices IGN, crece de forma monótona: |ρ Spearman| ≥ 0,8 con ≥ 80 % de cobertura.

Si no hay evidencia, los sectores se rotulan oeste / centro / este («orientación no verificada»). El sentido de digitalización del IGN no se usa: es inconsistente. La 688 y la 292 están digitalizadas de la desembocadura a la cabecera, y la 291 y la 588 al revés.

| Río | Extremos a la costa | HydroSHEDS | Resultado |
|---|---|---|---|
| La Leche (688) | 35 y 102 km: no llega a la costa | cobertura 100 %, ρ = −1,00 | VERIFICADA_RED_DE_FLUJO_HYDROSHEDS |
| Chancay-Lambayeque / Reque (291 + 588) | 119 y 0,9 km | fuera de cobertura (6 %) | VERIFICADA_DESEMBOCADURA |
| Zaña (3523 + 292) | 4,7 y 78 km | fuera de cobertura | VERIFICADA_DESEMBOCADURA |

Las posiciones no cambian respecto a 328cc64f: la evidencia física confirma el orden anterior.
- «Alto» es el sector superior **del tramo dentro de Lambayeque**, no la cabecera.
- La Leche no tiene zona de lluvia propia. Toma la cuenca Motupe como aproximación, y se indica que no es su área de aportación.

## Reglas (precedencia ROJO > AMARILLO > VERDE > GRIS)

| Color | Etiqueta | Regla |
|---|---|---|
| Rojo | Evento reportado y verificado | Confirmación verificada en el registro, con fecha, fuente y lugar, de las últimas 72 h. Puede referirse al punto, o al río para sus puntos de cauce |
| Amarillo | Lluvia satelital detectada (no es activación) | IMERG 24 h completa, < 12 h y ≥ 0,1 mm, o GOES-19 válido, < 90 min y > 0 |
| Verde | Sin lluvia satelital en datos recientes | IMERG 24 h completa, < 12 h y < 0,1 mm, y GOES-19 al día y nulo donde existe. No significa ausencia de peligro |
| Gris | No evaluable | Cualquier otro caso. Los avisos no lo cambian |

**Confianza:**
- ALTA: todas las fuentes locales aplicables al día.
- MEDIA: una de ellas antigua.
- BAJA: el punto está gris.
- En rojo: ALTA si la fuente es oficial y MEDIA si es un registro verificado.

## Antes y después (39 puntos, mismos datos archivados)

| Momento de evaluación | 328cc64f (rev. 0.1) | Revisión 0.2 | Por qué |
|---|---|---|---|
| Al corte (01-11 16:48 UTC) | 39 amarillo (R2: avisos 304/445/448) | **36 amarillo · 3 verde** | Los avisos ya no colorean. El amarillo es lluvia satelital de 0,1–2,5 mm/24 h, con datos al día. Los 3 verdes son celdas IMERG con 0,0 mm (Q-001, Q-016, Q-018) |
| Hora de la auditoría (02-11 02:32 UTC, equivalente a «Ahora») | 39 amarillo (R2, confianza baja) | **39 gris** | IMERG (fin 01-11 09:00) y GOES-19 (14:29) son antiguos. Los avisos 445/448 siguen vigentes, pero solo como contexto |
| Tras vencer el aviso 448 (04-11 06:00 UTC) | 39 gris | 39 gris | Sin datos locales recientes |

Al corte, los 36 amarillos no son 36 señales independientes:
- **31 comparten la media de 3 polígonos de zona:**
  - Motupe: 0,7 mm;
  - Chancay-Chongoyape: 2,5 mm;
  - Zaña-Oyotún: 1,0 mm.
- **Solo 5 usan su celda IMERG de 0,1°.**

La ventana de cada punto indica de dónde sale su lluvia.

## Verificación

- `tests/test_v09_surveillance_view.py` (métodos existentes ampliados) comprueba:
  - los avisos nunca cambian el color: el estado es el mismo con y sin avisos;
  - con datos locales antiguos el punto es gris aunque haya un aviso regional vigente;
  - el amarillo solo viene de lluvia satelital;
  - la orientación de cada río está verificada con evidencia física;
  - cada punto tiene el tipo de ubicación correcto (`CAUCE_IGN` o `POBLADO_ANA`) y está sobre un vértice IGN o un punto ANA exacto;
  - el rojo exige una confirmación verificada de menos de 72 h.
- Prueba de humo en escritorio y móvil:
  - 0 errores;
  - 39 símbolos, de ellos 30 cuadrados ANA;
  - franja de contexto visible;
  - la ventana emergente incluye «Contexto territorial» y «posible crecida».
- Paridad Python/JS:
  - **1.404 casos sintéticos, 0 discrepancias** en estado, regla, confianza y contexto;
  - de ellos, **226 casos «aviso regional vigente + datos locales antiguos», todos grises**;
  - autocomprobación al corte: 39/39.

## Archivos

| Archivo | Contenido |
|---|---|
| `config/v09_semaforo_rules_v0_1.json` | Revisión 0.2 |
| `config/v09_semaforo_systems_v0_1.json` | `orientation_rule` y umbrales |
| `config/v09_semaforo_confirmations_v0_1.json` | Registro vacío; añade el campo `location_es` |
| `scripts/v09_build_semaforo.py` | `chain`, `orient`, `evaluate` |
| `data/v09/research/semaforo/semaforo_v0_1.json` | Datos del semáforo |
| `site/v09/vigilancia.html` | `smEval`, símbolos y contexto |

También se regeneraron el paquete `site/data/v09/surveillance_view_v0_1.json`, la copia privada v0.9.1 y el manifiesto de la candidata.

## Limitaciones que siguen

- No hay caudal, nivel ni reportes de campo integrados.
- La lluvia de 31 puntos es una media de zona, y La Leche usa Motupe como aproximación.
- El registro de eventos está vacío y es manual.
- Los datos están congelados al 01-11-2026: en «Ahora» todo sale gris.
