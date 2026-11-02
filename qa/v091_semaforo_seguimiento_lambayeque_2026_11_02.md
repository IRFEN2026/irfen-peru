# IRFEN v0.9.1 · Semáforo de seguimiento (experimental) · piloto Lambayeque — 02-11-2026

**Estado:** RESEARCH_ONLY / TEST_ONLY · `official_alert=false` · `public_alerting=false` · `notifications_enabled=false` ·
`predictive=false` · no fusionado en `main` · no publicado. Rama `research/v09-coastal-hydrography-contrast-20261102` (PR #466).
La versión congelada Research Preview 1 (rama `release/irfen-v0.9-research-preview-1`, 25e611ac) no se ha tocado.

**No es una alerta oficial.** Ordena visualmente el seguimiento de ríos y quebradas con las fuentes que la vista ya tenía
(avisos de SENAMHI vía INDECI/COEN, IMERG Early, GOES-19 RRQPE). No predice crecidas ni huaicos.

## Archivos

| Archivo | Papel |
|---|---|
| `config/v09_semaforo_rules_v0_1.json` | Reglas, colores, antigüedades máximas, confianza, qué no se usa |
| `config/v09_semaforo_systems_v0_1.json` | Sistemas por departamento (Lambayeque = `PILOTO_ACTIVO`; los otros 10 = `PENDIENTE`) |
| `config/v09_semaforo_confirmations_v0_1.json` | Registro manual de confirmaciones documentadas (única vía al rojo). Vacío |
| `scripts/v09_build_semaforo.py` | Coloca los puntos y prepara sus entradas; `evaluate()` es la referencia de la lógica |
| `data/v09/research/semaforo/semaforo_v0_1.json` | Salida (82 kB), incrustada en `site/data/v09/surveillance_view_v0_1.json` como `semaforo` |
| `site/v09/vigilancia.html` | Capa «Semáforo de seguimiento», pestaña «Semáforo», ventana emergente; `smEval()` replica `evaluate()` |

Orden de construcción: `v09_build_semaforo.py` → `v09_build_surveillance_view.py` → `v09_build_surveillance_demo.py`.
Si el panel de zonas cambia y no se regenera el semáforo, el paquete lo marca `PENDIENTE` y la página no lo muestra.

## Lógica (precedencia ROJO > AMARILLO > VERDE > GRIS)

| Color | Regla |
|---|---|
| **Rojo** · evento confirmado | Confirmación **verificada** en el registro, con fuente, en las últimas 72 h, para ese punto (o para el sistema fluvial: solo sus puntos de río). Ni la lluvia ni un aviso producen rojo. |
| **Amarillo** · vigilancia | R2 aviso de lluvia vigente relacionado (por las fechas de su texto) · R3 aviso futuro, o de vigencia desconocida solo si la comprobación de avisos está al día · R4 IMERG 24 h ≥ 0,1 mm o GOES-19 > 0 mm/h con datos al día |
| **Verde** · sin señal en los datos | R6: comprobación de avisos al día y sin aviso relacionado; IMERG 24 h completa, al día y < 0,1 mm; GOES-19 válido, al día y nulo donde existe. No significa ausencia de peligro |
| **Gris** · no evaluable | R5: todo lo demás. **Un dato ausente o antiguo nunca da verde** |

- Antigüedad máxima: IMERG 12 h · GOES-19 90 min · comprobación de avisos 180 min (las mismas del panel de zonas).
- Relación aviso–punto: el aviso de lluvia (ACP-LLUVIAS, ACP-QUEBRADAS, AVISO-METEOROLOGICO marcado como de lluvia; sin
  cancelación ni sustitución) enumera el departamento y, si enumera provincias, la provincia INEI del punto.
- Confianza: ALTA si todas las fuentes aplicables están al día; MEDIA si al menos una; BAJA si ninguna o si el estado es gris.
- Sin naranja: no hay una regla validada para un nivel intermedio. Sin umbrales en mm, percentiles ni modelos.
- Dos modos en la página: **Ahora** (hora del dispositivo; por defecto) y **Al corte de datos** (reconstrucción, rotulada como tal).

## Ubicación de los puntos (sin coordenadas inventadas)

- **Ríos:** vértices reales de la red IGN 1:500.000, encadenando los OBJECTID del sistema de este a oeste. Sectores alto / medio / bajo
  al 15 / 50 / 85 % de la longitud dentro de Lambayeque.
  - La Leche: 688, 84 km.
  - Chancay-Lambayeque / Reque: 291 + 588, 78 km.
  - Zaña: 3523 + 292, 77 km. El IGN lo escribe «Saña».
- **Lluvia de los ríos:**
  - Chancay y Zaña usan el polígono de su cuenca en el panel de zonas, aguas arriba de Chongoyape y de Oyotún.
  - La Leche no tiene zona propia. Usa el polígono que contiene cada punto, en la práctica la zona Motupe; se indica en la ventana emergente.
- **Quebradas:** ubicaciones documentales de centros poblados expuestos ANA 2016-17. Las 46 de Lambayeque se agrupan a ≤ 2 km en 30 puntos.
  - La coordenada es la del primer registro del grupo, no un centroide.
  - El nombre de la quebrada es el del cuadro ANA. Es OCR con errores visibles, como «Mufioz».
  - El tipo es «mixto» si el grupo está a ≤ 1 km de un cauce piloto (2 casos: La Compuerta y Leque Leque, junto al Zaña).
- Total: **39 puntos** (9 río, 28 quebrada, 2 mixto).

## Estado observado

- **Al corte (01-11-2026 16:48 UTC):** 39 amarillo (R2, avisos ACP-LLUVIAS 304 y meteorológicos 445/448 vigentes).
  - Confianza ALTA en los puntos de celda costera.
  - Confianza MEDIA en los puntos de zona, porque GOES-19 tenía 2 h 19 min (> 90 min).
- **«Ahora» (noche del 01-11 en Lima):** 39 amarillo de confianza BAJA.
  - El aviso 448 sigue vigente por su texto hasta el 03-11.
  - Todas las demás fuentes están antiguas; la ventana lo explica.
  - Cuando venza el aviso, todos pasarán a gris mientras los datos sigan congelados.

## Verificación

- `tests/test_v09_surveillance_view.py` amplía métodos existentes, sin cambiar el manifiesto de pytest:
  - guardas;
  - puntos sobre un vértice IGN o un punto ANA exacto;
  - tres sistemas con sectores alto, medio y bajo;
  - rojo solo con confirmación verificada y dentro de 72 h;
  - nunca verde sin datos;
  - gris con datos antiguos;
  - reconstrucción byte a byte.
- Prueba de humo, escritorio 1440×900 y móvil 390×844:
  - 0 errores JS;
  - pestaña, filtros (ríos 11, quebradas 30, amarillos y rojos, departamento pendiente) y ventana emergente con todos los campos;
  - autocomprobación al corte: 39/39;
  - **1.404 casos sintéticos** evaluados igual por el navegador y por `evaluate()` (ROJO 40, AMARILLO 880, VERDE 16, GRIS 468; 0 discrepancias).

## Limitaciones

- No hay caudal, nivel ni observación de campo: el color resume lluvia estimada y avisos, no el estado del cauce.
- Los avisos se relacionan con los puntos por límites administrativos, no por la huella del aviso.
- Los puntos de celda costera usan una instantánea de investigación y quedan antiguos enseguida.
- El registro de confirmaciones está vacío y es manual: hoy no puede haber rojo.
- Los datos de la vista están congelados al 01-11-2026.

## Ampliar a otro departamento

1. En `config/v09_semaforo_systems_v0_1.json`, cambiar el estado a `PILOTO_ACTIVO`.
2. Listar sus sistemas con los OBJECTID IGN verificados y, si existe, la zona de lluvia de su cuenca.
3. Indicar la fuente documental de quebradas.
4. Regenerar con los tres scripts.
