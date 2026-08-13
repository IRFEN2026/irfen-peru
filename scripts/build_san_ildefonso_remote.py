#!/usr/bin/env python3

import json
import math
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.ops import unary_union
from pyproj import Geod


SERVICE = (
    "https://services1.arcgis.com/"
    "euMKmvUChvyJxWq2/ArcGIS/rest/services/"
    "HaydroBASINS_15s/FeatureServer/15/query"
)

FIELDS = (
    "HYBAS_ID,NEXT_DOWN,SUB_AREA,UP_AREA,PFAF_ID"
)

TARGET_AREA = 28.9

# Referencia aproximada del sector bajo de San Ildefonso.
REF_LON = -78.997
REF_LAT = -8.063

OUT = Path(
    "site/data/watersheds/"
    "san_ildefonso_hydrobasins.geojson"
)

REPORT = Path(
    "site/data/watersheds/"
    "san_ildefonso_validation.json"
)


def request_arcgis(params, attempts=3):

    last_error = None

    for attempt in range(1, attempts + 1):

        try:

            response = requests.get(
                SERVICE,
                params=params,
                timeout=60
            )

            try:
                data = response.json()
            except Exception:
                data = None

            if response.status_code != 200:

                detail = (
                    json.dumps(data)
                    if data is not None
                    else response.text[:1000]
                )

                raise RuntimeError(
                    f"HTTP {response.status_code}: "
                    f"{detail}"
                )

            if (
                isinstance(data, dict)
                and
                "error" in data
            ):

                raise RuntimeError(
                    json.dumps(
                        data["error"],
                        ensure_ascii=False
                    )
                )

            return data

        except Exception as exc:

            last_error = exc

            print(
                f"Intento {attempt}/{attempts} falló:"
            )

            print(
                str(exc)
            )

            if attempt < attempts:

                wait = attempt * 10

                print(
                    f"Esperando {wait}s..."
                )

                time.sleep(wait)

    raise RuntimeError(
        f"ArcGIS no respondió correctamente: "
        f"{last_error}"
    )


def service_test():

    print(
        "1. Comprobando servicio HydroBASINS..."
    )

    data = request_arcgis({

        "where":
            "1=1",

        "outFields":
            "HYBAS_ID,UP_AREA",

        "returnGeometry":
            "false",

        "resultRecordCount":
            "1",

        "f":
            "json"

    })

    features = data.get(
        "features",
        []
    )

    if not features:

        raise RuntimeError(
            "El servicio respondió "
            "pero no devolvió registros."
        )

    print(
        "Servicio HydroBASINS OK."
    )

    print(
        "Primer registro:",
        features[0].get(
            "attributes",
            {}
        )
    )


def point_query(lon, lat):

    data = request_arcgis({

        "where":
            "1=1",

        "geometry":
            f"{lon},{lat}",

        "geometryType":
            "esriGeometryPoint",

        "inSR":
            "4326",

        "spatialRel":
            "esriSpatialRelIntersects",

        "outFields":
            FIELDS,

        "returnGeometry":
            "true",

        "outSR":
            "4326",

        "f":
            "geojson"

    })

    return data.get(
        "features",
        []
    )


def search_candidates():

    print()
    print(
        "2. Explorando subcuencas "
        "alrededor de San Ildefonso..."
    )

    # Malla de puntos alrededor del sector bajo.
    offsets = [
        -0.06,
        -0.04,
        -0.02,
        0.00,
        0.02,
        0.04,
        0.06
    ]

    found = {}

    total = (
        len(offsets)
        *
        len(offsets)
    )

    count = 0

    for dx in offsets:

        for dy in offsets:

            count += 1

            lon = (
                REF_LON
                +
                dx
            )

            lat = (
                REF_LAT
                +
                dy
            )

            print(
                f"Punto {count}/{total}: "
                f"{lon:.4f}, {lat:.4f}"
            )

            try:

                features = point_query(
                    lon,
                    lat
                )

            except Exception as exc:

                print(
                    "  Consulta omitida:",
                    exc
                )

                continue

            for feature in features:

                props = feature.get(
                    "properties",
                    {}
                )

                hid = props.get(
                    "HYBAS_ID"
                )

                if hid is None:
                    continue

                found[
                    int(hid)
                ] = feature

    print()
    print(
        "Subcuencas únicas encontradas:",
        len(found)
    )

    if not found:

        raise RuntimeError(
            "No se encontraron "
            "subcuencas en la malla."
        )

    return list(
        found.values()
    )


def choose_candidate(features):

    print()
    print(
        "3. Seleccionando candidato "
        "más compatible con 28.9 km²..."
    )

    candidates = []

    for feature in features:

        props = feature.get(
            "properties",
            {}
        )

        try:

            up_area = float(
                props.get(
                    "UP_AREA"
                )
            )

        except Exception:

            continue

        # Margen amplio para no descartar
        # prematuramente un candidato.
        if not (
            5
            <=
            up_area
            <=
            100
        ):

            continue

        geom = shape(
            feature[
                "geometry"
            ]
        )

        center = (
            geom
            .representative_point()
        )

        area_error = abs(
            math.log(
                max(
                    up_area,
                    0.001
                )
                /
                TARGET_AREA
            )
        )

        distance = math.hypot(
            center.x - REF_LON,
            center.y - REF_LAT
        )

        # El área domina la selección;
        # la distancia actúa solo como
        # segundo criterio.
        score = (
            area_error
            +
            0.75
            *
            distance
        )

        candidates.append(
            (
                score,
                feature
            )
        )

    if not candidates:

        raise RuntimeError(
            "Ninguna subcuenca encontrada "
            "tiene UP_AREA entre 5 y 100 km²."
        )

    candidates.sort(
        key=lambda x:
        x[0]
    )

    print(
        "Top candidatos:"
    )

    ranking = []

    for score, feature in candidates[:10]:

        props = feature[
            "properties"
        ]

        row = {

            "HYBAS_ID":
                int(
                    props[
                        "HYBAS_ID"
                    ]
                ),

            "UP_AREA":
                float(
                    props[
                        "UP_AREA"
                    ]
                ),

            "SUB_AREA":
                float(
                    props[
                        "SUB_AREA"
                    ]
                ),

            "score":
                round(
                    score,
                    5
                )

        }

        ranking.append(
            row
        )

        print(
            row
        )

    selected = (
        candidates[0][1]
    )

    return (
        selected,
        ranking
    )


