# IRFEN v0.9.1 · correo privado cuando un punto pasa a ROJO (RESEARCH_ONLY / TEST_ONLY)

> **Estado actual: envío real DESHABILITADO** hasta tu autorización (`config/v091_owner_notifications.json`, con `sending_enabled: false`). Mientras siga así:
> - el script no abre ninguna conexión SMTP;
> - genera las hojas y los `.eml` de simulación;
> - anota `NO_ENVIADO_ENVIO_DESHABILITADO` en el historial.
>
> Los eventos rojos que sigan vigentes se enviarán al habilitarlo.
>
> **Destinatario único:** solo se acepta la dirección cuya huella SHA-256 figura en esa configuración (la tuya).

| Estado | Correo |
|---|---|
| ROJO | Sí: evento reportado y verificado |
| NARANJA | Solo con una regla de anticipación **validada**. Hoy no hay ninguna (`docs/V091_ANTICIPATION.md`) |
| AMARILLO, VERDE, GRIS | **Nunca** |

**Para habilitarlo** hace falta tu autorización expresa: un commit propio que ponga `sending_enabled: true` y rellene `authorized_by` y `authorized_at_utc`. Después, primero la prueba controlada `--test-email`.

Avisa por correo **a una sola persona** cuando un punto del semáforo pasa a rojo.
- No es una alerta pública.
- No publica nada.
- No usa servicios de pago.
- Funciona en tu ordenador, con tu propia cuenta de correo.

## 1. Qué es ROJO (y qué no)

| En el registro de eventos (`config/v09_semaforo_confirmations_v0_1.json`) | Mapa | Correo |
|---|---|---|
| `verified: true`, enlace `https://`, fecha y lugar (`checkpoint_id`, o `system_id` para los puntos de cauce de un río), en las últimas 72 h | **ROJO** · «reportado y verificado» | **Sí**, una vez |
| Entrada sin verificar (`verified: false`) o sin enlace `https://` | Sin cambio de color; en la ficha del punto aparece «**pendiente de verificación**» | No; queda anotada en el historial |
| Lluvia satelital, aunque sea extrema | Amarillo como mucho; es contexto | No |
| Aviso regional de SENAMHI vía INDECI/COEN | No cambia el color; es contexto | No |

Tipos de evento (`event_kind`): `ACTIVACION_QUEBRADA`, `DESBORDE_RIO`, `OTRO_EVENTO`. El tipo da título a la hoja.

**El rojo dice que el evento ocurrió, según una fuente verificada. No dice que siga activo ni lo predice.** Un estado predictivo de posibles crecidas o activaciones será una capa independiente, cuando haya datos históricos y validación científica suficientes.

## 2. Cómo se registra un evento

1. Edita `config/v09_semaforo_confirmations_v0_1.json` en la rama `research/v091-live-integration-20261102`. Añade una entrada a `confirmations`; el formato está en `example_es`.
   - Usa un `id` único y estable: es lo que evita los correos repetidos.
   - Pon `verified: true` solo después de revisar la fuente.
2. El ciclo automático incluye el registro en su comprobación de cambios. En unos 20 minutos se publica un paquete nuevo de tipo `REGISTRO_DE_EVENTOS` y el visor privado muestra el punto en rojo.
3. El script de tu ordenador lee ese paquete, evalúa los puntos a la hora actual y te envía el correo.

Ten en cuenta que el repositorio es público: lo que entre en el registro será visible. Usa solo información y enlaces que ya sean públicos.

## 3. Qué recibes

- **Hoja de alerta** `hoja_alerta.png` (1080×1350, formato vertical para redes). Contiene:
  - IRFEN v0.9.1 y el título del evento;
  - departamento, provincia, distrito, río o quebrada, y el punto IRFEN;
  - fecha y hora del evento (Lima);
  - lluvia satelital de 1, 3, 6, 24 y 72 h, como contexto (si no es reciente se indica: dato ausente, no cero);
  - fuentes;
  - una interpretación breve y recomendaciones básicas;
  - el pie «uso de investigación / monitoreo ciudadano; no sustituye a SENAMHI, INDECI ni a las autoridades».
- **Correo**, con estos elementos:
  - asunto «IRFEN · Desborde de río reportado y verificado: Río … (Departamento) · dd/mm hh:mm»;
  - un texto breve;
  - la imagen adjunta;
  - el bloque «TEXTO LISTO PARA REDES».
- Si no hay Playwright, se adjunta la hoja en HTML y el correo lo indica.

## 4. Sin repeticiones y rearme

El estado se guarda en `~/.irfen_alerts/state.json` y el historial en `~/.irfen_alerts/alerts_log.jsonl`. Las hojas y los correos quedan en `~/.irfen_alerts/out/`. Nada de esto se guarda en el repositorio.

