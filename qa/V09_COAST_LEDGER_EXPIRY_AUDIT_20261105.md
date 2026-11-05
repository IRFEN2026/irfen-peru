# Auditoría de caducidad del ledger costero — 2026-11-05

**RESEARCH_ONLY / TEST_ONLY; Tumbes–Tacna exclusivamente.** La revisión del ledger del PR #491 encontró dos rutas de contaminación temporal:

1. `published_at` podía estar después de `ingest_time` cuando `available_at` era null. Ahora se rechaza: un archivo no puede atribuirse conocimiento de una publicación futura.
2. `expires_at` se comprobaba solo frente a `observation_time`. Una observación ya caducada en el momento de ingesta podía marcarse apta para replay prospectivo. Ahora queda archivada como evidencia, pero `fresh_at_ingestion=false` y `eligible_for_prospective_replay=false`.

Se añaden tres casos sintéticos a los ocho originales. Estas barreras **no demuestran predictibilidad** y no importan datos meteorológicos. La frescura retrospectiva del producto y el conocimiento disponible en cada instante de emisión requieren `available_at` verificable; nunca inferirlo de la latencia nominal de IMERG Early. Los cambios no afectan `main`, alertas, semáforos, publicaciones o umbrales.

**Auditoría de fuentes:** #491 ya registra la presencia de archivos IMERG Early para costa y norte, GOES-19 norte y avisos INDECI/COEN en ramas de integración. No se repiten descargas. Ninguna nueva serie de caudal/nivel horario independiente ha sido verificada en esta revisión. Las 11 regiones costeras tienen soporte de metadatos; no hay prueba de continuidad de capturas en todas ellas. En consecuencia, los horizontes 1/3/6/12/24 h siguen `NO_EVALUABLE` para habilidad hidrológica.

**Nota metodológica:** la caducidad de una observación es una política de uso de señales, no la eliminación de evidencia histórica. Para reconstrucción histórica, el evento debe existir con `observation_time`, `published_at` y `available_at` originales, y no se debe inventar una `ingest_time` antigua. Este ledger preserva registros sin sobrescribirlos, pero no es almacenamiento WORM certificado.

Pruebas: `python -m unittest discover -s tests -p 'test_v09_coastal_season_ledger.py' -v`.
