# Taxonomía de excepciones para descubrimiento/parsing

## Principio

IRFEN aplica `UNKNOWN_NOT_LOW_RISK` también al software. Un dato ausente, un
valor malformado, un cambio de esquema y un error de programación no son lo
mismo y no deben convertirse silenciosamente en el mismo `None`/continue.

## Categorías

- `SOURCE_DATA_MISSING`: la fuente no trae el valor esperado. Se conserva
  como ausencia/UNKNOWN, nunca como NONE.
- `PARSE_INPUT_INVALID`: existe un valor pero no tiene la forma esperada.
  Se captura únicamente la excepción concreta de la operación.
- `SOURCE_SCHEMA_CHANGED`: faltan claves estructurales previamente esperadas.
  Se registra por separado para que el cambio aguas arriba sea visible.
- `NETWORK_OR_SOURCE_FAILURE`: caída o respuesta inválida de la fuente. Los
  handlers de frontera deben registrar tipo/mensaje del error o devolver un
  estado explícito de fuente no disponible.
- `PROGRAMMING_ERROR`: errores inesperados de código. En los sitios
  endurecidos por esta corrección no se absorben mediante `except:` desnudo;
  se dejan propagar fuera de ese sitio.

Esta PR no afirma que todos los handlers amplios históricos del repositorio
hayan sido eliminados. Endurece los sitios auditados y, además, estrecha los
handlers de frontera de los tres parsers PDF/SENAMHI tocados cuando era
necesario para que un error de programación no quede disfrazado de ausencia.

## Excepción controlada: extracción de texto PDF

`pypdf` puede lanzar diferentes excepciones internas al extraer una página.
En los tres sitios de extracción por página se mantiene
`except Exception as exc`, pero el fallo queda registrado como:

```json
{"page": 2, "error_type": "PdfReadError", "error": "..."}
```

La salida añade `page_extraction_status` y `extraction_errors`. Si no hay
ninguna página legible y hubo fallos de extracción, el estado superior es
`pdf_text_extraction_failures`, no `downloaded_without_text_layer`.

## Sitios endurecidos

| Archivo / operación | Tratamiento |
|---|---|
| San Ildefonso `millis()` | `ValueError` -> PARSE_INPUT_INVALID |
| San Ildefonso muestra `value` | ausencia y valor malformado se cuentan por separado |
| Catacaos EVAR extracción PDF | contexto de página/tipo/mensaje |
| Catacaos EVAR tokens numéricos | `ValueError` |
| INGEMMET Chosica extracción PDF | contexto de página/tipo/mensaje |
| Chosica local UTM/lon-lat | `ValueError` |
| Chosica local extracción PDF | contexto de página/tipo/mensaje |
| SENAMHI `num()` | `ValueError` |
| SENAMHI `decode()` | `UnicodeDecodeError` |
| SENAMHI `csv.Sniffer().sniff()` | `csv.Error` |
| Chosica controls `area_km2()` | `ValueError` |
| Chosica controls claves lon/lat/UTM | `KeyError` -> SOURCE_SCHEMA_CHANGED; valores no numéricos -> PARSE_INPUT_INVALID |

## Guardas científicas

Este cambio no modifica contratos Phase-2, casos científicos,
`decision_thresholds`, `activation_gate`, `production_use`,
`production_ready`, `operational_alerting_enabled` ni scorecard.
