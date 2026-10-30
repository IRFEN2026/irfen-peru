# IRFEN v0.9 · Primera validación histórica de crecidas: río Piura, Niño Costero 2017 (control 2018)

RESEARCH_ONLY / TEST_ONLY. Sin umbrales, sin alertas, sin capacidad predictiva declarada. Sigue el protocolo `qa/V09_FLOOD_VALIDATION_PROTOCOL_20261031.md` v0.1, fijado antes de calcular nada.

**Pregunta:** ¿contienen los acumulados de precipitación señales temporalmente útiles para explicar las crecidas observadas?

```bash
python scripts/v09_pechp_extract.py --check            # caudales y lluvias PECHP (dos lectores)
python scripts/v09_piura_2017_validation.py --check    # análisis + vista research/v09/piura_2017_validation.html
python -m unittest tests.test_v09_piura_2017_validation
# capturas (runner): scripts/v09_hist_sources_capture.py --stage pechp|emsr ; scripts/v09_imerg_final_daily_capture.py
```

## 1. Evidencias archivadas
| Fuente | Qué se obtuvo | Estado |
|---|---|---|
| **PECHP**, informes hidrometeorológicos mensuales (gob.pe; robots.txt respetado) | 16 PDF, enero–abril de 2016 a 2019, con SHA-256, más sus capas de texto de dos lectores independientes (`pdftotext -layout` y `pypdf`) | ✅ Archivado |
| Tablas diarias de caudal **en texto** (extraíbles) | Marzo y abril de 2017; enero a abril de 2018 (ríos); marzo y abril de 2018 (Ñácara/Tambogrande) | ✅ 100 % de las filas con dos lectores coincidentes |
| Tablas diarias **en imagen** | Enero y febrero de 2017, todo 2016 y todo 2019 | Se declaran `TABLA_EN_IMAGEN`; no se usan sin una lectura doble trazable. Hace falta OCR o transcripción visual, como en ANA 2016-17 |
| **IMERG Final V07 diario** (GPM_3IMERGDF) | 439 de 454 días: dic.–abr. de 2015-16, 2016-17 y 2017-18 | ✅ Comprobado: todo **V07B**, unidades `mm/day`, día interno = día del nombre en los 439, `precipitation_cnt` = 48 medias horas en todas las celdas, SHA-256 de cada gránulo |
| Días IMERG ausentes | 15 (31-12-2015 → 14-01-2016): fallo de descarga en dos intentos | Desconocido, no 0. No se reintenta más (política acotada). Solo afecta al antecedente del control de 2016 |
| **Copernicus EMS EMSR199** | API `public-activations`: **403** desde el runner (dos intentos, con y sin cabeceras de navegador). Página antigua y ZIP de productos: **404** | ⛔ **Bloqueado**. Hay que descargar a mano los paquetes vectoriales del portal (son públicos) y archivarlos. No se suplió con otra fuente |

**Extracción PECHP verificada:**
- **Checksum de la fuente:** la suma de las medias diarias de Sánchez Cerro en marzo de 2017 da **3 530,7 MMC**, igual a la masa que declara el informe.
- **Revisión visual:** la página 6 (días 23–31) coincide, incluido el pico del 27-03 de **2 754,5 m³/s**. El recorte está archivado en `visual_check_2017-03_p6_days23-31.png`.
- **Identidad de las columnas:** sale de las notas del propio informe: «(1) PUENTE SANCHEZ CERRO» y «(2) ESTACION EL PAPAYO».
- **Medias diarias frente a máximos instantáneos:** se separan.
  - Para el río Piura, los informes **no publican máximos instantáneos**; solo medias diarias.
  - Los instantáneos que aparecen son los del Chira, Macará y Quiroz (por ejemplo, El Ciruelo con 2 286,2 m³/s el 31-03-2017). Quedan para la línea Chira.
- **Incoherencias de la fuente, registradas sin corregir:**
  - el informe de abril de 2017 rotula el periodo enero–abril como «2016»;
  - El Papayo tiene **dos valores distintos** en dos tablas del mismo informe (abril de 2017 y abril de 2018). Se usa la tabla de ríos;
  - en marzo de 2018 aparece un caudal negativo impreso (−1,7 m³/s en El Papayo). Se conserva y se excluye del logaritmo;
  - hay celdas vacías (por ejemplo, Curumuy los días 21 y 22-03-2017). Quedan como `null`.

## 2. ¿Representa el polígono el área que drena a la estación? (protocolo §4)
**No puede establecerse.** Todos los resultados llevan la marca `POLIGONO_NO_EQUIVALENTE_A_LA_CUENCA_DE_LA_ESTACION`.
- La UH ANA 1378 (10 872 km²) incluye el Bajo Piura aguas abajo de Sánchez Cerro.
- No hay coordenadas oficiales de las estaciones ni una cuenca delimitada hasta cada una.
- Sánchez Cerro está regulado por la presa derivadora Los Ejidos y recibe el trasvase Chira→Piura. En marzo de 2017, Curumuy aportó 102,8 MMC y el canal Ejidos derivó 57,0 MMC, frente a 3 530,7 MMC que pasaron por Sánchez Cerro.
- En el control de 2018, Sánchez Cerro registró ≈ 3 MMC en marzo. El río estuvo casi seco en la ciudad mientras el trasvase aportaba 80,9 MMC: **la regulación domina en los años normales.**
- **Consecuencia:** solo se afirma una asociación temporal, no causalidad ni balance hídrico.

## 3. Resultados
**Lluvia IMERG (media de la UH 1378, mm):**

