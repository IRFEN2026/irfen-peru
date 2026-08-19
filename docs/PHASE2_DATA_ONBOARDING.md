# IRFEN — flujo único para incorporar nuevas zonas

## Objetivo

La expansión territorial usa un solo contrato y un solo pipeline para todas
las quebradas y sistemas fluviales. Esto permite cargar geometría, exposición,
eventos y fuentes en paralelo sin copiar lógica de los pilotos ni activar una
zona antes de validarla.

La v0.8 mantiene como únicos pilotos operativos en prueba a San Ildefonso,
Huaycoloro/Chosica y Catacaos/Bajo Piura. Todo lo descrito aquí permanece en
`RESEARCH_ONLY` y no modifica v0.7.1.

## Paquete mínimo por zona

Cada candidato tiene un archivo en
`site/data/validation/phase2_zone_contracts/`. Esta ubicación ya está incluida
en el disparador del workflow principal. El contrato
referencia seis activos independientes:

1. `geometry`: cuenca, quebrada, abanico o tramo oficial identificable.
2. `exposure`: centros poblados, carreteras, servicios, agricultura y aislamiento.
3. `historical_events`: días con evento verificado y controles sin evento.
4. `observations`: lluvia o estado hidrológico observado con procedencia y latencia.
5. `forecast`: pronóstico espacial y temporalmente comparable con la observación.
6. `hydraulic_context`: capacidad, defensas, obstrucciones u obras; sin factores inventados.

Los archivos de evidencia se guardan bajo `site/data/phase2/zones/<candidate_id>/`
y se enlazan con `path` desde el contrato. Un activo solo puede marcarse
`READY` si el archivo existe. `MISSING`, `CANDIDATE` y `PARTIAL` se publican
como brechas, nunca como bajo riesgo.

### Eventos de oportunidad todavía no verificados

Un reporte reciente puede ser útil antes de que la zona forme parte del
inventario. Se registra en `site/data/validation/phase2_event_intake/` sin
suponer el nombre de la quebrada, las coordenadas ni la hora. El generador
`scripts/build_phase2_event_catalog.py` bloquea el reanálisis hasta contar con
identidad espacial y temporal y una fuente oficial específica del evento.

Una vez verificado, el caso permite comparar IMERG 3/6/24 h y el forecast GEOS
contra la observación. Sigue siendo `RESEARCH_ONLY`: no cuenta para el cierre
v0.8, no activa una zona, no deriva umbrales y no transfiere factores
hidráulicos. Las fuentes que solo describen el contexto territorial deben
marcarse explícitamente como incapaces de confirmar el evento.

Los eventos urbanos de lluvia que no correspondan a una quebrada, huaico o
torrente se etiquetan `METEOROLOGICAL_REFERENCE_EVENT`. Sirven exclusivamente
para validar ingestión, continuidad y acumulados de precipitación. No son
evidencia de respuesta hidrológica o hidráulica, no entrenan activaciones y no
se incorporan al inventario territorial. Villa El Salvador pertenece a este
carril meteorológico de referencia.

### Corridas con cuencas análogas cuando falta historia local

La falta de eventos históricos locales no detiene la preparación, pero tampoco
autoriza a copiar un umbral. El contrato
`config/phase2_analog_transfer_contract.json` permite únicamente escenarios y
pruebas de sensibilidad en `RESEARCH_ONLY`:

1. comparar más de una cuenca donante por geometría, pendiente y tiempo de
   respuesta, geología/suelo, cobertura, drenaje, climatología y obras;
2. transferir la firma completa de eventos verificados: intensidad, acumulados
   3/6/24 h, lluvia antecedente 24/72 h y 7 días, forma del hietograma y estado
   antecedente;
3. normalizar contra la climatología, geometría y representatividad satelital o
   pluviométrica del objetivo;
4. conservar separados los mecanismos: una quebrada de flujo de detritos no
   valida por sí sola el desborde de un río, que además requiere nivel/caudal,
   capacidad actual, defensas, obstrucciones y tiempo de tránsito;
5. etiquetar la salida `ANALOG_TRANSFER_TEST_ONLY`, con validación local,
   alerta operacional y promoción de umbrales deshabilitadas.

Una ausencia de reporte no se clasifica como día `NONE`. La validación local
continúa bloqueada hasta contar con un evento u observación local revisada por
una persona responsable.

## Secuencia eficiente

