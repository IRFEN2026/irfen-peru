# Protocolo universal de ingreso de evidencia externa IRFEN

## Propósito y alcance

Este protocolo define un ingreso reproducible, auditable y **fail-closed** para evidencia externa futura. Aplica a aforos, hojas de campo, series hidrológicas/pluviométricas, secciones transversales, geometrías/SIG, planos, memorias hidráulicas, actas, bitácoras, informes, fotografías/capturas originales, QA/QC y evidencia territorial de activación, impacto o ausencia confirmada de impacto.

El contrato de ingreso **no sustituye** `config/v08_external_validation_contract.json`, `site/data/validation/v08_external_evidence.json` ni el workflow humano `review-v08-external-evidence.yml`. Es una capa anterior: recibe y valida paquetes. La única fuente científica de verdad para `ACCEPTED` continúa siendo el ledger humano canónico `site/data/validation/v08_external_evidence.json`.

## Separación obligatoria

`package_validation` comprueba estructura e integridad del paquete. `scientific_disposition` describe la disposición científica efectiva expuesta por el intake. Son ejes distintos.

- `package_validation`: `VALID` o `INVALID`.
- `scientific_disposition`: `RECEIVED_UNREVIEWED`, `CANDIDATE`, `PARTIAL`, `ACCEPTED`, `REJECTED`.

Un paquete estructuralmente válido puede permanecer `RECEIVED_UNREVIEWED`, `CANDIDATE`, `PARTIAL` o `REJECTED`. Ningún validador ni builder puede originar una promoción a `ACCEPTED`.

## Regla única de ACCEPTED

El manifiesto puede conservar una declaración de revisión humana, pero esa declaración no crea aceptación científica. Para que el índice proyecte `ACCEPTED` deben cumplirse simultáneamente:

1. `review.automatic=false`;
2. revisor, fecha, decisión y justificación humanas completas;
3. requisito IRFEN v0.8 específico;
4. `review.ledger_reference` con `zone_id`, `evidence_id`, `reviewed_at` y `reviewed_by`;
5. el elemento correspondiente del ledger canónico debe estar ya en `status=ACCEPTED` con revisión humana coincidente;
6. esa revisión del ledger debe contener `source_evidence_package_id` igual al `evidence_package_id` del paquete.

Si un manifiesto declara `ACCEPTED` pero el ledger no contiene esa aceptación trazada al mismo paquete, el paquete puede seguir siendo estructuralmente válido, pero el intake lo degrada fail-closed a `CANDIDATE` y registra `UNRECONCILED_ACCEPTED_DECLARATION`. `summary.accepted` cuenta únicamente proyecciones reconciliadas. `summary.actually_unlocked_requirements` es una vista global derivada exclusivamente del ledger canónico, independientemente de qué paquetes estén presentes en intake.

El workflow humano vigente no se modifica en esta PR. Mientras dicho proceso no registre explícitamente `source_evidence_package_id`, ningún paquete de intake puede proyectarse como `ACCEPTED`; esto es una limitación deliberadamente fail-closed y evita atribuir a un paquete una aceptación producida por otra evidencia.

## Originales, derivados y faltantes

Los originales se conservan sin modificación en almacenamiento de ingreso no publicado. **Nunca se usa `site/` como raíz por defecto para originales.** El builder exige `--packages-root` explícito para procesar evidencia real; `--check` puede reproducir el índice vacío usando una raíz local no publicada e inexistente. Sólo se versionan manifiestos permitidos, el índice derivado, fixtures sintéticos, hashes y metadatos no restringidos.

Toda normalización o transformación se registra como archivo derivado con `source_sha256`, `sha256`, método, operador y fecha. Los metadatos desconocidos se expresan como `null`; no se inventan valores ni se transforma ausencia en cero. Cuando corresponde se usa `metadata_state`: `provided`, `not_provided`, `not_applicable` o `unknown`.

## Duplicados y versiones

El índice detecta sin borrar ni sobrescribir:

- SHA-256 idéntico en el mismo o en distintos paquetes (`EXACT_CONTENT_DUPLICATE`);
- mismo nombre original con bytes distintos (`SAME_NAME_DIFFERENT_BYTES`);
- nueva versión declarada mediante `version_relation`;
- posible sustitución no declarada cuando un nombre previo reaparece con bytes diferentes sin relación declarada;
- discrepancia entre manifiesto y archivo real (hash, tamaño, MIME o ausencia), que vuelve `INVALID` al paquete.

## Flujo reproducible

1. Copiar los originales a un directorio inmutable de ingreso fuera de `site/` y calcular SHA-256.
2. Crear `manifest.json` conforme a `config/external_evidence_package.schema.v1.json` sin inventar metadatos.
3. Ejecutar `python scripts/validate_external_evidence_package.py <ruta-paquete>`.
4. Si es `INVALID`, conservar el paquete y corregir sólo el manifiesto o incorporar la evidencia faltante; nunca alterar el original para hacerlo pasar.
5. Si es `VALID`, mantener inicialmente `RECEIVED_UNREVIEWED` o una disposición humana explícita no aceptante.
6. Ejecutar `python scripts/build_external_evidence_intake_index.py --packages-root <raíz-no-publicada> --output site/data/validation/external_evidence_intake_index.json`.
7. La revisión científica de requisitos v0.8 continúa mediante el proceso humano canónico existente.
8. Sólo después de que el ledger humano registre una aceptación trazada al mismo `evidence_package_id`, el intake puede reflejar esa decisión como `ACCEPTED`.

## Guardas

Este subsistema no modifica evidencia histórica, `EVENT/NONE`, scorecard, release, umbrales, correcciones de sesgo ni estado productivo. Deben permanecer `production_use=false`, `production_ready=false` y `operational_alerting_enabled=false`. La información institucional recibida permanece candidata hasta revisión humana.

## Paridad v0.8

Los requisitos permitidos se toman de `config/v08_external_validation_contract.json`. El builder separa `potential_requirement_ids` de cada paquete, `unlocked_requirement_ids` atribuibles a ese paquete y `summary.actually_unlocked_requirements` como verdad global del ledger. Un paquete sólo recibe un `unlocked_requirement_id` cuando su `ledger_reference` coincide con una revisión `ACCEPTED` del ledger trazada al mismo `evidence_package_id`; el resumen global de requisitos desbloqueados se deriva únicamente del ledger y nunca del manifiesto.
