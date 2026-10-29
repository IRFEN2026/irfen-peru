# IRFEN v0.9 — prototipo CesiumJS 2D/3D en revisión privada (29-10-2026)

**Estado:** RESEARCH_ONLY / TEST_ONLY. No sustituye el visor territorial, no está publicado, no emite alertas y no cambia fuentes/umbrales/calendarios de captura.

## Contenido
- \`site/v09/cesium.html\`: CesiumJS 1.146 pinneado a CDN oficial, globo Perú 2D/3D con cartografía OSM para **exploración manual local** (no uso productivo ni precarga).
- Lee únicamente \`site/data/v09/territory_v0_1.json\` de la rama de integración #403, respeta las guardas del archivo y dibuja solo geometrías existentes (no agrega cuencas/cauces imaginarios).
- Enfoque Perú, costa norte o Rímac; seis capas seleccionables; ficha con identidad/procedencia/estado.
- Modo 3D sin cuenta: globo WGS84 sin relieve altimétrico. Para montañas y valles, botón opcional Cesium World Terrain con token de **solo lectura** de Cesium ion, proporcionado por el operador dentro de la página durante la sesión. No se persiste ni se sube token a GitHub. Activación puede fallar por cuota, permisos o red sin alterar el globo.
- No existe comparación estación–celda IMERG ni nueva capa de lluvia en este prototipo. El visor 2D existente mantiene su separación semántica de lluvia, estado y registros faltantes.
- El listado documental sigue en \`inventario.html\`; no deducir ausencia de peligro por ausencia de geometría.

## Prueba local
Desde clon de la rama de este PR, con un navegador moderno y acceso a internet:
\`\`\`
python -m http.server 8000 --bind 127.0.0.1 --directory site
\`\`\`
Abrir \`http://127.0.0.1:8000/v09/cesium.html\`.

**No abrir por \`file://\`** (fetch falla) ni subir la web a alojamiento público sin autorización separada y revisión de acceso protegido. La rama #403 todavía no está en \`main\`.

## Activar relieve 3D
1. Crear cuenta desde \`https://ion.cesium.com/\`.
2. En **Access Tokens**, crear un token limitado al recurso **Cesium World Terrain**, de lectura, restringido por origen/dominio donde sea posible. No usar un token de escritura de activos.
3. Pegarlo **solo en el campo local de la vista** y pulsar “Activar relieve”.
4. En la vista 3D, inclinar/rotar la cámara y seleccionar capas. Verificar la resolución del terreno; no interpretar imágenes 3D como prueba de conectividad hidráulica.

**Licencias:** CesiumJS abierto (Apache-2.0), Cesium ion es un servicio separado con planes/cuotas/licencia según uso; el plan gratuito Community aplica a evaluación y uso personal no comercial bajo condiciones. Cartografía OSM solo como prueba interactiva modesta, con atribución visible y sujeto a la política de \`tile.openstreetmap.org\` (sin descarga masiva, precarga ni servicio de producción). Para un despliegue real, elegir proveedor de tiles con contrato/cuota, alojado o licencia adecuados.

## Puertas pendientes
- Probar carga WebGL/terreno Cesium ion en navegador real de escritorio y móvil. La revisión estática no es prueba de render.
- Añadir infraestructura de teselas para producción privada, atribuciones y presupuesto.
- Revisar metadata, selección de features y conexiones con catálogo nacional.
- Añadir fuentes de lluvia después de validación temporal y espacial (no confundir precipitación estimada IMERG con lluvia puntual SENAMHI).
- Revisión humana; merge y publicación requieren decisiones separadas.

**Referencias:** https://cesium.com/learn/cesiumjs-learn/cesiumjs-quickstart/ · https://cesium.com/learn/cesiumjs-learn/cesiumjs-terrain/ · https://cesium.com/learn/ion/cesium-ion-access-tokens/ · https://operations.osmfoundation.org/policies/tiles/
