# IRFEN v0.8 — expediente de cierre

Release status: BLOCKED

Este documento prepara el expediente auditable de IRFEN v0.8. No declara una
liberación operativa ni autoriza alertas públicas. Todo el alcance de v0.8 se
mantiene en `TEST_ONLY`, con `production_use=false` y sin sustituir la alerta
oficial de SENAMHI, ANA, COEN/INDECI o las autoridades locales.

## Alcance invariable

- San Ildefonso (Trujillo).
- Huaycoloro/Chosica, incluidos sus submodelos declarados.
- Catacaos/Bajo Piura.

La expansión territorial posterior permanece `RESEARCH_ONLY` y no forma parte
de esta liberación. La versión v0.7.1 se conserva como referencia protegida.

## Evidencia ya cerrada

- Automatización, publicación, smoke test y regresión con guardas `TEST_ONLY`.
- Continuidad y latencia observada de IMERG Early, con ventanas 3/6/24 horas.
- Pares maduros forecast GEOS–observación para los tres pilotos.
- Contratos de validación completos o con bloqueos externos explícitos.

La evidencia cuantitativa vigente se publica en
`site/data/v08_scorecard.json`; este documento no duplica cifras que cambian
con cada corrida.

## Bloqueos que impiden cerrar

1. Completar la muestra mínima de días en sombra revisados y elegibles,
   incluyendo los mínimos de días `EVENT` y `NONE` definidos en el contrato.
2. Resolver con evidencia los bloqueos hidráulicos de San Ildefonso y Chosica,
   y validar en vivo el submodelo local de Pedregal.
3. Resolver para Catacaos la capacidad actual del cauce/planicie y el acceso
   numérico oficial al estado del río, o documentar una alternativa validada
   conforme al contrato. La ausencia de datos nunca se interpreta como caudal
   nulo ni bajo riesgo.
4. Ejecutar la auditoría final después de que los tres puntos anteriores estén
   satisfechos.

## Regla de firma

El marcador de cierre solo puede incorporarse después de que la scorecard
confirme simultáneamente la evidencia en sombra, la resolución científica e
hidráulica y la regresión satisfactoria. La mera existencia de este expediente
no suma porcentaje ni elimina bloqueos.

## Lista de auditoría final

- [ ] Scorecard en 100% por evidencia, sin excepciones manuales.
- [ ] Smoke test público y regresión en verde sobre el commit candidato.
- [ ] Los tres pilotos siguen siendo los únicos del alcance v0.8.
- [ ] Todas las recomendaciones siguen en `TEST_ONLY`.
- [ ] Ningún umbral o factor hidráulico fue promovido sin respaldo trazable.
- [ ] Días en sombra revisados conforme al protocolo y con fuentes archivadas.
- [ ] Bloqueos científicos e hidráulicos cerrados con evidencia enlazada.
- [ ] Sitio publicado verificado después del despliegue final.
- [ ] Notas de versión y limitaciones revisadas.

## Reversión

Ante una regresión, inconsistencia de datos o pérdida de trazabilidad, se debe
detener la promoción del candidato, mantener v0.7.1 intacta y conservar v0.8 en
modo experimental hasta repetir la auditoría completa.
