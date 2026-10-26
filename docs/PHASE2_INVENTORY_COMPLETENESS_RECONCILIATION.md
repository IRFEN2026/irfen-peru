# Conciliación documental y auditoría de completitud del inventario nacional (RESEARCH_ONLY / TEST_ONLY)

`scripts/phase2_inventory_completeness_reconcile.py` responde por separado a dos preguntas:

1. **Completitud documental:** qué unidades documentales conocemos, de dónde salen, dónde están y qué evidencia les falta.
2. **Madurez cartográfica:** cuáles podrían representarse en un mapa y por qué hoy no.

Una fila puede pertenecer al inventario sin ser apta para el mapa.

**Qué no hace la herramienta:**
- no fusiona, no divide, no renombra y no promueve;
- no escribe en sus entradas;
- no fija `map_eligible`, no crea geometrías, outlets, eventos ni umbrales.

La normalización de nombres sirve solo para buscar: no prueba identidad hidrológica.

## Uso
```bash
python scripts/phase2_inventory_completeness_reconcile.py --help
python scripts/phase2_inventory_completeness_reconcile.py            # entradas de main → data/phase2/inventory_reconciliation/reconciliation_main_v0_1.{json,md}
python scripts/phase2_inventory_completeness_reconcile.py --check    # recalcula y compara con el informe confirmado
# Delta de PR, leído con `git show` y nunca integrado (ETIQUETA[@ADAPTADOR[:CORREDOR]]=git:REV:RUTA o una ruta local):
python scripts/phase2_inventory_completeness_reconcile.py \
  --delta pr404=git:4aa58886498532a6130b2ef7a99503cfe7589ca0:config/phase2_national_inventory_r8_sigrid_sweep_v0_1.json \
  --delta pr404_sweep@sweep_ledger=git:4aa58886498532a6130b2ef7a99503cfe7589ca0:data/phase2/source_archive/sigrid_ana2016_sweep_20261022/sweep_ledger_v0_1.json \
  --delta pr407@corridor_units:CARRETERA_CENTRAL_RIMAC_SANTA_EULALIA=git:c8d2811b82dc32e5c84fc8a0e34ad97b7b8cd497:config/phase2_rimac_corridor_master_documentary_inventory_v0_1.json \
  --out-json /tmp/pilot.json --out-md data/phase2/inventory_reconciliation/reconciliation_pilot_prs_v0_1.md
```
Para el piloto hacen falta los objetos de esos PR en el clon: `git fetch origin pull/404/head pull/407/head`.

**Entradas** (`config/phase2_inventory_reconciliation_sources_v0_1.json`). Todas se leen sin modificarlas.

| Entrada | Adaptador | Qué aporta |
|---|---|---|
| Inventario maestro | `national_inventory` | Filas, fuentes, grupos de alias, nombres sin fuente y cobertura de barrido. Se ejecuta además su propio validador (sin tocarlo). |
| Delta r8 de #404 | `national_inventory` | Filas, `split_basis`, auditoría de compuestos embebida y diagnóstico por corredor. |
| Ledger de barrido de #404 | `sweep_ledger` | Fichas con HTTP 404 o error: fuentes pendientes, nunca ausencias. |
| Inventario Rímac de #407 | `corridor_units` | Unidades y grupos de identidad pendientes. |
| `phase2_candidate_inventory_v0_1/v0_2` | `system_ledger` | Sistemas, con otra granularidad: solo referencias cruzadas. Se comprueba que la versión nueva contiene a la anterior. |
| `phase2_north_coast_discovery_inventory_v0_1` | `discovery_ledger` | Sistemas y su `must_not_merge_with`. |
| `phase2_pisco_quitasol_paracas_sigrid_identity_v0_1` | `identity_entries` | Integridad referencial y documento archivado. |
| `zorritos_priority_ana_capture_attempts_v0_1` | `capture_log` | Capturas bloqueadas: fuentes pendientes. Un manifiesto de captura nunca es geometría. |
| `config/phase2_inventory_annotations_v0_1.json` | sidecar | Anotaciones versionadas por `inventory_id`. |