def query_children(
    downstream_id
):

    data = request_arcgis({

        "where":
            (
                "NEXT_DOWN = "
                f"{int(downstream_id)}"
            ),

        "outFields":
            FIELDS,

        "returnGeometry":
            "true",

        "outSR":
            "4326",

        "f":
            "geojson"

    })

    return data.get(
        "features",
        []
    )


def collect_upstream(seed):

    print()
    print(
        "4. Reconstruyendo "
        "la cuenca aguas arriba..."
    )

    seed_id = int(
        seed[
            "properties"
        ][
            "HYBAS_ID"
        ]
    )

    found = {
        seed_id:
            seed
    }

    frontier = [
        seed_id
    ]

    while frontier:

        current = (
            frontier.pop(0)
        )

        print(
            "Buscando tributarios de:",
            current
        )

        children = (
            query_children(
                current
            )
        )

        for feature in children:

            props = feature[
                "properties"
            ]

            child_id = int(
                props[
                    "HYBAS_ID"
                ]
            )

            if child_id in found:
                continue

            found[
                child_id
            ] = feature

            frontier.append(
                child_id
            )

        if len(found) > 300:

            raise RuntimeError(
                "Más de 300 subcuencas "
                "aguas arriba. "
                "Se detiene por seguridad."
            )

    print(
        "Subcuencas aguas arriba:",
        len(found)
    )

    return list(
        found.values()
    )


def geodesic_area_km2(geom):

    geod = Geod(
        ellps="WGS84"
    )

    area, _ = (
        geod
        .geometry_area_perimeter(
            geom
        )
    )

    return (
        abs(area)
        /
        1e6
    )


def save_result(
    seed,
    upstream,
    ranking
):

    print()
    print(
        "5. Generando geometría "
        "y validación..."
    )

    geometries = [

        shape(
            feature[
                "geometry"
            ]
        )

        for feature in upstream

    ]

    basin = (
        unary_union(
            geometries
        )
        .buffer(0)
    )

    area = (
        geodesic_area_km2(
            basin
        )
    )

    relative_error = (

        abs(
            area
            -
            TARGET_AREA
        )

        /
        TARGET_AREA

    )

    if (
        relative_error
        <=
        0.15
    ):

        status = "PASS"

    elif (
        relative_error
        <=
        0.25
    ):

        status = "REVIEW"

    else:

        status = "FAIL"

    props = seed[
        "properties"
    ]

    feature = {

        "type":
            "Feature",

        "properties": {

            "id":
                "san_ildefonso",

            "name":
                (
                    "Quebrada San Ildefonso "
                    "— candidato HydroBASINS L12"
                ),

            "dataset":
                (
                    "HydroBASINS "
                    "v1c level 12"
                ),

            "candidate_hybas_id":
                int(
                    props[
                        "HYBAS_ID"
                    ]
                ),

            "candidate_up_area_km2":
                float(
                    props[
                        "UP_AREA"
                    ]
                ),

            "reference_area_km2":
                TARGET_AREA,

            "delineated_area_km2":
                round(
                    area,
                    3
                ),

            "relative_area_error":
                round(
                    relative_error,
                    4
                ),

            "validation_status":
                status,

            "n_subbasins":
                len(
                    upstream
                ),

            "production_ready":
                False,

            "note":
                (
                    "Candidato de validación "
                    "HydroBASINS L12. "
                    "No sustituye todavía "
                    "la delineación final "
                    "de alta resolución."
                )

        },

        "geometry":
            basin.__geo_interface__

    }

    report = {

        "zone_id":
            "san_ildefonso",

        "status":
            status,

        "reference_area_km2":
            TARGET_AREA,

        "delineated_area_km2":
            round(
                area,
                3
            ),

        "relative_area_error_pct":
            round(
                relative_error
                *
                100,
                2
            ),

        "selected_candidate": {

            "HYBAS_ID":
                int(
                    props[
                        "HYBAS_ID"
                    ]
                ),

            "UP_AREA":
                float(
                    props[
                        "UP_AREA"
                    ]
                ),

            "SUB_AREA":
                float(
                    props[
                        "SUB_AREA"
                    ]
                )

        },

        "n_upstream_subbasins":
            len(
                upstream
            ),

        "top_candidates":
            ranking

    }

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUT.write_text(
        json.dumps(
            feature,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    REPORT.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print()
    print(
        "================================"
    )

    print(
        "RESULTADO FINAL"
    )

    print(
        "================================"
    )

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        )
    )


def main():

    service_test()

    features = (
        search_candidates()
    )

    seed, ranking = (
        choose_candidate(
            features
        )
    )

    print()
    print(
        "Candidato seleccionado:"
    )

    print(
        json.dumps(
            seed[
                "properties"
            ],
            ensure_ascii=False,
            indent=2
        )
    )

    upstream = (
        collect_upstream(
            seed
        )
    )

    save_result(
        seed,
        upstream,
        ranking
    )

    return 0


if __name__ == "__main__":

    sys.exit(
        main()
    )