| Situación | Acción | Historial |
|---|---|---|
| Un evento pasa a rojo | 1 correo (aunque afecte a varios puntos del mismo río) | `ALERTA_ENVIADA` |
| Sigue en rojo, sin cambios | Nada | — |
| Cambia el tipo, la descripción, la fecha, el lugar, la fuente o los puntos afectados | 1 correo `[ACTUALIZACIÓN]` | `ACTUALIZACION_ENVIADA` |
| Deja de estar en rojo (pasan las 72 h o se retira la entrada o su verificación) | Se **rearma** | `REARMADO` |
| Vuelve a ponerse en rojo después del rearme | 1 correo nuevo | `ALERTA_ENVIADA` |
| El envío falla | Se reintenta en las siguientes comprobaciones, como máximo 3 veces por versión del evento | `ERROR_DE_ENVIO` (sin credenciales) |
| Envío deshabilitado | Se generan la hoja y el `.eml`, no se marca como enviado y se enviará al habilitarlo | `NO_ENVIADO_ENVIO_DESHABILITADO` (una vez) |
| El ordenador se apaga a mitad de un envío | Antes de enviar se anota el envío en curso; en la siguiente comprobación se reenvía con la nota «posible repetición» | — |
| El evento se detecta tarde (más de 6 h después de ocurrir) | Se envía con la nota «detectado con retraso». No se pierde mientras siga dentro de las 72 h | — |
| Un punto pasa de NARANJA a ROJO | Correo de ROJO aparte (otra clave) | `ALERTA_ENVIADA` |
| Reporte sin verificar | Nada | `PENDIENTE_DE_VERIFICACION` (una vez) |

**Rearme manual:** el rearme ocurre solo. Para forzar el reenvío de un evento sin cambiarlo, borra su clave de `active` en `~/.irfen_alerts/state.json`.

## 5. Configurar tu correo (Gmail con contraseña de aplicación)

Gmail permite enviar por SMTP con una **contraseña de aplicación**: un código de 16 caracteres que sirve solo para esto, que puedes revocar cuando quieras y que no es tu contraseña.

1. Activa la verificación en dos pasos de tu cuenta de Google: Cuenta de Google → Seguridad → «Verificación en dos pasos». Es obligatoria para poder crear contraseñas de aplicación.
2. Crea la contraseña de aplicación en https://myaccount.google.com/apppasswords: ponle el nombre «IRFEN» y copia el código de 16 caracteres. Google solo lo muestra una vez. Si esa página no aparece, suele ser porque la cuenta es de una organización que lo bloquea o porque no está activada la verificación en dos pasos.
3. Crea el archivo de configuración en tu ordenador, **fuera del repositorio**:
   ```bash
   mkdir -p ~/.irfen_alerts && chmod 700 ~/.irfen_alerts
   cat > ~/.irfen_alerts/smtp.env <<'EOF'
   IRFEN_SMTP_HOST=smtp.gmail.com
   IRFEN_SMTP_PORT=465
   IRFEN_SMTP_USER=TU_CUENTA@gmail.com
   IRFEN_SMTP_APP_PASSWORD=PEGAR_AQUI_LA_CONTRASENA_DE_APLICACION
   IRFEN_ALERT_TO=TU_CORREO_DESTINO@gmail.com
   EOF
   chmod 600 ~/.irfen_alerts/smtp.env
   ```
   - `IRFEN_ALERT_TO` admite **una sola dirección**: el script rechaza listas.
   - Puedes enviarte el correo a ti mismo (la misma cuenta en USER y TO).
   - El script rechaza el archivo si lo pueden leer otros usuarios. En Windows, guárdalo en tu carpeta de usuario o usa variables de entorno con los mismos nombres.
   - **No pegues nunca esta contraseña en el repositorio, en issues ni en chats.**
4. Instala las dependencias (una vez), desde una copia del repositorio en la rama de integración:
   ```bash
   git switch research/v091-live-integration-20261102
   python3 -m pip install "numpy>=1.26,<2" playwright
   python3 -m playwright install chromium     # para el PNG; sin esto se adjunta el HTML
   ```
5. Prueba el envío (solo después de habilitarlo; antes, el script responde «No se envió nada» y sale con el código 3):
   ```bash
   python3 scripts/v091_red_alerts.py --test-email            # correo de prueba de la configuración
   python3 scripts/v091_red_alerts.py --example [--send]      # SIMULACROS con datos históricos reales (río Piura, 2017): NARANJA y ROJO
   ```
   Los simulacros llevan la marca SIMULACRO en la imagen, en el asunto y en el texto para redes. Usan valores reales de IMERG Final y el desborde documentado del 27-03-2017, y no se guardan como alertas enviadas.
6. Ponlo en marcha:
   ```bash
   python3 scripts/v091_red_alerts.py --watch 10   # comprueba cada 10 min mientras esté abierto
   ```
   Lee el último paquete validado de `research/v091-live-data` por HTTPS (o con `--from-git`). Para que funcione sin tener una terminal abierta, prográmalo con `cron`, `launchd` (macOS) o el Programador de tareas (Windows) usando `--once` cada 10 minutos. Solo envía mientras el ordenador esté encendido.

**Para dejar de recibir correos:** detén el script o revoca la contraseña de aplicación en la misma página de Google.

## 6. Límites

- La lluvia y los avisos que aparecen en la hoja son contexto: no confirman ni causan el evento.
- IRFEN no mide caudal ni nivel.
- El envío depende de que tu ordenador esté encendido. La alternativa desde GitHub Actions exigiría guardar las credenciales como secretos de un repositorio público, y no se ha hecho.
- Gmail limita los envíos diarios; un correo por evento queda muy por debajo de ese límite.
