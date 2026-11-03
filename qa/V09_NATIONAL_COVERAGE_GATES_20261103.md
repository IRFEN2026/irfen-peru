# Cobertura nacional de investigación IRFEN — revisión del 3 de noviembre de 2026

**Resultado:** los 536 checkpoints del PR #480 corresponden a la investigación de los **11 departamentos costeros**, NO a una red predictiva nacional. Se registran 25 departamentos (24 + Callao) con estado de capacidad predictiva **NO_DEMOSTRADA**, incluidos los 14 fuera del inventario costero. Una región política no es una cuenca; incluso departamentos costeros incluyen zonas que drenan a otras vertientes.

## Tres regiones hidrográficas, tres tipos de problema

- **Pacífico:** crecidas súbitas en cuencas de pendiente pronunciada, desbordes en valles costeros y quebradas. Investigar por ejemplo Santa, Rímac, Chillón, Cañete, Ica y Tambo, además del norte. Los checkpoints y acumulados ya desarrollados son observacionales o proxies, NO pronósticos validados.
- **Amazonas/Atlántico:** grandes cuencas con crecidas y propagación que pueden durar días, además de inundaciones pluviales locales. Investigar Marañón, Huallaga, Ucayali y Madre de Dios con referencias de aforo verificadas y desfases propios; no reutilizar tiempos de respuesta ni pesos del río Piura.
- **Titicaca:** cuencas y desbordes lacustres/fluviales con dinámica distinta; explorar Ramis, Coata e Ilave y observaciones de nivel relevantes, sin trasladar coeficientes costeros.

Los sistemas PHISIS de SENAMHI abarcan las tres regiones hidrográficas y ANA informa de información de niveles/caudales de estaciones automáticas; su existencia NO autoriza asumir una API accesible ni series descargadas. Fuentes: https://www.gob.pe/21712-consultar-la-informacion-hidrologica-peruana-en-la-plataforma-phisis-consultar-el-monitoreo-hidrologico-de-los-rios-peruanos ; https://www.gob.pe/institucion/ana/noticias/1424775-ana-herramientas-digitales-permiten-el-monitoreo-permanente-de-los-caudales-en-rios

## Protocolo para el módulo nacional

1. Conservar estimaciones IMERG Early con sus horas de observación **y disponibilidad**, versiones, cobertura y huecos; datos no actuales como DESACTUALIZADOS, nunca cero.
2. Asignar cada punto a su **cuenca aportante verificada** antes de correlacionar lluvia–aforo; prohibir mezclas provincia-cuenca.
3. Diferenciar fenómenos: anegamiento pluvial, subida de nivel, crecida de río, desborde, activación de quebrada. Ninguna variable sustituye otra.
4. Para adelanto real a 3/6/12/24h, exigir caudales/niveles independientes con paso subdiario y hora de disponibilidad histórica, calibración en episodios de entrenamiento y validación fuera de muestra contra persistencia y antecedentes de caudal.
5. En cuencas amazónicas no presuponer misma relación lluvia–caudal ni misma ventana que en costa. Titicaca requiere diseños propios. Si no hay datos suficientes: NO_EVALUABLE.
6. No cambiar `main`, `site/`, semáforo o alertas, ni fusionar PR sin revisión y autorización.

## Entrega de investigación con plazo de 48h

**Objetivo verificable, no promesa de acierto:** versión experimental reproducible, tabla de errores de los ensayos realmente evaluables, matriz nacional de 25 departamentos e impedimentos transparentes. Si las observaciones horarias faltan, mantener NO_EVALUABLE y entregar código, pruebas y resultados negativos; no fabricar un predictor 'preciso'.

Implementación: `config/v09_national_coverage_gates_v0_1.json`, `scripts/v09_national_coverage_audit.py`, `tests/test_v09_national_coverage_audit.py`.
