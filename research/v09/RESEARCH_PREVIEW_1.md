# IRFEN v0.9 — Research Preview 1 (versión privada congelada, 01-11-2026)

**RESEARCH_ONLY / TEST_ONLY.**
- No es un sistema de alerta y no predice crecidas, huaicos ni inundaciones.
- No se ha fusionado en `main` ni se ha publicado al público general.
- Las notificaciones y el motor predictivo están desactivados.
- La puerta de Pages retira esta vista.

| | |
|---|---|
| Etiqueta git | `irfen-v0.9-research-preview-1` (anotada; el SHA del commit está en el mensaje de la etiqueta y en el PR) |
| PR | #464 (borrador, rama `integration/v09-private-surveillance-view-20261101`) |
| Manifiesto | `research/v09/RESEARCH_PREVIEW_1_MANIFEST.json`, con el SHA-256 de cada archivo publicado y de sus datos de entrada |
| Copia privada alojada | Página privada de claude.ai «Vigilancia costera IRFEN», propiedad de la cuenta del propietario. Es una comodidad, **no la fuente de verdad**. |

## Fecha del último dato (UTC)

| Fuente | Último dato |
|---|---|
| Avisos SENAMHI vía INDECI/COEN | Última comprobación correcta: **2026-11-01 16:47** |
| IMERG Early, 22 zonas del norte | Ventanas que terminan el **2026-11-01 09:00** |
| IMERG Early, costa Tumbes–Tacna | Instantánea con ventanas que terminan el **2026-11-01 12:00** (capturada a las 17:19) |
| Límites INEI (SERFOR) | Obtenidos el 2026-11-01 17:19 |
| Histórico de caudales PECHP | Medias diarias de 2017 a 2023 (24 meses) |

Cuando estos datos superan su antigüedad máxima, la página lo indica:
- muestra el aviso «Datos congelados, no actuales»;
- marca en rojo los chips de cada fuente;
- advierte que los avisos emitidos después no aparecen.

## Cómo abrirla sin depender del enlace de Claude

**A. Archivo único, sin servidor**
1. Abrir `research/v09/private_demo/irfen_vigilancia_privada.html` en un navegador. Lleva los datos y la hoja de estilos de Leaflet incrustados y solo descarga `leaflet.js` de unpkg, con verificación SRI.
2. Comprobar su SHA-256 con el del manifiesto:
   ```bash
   sha256sum research/v09/private_demo/irfen_vigilancia_privada.html
   ```

**B. Versión completa, con mapa base OSM y enlaces a las otras páginas v0.9**
```bash
git clone https://github.com/IRFEN2026/irfen-peru && cd irfen-peru
git checkout irfen-v0.9-research-preview-1
python scripts/v09_build_surveillance_view.py --check        # paquete idéntico byte a byte
python -m http.server 8000 --bind 127.0.0.1 --directory site  # http://127.0.0.1:8000/v09/vigilancia.html
```

**C. Reconstruir el archivo único**
```bash
curl -sSLo /tmp/leaflet.css https://unpkg.com/leaflet@1.9.4/dist/leaflet.css
python scripts/v09_build_surveillance_demo.py --leaflet-css /tmp/leaflet.css   # se detiene si el hash SRI no coincide
sha256sum research/v09/private_demo/irfen_vigilancia_privada.html              # debe coincidir con el manifiesto
```

**D. Comprobar la versión**
```bash
python -m unittest tests.test_v09_surveillance_view           # incluye la comprobación de hashes del manifiesto
python qa/replay_tools/v09_surveillance_view_smoke.py --out /tmp/smoke   # escritorio y móvil (Playwright y Chromium)
```

## Limitaciones conocidas

1. La lluvia de la costa centro y sur es una **instantánea**: no se actualiza. Solo el norte tiene archivo continuo, y solo en `main`.
2. IMERG Early es una estimación satelital con horas de latencia, sin validación local. No es un pluviómetro.
3. No hay caudal ni nivel en tiempo real, ni avisos hidrológicos de SENAMHI. Las crecidas de ríos solo tienen histórico (medias diarias PECHP) y resultados experimentales. La anticipación horaria es NO_EVALUABLE.
4. Avisos:
   - el nivel aparece solo cuando está escrito en el texto reproducido;
   - la relación con los departamentos es administrativa, no la huella del fenómeno.
5. GloFAS no está integrado y no hay datos de inundación pluvial urbana observada.
6. Las geometrías de quebradas solo cubren la costa norte y el Rímac. Los 619 centros poblados ANA son ubicaciones documentales, no quebradas.
7. Las cuencas binacionales son experimentales (HydroSHEDS), no oficiales.
8. Los enlaces externos (boletines INDECI, notas PECHP, artículos) no se han verificado desde el entorno de esta auditoría.
9. La versión de un solo archivo no carga mapa base y depende de unpkg para `leaflet.js`.

## Qué impide un uso público

Decisión posterior del propietario. Requiere:
- QA humana independiente;
- abrir la puerta de Pages;
- un acuerdo de atribución con INDECI/COEN y SENAMHI;
- un alojamiento con control de acceso o una revisión legal y de comunicación;
- lluvia continua en toda la costa;
- caudales en tiempo real.
