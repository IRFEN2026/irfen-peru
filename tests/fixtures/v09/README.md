# Paquetes v0.9 congelados para pruebas de interfaz (TEST_ONLY)

Copias exactas comprimidas (gzip, sin modificar) de los paquetes **reales** confirmados en el HEAD `fea649ae` de #403:

| Archivo | Origen | SHA-256 descomprimido |
|---|---|---|
| `territory_v0_1_fea649ae.json.gz` | `site/data/v09/territory_v0_1.json` @ `fea649ae` | `17a9ca3bb7a6b821cfe9865ec91b3893c4c1f87a64f8dd6117e2bffa58228c57` |
| `dashboard_v0_1_fea649ae.json.gz` | `site/data/v09/dashboard_v0_1.json` @ `fea649ae` | `6c601f2b1b22ba8260299ad580ec3960a694ffb664074a860a557def845fbdcb` |

- **Datos:** evaluados el 28-10-2026 a las 16:10Z, con ventanas IMERG completas en las 22 zonas.
- **Uso:** solo dos pruebas de navegador de `tests/test_v09_territory.py`. Sus aserciones necesitan ventanas completas: «al día» o «parcial» en la portada, y «mm acumulados» que envejecen con el reloj.
- **Por qué congelados:** el paquete en vivo sigue a las fuentes reales. Tras una interrupción en la fuente, como la migración del ingest de NASA GES DISC del 28 al 30 de octubre de 2026, no tiene ninguna ventana completa y la interfaz lo dice correctamente. Eso no debe poner en rojo estas pruebas de interfaz.

No son observaciones actuales y nunca se publican. Si cambia el esquema del paquete, la prueba `Bundle::test_ui_fixtures_are_frozen_real_snapshots` falla y hay que regenerarlos desde un paquete confirmado con ventanas completas.
