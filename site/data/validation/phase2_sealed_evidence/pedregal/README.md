# Pedregal — clean room de evidencia sellada

## Qué es esto

Este directorio es el contenedor del **clean room** de Pedregal: el mecanismo
que impide que evidencia de resultado (`outcome_bearing`) contamine el
emparejamiento de candidatos, el reranking, la selección de controles o la
adjudicación, antes de un *safe-unblind* explícitamente autorizado.

**El clean room protege la integridad del proceso, no la confidencialidad del
dato.** El archivo que hoy contiene el subárbol sellado de Pedregal
(`site/data/validation/phase2_research_evidence/ingemmet_chosica_santa_eulalia_2015.json`,
clave `pedregal.*`) sigue siendo legible por cualquiera con acceso normal al
repositorio — de eso no se protege. Lo que se protege es que ningún proceso de
matching, reranking, selección de control o adjudicación pueda leer ese
subárbol sin pasar por una autorización canónica, verificable y trazable.

## Estado actual — esqueleto vacío, intencional

- `manifest.json` tiene `entries: []` y `safe_unblind_authorized: false`.
- **No se ha migrado ningún dato sellado real a este directorio.** El
  contenido sigue físicamente donde está hoy; el manifiesto solo registrará,
  en una PR futura y separada, un puntero (`source_path` +
  `source_key_path` + hash de integridad) hacia él — nunca el contenido en
  sí.
- `config/pedregal_clean_room_authorized_consumers.json` tiene `consumers: []`.
  Hoy, ningún script está autorizado a leer evidencia sellada.

Esto es deliberado: la construcción de la infraestructura (manifiesto, lista
de consumidores, loader fail-closed, validador estático) se aprueba y se
fusiona antes de mover o registrar cualquier dato real.

## Cómo se autoriza un safe-unblind (cuando corresponda)

1. Se registra una decisión humana canónica y verificable —
   nunca solo una línea de `unblind_log` — en `manifest.json`, bajo
   `canonical_unblind_decision`: un identificador, el rol que decide, la
   fecha, y una referencia (`decision_record_ref`) a un registro que un
   tercero pueda verificar de forma independiente (un PR revisado, un acta de
   gobernanza publicada, una enmienda de protocolo pública).
2. Solo entonces `safe_unblind_authorized` puede pasar a `true`.
3. Un consumidor (script) solo puede leer evidencia sellada si aparece en
   `config/pedregal_clean_room_authorized_consumers.json` **y** su
   `canonical_decision_ref` coincide con el `decision_id` vigente en el
   manifiesto. Si cualquiera de las dos condiciones falta, el loader
   (`scripts/pedregal_clean_room_loader.py`) falla de forma cerrada.

## Qué NO hace este esqueleto

- No mueve, copia ni expone el contenido sellado real.
- No habilita ningún consumidor.
- No implementa el proceso de decisión de safe-unblind en sí (eso es un
  proceso humano/de gobernanza, fuera del alcance de esta PR).
- No cambia `activation_gate`, `decision_thresholds` ni ningún otro guardrail
  de IRFEN.
