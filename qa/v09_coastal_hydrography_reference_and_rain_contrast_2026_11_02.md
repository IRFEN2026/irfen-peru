# IRFEN v0.9 · Ajuste cartográfico costero (02-11-2026)

**Estado:** rama de investigación posterior al freeze `25e611ac`. No altera `release/irfen-v0.9-research-preview-1`, no modifica `main`, no es publicación ni habilita alertas.

## Problema real identificado

Las geometrías de quebradas IRFEN integradas en `site/v09/vigilancia.html` están concentradas en el norte y el Rímac. Los centros poblados ANA NO son geometrías de quebradas. Faltan trazados de cursos de agua referenciales desde La Libertad hasta Tacna, aunque pueden incorporarse sin disponer de una validación hidráulica o de una cuenca completa.

No confundir:
- **Cauce/recorrido cartográfico:** línea documentada de río o quebrada, útil para orientación.
- **Cuenca hidrográfica:** polígono de drenaje con metodología, escala, geometría y salida.
- **Quebrada peligrosa o activada:** exige evidencia adicional; ni un cauce intermitente ni una lluvia acumulada lo demuestran.
- **Zona de impacto:** no inferible de las líneas hidrográficas.

## Fuentes públicas documentadas

1. **IGN — Ríos y Quebradas 1:500.000**: `https://www.idep.gob.pe/geoportal/rest/services/SERVICIOS_IGN/HIDROGRAFIA_500K/FeatureServer/1`. Geometría `esriGeometryPolyline`, campos `Nombre`, `Rasgo_Prin`, `Rasgo_Secu` (Perenne/Intermitente). Cobertura nacional, consultas `geoJSON`, límite de 2.000 entidades por respuesta, paginación e IDs disponibles. No se ha descargado ni auditado su geometría aún. Citar al IGN y verificar condiciones de reutilización antes de publicar.
2. **IGN — WMS de hidrografía nacional 1:500.000**: `https://www.idep.gob.pe/geoportal/services/SERVICIOS_IGN/HIDROGRAFIA_500K/MapServer/WMSServer`; capa 1 «Ríos y Quebradas». La ruta la publica el IGN en `https://www.idep.gob.pe/wms/wms_ign.html`. En la página completa del repositorio se añadió una capa **optativa, desactivada por defecto**, con manejo de errores de conexión. **No se ha probado realmente el servidor WMS**; verificar `GetCapabilities`, nombres de capa y respuesta en navegador antes de darla por funcional.
3. **IGN — hidrografía 1:100.000**: el IGN publica WMS independiente más detallado, útil tras la primera capa nacional, pero no se ha obtenido todavía una cobertura descargable validada.
4. **ANA — red «Ríos y Quebradas»**: `https://geosnirh.ana.gob.pe/server/rest/services/ONRH/Rios_Quebradas_AAVI/MapServer/0`, campos `NOMBRE_CA`, `TIPO_CA`, `NOMBRE_UH`, `CODIGO_UH`, geometrias lineales; algunos accesos han agotado tiempo en esta investigación. Una sola prueba controlada, sin reintentos insistentes. En caso de bloqueo mantener UNKNOWN.
5. **INGEMMET — cartografía base**: `https://geocatmin.ingemmet.gob.pe/arcgis/rest/services/SERV_CARTOGRAFIA_BASE_WGS84/MapServer`, capas 14, 15 y 16 para ríos principales, ríos y ríos secundarios. Consultas limitadas, actualmente no verificadas.

## Trabajo ya realizado en este PR

- Paleta IMERG de seis tonos más contrastados (amarillo→naranja→magenta→violeta) y trazo fino para celdas, aumentando opacidad para el mapa claro; intervalos en mm, **no** umbrales de riesgo.
- Capa voluntaria `hydroIGN` sobre página completa (no el archivo auto-contenido), con atribución visible, escala y fecha de origen, y desactivación si la red devuelve cuatro errores.
- Se preservan las capas IRFEN originales y los datos ya archivados.
- Este PR **no demuestra** que funcionen las teselas IGN, no integra un GeoJSON nacional local ni actualiza la copia de Claude. No se confunda «código incorporado» con «capa validada y visible».

## Acciones de integración restantes (bloqueantes para declarar este cambio terminado)

1. En un runner con acceso autorizado, probar `GetCapabilities` y una tesela WMS IGN, **registrando estado HTTP, latencia y licencia**. Si falla, suspender WMS sin bucle.
2. Preferentemente consultar **una sola captura versionada** de IGN FeatureServer/1, en recortes espaciales acotados y paginación o `objectIds`, sin superar 2.000 por página ni recursión infinita. Extraer solo polígonos/lineas relevantes a las cuencas de vertiente Pacífico y preservar nombre, régimen, escala, ID, origen, fecha, SHA y límites. Validar coordenadas y evitar asociaciones de cuenca inventadas.
3. Reforzar por región con nombres verificados: La Libertad; Áncash; Lima sur chico; Ica; Arequipa; Moquegua; Tacna. **No dibujar a mano** líneas de ríos con una serie de coordenadas aproximadas sin fuente; no usar puntos de poblados ANA como cauces.
4. Superponer los trazados en la copia **autocontenida** de Claude para que funcionen sin peticiones externas. Diferenciar «Red IGN: permanente/intermitente» de «Geometrías IRFEN validadas/experimentales» y «Quebradas nombradas» de «cursos sin nombre». A zoom bajo priorizar ríos con nombre; al acercar añadir tributarios, cursos intermitentes y quebradas.
5. Reconstruir `surveillance_view_v0_1.json` y `private_demo` con la herramienta del repositorio; actualizar hashes y pruebas en rama nueva. No tocar release anterior.
6. QA visual en Piura, Trujillo, Chimbote, Cañete, Pisco/Ica, Arequipa/Camaná, Ilo/Moquegua y Tacna; demostrar referencias y capas legibles sin confundir cauce con nivel de peligro. Revisar paleta también con celdas solapadas y tema oscuro.
7. Si la fuente no funciona, no declarar la capa completa; conservar el contraste y documentar `UNAVAILABLE`.

## Criterio de alcance

No hay obligación de disponer de polígonos de cuencas perfectamente delimitadas ni de evaluar activación de quebradas para mostrar **cauces fluviales de referencia**. Lo imprescindible es geometría trazable, identificación honesta, actualización no simulada y ausencia de lenguaje de alerta no validada.

El cierre anterior de v0.9 Research Preview 1 permanece válido; esta mejora debe considerarse candidata v0.9.1 de visualización en otra rama hasta superar aceptación independiente.
