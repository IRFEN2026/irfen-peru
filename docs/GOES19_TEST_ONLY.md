# GOES-19 RRQPE — contrato de evaluación `GOES_TEST_ONLY`

GOES-19 es el satélite **GOES-East operado por NOAA/NESDIS**, no por el
Estado peruano. SENAMHI publica y utiliza imágenes GOES, pero la fuente
numérica conectada aquí es el bucket público oficial de NOAA.

El producto `ABI-L2-RRQPEF` estima tasa de lluvia en `mm h-1`, a 2 km en el
nadir y con barrido nominal de disco completo cada 10 minutos. IRFEN lo prueba
por su menor latencia y mayor detalle espacial potencial frente a IMERG. No lo
trata como verdad de terreno: deriva lluvia de propiedades de las nubes y puede
subestimar, omitir o atribuir lluvia que no llega a superficie.

## Aislamiento obligatorio

- `production_use=false` y `production_ready=false`.
- No sustituye IMERG, estaciones, partes oficiales ni estado fluvial.
- No modifica umbrales, factores hidráulicos, prioridad, riesgo o alertas.
- Un faltante o una tasa de 0 mm/h no significa ausencia de peligro.
- No suma evidencia a la scorecard v0.8.
- Solo cubre los tres pilotos v0.8 para evaluar la fuente; no activa zonas.

## Decisión de conservar o descartar

Se conserva provisionalmente mientras se acumula evidencia en sombra. Un probe
horario permite iniciar la revisión de disponibilidad con 72 registros (tres
días): se descarta el canal si la
disponibilidad es menor a 80% o la latencia p90 supera 30 minutos. La utilidad
científica requiere comparaciones co-localizadas con IMERG, casos de lluvia o
activación oficialmente verificados y controles sin evento revisados por una
persona. Si no añade señal espacial o temporal reproducible, se descarta.

Fuentes oficiales: [NOAA Enterprise Rain Rate](https://www.ospo.noaa.gov/products/atmosphere/err/)
y [NOAA GOES Open Data](https://registry.opendata.aws/noaa-goes/).
