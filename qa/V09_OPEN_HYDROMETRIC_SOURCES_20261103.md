# IRFEN — auditoría de acceso hidrométrico gratuito (03-11-2026)

**RESEARCH_ONLY · TEST_ONLY · NO FUSIONAR · NO ALERTAS · SIN COMPRAS**

## Hallazgo nuevo prioritario: datos abiertos de Piura

El Gobierno Regional de Piura publica «Datos Hidrometereológicos [Gobierno Regional Piura]», atribuido al Proyecto Especial Chira Piura (PECHP), con **CSV**, diccionario XLSX y metadatos DOCX; la ficha indica actualización mensual y última modificación **2026-09-09** (metadato de catálogo; no constituye fecha del último registro), licencia **Open Data Commons Attribution**.

- Ficha pública: https://www.datosabiertos.gob.pe/dataset/datos-hidrometereol%C3%B3gicos-gobierno-regional-piura
- Diccionario: https://www.datosabiertos.gob.pe/dataset/datos-hidrometereol%C3%B3gicos-gobierno-regional-piura/resource/d7437ef6-8950-4c25-bc91
- Servicio PECHP: https://servicios.regionpiura.gob.pe/datosh
- Fuente oficial: https://www.gob.pe/23713-consultar-informe-hidrometeorologico-diario-del-sistema-de-rios-chira-piura

**Diccionario textual confirmado en la ficha:** DEPARTAMENTO, PROVINCIA, DISTRITO, UBIGEO, FECHA_CORTE, FECHA_REGISTRO, CUENCA, ESTACION, UNIDAD_MEDIDA, TIPO_ESTACIÓN, CAUDAL07H, PROMEDIO24H, MAXIMA24H, PRECIP24H.

**Convención temporal documentada SOLO para PRECIP24H en este dataset:** 07:00 del día previo a 07:00 del día de observación. No extender esta convención sin evidencia a los TXT históricos de SENAMHI ni a PROMEDIO24H/MAXIMA24H. Valor vacío significa ausencia de medición, no 0. Las horas indicadas no establecen por sí solas hora real de publicación, necesaria para replay causal.

**Limitación de acceso en esta comprobación:** índice web y diccionario consultables, pero lectura directa de fichas devolvió HTTP 403 y el portal de PECHP expiró; no se obtuvo ni se validó el archivo CSV. **Cero observaciones importadas y cero series horarias independientes aptas**. No afirmar disponibilidad 2017/2023 ni vigencia casi real a partir de fecha de edición.

## Otras rutas oficiales

| Fuente | Evidencia pública | Granularidad probada | Acceso al histórico de prueba | Decisión |
|---|---|---|---|---|
| SENAMHI PHISIS | https://www.gob.pe/21712-plataforma-hidrologica-phisis-monitoreo-hidrologico | Visualización de niveles/caudales y análisis diario; hay presentación en tiempo real | No se obtuvo archivo horario descargable con fecha de disponibilidad | **CATALOGO/CONSULTA**, no feed automatizado |
| PECHP/GORE Piura | ficha arriba | Campos a 07:00 y 24h, CSV anunciado | 403/timeout en esta sesión | **CANDIDATO_ABIERTO**, pendiente descarga verificada |
| INAMHI visor | https://inamhi.gob.ec/ddia/visor | Estaciones meteorológicas e hidrológicas; estado transmisión | Sin serie horaria Puyango/Catamayo verificada | **CATALOGO/CONSULTA** |
| ANA SNIRH | https://www.gob.pe/86460-acceder-al-sistema-nacional-de-informacion-de-recursos-hidricos | Información oficial de recursos hídricos | Sin serie subdiaria ni timestamp de publicación | **CONTEXTO**, no input de anticipación |
| SENAMHI acceso a información pública | https://www.senamhi.gob.pe/pdf/trans/tupa/tupa-senamhi.pdf | Vía para solicitar registros existentes | Solicitud pendiente de autorización y envío | **NO SOLICITADO** |

No reintentar scrapers bloqueados ni suplir la ausencia con cifras en noticias. Los boletines y avisos siguen siendo contexto verificable, no pares de caudal horario para métricas. La tarifa de SENAMHI 2024 registrada en #460 **no se declara vigente hoy**.

## Criterio de aceptación de los datos para el laboratorio

1. Descargar CSV legítimamente, preservar bytes, SHA-256, fecha real de acceso y licencia; anotar edición y cobertura temporal reales. Sin credenciales, scraping protegido ni TLS inseguro.
2. Validar cabeceras, estaciones y unidades, tipos de serie, fechas y duplicados; conservar los valores vacíos como `null`.
3. Verificar definición de cada ventana de acumulación, zona horaria, fecha de observación **y hora de publicación disponible en su momento**. Un dato recuperado hoy **no fue necesariamente disponible** en 2017.
4. Para #460: se necesitan registros de caudal/nivel subdiarios de episodios independientes y controles de regulación hidrológica; el CSV diario **no satisface** la evaluación de 3/6/12/24h por sí solo.
5. Comparar lluvia IMERG Early realmente disponible en t con caudal medido disponible en t+H, conservar un holdout fuera de muestra y evaluar contra línea base hidrométrica.
6. **Sin actualización de parámetros ni publicación:** activation_gate=BLOCKED; sin riesgo inferido de falta de datos.

## Próxima solicitud sin enviar

Utilizar los borradores existentes en `research/v09/requests/SOLICITUDES_DATOS_HIDROMETRICOS_BORRADOR_20261031.md`; priorizar PECHP (Ñácara, Los Ejidos, Sánchez Cerro, Tambogrande y regulación de Poechos/Curumuy) y SENAMHI (El Tigre), y Ecuador para Puyango/Catamayo, solo tras aprobación del responsable. No crear solicitudes duplicadas ni enviarlas.
