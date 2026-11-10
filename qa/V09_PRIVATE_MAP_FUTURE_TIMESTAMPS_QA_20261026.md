# v0.9 mapa privado: marcas temporales posteriores al reloj y control R1 (QA, 26-10-2026)

Ámbito: rama de integración de #403. RESEARCH_ONLY / TEST_ONLY. Sin publicar, sin activar nada y sin cambiar puertas ni guardas.

## 1. Observaciones con fecha posterior al reloj de evaluación

**Defecto.** `imerg_usable_at` / `goes_usable_at` (motor) e `imergUsableAt` / `goesUsableAt` (bloque SHARED-RULES del panel y del visor) solo comprobaban `t − fin ≤ límite`. Una marca temporal posterior al instante de evaluación da una diferencia negativa y se aceptaba como dato «al día».

**Cuándo ocurre.** El navegador del lector evalúa con su propio reloj. Basta un equipo con la hora atrasada o una fuente con la marca mal puesta.

**Reproducción** (Chromium, reloj 2 h antes del último escaneo GOES del paquete):
- Visor: chip GOES-19 en verde «(hace -120 min)» y «Paquete generado … (hace -309 min)» en verde.
- Panel: edades «hace -120 min» y «hace -74 min».
- La prioridad podía apoyarse en esos datos: R4, o R6 «sin señal».

**Corrección.** No se añade ninguna tolerancia, porque ninguna está documentada.
- Un dato con fecha posterior a la evaluación no es utilizable. Cuenta como ausente: nunca como cero ni como «sin señal».
- El motor y el navegador dan el motivo («con fecha posterior a la evaluación»).
- El final de esa ventana pasa a ser un borde de `next_change`.
- Un ciclo GEOS-CF con inicio posterior a la evaluación da `NO_DISPONIBLE`.
- Interfaz:
  - edad «fecha posterior a la hora de este equipo (+N min)»;
  - etiqueta roja «no cuenta para la prioridad»;
  - chips del visor (GEOS-CF, avisos, paquete) nunca en verde con edad negativa;
  - frescura de fuentes `FECHA_FUTURA`.

**Efecto sobre los datos actuales.** Ninguno en la evaluación ni después. Sobre el estado de `main` `b524ace9` (evaluado el 26-10 a las 19:36 UTC), las reglas antigua y nueva dan resultados idénticos en 88/88 casos: 22 zonas × {0, +6 h, +13 h, +2 d}. Evaluado 1 día antes, la regla antigua consideraba utilizables los datos de las 22 zonas y la nueva, de ninguna.

## 2. Control negativo de «lluvia sobre otro polígono» (R1)

**Defecto.** `check_rain_polygon` saltaba (`continue`) toda geometría cuya `v09_zone` no tuviera polígono registrado. Una unidad hidrográfica coloreada con la lluvia de una provincia INEI de contexto pasaba la QA. La puerta quedaba abierta ante el fallo, en lugar de cerrada.

**Cómo apareció.** El motor ordena `zone_rain` por prioridad. Con el estado actual de `main`, la primera zona es `tumbes_province_context:ZARUMILLA`, y la prueba negativa (que tomaba la primera clave distinta) pasó a dar PASS. Con la fusión de #403 sobre `main` `b524ace9` falla `test_zone_rain_on_another_polygon_fails`.

**Corrección.**
- Esa geometría ahora falla.
- La prueba cubre los dos casos, independientemente del orden: otra cuenca registrada y una zona sin polígono.

## Pruebas
- No se añaden funciones de prueba: se amplían las existentes, así que los node IDs y el manifest no cambian.
- Fusión con `main` `b524ace9`: 96 pruebas OK. Las 12 omitidas son browser v0.8, que necesitan Leaflet, y la reproducción del motor, que se omite sola cuando cambia una entrada.
- QA independiente: 6/6 PASS.
- Control negativo: las pruebas ampliadas, ejecutadas contra el código de #403, dan 5 fallos.
