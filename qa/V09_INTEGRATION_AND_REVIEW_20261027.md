# v0.9 mapa privado: integración #417 → #403, CI sin bucle y revisión (27-10-2026, RESEARCH_ONLY / TEST_ONLY)

Rama `integration/v09-territory-private-map-20261022` (PR #403).
- Sin merge en `main`, sin publicación y sin activaciones.
- `publish_v09_dashboard=false` y `publish_v09_territory` sin valor.

## A. Integración
| Commit | Qué |
|---|---|
| `5682ba90` | #417 sin cambios, por avance rápido (no se reescribe ningún commit). Datos con fecha posterior al reloj, nunca actuales; QA R1 cerrada ante zonas sin polígono. |
| `4c7f9896` | Fusión de `main` `6e2b9f0f`: 146 commits, todos de github-actions[bot] (datos de lluvia, avisos y evidencias), sin conflictos. Los datos de `main` se conservan byte a byte: `zone_rain_state`, registro de avisos, `dashboard_v0_1.json` y la puerta. |
| `18c44f49` | Paquete territorial reconstruido desde los datos actuales de `main` (`--check` OK). |
| `e48d6a38` | QA privada integrada de solo lectura (sección D). |
| siguiente | Este documento y `qa/replay_tools/v09_local_review_smoke.py`. |

El manifest pytest no cambia: no se añaden funciones de prueba (la nueva regresión amplía una existente) y el de `main` no ha cambiado desde la base de #403.

## B. QA (local, Python 3.13 + Chromium de Playwright)
**Suite v0.9: 96 pruebas OK** (`test_v09_territory`, `test_v09_territory_independent_qa`, `test_v09_pages_publication_gate`, `test_v09_continuity_evidence`, `test_v09_dashboard_browser`, `test_v09_demo_summary`, `test_v09_rule_parity`, `test_v09_zone_rain_engine`, `test_v08_recent_advances`, `test_v08_map_panels`, `test_map_semantic_consolidation`).
- Las 11 omitidas son las de navegador v0.8 de `test_v08_map_panels`, que necesitan Leaflet; en local no hay red.

**Controles:**
- Motor `--check` OK: 22 zonas.
- Paquete `--check` OK.
- QA independiente 6/6 PASS.

**Suite amplia, archivo por archivo, sobre la cabeza integrada y sobre `main`:** mismos resultados en todos los archivos comunes.
- 12 archivos fallan igual en los dos árboles por el entorno (`shapely` o `pyproj` no instalados; `test_v08_territorial_inventory`).
- 98 son de estilo pytest y se ejecutan en el CI.

**Lo que fijan las pruebas de #417 y #403:**
- Una observación con fecha posterior no cuenta como actual ni como «sin señal».
- Una edad negativa nunca da verde.
- Un dato ausente o antiguo se raya («no es lluvia cero»).
- Las ventanas IMERG parciales o contradictorias son PARCIAL o UNKNOWN.
- Una zona sin polígono registrado no puede colorear otra geometría.
- Solo se dibujan geometrías admitidas o verificadas.
- `map_publishable=false`.

## C. Mapa: revisión en navegador
`python qa/replay_tools/v09_local_review_smoke.py`, en escritorio 1440×900 y móvil 390×844:
- 0 errores JS, 0 recursos locales ausentes y 0 peticiones externas;
- sin desbordamiento horizontal y sin «hace -»;
- navegación panel ⇄ visor;
- 6 capas: el mapa pasa de 37 a 0 y a 37 trazos al apagarlas y encenderlas;
- fichas en las dos regiones (2 y 7 quebradas), con lo que falta;
- leyenda y resumen por zona (5);
- inventario consultable: 309 registros, «publicables en mapa: 0», filtro de geometría reproducible = 3 y búsqueda funcional;
- 3 capas pendientes.

**Las tres categorías:**

| Categoría | En #403 | Con datos actuales |
|---|---|---|
| Primaria: geometría reproducible con procedencia | Capas dibujadas (oficial / documental / derivada / candidata DEM, con su trazo) y filtro «geometría reproducible» | 62 trazos: 43 oficiales, 10 candidatos DEM, 7 ubicaciones documentales, 2 derivados. 3 filas del inventario con geometría reproducible. Ninguna apta para alerta ni publicable. |
| Secundaria: identidad documental sin geometría | Filas del inventario `INVENTARIADO` con `PENDIENTE` / `SIN_GEOMETRIA`, sin trazado | 306 (17 + 289) |
| Terciaria: candidato sin GIS | `CANDIDATO_NO_INTEGRADO`, solo en listados | 0: el visor lo admite, pero solo lo puebla el ledger de #378, que no está en `main` |

**Cómo incorporar #418 y #404 sin fusionarlos (no implementado aquí):**
1. Cuando #418 esté en `main`, el constructor del paquete podría leer `data/phase2/inventory_reconciliation/reconciliation_main_v0_1.json` de solo lectura: tabla `rows` y hallazgos.
2. Las filas de un delta (p. ej. r8 de #404) entrarían solo como `CANDIDATO_NO_INTEGRADO`, con `geometry=SIN_GEOMETRIA` y `map_publishable=false`.
3. Cada fila llevaría sus hallazgos (`CROSS_PR_OVERLAP`, `POTENTIAL_ALIAS`, `UNNAMED_IDENTITY_UNRESOLVED`…).
4. Pruebas necesarias:
   - ninguna geometría nace de un candidato;
   - ningún candidato es publicable;
   - los ids que solapan con el maestro no se duplican;
   - el informe de entrada coincide con su `comparable_sha256`.

## D. CI: `action_required`
**Causa verificada.**
- El último paso de `v09-private-integrated-qa.yml` hacía commit y push como github-actions[bot].
- Esa cabeza dejaba los tres workflows `pull_request` de #403 en `action_required` con 0 jobs, a la espera de aprobación de alguien con escritura.
- Ocurrió en las tres cabezas del bot (`c8bbc4c0`, `9cc67615`, `b1c32bf3`); las cabezas humanas se ejecutaron.
- No es un fallo de código. Las ejecuciones antiguas de `b1c32bf3` (39819184714 / 39819184721 / 39819184798) quedan obsoletas: ya no son la cabeza.

**Solución (`e48d6a38`).**
- `permissions: contents: read`; sin `git config` / `commit` / `push`.
- Manifest verificado sin reescribirlo; guardas completas.
- Paquete reconstruido desde la lluvia de `main`, comparado con el confirmado (aviso si difiere) y subido como artefacto de 14 días.
- Falla si la QA modifica otros archivos rastreados.
- `tests/test_v09_territory.py::Isolation` falla si el workflow vuelve a escribir.
- No se eludió ninguna aprobación: la cabeza nueva la sube una persona.

**Pendiente del propietario.** Ninguna aprobación es necesaria para las cabezas humanas. Si en el futuro otro workflow sube commits a la rama, cada ejecución del PR volverá a pedir aprobación: es el comportamiento de seguridad de GitHub.

## E. Revisión y publicación
**1. Revisión local (disponible ya, sin alojamiento):**
```bash
git clone https://github.com/IRFEN2026/irfen-peru && cd irfen-peru
git checkout integration/v09-territory-private-map-20261022
python -m http.server 8000 --bind 127.0.0.1 --directory site
# http://127.0.0.1:8000/v09/index.html   y   http://127.0.0.1:8000/v09/territorio.html
python qa/replay_tools/v09_local_review_smoke.py   # opcional: misma revisión automatizada (Playwright)
```
Todo el contenido de la rama ya es público en el repositorio: la privacidad del mapa evita presentarlo como producto, no oculta datos.

**2. Publicación protegida (pendiente de autorización y de la cuenta del propietario; no ejecutada):**
1. Proyecto Cloudflare Pages con subida directa solo de `site/` desde una copia local de la rama. Nunca desde Actions con credenciales en el repositorio; los secretos van en el panel del proveedor, nunca en la conversación.
2. Settings → General → **Enable access policy** protege las vistas previas.
3. Para proteger también `*.pages.dev`, quitar el comodín del subdominio en la aplicación Access. Deben quedar dos políticas: dominio y vistas previas.
4. Un dominio propio necesita su propia aplicación self-hosted en Zero Trust.
5. Política: lista de correos de revisores (incluir, no «everyone») con PIN de un solo uso.

**Verificación:**
- Sin sesión, `curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' https://<proyecto>.pages.dev/v09/index.html` debe dar **302** hacia `https://<equipo>.cloudflareaccess.com/...` (o 401/403), **nunca 200**.
- Repetir con una URL de vista previa y con `.../data/v09/territory_v0_1.json`.
- Con sesión de un correo autorizado en el navegador: 200 y la misma revisión de la sección C.
- Con un correo no autorizado: rechazo.

**3. Publicación pública: no autorizada.**
- La puerta de Pages sigue cerrada y la ejecutan `update-and-deploy` y `publish-committed-data`.
- GitHub Pages de este repositorio público es siempre público.

## F. Decisión
**QA_PARTIAL.**
- La integración y la QA local están completas.
- Para aceptar falta:
  1. el CI de la cabeza final de #403 (`validate`, navegador y QA privada integrada nueva) en verde, sin omisiones;
  2. la revisión independiente de un humano sobre el mapa local;
  3. que el propietario decida si integra en `main` y si autoriza la publicación protegida.