| Año | Dic. (año anterior) | Ene. | Feb. | Mar. | Abr. |
|---|---|---|---|---|---|
| 2016-17 | 22 | 74 | 201 | **559** | 68 |
| 2017-18 | 24 | 35 | 29 | 29 | 39 |
| 2015-16 | 2 | 57 (17 días) | 66 | 114 | 46 |

**Caudal medio diario máximo (PECHP):**
- **2017:**
  - Ñácara: 940 m³/s el 04-03;
  - Tambogrande: **2 676 m³/s el 26-03**;
  - Sánchez Cerro: **2 754,5 m³/s el 27-03** (desborde en la ciudad).
- **2018:** Tambogrande 194 m³/s y Sánchez Cerro 138 m³/s, ambos el 6–7 de abril.

**Desfase lluvia → caudal.** Correlación de Spearman entre la lluvia del día d y el caudal del día d+L, para L de 0 a 10 días; las curvas completas están en el JSON y en la vista. Ventana: enero–abril, solo los días con caudal y lluvia (61 días en 2017).

| Estación | 2017 · nivel | 2017 · **diferencias diarias** (sin tendencia estacional) | 2017 · sin ±3 días del pico | 2018 (control) · nivel | 2018 · diferencias |
|---|---|---|---|---|---|
| Ñácara (aguas arriba) | ρ 0,83 con L = 0 | **0,73 con L = 0** (≈ 0 con L ≥ 1) | 0,84 con L = 0 | 0,42 con L = 6 | 0,33 con L = 1 |
| Tambogrande | 0,73 con L = 0–1 | **0,58 con L = 0** | 0,72–0,74 con L = 0–1 | 0,43 con L = 6 | 0,23 con L = 1 |
| Sánchez Cerro | 0,86 con L = 1 | **0,42 con L = 1** (0,27 con L = 0) | 0,85 con L = 1 | 0,32 con L = 10 | 0,25 con L = 2 |

**Desfase entre estaciones (caudal → caudal):**
- 2017: Ñácara → Tambogrande, L = 0 (ρ 0,86); Tambogrande → Sánchez Cerro, L = 0 (0,91); Ñácara → Sánchez Cerro, L = 1 (0,90).
- 2018: L = 1 en todos los tramos (0,99 / 0,69 / 0,68).

**Cronología del episodio:** el acumulado de 3 días alcanza su máximo el **27-03** (desfase 0 con el pico de Sánchez Cerro) y el de 7 días el 26-03 (desfase 1).

**Pluviómetros PECHP frente a IMERG** (marzo de 2017; descriptivo, punto frente a área):
- **Volumen:** IMERG da 559 mm de media en la cuenca, frente a 1 155 mm en Chulucanas, 1 150 mm en Tambogrande y 456 mm en Piura. IMERG queda muy por debajo de los pluviómetros de la cuenca media y alta.
- **Desfase de día:** la correlación diaria es máxima cuando el día del pluviómetro se compara con el día UTC **siguiente** de IMERG (ρ 0,44–0,52). Sugiere que la fecha del pluviómetro corresponde a lluvia caída mayoritariamente en el día UTC siguiente, pero la convención no está declarada.

## 4. Lectura según el protocolo (§5.4)
- **(a) Desfase físicamente plausible (≥ 0): sí.** En 2017 el desfase aumenta aguas abajo: L = 0 en Ñácara y Tambogrande, L = 1 en Sánchez Cerro. Lo confirman las diferencias diarias, que eliminan la tendencia estacional común.
- **(c) No depende de un único día extremo: sí en 2017.** Excluyendo ±3 días alrededor del pico, ρ apenas cambia (0,72–0,85).
- **(b) Persiste en un control: no de forma robusta.**
  - En 2018 los caudales son pequeños y regulados.
  - La señal diaria es débil (ρ 0,23–0,33 en diferencias) y depende del repunte de abril.
  - Solo los acumulados largos (A10–A15) dan ρ ≈ 0,78–0,87 con L = 0–2. Al excluir el pico desaparece la señal de la lluvia diaria; para los acumulados no se ha calculado esa exclusión, así que no se les da peso.
- **Veredicto de esta fase:** en el episodio de 2017, la lluvia diaria IMERG sobre la cuenca del Piura contiene una **señal temporal coherente** con las crecidas observadas.
  - La respuesta es del mismo día en la cuenca media y de +1 día en la ciudad de Piura.
  - Con resolución diaria **no se puede resolver la propagación** entre estaciones: es de 0–1 día.
  - El control de 2018 **no confirma** la señal: con caudales bajos y regulados, la lluvia diaria explica poco.
  - **No es capacidad predictiva** ni una relación causal (§2).

## 5. Limitaciones y siguientes pasos
1. **Polígono hasta cada estación.** Hacen falta las coordenadas oficiales de Ñácara, Tambogrande y Sánchez Cerro (solicitud a PECHP/SENAMHI) y una delimitación reproducible con un modelo digital del terreno, declarada como no oficial.
2. **Más episodios y controles:**
   - transcribir con doble lectura las tablas en imagen (enero y febrero de 2017, 2016, 2019);
   - añadir 2023 (Yaku);
   - añadir años secos, para tener controles con caudales naturales.
3. **Resolución sub-diaria:** IMERG Final por media hora y niveles horarios, si PECHP o SENAMHI los facilitan, para medir la propagación de 0–1 día.
4. **Sesgo de volumen de IMERG:** comparar formalmente con los pluviómetros cuando haya coordenadas.
5. **EMSR199:** descarga manual de los vectores de las AOI de Piura. Debe conservarse, por producto, la fecha de adquisición, el sensor, la resolución y la fiabilidad.
6. **Chira y Tumbes** siguen como líneas distintas: requieren la cabecera ecuatoriana (polígono binacional y caudales de Macará y El Ciruelo, o INAMHI).
