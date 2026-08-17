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

Cada candidato tiene un archivo en `config/phase2_zone_contracts/`. El contrato
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

## Trabajo paralelo recomendado

- Carril A — geometría y mecanismo: ANA, INGEMMET y CENEPRED.
- Carril B — eventos e impactos: INDECI, COEN y autoridades regionales/locales.
- Carril C — observación y forecast: SENAMHI, IGP, IMERG y GEOS.
- Carril D — exposición y respuesta: centros poblados, vías, servicios y aislamiento.
- Carril E — hidráulica: obras actuales, capacidad, mantenimiento y puntos críticos.

El catálogo generado en `site/data/phase2/catalog.json` permite ver qué carril
falta en cada zona sin convertir preparación documental en una alerta.

## Primera ola registrada

El pipeline prepara contratos para los diez sistemas del inventario inicial:
Lima norte (Huerta Vieja, Arahuay/Chillón y Lampián), Lima sur/Sur Chico
(Malanche y Chilca–Pucusana), Ica/Pisco (Pisco–San Andrés y
Palpa–Changuillo), Lambayeque (Chongoyape–Oyotún–Zaña y
Motupe–La Leche–Pítipo) y Acarí/San Agustín en Arequipa.

Esta lista es una cola de investigación equilibrada, no una declaración de
prioridad definitiva. La puntuación permanece retenida hasta normalizar la
evidencia y resolver cada sistema hasta una geometría y mecanismo concretos.