## Hallazgos
Cada hallazgo indica:
- los IDs implicados;
- el motivo;
- las evidencias;
- la incertidumbre;
- la acción recomendada;
- `merge_or_split_performed=false`.

No existe la categoría `SAME_UNIT`.

| Gravedad | Tipos |
|---|---|
| Bloqueante | `GUARD_VIOLATION`, `MASTER_RULES_VIOLATION`, `EXACT_RECORD_DUPLICATE` (mismo id dentro de una entrada), `IDENTIFIER_CONFLICT` (id sustituido aún presente), `SOURCE_REFERENCE_CONFLICT` (un mismo id de documento con URL, SHA-256 o institución contradictorios), `PROMOTION_WITHOUT_EVIDENCE`, `EVENT_EVIDENCE_WITHOUT_VERIFIED_SOURCE`, `FAJA_MARGINAL_AS_FOOTPRINT`, `SIDECAR_REJECTED` |
| Revisión humana | `CROSS_PR_OVERLAP`, `POTENTIAL_ALIAS` (mismo nombre normalizado, variante documental o una sola edición, en el mismo territorio), `COMPOUND_NAME_REVIEW`, `UNNAMED_IDENTITY_UNRESOLVED`, `DOCUMENTARY_RELATION_UNRESOLVED`, `REFERENTIAL_INTEGRITY`, `INSUFFICIENT_EVIDENCE` |
| Informativo | `HOMONYM_DISTINCT_CONTEXT` (agrupado por nombre; nunca se fusiona), `LEDGER_CROSS_REFERENCE`, `SOURCE_UNAVAILABLE_NOT_ABSENCE` |

**Reglas de los hallazgos:**
- Que varias filas citen el mismo documento es legítimo: un mapa departamental cubre muchas quebradas. Solo es conflicto si los metadatos del documento se contradicen.
- Las series numeradas («El Establo 1 / 2») y los hermanos de un `split_basis` no se tratan como variantes ortográficas.
- Un evento verificado dado como puntero del repositorio (`ruta.json#/a/0`) cuenta solo si el registro apuntado existe y declara un estado confirmado o verificado.

## Campos por fila y sidecar
**Estados de campo:**
- `KNOWN`: valor sustentado.
- `UNKNOWN`: sin valor; nunca se lee como negativo.
- `PENDING_VERIFICATION`: hay un indicio, sin verificar.
- `CONFLICT`: las entradas se contradicen.
- `NOT_EVALUATED`: nadie lo ha revisado.

**Campos auditados:**
- nombre documental, alias, departamento, provincia, distrito y corredor;
- cuenca padre, solo si está documentada;
- institución, referencia persistente y tipo de evidencia;
- documento primario: texto verificado, ficha archivada con SHA-256 o solo referencia;
- evento, geometría y outlet;
- conexión costera.

**Motivos de bloqueo cartográfico** (derivados; el maestro no los registra explícitamente):
- `IDENTITY_PENDING_ADJUDICATION`;
- `GEOMETRY_NOT_REPRODUCIBLE` / `GEOMETRY_LEAD_ONLY_NOT_REPRODUCIBLE`;
- `OUTLET_PENDING`;
- `HYDROLOGIC_ATTRIBUTION_NOT_SUPPORTED`;
- `INDEPENDENT_QA_PENDING`;
- `INSUFFICIENT_INFORMATION`.

Aunque se cumplan geometría y outlet, la QA independiente sigue pendiente y no hay promoción.

**Conexión costera:** `COASTAL_IMPACT_DOCUMENTED` / `CANDIDATE` / `UNKNOWN` / `NOT_ASSESSED`.
- Por defecto es `NOT_ASSESSED`. Estar en una región costera no prueba nada, y no existe una categoría negativa.
- `DOCUMENTED` exige en el sidecar una fuente `VERIFIED` con su SHA-256 real y el archivo congelado en el repositorio.
- `CANDIDATE` exige una base escrita.

**El sidecar** se rechaza si:
- fija `map_eligible`, `suggested_state`, coordenadas, umbrales, caudales o tiempos;
- pone geometría u outlet en `KNOWN`;
- pone un `KNOWN` sin fuente (institución, URL o identificador, y estado de lectura);
- escribe un hash mal formado.

