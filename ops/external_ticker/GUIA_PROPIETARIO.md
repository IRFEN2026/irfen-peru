# Guía del propietario · credenciales y despliegue del reloj externo (Cloudflare Worker)

Procedimiento mínimo y seguro para IRFEN v0.9 (RESEARCH_ONLY / TEST_ONLY). Lo ejecuta solo el propietario
(IRFEN2026). Ningún secreto se escribe en el repositorio, en incidencias, en chats ni en registros.

## Qué hace y qué no hace el Worker
- Cada 10 min consulta si el respaldo `v08-scheduler-fallback.yml` está en cola o en curso; si no lo está, pide a
  GitHub que lo ejecute en `main`. Nada más: no lee datos, no cambia ramas, guardas ni umbrales, no publica Pages.
- El respaldo decide por workflow (activo, en `main`, sin ejecución en curso o en cola, espera mínima cumplida),
  nunca lanza los workflows que consultan SENAMHI ni la publicación de Pages, y anota cada disparo.
- Con `ENABLED="false"` (valor del repositorio) solo registra lo que haría.

## Requisitos (marcar antes de empezar)
- [x] #375 en `main` (respaldo seguro: excluye SENAMHI y Pages, salta workflows deshabilitados, anota disparos).
- [x] Workflows con consultas a SENAMHI deshabilitados en Actions (Ñácara, evidencia oficial, estado Piura).
- [ ] En GitHub → *Settings → Secrets and variables → Actions*: solo existen los secretos esperados
      (`EARTHDATA_TOKEN`). Si aparece otro que no reconoce, no continúe.
- [ ] Cuenta de Cloudflare con verificación en dos pasos activada y sin otros miembros.
- [ ] Ordenador propio con Node.js 20 o posterior y una copia de la rama `v09/external-ticker`
      (solo hacen falta los archivos de `ops/external_ticker/`).

## Paso 1 · Token de GitHub (5 min)
1. GitHub → foto de perfil → *Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained tokens* →
   *Generate new token*.
2. Rellenar exactamente:
   - *Token name*: `irfen-v09-external-ticker`
   - *Expiration*: 30 días (anotar la fecha de caducidad)
   - *Resource owner*: `IRFEN2026`
   - *Repository access*: *Only select repositories* → `irfen-peru`
   - *Repository permissions*: **Actions → Read and write**. Nada más (GitHub añade *Metadata: Read-only*).
3. *Generate token* y copiarlo. Se muestra una sola vez. No pegarlo en ningún sitio salvo en el paso 2.3.

## Paso 2 · Despliegue en modo ensayo (10 min + 30 min de observación)
Desde `ops/external_ticker/`:
1. `npx wrangler@4 login` — abre el navegador para autorizar a Wrangler en la cuenta de Cloudflare
   (no hace falta crear un token de API de Cloudflare).
2. `grep '^ENABLED' wrangler.toml` — debe mostrar `ENABLED = "false"`.
3. `npx wrangler@4 secret put GITHUB_TOKEN` — pegar el token cuando lo pida. Queda cifrado en Cloudflare.
4. `npx wrangler@4 secret list` — debe listar solo el nombre `GITHUB_TOKEN` (nunca su valor).
5. `npx wrangler@4 deploy`
6. `npx wrangler@4 tail` (o Cloudflare → *Workers & Pages* → `irfen-v09-external-ticker` → *Logs*).
   En 30 min deben aparecer 3 líneas como `{"at":"…","dispatched":false,"reason":"DRY_RUN: ENABLED is not 'true'"}`
   (o `FALLBACK_ACTIVE`). Ninguna `LIST_FAILED`.
7. En GitHub → *Actions* → «IRFEN - Respaldo controlado del planificador»: ninguna ejecución nueva lanzada por el
   Worker durante esos 30 min.

Si algo no coincide: `npx wrangler@4 delete`, revocar el token (paso 5) y avisar a Claude.

## Paso 3 · Ensayo activo de 24 h (solo con autorización expresa)
1. `npx wrangler@4 deploy --var ENABLED:true` — el repositorio sigue con `ENABLED="false"`; solo cambia el despliegue.
2. Anotar la hora UTC de inicio y comunicársela a Claude, que generará a las 24 h el informe
   `scripts/v09_continuity_report.py` (tabla por workflow, PASA / NO PASA con el criterio fijado y la traza de cada
   disparo).
3. Criterio: ningún intervalo entre ejecuciones correctas de la captura de avisos y de la lluvia por encima de
   90 min, y cero duplicados (dos ejecuciones creadas a menos de 10 min o solapadas). Todo incumplimiento se reporta.

## Paso 4 · Parada
- Normal (fin del ensayo): `npx wrangler@4 deploy` — vuelve a `ENABLED="false"` (solo registra).
- Completa: `npx wrangler@4 delete`.
- Emergencia (comportamiento inesperado, sospecha sobre el token): revocar el token (paso 5). El Worker deja de poder
  actuar de inmediato, aunque siga desplegado.

## Paso 5 · Revocar o rotar el token
GitHub → *Settings* → *Developer settings* → *Fine-grained tokens* → `irfen-v09-external-ticker` → *Revoke*.
Para rotarlo: crear uno nuevo (paso 1) y repetir el paso 2.3 y 2.5. Rotar antes de la caducidad anotada.

## Nunca
- Poner el token en `wrangler.toml`, en un archivo `.dev.vars`, en variables de un workflow, en el repositorio, en un
  chat o en una incidencia. (`ops/external_ticker/.gitignore` excluye `.dev.vars` y `.wrangler/` por precaución.)
- Dar al token más permisos que *Actions: Read and write* o acceso a otros repositorios.
- Activar `workers_dev` ni rutas públicas: el Worker no tiene interfaz web (responde 404).
- Cambiar `ENABLED` a `"true"` en el repositorio: la activación permanente necesita una autorización posterior a la
  revisión de resultados.
- Abrir la puerta de GitHub Pages ni habilitar alertas públicas.
