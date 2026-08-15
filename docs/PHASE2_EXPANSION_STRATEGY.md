# IRFEN — Estrategia de expansión territorial posterior a v0.8

## Decisión de alcance

IRFEN no priorizará únicamente grandes ciudades. Su propósito es anticipar
activaciones de quebradas, huaicos e inundaciones donde puedan afectar a
personas, servicios, carreteras y medios de vida, incluidas localidades
pequeñas, rurales o con limitada capacidad de respuesta.

La v0.8 mantiene sus tres pilotos actuales para cerrar y comprobar el método:
San Ildefonso, Lima Este (Huaycoloro/Chosica) y Catacaos/Bajo Piura. Esto no
reduce la ambición territorial. Evita multiplicar modelos no validados antes
de disponer de un contrato técnico y científico reutilizable.

## Qué puede avanzar antes de cerrar v0.8

Sí puede iniciarse en paralelo la preparación de la fase siguiente:

1. Consolidar puntos críticos oficiales de ANA, CENEPRED, INGEMMET e INDECI.
2. Normalizar nombres, coordenadas, mecanismo y localidad expuesta.
3. Vincular activaciones históricas, población, vías, servicios y aislamiento.
4. Identificar fuentes meteorológicas, satelitales e hidrológicas disponibles.
5. Clasificar cada caso como quebrada local, flujo de detritos, río, llanura de
   inundación o sistema compuesto.
6. Construir un ranking nacional transparente y auditable.

Lo que no se hará es activar nuevas alertas, copiar umbrales entre quebradas o
declarar bajo riesgo por falta de datos.

## Criterios de prioridad

La puntuación preliminar asigna 30% a severidad/exposición, 20% a recurrencia,
20% a rapidez y fragilidad de accesos, 20% a brecha de respuesta y equidad
territorial, y solo 10% a disponibilidad de datos. Así, una comunidad pequeña
no queda desplazada por una capital ni castigada porque mida menos.

## Cobertura territorial que debe investigarse

- Lima norte y cuencas costeras: Chillón/Canta, Chancay-Huaral, Huaura y sus
  quebradas/localidades oficiales.
- Lima sur y Sur Chico: Lurín, Cieneguilla, Malanche/Punta Hermosa, Punta
  Negra, San Bartolo, Pucusana y Chilca.
- Ica, Chincha, Pisco, San Andrés, Santiago, Palpa, Changuillo y Nazca.
- Lambayeque: Motupe, Chongoyape, Oyotún, Zaña, Cayaltí, Lagunas,
  Reque/La Puntilla, Yaipón y Chiriquipe/Juana Ríos.
- Costa norte adicional: Tumbes, Piura fuera de Catacaos, otras quebradas de
  La Libertad y Áncash.
- Costa sur adicional: Arequipa, Moquegua y Tacna.

Esta lista es un ámbito de investigación, no una selección final. Cada nombre
debe resolverse hasta una quebrada, tramo, abanico o sistema fluvial concreto
con evidencia oficial y población expuesta identificada.

## Primera ola posterior a v0.8

La primera preselección debe contener entre 8 y 12 sistemas de peligro y:

- representar costa norte, centro y sur;
- mantener al menos la mitad fuera de Lima Metropolitana;
- incluir expresamente localidades pequeñas o rurales;
- explicar por qué entra cada zona y por qué otras quedan para una ola posterior;
- documentar mecanismo, geometría, eventos, fuentes, exposición, tiempo de
  reacción y brechas antes de programar su modelo.

El archivo `config/phase2_expansion_scope.json` contiene el contrato legible
por máquina para esta preparación. El inventario preliminar y auditable está
en `config/phase2_candidate_inventory_v0_1.json`: sus candidatos permanecen
en `RESEARCH_ONLY`, sin puntuación numérica ni activación, hasta resolver la
geometría, el mecanismo y el contrato de validación de cada sistema.
