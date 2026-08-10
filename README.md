# IRFEN Perú v0.5

MVP operativo para combinar precipitación NASA GPM IMERG Late Daily con un indicador de prioridad territorial.

## Qué hace
- Busca automáticamente `GPM_3IMERGDL`.
- Intenta versión 08 y usa 07 como fallback.
- Descarga los últimos días disponibles con `earthaccess`.
- Promedia precipitación sobre áreas configurables por zona.
- Calcula lluvia de 24 h, 72 h y 7 días.
- Genera `site/data/latest.json`.
- Publica `site/` mediante GitHub Pages.

## Seguridad
NO subas el token Earthdata al repositorio.

En GitHub:
1. Settings
2. Secrets and variables
3. Actions
4. New repository secret
5. Nombre: `EARTHDATA_TOKEN`
6. Valor: tu Bearer Token de Earthdata

## Activar GitHub Pages
Settings > Pages > Build and deployment > Source > GitHub Actions.

Después: Actions > IRFEN — Actualizar IMERG y publicar > Run workflow.

## Prueba local sin NASA
```bash
pip install -r requirements.txt
python scripts/fetch_imerg.py --demo
python -m http.server 8000 --directory site
```

## Advertencia científica
Las cajas espaciales de `config/zones.json` son aproximaciones provisionales. El próximo paso científico es sustituirlas por polígonos reales de microcuencas y calibrar los umbrales con SENAMHI/eventos históricos.