Sus anotaciones pueden referirse a filas de un delta abierto (`expected_in`); solo se aplican cuando ese delta se carga.

## Informe por corredor
Cada corredor incluye:
- filas e IDs por entrada;
- posibles solapes;
- identidades pendientes;
- filas sin procedencia suficiente;
- filas sin distrito, sin geometría y sin outlet;
- filas sin motivo de bloqueo explícito en la fuente;
- conexión costera;
- fuentes y barridos pendientes;
- estados de campo dentro del conjunto conocido.

`state` toma uno de estos valores: `AUDITADO_PARCIAL`, `FUENTES_PRIORITARIAS_REVISADAS`, `FUENTES_PENDIENTES` o `NO_AUDITADO`. `complete` es siempre `false`. Los porcentajes se calculan solo sobre las filas cargadas, nunca sobre «todas las quebradas del Perú», porque ese denominador no está demostrado.

## Salidas
**JSON determinista** (`schema_version`, SHA-256 de cada entrada y, si procede, commit y blob de git):
- resumen, corredores y casos vigilados;
- errores bloqueantes, cola de revisión, advertencias y relaciones;
- tabla compacta de filas (estado por campo y motivos de bloqueo);
- límites de cobertura.

El contenido comparable no incluye la fecha de ejecución, que va en `run_metadata`; su huella es `comparable_sha256`. El orden de las entradas no cambia el resultado (probado).

**Markdown** con:
- resumen ejecutivo;
- errores bloqueantes;
- corredores;
- duplicidad y alias;
- identidades sin resolver;
- lagunas de evidencia;
- casos vigilados;
- próximas acciones.

## Resultados del 26-10-2026
**`main` `a0fba94a`:**
- 400 filas y 400 IDs; 0 errores bloqueantes y 99 hallazgos de revisión.
- Destaca un alias ortográfico posible en el mismo distrito: «La Chava» / «La Chiva» (Papayal).
- 3 grupos de filas `s/n`.
- 39 relaciones documentales sin resolver.
- 14 filas con evidencia insuficiente.

**Piloto con #404 y #407** (`reconciliation_pilot_prs_v0_1.md`): 464 filas y 420 IDs, 0 bloqueantes.
- **#407:** sus 51 unidades son 44 filas del maestro (mismo nombre y territorio, sin duplicar) y 7 nuevas.
  - «Dos Barrios» aparece como fila nueva, cuando el maestro la registra como `NO_SOURCE_FOUND_IN_THIS_SWEEP`: queda como relación por revisar.
  - El evento de Media Luna remite a un registro confirmado de `main` (`phase2_jicamarca_discovery_v0_1.json#/historical_evidence/0`).
- **Santa/Casma (#404):** 3 filas `s/n`, sin prueba de que sean distintas ni idénticas. El Establo 1 y 2 conservan su `split_basis`, y su independencia hidrológica queda `PENDING_VERIFICATION` en el sidecar.
- **Pisco/Ica:** «Cabeza de Cura» de Nasca y la de Vista Alegre son homónimas en contextos distintos y no se fusionan.
- **Tumbes/Zorritos:**
  - #408 solo cambia el script y las pruebas de congelación.
  - El registro de intentos de `main` sigue en `CAPTURE_BLOCKED_NOTHING_WRITTEN` y figura como fuente pendiente.
  - 24 de 68 filas no tienen distrito.

## Limitaciones y decisiones pendientes
- **Granularidad de los ledgers.** Los ledgers de sistemas solo se cruzan por nombre exacto. Enlazar un sistema con una quebrada requiere una fuente.
- **Motivos de bloqueo.** Se derivan, porque el maestro no los registra. Una decisión pendiente es si el maestro debe registrar `map_block_reason`.
- **Reglas de nombre.** «Posible alias» usa reglas simples (igualdad, variante documentada, una edición). No sustituyen la lectura de las fuentes.
- **Ritmo del sidecar.** Arranca con 5 anotaciones de identidad. La conexión costera queda `NOT_ASSESSED` en todo el inventario hasta que alguien lea y archive fuentes que la documenten.
- **Informe piloto.** Depende de objetos de PR abiertos y solo se confirma el Markdown. El JSON se reproduce con el comando anterior.
