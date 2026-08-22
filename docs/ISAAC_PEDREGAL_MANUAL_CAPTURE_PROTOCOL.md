# ISAAC Pedregal Koica — protocolo de captura manual v0.1

**Estado:** `TEST_ONLY`  
**Ámbito:** evidencia local prospectiva de precipitación para Pedregal Koica.  
**Producción:** prohibida (`production_use=false`).  
**Clasificación automática de resultado:** prohibida.  
**Corrección automática de sesgo IMERG:** prohibida.

## 1. Objetivo

Este protocolo define cómo conservar una observación visible en la plataforma oficial
SENAMHI/ISAAC de forma reproducible y auditable. La captura documenta **lluvia**;
no demuestra por sí sola activación, no activación, impacto ni ausencia de impacto.

La fuente pública verificada es la vista ISAAC de SENAMHI. La estación/punto objetivo
debe ser exactamente `Pedregal Koica`. No se sustituye por Chosica, Huaycoloro ni una
estación vecina.

## 2. Principios fail-closed

1. Todo campo no visible o no documentado se almacena como `null`.
2. Dato faltante o ilegible significa `UNKNOWN_NOT_ZERO`; nunca se convierte en `0`.
3. `Normal` y `Operativo` son estados de contexto de estación, no QA/QC de una lectura.
4. Una captura ISAAC no genera `EVENT`, `NONE` ni crédito de scorecard.
5. No se reconstruyen endpoints internos de Power BI ni APIs no documentadas.
6. No se aplica corrección automática a IMERG.
7. Una captura no se promociona a observación científica si la selección de
   `Pedregal Koica` no queda probada visualmente.
8. El original se conserva sin recorte, anotación, compresión ni conversión.

## 3. Procedencia de campos

Cada dato derivado de la interfaz debe indicar su procedencia con una de estas categorías:

- `TOOLTIP`
- `AXIS`
- `CHART_TITLE`
- `CHART_NOTE`
- `VISIBLE_FILTER`
- `OPERATOR_ANNOTATION`
- `INSTITUTIONAL_METADATA`

No se presenta como explícito un valor que sólo fue inferido del contexto.

## 4. Captura

### 4.1 Sesión

- Abrir la vista oficial en Chrome o Edge.
- Restablecer filtros cuando sea posible.
- Seleccionar exactamente `Pedregal Koica`.
- Mantener visible el título del visual, eje/unidad, selector temporal y tooltip.
- Registrar URL final y pestaña/visual.
- Comprobar si existe una opción visible de exportación sin recurrir a endpoints internos.

### 4.2 Evidencia de selección

La selección debe quedar visible en la captura mediante un filtro, fila resaltada,
selector o señal equivalente. La declaración del operador por sí sola no es suficiente
para promoción científica.

Si Power BI no permite mostrar simultáneamente selección y tooltip, se permiten
**dos capturas consecutivas de la misma sesión y dentro del mismo minuto**:

1. captura de selección/filtros;
2. captura de lectura/tooltip.

Ambas deben compartir un `capture_session_id` y conservar SHA-256 independientes.

### 4.3 Original

Conservar el PNG original y calcular SHA-256 antes de subirlo o transformarlo.

Campos mínimos del archivo:

- nombre;
- MIME;
- tamaño;
- ancho/alto;
- SHA-256.

## 5. Manifiesto

El manifiesto debe cumplir `config/isaac_pedregal_manual_capture.schema.json`.

Deben registrarse por separado:

- momento real de captura y zona horaria;
- identidad del operador;
- revisor cuando se solicite promoción científica;
- URL y visual;
- estación y evidencia de selección;
- timestamp mostrado por ISAAC;
- valor raw y normalizado;
- unidad y procedencia;
- periodo y procedencia;
- semántica exacta de ventana cuando esté documentada;
- filtros;
- QA/QC visible, si existe;
- indicador de dato faltante;
- estado de exportación;
- ambigüedades.

## 6. Captura parcial

Una captura puede ser archivada como `PARTIAL` para trazabilidad si faltan metadatos.
Eso no la convierte en observación científica.

Ejemplos de campos que deben permanecer `null` hasta confirmación institucional:

- zona horaria del timestamp mostrado;
- semántica exacta de la hora;
- código oficial de estación;
- metadata de instrumento;
- QA/QC de la observación.

## 7. Solicitud de promoción científica

`scientific_use.rainfall_candidate=true` sólo solicita evaluar la captura como
candidata de lluvia. No la acepta automáticamente.

El validador rechaza esa solicitud si faltan, como mínimo:

- SHA-256 correcto del original;
- operador y revisor;
- URL de reporte;
- estación `Pedregal Koica`;
- selección probada mediante `VISIBLE_FILTER`;
- timestamp mostrado y zona horaria;
- valor raw y numérico;
- unidad y su evidencia;
- periodo y su evidencia;
- semántica exacta de ventana;
- completitud `COMPLETE`.

Incluso si pasa estas comprobaciones, `scientific_use.scientific_observation_accepted`
permanece obligatoriamente en `false` en v0.1. La aceptación requiere un proceso
científico posterior y separado.

## 8. Resultado territorial

La evidencia territorial se obtiene fuera de ISAAC.

- `EVENT`: requiere fuente oficial/local independiente, fechada y espacialmente pertinente.
- `NONE`: requiere confirmación positiva de monitoreo suficiente sin activación/impacto.
- `UNCERTAIN`: evidencia insuficiente, parcial o contradictoria.

El manifiesto v0.1 de captura manual fuerza `outcome_label=null` y
`automatic_outcome_classification=false`.

## 9. IMERG

La comparación con IMERG puede hacerse sólo como diagnóstico, con ventanas temporalmente
alineadas cuando la semántica ISAAC esté confirmada. Se prohíbe:

- rellenar faltantes con cero;
- convertir una razón diagnóstica en multiplicador general;
- corrección automática de sesgo;
- cambio de umbrales.

## 10. Validación

Ejecutar:

```bash
python scripts/validate_isaac_pedregal_capture.py \
  --manifest ruta/al/manifiesto.json \
  --original ruta/al/original.png
```

El validador devuelve código `0` si el manifiesto es estructural y semánticamente válido
para su estado declarado. La validación **no** equivale a aceptación científica ni a
autorización operativa.
