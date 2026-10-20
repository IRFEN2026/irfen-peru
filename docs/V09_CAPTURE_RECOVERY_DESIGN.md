# Diseño: recuperación de intervalos IMERG y escaneos GOES-19 perdidos (NO ACTIVADO)

Estado: **diseño técnico, sin código de descarga ni disparadores**. RESEARCH_ONLY / TEST_ONLY. Cada paso de activación del final necesita autorización expresa. Este documento no cambia ningún workflow, archivo científico, regla ni umbral.

## 1. Punto de partida medido (instantánea de QA del registro, 13-10 a 20-10-2026)
| | IMERG Early `GPM_3IMERGHHE` v07 | GOES-19 `ABI-L2-RRQPEF` (M6) |
|---|---|---|
| Intervalos esperados | 336 (30 min) | 1.008 (10 min) |
| `CAPTURED` | 300 | 71 |
| `MISSING_RETRYING` (existen en origen) | **34** (15-10 09:30 a 16-10 23:30) | 937. La mayoría se deben al diseño: un escaneo por ejecución |
| `ABSENT_AT_SOURCE` (en la fecha de la consulta) | 1 (19-10 15:00) | 0 |
| `PENDING_SOURCE_LATENCY` | 1 | 0 |
| `UNKNOWN` | 0 | 0 |
| Tamaño por objeto, según el catálogo | mediana 7,05 MB, máx. 7,38 MB (`granule_size` de CMR) | mediana 1,55 MB, máx. 2,07 MB (`Size` de S3) |
| Volumen diario en origen | 48 × ~7 MB ≈ 340 MB | 144 × ~1,55 MB ≈ 226 MB |

Hallazgos que motivan el diseño:
1. Las 34 medias horas IMERG perdidas **existen en NASA**. Son huecos de captura, y el flujo actual ya no las reintentará porque su ventana es de 30 h.
2. La cadencia real de GitHub Actions es de unas 4–5 h, frente a los 30–60 min declarados.

## 2. Principios
- **Solo se recupera lo que el registro clasifica como `MISSING_RETRYING`.**
  - `UNKNOWN` primero se vuelve a consultar en el catálogo.
  - `ABSENT_AT_SOURCE` y `PENDING_SOURCE_LATENCY` no se descargan.
- **Mismo procesamiento que la captura en vivo.** Las mismas estadísticas por zona y el mismo código, con la versión del producto y el SHA-256 del archivo descargado registrados. Ningún valor se inventa, interpola ni sustituye.
- **Archivo aparte, de solo adición.**
  - Lo recuperado va a `data/v09/rain/recovered/<producto>_recovered_v0_1.json`, con `recovered=true`, `recovered_at_utc`, nombre del gránulo o clave, SHA-256, tamaño y `retrieved_from`.
  - Así no se mezcla con los archivos en vivo, que podan a 96 h y que escriben otros workflows.
  - El motor y el visor **no** lo consumen hasta una validación científica explícita.
- **IMERG Late o Final nunca sustituyen en silencio a Early.** Si alguna vez se usan para cubrir un `ABSENT_AT_SOURCE`, será como producto distinto, etiquetado y con su propio registro.
- **No se guardan HDF5 ni NetCDF** en el repositorio: solo las estadísticas derivadas y la procedencia, igual que hoy.
- **Idempotente.** Un intervalo que ya está `CAPTURED` o recuperado no se vuelve a descargar. Si dos ejecuciones se solapan, el `concurrency group` por producto las serializa.

## 3. Límites de descarga propuestos (presupuesto por ejecución)
| | IMERG Early | GOES-19 |
|---|---|---|
| Objetos por ejecución | ≤ 16, la misma cota que `max_downloads_per_run` de v0.9 | ≤ 36 (≈ 6 h de escaneos) |
| Bytes por ejecución | ≤ 16 × 7,4 MB ≈ 120 MB, con corte duro a 150 MB | ≤ 36 × 2,1 MB ≈ 75 MB, con corte duro a 100 MB |
| Tamaño máximo por objeto | 12 MB (rechazar si `granule_size` lo supera) | 12 MB (`MAX_FILE_BYTES` actual de la sonda) |
| Orden | El más antiguo primero, dentro de la retención | El más antiguo primero |
| Pausa entre peticiones | ≥ 1 s; tras un 429 o 5xx, espera creciente y parada de esa ejecución | ≥ 0,2 s; igual tras un 503 `SlowDown` |
| Tiempo de job | ≤ 30 min | ≤ 30 min |