1. Registrar el candidato y sus fuentes oficiales en
   `config/phase2_candidate_inventory_v0_1.json`.
2. Generar el contrato bloqueado con:
   `python scripts/build_phase2_catalog.py --bootstrap`.
3. Cargar los seis activos por carriles independientes; no es necesario esperar
   a que termine uno para investigar los demás.
4. Actualizar el estado del activo y su `path` únicamente cuando la evidencia
   correspondiente exista y sea trazable.
5. Ejecutar `python scripts/build_phase2_catalog.py`. El pipeline rechaza
   activación, umbrales, factores hidráulicos y la equivalencia “sin datos = bajo riesgo”.
6. Abrir revisión científica, hidrológica/hidráulica y de resultado local.
7. Mantener la puerta `BLOCKED` incluso con contrato completo. La futura
   activación exige un proceso de promoción separado y explícito.

Para eventos de oportunidad, ejecutar
`python scripts/build_phase2_event_catalog.py` después de actualizar su ficha.
El catálogo resultante queda en `site/data/phase2/research_events.json`.

## Trabajo paralelo recomendado

- Carril A — geometría y mecanismo: ANA, INGEMMET y CENEPRED.
- Carril B — eventos e impactos: INDECI, COEN y autoridades regionales/locales.
- Carril C — observación y forecast: SENAMHI, IGP, IMERG y GEOS.
- Carril D — exposición y respuesta: centros poblados, vías, servicios y aislamiento.
- Carril E — hidráulica: obras actuales, capacidad, mantenimiento y puntos críticos.

El catálogo generado en `site/data/phase2/catalog.json` permite ver qué carril
falta en cada zona sin convertir preparación documental en una alerta.

### Cartografía secundaria de GEO GPS Peru

La página de GEO GPS Peru sobre ríos y quebradas es útil como índice y espejo
de capas que atribuye a GEOANA/ANA 2023. IRFEN la registra como
`RESEARCH_ONLY_REFERENCE_PENDING_PRIMARY_VERIFICATION`, no como fuente oficial.
La red lineal puede ayudar a normalizar nombres, revisar conectividad y proponer
puntos de salida para una corrida DEM. Los límites publicados pueden servir
como comparación de cuenca o subcuenca, pero no sustituyen una delimitación
reproducible ni validan una microcuenca local.

Antes de incorporar cualquier geometría se exige localizar el endpoint o
publicación original de ANA, documentar licencia, fecha, CRS y esquema, calcular
checksums, revisar topología y confirmar la cuenca y el outlet con dirección y
acumulación de flujo del DEM. Mientras falte cualquiera de esos controles, la
capa no cuenta para validación, no habilita mapas operativos y no permite crear
umbrales o factores hidráulicos. La evaluación auditable está en
`site/data/phase2/source_assessments/geogpsperu_hydrography.json`.

## Automatización reutilizada

No se necesita un workflow privilegiado adicional. El flujo vigente queda así:

1. Un cambio en `site/data/validation/**` activa `update-and-deploy.yml`.
2. La suite unitaria existente importa el generador, valida todos los contratos
   y comprueba que el catálogo confirmado coincide con ellos.
3. La regresión v0.8 y sus guardas se ejecutan sin alterar el alcance de los pilotos.
4. El publicador existente despliega el sitio completo y el smoke test conserva su cobertura.

5. `python scripts/build_map_layer_catalog.py` reconstruye el manifiesto de
   capas, hashes y trazabilidad. Una zona sin archivo geométrico reproducible
   permanece fuera del mapa; no se sustituye por un punto aproximado.

Un contrato inválido o un catálogo no regenerado detiene el pipeline. Un contrato
válido únicamente actualiza la visibilidad de las brechas; nunca habilita alertas
ni altera los pilotos v0.8. La vista pública independiente queda en
`/irfen-peru/expansion.html`.

## Cola territorial registrada

El pipeline mantiene contratos para los 18 sistemas del inventario actual.
La secuencia de desarrollo, sin puntaje de riesgo, está en
`config/phase2_map_priority_v0_1.json`; el modelo cartográfico y la auditoría
de incorporación están en `docs/PHASE2_MAP_LAYER_MODEL.md`.

Esta lista es una cola de investigación equilibrada, no una declaración de
prioridad definitiva. La puntuación permanece retenida hasta normalizar la
evidencia y resolver cada sistema hasta una geometría y mecanismo concretos.
