# Evidencia instrumental histórica aportada por usuario — inventario preliminar (27-10-2026)

**Clasificación:** RESEARCH_ONLY / EVIDENCE_UNVERIFIED / NO_VALID_PAIRS.  
**Procedencia declarada:** archivos TXT descargados por el responsable en páginas de datos de estaciones de SENAMHI (pendiente constatar URL, licencia específica, código, identidad y coordenadas de estación). No se publican datos sin corroborar su licencia. Los archivos originales están adjuntos a la conversación, **no** almacenados en este repositorio; el presente documento es un manifiesto analítico y NO sustituye su archivo permanente ni sus hashes individuales.

## Alcance de los ficheros examinados en la sesión

- **58 archivos TXT** adjuntos por el responsable en varios lotes, incluidos los grupos etiquetados por el usuario como Piura y Tumbes, además de lotes previos presuntamente Lambayeque.
- **54 contenidos distintos por SHA-256** (duplicados bit a bit excluidos de los siguientes recuentos).
- **950.479 líneas con seis campos y fecha interpretable**, de las cuales **858.034** tienen el cuarto valor numérico no negativo y **253.834** corresponden a 2001 o posterior con cuarto valor no negativo. Los últimos dos números son **candidatos preliminares**, no observaciones validadas.
- Duplicados detectados: `qc00000791.txt` = `qc00000791 (1).txt`; `qc00000247 (2).txt` = `qc00000247 (3).txt`; `qc00000340 (1).txt` = `qc00000340 (2).txt`; `qc00000208.txt` = `qc00000208 (1).txt`.
- Cada registro contiene `año mes día v4 v5 v6`. Los valores de la cuarta columna son compatibles con precipitación diaria y las otras dos con temperatura, pero el significado preciso, unidad, validación, hora de cierre y convención de datos ausentes exigen documentación propia de estos TXT. La marca `-99.9` se trata como **faltante candidato**, nunca como cero.
- La fecha documental de los datos NO debe inferirse de las fechas de carga. La serie diaria histórica es independiente del dataset horario GBON/RBON 2015–2024 subido también por el responsable; no mezclarlos.

## Estaciones y límites científicos

El nombre de fichero `qcNNNNNNNN.txt` **no prueba** WIGOS, nombre, ubicación o departamento. Los lotes han sido etiquetados por el responsable como Piura/Tumbes, pero falta catálogo oficial que asocie cada `qc` con la estación, coordenadas y resolución, y documento que precise la ventana diaria. **No seleccionar píxeles IMERG a partir del código**, ni asignar automáticamente estaciones de este conjunto a OSCAR o a la tabla de 11 GBON/RBON. Tampoco confundir valores anteriores a 2000 con candidatos de contraste contra GPM IMERG.

Es prioritario solicitar al responsable el índice/catálogo de descarga y la documentación para asociar códigos `qc` con estaciones, sobre todo Lambayeque, Piura y Tumbes. Posteriormente: inspeccionar faltantes y continuidad por año/estación; revisar fechas críticas y extremos contra informes oficiales; resolver día pluviométrico y coordenadas; identificar SOLO entonces intervalos coincidentes con IMERG disponible, sin reinterpretar desfases. Se pueden estudiar extremos de 1982–83/1997–98 históricamente, pero nunca compararlos contra GPM IMERG como si hubiera cobertura del satélite.

## Política de integración

1. Mantener la evidencia **RESEARCH_ONLY** y registros de procedencia sin afirmaciones de calibración.
2. **0 pares reales gauge–IMERG** constatados de este material y **calibración bloqueada**. Sin métricas; ninguna alerta operativa.
3. No descargar gránulos NASA, no modificar `main`, producción, configuración, visor, publicaciones, ni las ramas/PR #419, #420, #422, #427.
4. Los originales TXT requieren almacenamiento de investigación persistente autorizado y manifiesto SHA-256 de **cada** archivo antes de usarse cuantitativamente. Este documento registra únicamente los resultados de inspección de adjuntos.
5. El inventario de 54 archivos no representa 54 estaciones confirmadas. La validación espacial y la independencia instrumental siguen pendientes.

**Siguiente compuerta:** catálogo autenticado `qc -> nombre -> coordenadas -> red/departamento`, documentación de precipitación diaria y conservación verificable de los TXT fuente.