- **Recuperar los 34 IMERG pendientes:** unos 240 MB, en 3 ejecuciones.
- **Recuperar todo GOES:** 226 MB/día. Antes hace falta una decisión científica sobre el muestreo: todos los escaneos, o uno fijo cada 30 min (48/día, unos 75 MB/día).
- **Crecimiento estimado del repositorio:** solo estadísticas por zona, del orden de 1–2 kB por intervalo y zona (comprobar con el formato real antes de activar).

## 4. Retención de las fuentes (pendiente de verificar)
El contrato del registro declara `retention.status = NOT_VERIFIED` para ambas fuentes, y por eso `UNRECOVERABLE` no se asigna nunca. Para verificarla:
- **IMERG Early:**
  - leer la ficha de la colección `C2723758340-GES_DISC` en CMR (cobertura temporal) y consultar el gránulo más antiguo (`sort_key=start_date&page_size=1`);
  - citar la política de GES DISC;
  - registrar todo en el contrato mediante un PR, como `VERIFIED` con fuente y fecha.
- **GOES-19:** listar el prefijo más antiguo del bucket `noaa-goes19` y citar la documentación de NOAA Open Data Dissemination.
- Mientras no se verifique, la recuperación se limita a intervalos que el catálogo **lista ahora**.

## 5. Mecanismos de programación que no dependen solo del cron
Todos ejecutan el mismo trabajador idempotente, con el mismo `concurrency group` y el mismo presupuesto. Ninguno queda activado por este documento.

| Mecanismo | Dependencia | Ventajas | Riesgos / requisitos |
|---|---|---|---|
| A. `workflow_dispatch` manual con rango `from`/`to` | Una persona | Control total; ideal para recuperar huecos históricos | Manual |
| B. `workflow_run` al terminar `v09-rain-north` o `goes19-rrqpe-probe` | GitHub, pero no el cron del trabajador | Más oportunidades de ejecución sin infraestructura nueva | Hereda los retrasos de los workflows previos; hay que acotarlo para que no se encadene a sí mismo |
| C. Planificador externo que llame a `workflow_dispatch` o `repository_dispatch` | Plataforma del propietario | Independiente del planificador de GitHub | El propietario crea un token de grano fino solo con `actions:write` en este repositorio y elige plataforma. **Cloudflare excluido** por las restricciones vigentes. No se crea ninguna credencial desde aquí |
| D. Runner autoalojado institucional con temporizador del sistema | Un servidor del propietario | No depende de las colas de GitHub | Mantenimiento y seguridad del runner; decisión institucional |
| E. Reducir la carga del planificador (consolidar crons y escalonar minutos) | GitHub | Puede mejorar la cadencia | Efecto no garantizado; la causa del retraso no es observable desde aquí |

Recomendación: empezar por **A**, seguir con **B** cuando A esté validado, y evaluar **C** o **D** solo con una decisión del propietario.

## 6. Controles antes de activar
- **Pruebas offline:**
  - presupuesto respetado y corte por bytes;
  - nunca se descarga un intervalo que no sea `MISSING_RETRYING`;
  - un 401, 403, 429 o 5xx detiene la ejecución sin marcar nada como ausente;
  - SHA-256 registrado;
  - idempotencia en dos ejecuciones;
  - los archivos en vivo no cambian;
  - no hay sustitución Late/Final.
- **Prueba negativa con el registro:** un `UNKNOWN` o un `ABSENT_AT_SOURCE` nunca disparan una descarga.
- **Prueba de equivalencia:** un intervalo recuperado y el mismo intervalo capturado en vivo (si existe) dan estadísticas idénticas con el mismo código.
- **Credenciales:** Earthdata ya se usa en la captura en vivo mediante secretos del repositorio. La recuperación usaría los mismos, sin crear otros.

## 7. Secuencia de activación (cada paso, con autorización expresa)
1. PR de verificación de retención: solo consultas de catálogo y documentación.
2. PR del trabajador IMERG: solo mecanismo A, presupuesto del §3 y archivo separado. Ejecutarlo una vez para los 34 intervalos.
3. Revisión científica de lo recuperado antes de que el motor o el visor lo usen.
4. Decisión del muestreo GOES y su trabajador, de nuevo solo con A.
5. Mecanismo B y, si el propietario lo decide, C o D.
