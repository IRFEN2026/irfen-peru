# IRFEN v0.9 · Vista privada unificada de vigilancia costera (01-11-2026)

PR de integración en borrador **#464**, rama `integration/v09-private-surveillance-view-20261101`, apilada sobre #462 (y por tanto sobre #403 → #455 … #461).
RESEARCH_ONLY / TEST_ONLY. Sin fusión en `main`, sin publicación general, sin notificaciones, sin alertas y con el motor predictivo desactivado.

## 1. Estado de los PR revisados

| PR | Contenido | Papel en la integración |
|---|---|---|
| #403 | Visor territorial, inventario, portada y navegación v0.9 | Base de la pila. Se reutilizan `peru.html`, `territorio.html`, `inventario.html`, `nav.js`, sus paquetes y la puerta de Pages |
| #455 | Revisión visual de las filas ANA 2016-17 | Centros poblados ANA admitidos (619) |
| #456 | UH ANA y asociación con centros poblados | Polígonos de las UH del norte |
| #457 | Lluvia IMERG por UH | Superado para la vista por el archivo continuo de `main` (más reciente) |
| #458 / #459 | Validación del río Piura 2017/2023, cuencas y robustez | Histórico PECHP y resultados experimentales (texto) |
| #460 | Viabilidad de la anticipación (v0.3) | Estado NO_EVALUABLE, estaciones y cuencas binacionales |
| #461 | Verificación de vías de acceso hidrométricas | Solo documentación; sin cambios de código |
| #462 | Laboratorio norte con datos gratuitos | Página de investigación aparte; no la usa la vista. GloFAS sigue pendiente |

- **Dependencias:** la pila es lineal (cada PR tiene como base el anterior) y todos están limpios.
- **Conflictos:** la fusión de `main` (71 commits, solo del bot) entró sin conflictos.
- **Investigaciones:** no se ha repetido ninguna.

## 2. Qué se ha construido

**`site/v09/vigilancia.html`** (cargada desde `site/data/v09/surveillance_view_v0_1.json`, de 0,85 MB)

**Mapa de toda la costa:**
- 11 departamentos y 77 provincias INEI (límites censales referenciales, servicio SERFOR);
- lluvia IMERG Early en 1, 3, 6, 24 y 72 h:
  - 2 215 celdas de 0,1° sobre los 11 departamentos (instantánea);
  - 22 zonas del norte (archivo continuo de `main`);
  - una ventana incompleta no se dibuja y nunca se muestra como cero;
- UH ANA, estaciones hidrométricas documentadas, geometrías IRFEN de quebradas y centros poblados ANA.

**Pestañas:**
- **Resumen**, con una tabla por departamento: avisos vigentes y próximos, lluvia media y máxima, centros ANA, inventario y crecidas.
- **Lluvia**.
- **Avisos**:
  - de SENAMHI reproducidos por INDECI/COEN, con enlace al boletín;
  - el estado se calcula al abrir la página;
  - el nivel solo aparece si está escrito;
  - se pueden resaltar en el mapa los departamentos enumerados.
- **Crecidas de ríos**: histórico PECHP 2017–2023 en gráfico, eventos documentados, resultados de #458–#460 y cuencas binacionales experimentales.
- **Quebradas**.
- **Datos y vacíos**.

**Separación explícita** de crecida de ríos, inundación pluvial y activación de quebradas.

**Chips de frescura:** antigüedad por fuente; los datos antiguos se marcan en rojo y una fecha futura figura como «fecha no válida».

**Versión de un solo archivo:** `research/v09/private_demo/irfen_vigilancia_privada.html`, generada por `scripts/v09_build_surveillance_demo.py`. Incluye los datos y la hoja de estilos de Leaflet, verificada con su hash SRI; no carga mapa base externo.

## 3. Pruebas

- `tests/test_v09_surveillance_view.py`, 14 OK:
  - guardas y reproducibilidad byte a byte;
  - cobertura de Tumbes a Tacna;
  - ventanas sin ceros inventados;
  - atribución de avisos;
  - los tres fenómenos y los vacíos;
  - histórico solo como media diaria medida;
  - puerta de Pages;
  - recorrido en navegador de escritorio y móvil.
- **Regresión:** territory (con el ajuste de aislamiento documentado), dashboard_data, pages_publication_gate, ana2017_coastal_points, anticipation_feasibility, piura_*, hydro_association y uh_rain_context, todas OK.
- **Constructores:** `v09_build_territory_bundle.py`, `v09_build_inventory_view.py` y `v09_build_dashboard_data.py` dan `--check` OK sobre los datos fusionados.
- **Navegador:** 0 errores JS y 0 enlaces internos rotos, sin desbordamiento horizontal a 1440×900 ni a 390×844, y 79 avisos con «Ver en el mapa».

## 4. Datos reales disponibles

- Avisos INDECI/COEN: captura continua de `main`; última comprobación el 01-11-2026 16:47 UTC.
- IMERG Early norte: 22 zonas, ventanas de 1 a 72 h hasta el 01-11-2026 09:00 UTC.
- IMERG Early costa: instantánea de las 12:00 UTC del 01-11-2026, todas las ventanas completas.
- Límites INEI, centros poblados ANA 2016-17, inventario (400 filas) y geometrías IRFEN (53).
- Histórico PECHP: medias diarias de 24 meses entre 2017 y 2023.
- UH ANA y estaciones documentadas.

## 5. Pendiente

- Caudal y nivel en tiempo real o subdiario: hay solicitudes en borrador, no enviadas.
- Avisos hidrológicos de SENAMHI.
- IMERG continuo en la costa centro y sur.
- GloFAS.
- Inundación pluvial observada.
- Geometrías de quebradas fuera de la costa norte y el Rímac.
- Delimitación binacional oficial.

## 6. Qué impide un uso público

1. No hay validación hidrológica ni QA humana independiente de la vista, y la puerta de Pages está cerrada (`publish_v09_*` no están en `true`).
2. Falta un acuerdo de atribución y uso con INDECI/COEN y SENAMHI para reproducir avisos ante el público.
3. La lluvia es una estimación satelital con horas de latencia y sin validar localmente. La costa centro y sur depende de una instantánea.
4. Faltan caudales en tiempo real y avisos hidrológicos, así que no hay vigilancia de crecidas de ríos propiamente dicha.
5. El repositorio es público: un enlace público controlado exige un alojamiento con control de acceso (Cloudflare Access, Vercel Authentication) y la decisión del propietario.
6. Hay revisión legal y de comunicación pendiente. La interfaz evita el lenguaje de alerta, pero un uso público necesita un protocolo de comunicación con las autoridades.
