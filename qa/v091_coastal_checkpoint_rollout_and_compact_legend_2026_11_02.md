# IRFEN v0.9.1 — Cierre de checkpoints costeros y leyenda compacta

**Alcance:** RESEARCH_ONLY/TEST_ONLY; no emisión automática de avisos, no merge a main, no publicación.

## UI de leyenda (primer cambio en esta rama)
`site/v09/vigilancia.html` incorpora `#viewLegend` dentro de `details#viewDetails`, cerrado por defecto. El resumen «Estás viendo ...» queda visible, pero la extensa leyenda se abre solo a voluntad. No hay cambio de datos, reglas, colores ni georreferenciación. **Pendiente** ejecutar QA de navegador y actualizar la copia privada de Claude; no afirmar que ya esté actualizado el artefacto anterior.

## Situación de checkpoints contrastada
`config/v09_semaforo_systems_v0_1.json` tiene únicamente **LAMBAYEQUE = PILOTO_ACTIVO**, con 3 sistemas fluviales y 39 checkpoints. **TUMBES, PIURA, LA LIBERTAD, ANCASH, LIMA, CALLAO, ICA, AREQUIPA, MOQUEGUA, TACNA** siguen **PENDIENTE**, sin sistemas asociados. Por tanto, la red IGN costera trazada NO significa que existan puntos de evaluación para todos los ríos.

## Plan de cierre, sin inventar posiciones
1. **Norte primero:** Tumbes y Piura: enumerar ríos principales con OBJECTID exactos de IGN, conectividad comprobada, orientación por desembocadura o HydroSHEDS cuando sea defendible, y centros poblados expuestos ANA ya documentados; distinguir punto sobre cauce de poblado cercano.
2. **Restantes:** La Libertad, Áncash, Lima, Callao, Ica, Arequipa, Moquegua y Tacna; incorporar en lotes, auditar ausencia de tramos con nombre, agrupación y posiciones reproducibles.
3. **No transformar cada segmento IGN en checkpoint:** los 1.085 segmentos únicos son cartografía de referencia, no estaciones ni unidades hidrológicas. Elegir puntos por tramos significativos y exposiciones documentadas, sin inferir desde nombre del poblado que exista geometría exacta de la quebrada.
4. **Lluvia y estados:** si no hay una cuenca/observación reciente asociable, punto GRIS/NO EVALUABLE. No usar media de departamento para asignar verde ni amarillo. Sin naranja real salvo regla validada, rojo solo evento localizado verificable.
5. **QA y entregables por departamento:** `checkpoints_by_department`, total por tipo (`CAUCE_IGN`/`POBLADO_ANA`), origen y coordenada, OBJECTIDs, cobertura de lluvia, limitaciones, hash reproducible y pruebas de navegador; verificar iconos al zoom nacional para evitar saturación. Actualizar paquetes, demo privada y autocomprobación.

## Critérios de aceptación de la vista
- Leyenda colapsada por defecto en escritorio y móvil, expansión accesible con teclado/clic, no solapar el mapa.
- Lista de capas y semáforo siguen funcionales; la explicación completa de colores y fechas está accesible.
- Nuevos puntos sin señal meteorológica nueva no pueden generar estados positivos de peligro.
- No modificar la versión congelada Research Preview 1 ni fusionar sin autorización.

La integración v0.9.1 en PR #472 progresa en paralelo. Este PR no implementa aún los puntos adicionales; fija avance de interfaz y criterios de expansión verificables.
