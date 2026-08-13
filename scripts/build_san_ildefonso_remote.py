#!/usr/bin/env python3

import json
import math
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union
from pyproj import Geod


SERVICE = (
    "https://services1.arcgis.com/"
    "euMKmvUChvyJxWq2/"
    "ArcGIS/rest/services/"
    "HaydroBASINS_15s/"
    "FeatureServer/15/query"
)

TARGET_AREA = 28.9

BBOX = {
    "xmin": -79.08,
    "ymin": -8.13,
    "xmax": -78.91,
    "ymax": -7.97,
    "spatialReference": {
        "wkid": 4326
    }
}

DOWNSTREAM_REF = (
    -78.997,
    -8.063
)

OUT = Path(
    "site/data/watersheds/"
    "san_ildefonso_hydrobasins.geojson"
)

REPORT = Path(
    "site/data/watersheds/"
    "san_ildefonso_validation.json"
)


def post_json(params, attempts=4):

    last = None

    for i in range(attempts):

        try:

            response = requests.post(
                SERVICE,
                data=params,
                timeout=60
            )

            response.raise_for_status()

            data = response.json()

            if "error" in data:

                raise RuntimeError(
                    data["error"]
                )

            return data

        except Exception as exc:

            last = exc

            print(
                f"Intento {i + 1} falló:"
            )

            print(
                str(exc)
            )

            if i < attempts - 1:

                wait = (
                    i + 1
                ) * 10

                print(
                    f"Esperando {wait}s..."
                )

                time.sleep(
                    wait
                )

    raise RuntimeError(
        "ArcGIS/HydroBASINS no respondió: "
        f"{last}"
    )


def query_bbox():

    return post_json({

        "where":
            "1=1",

        "geometry":
            json.dumps(
                BBOX
            ),

        "geometryType":
            "esriGeometryEnvelope",

        "inSR":
            "4326",

        "spatialRel":
            "esriSpatialRelIntersects",

        "outFields":
            (
                "HYBAS_ID,"
                "NEXT_DOWN,"
                "SUB_AREA,"
                "UP_AREA,"
                "PFAF_ID"
            ),

        "returnGeometry":
            "true",

        "outSR":
            "4326",

        "f":
            "geojson"

    })


def query_upstream_children(
    down_id
):

    return post_json({

        "where":
            f"NEXT_DOWN={int(down_id)}",

        "outFields":
            (
                "HYBAS_ID,"
                "NEXT_DOWN,"
                "SUB_AREA,"
                "UP_AREA,"
                "PFAF_ID"
            ),

        "returnGeometry":
            "true",

        "outSR":
            "4326",

        "f":
            "geojson"

    })


def geodesic_area_km2(
    geom
):

    geod = Geod(
        ellps="WGS84"
    )

    area, _ = (
        geod.geometry_area_perimeter(
            geom
        )
    )

    return (
        abs(area)
        /
        1e6
    )


def choose_candidate(
    feature_collection
):

    features = (
        feature_collection
        .get(
            "features",
            []
        )
    )

    print(
        f"Polígonos recibidos: "
        f"{len(features)}"
    )

    if not features:

        raise RuntimeError(
            "No se recibieron "
            "polígonos HydroBASINS."
        )

    reference = Point(
        *DOWNSTREAM_REF
    )

    candidates = []

    for feature in features:

        props = (
            feature.get(
                "properties",
                {}
            )
        )

        up_area = (
            props.get(
                "UP_AREA"
            )
        )

        if up_area is None:
            continue

        up_area = float(
            up_area
        )

        if not (
            5
            <= up_area
            <= 100
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

        area_score = abs(
            math.log(
                max(
                    up_area,
                    0.001
                )
                /
                TARGET_AREA
            )
        )

        distance = (
            center.distance(
                reference
            )
        )

        spatial_score = (
            1.5
            *
            distance
        )

        score = (
            area_score
            +
            spatial_score
        )

        candidates.append(
            (
                score,
                feature
            )
        )

    if not candidates:

        raise RuntimeError(
            "No se encontraron "
            "candidatos con UP_AREA "
            "entre 5 y 100 km²."
        )

    candidates.sort(
        key=lambda item:
        item[0]
    )

    selected = (
        candidates[0][1]
    )

    ranking = []

    for score, feature in (
        candidates[:10]
    ):

        props = (
            feature[
                "properties"
            ]
        )

        ranking.append({

            "HYBAS_ID":
                props.get(
                    "HYBAS_ID"
                ),

            "UP_AREA":
                props.get(
                    "UP_AREA"
                ),

            "SUB_AREA":
                props.get(
                    "SUB_AREA"
                ),

            "score":
                round(
                    score,
                    5
                )

        })

    return (
        selected,
        ranking
    )


def collect_upstream(
    seed_feature,
    max_nodes=250
):

    seed_id = int(
        seed_feature[
            "properties"
        ][
            "HYBAS_ID"
        ]
    )

    found = {
        seed_id:
        seed_feature
    }

    frontier = [
        seed_id
    ]

    while frontier:

        down_id = (
            frontier.pop(
                0
            )
        )

        fc = (
            query_upstream_children(
                down_id
            )
        )

        for feature in (
            fc.get(
                "features",
                []
            )
        ):

            hyd_id = int(
                feature[
                    "properties"
                ][
                    "HYBAS_ID"
                ]
            )

            if hyd_id in found:
                continue

            found[
                hyd_id
            ] = feature

            frontier.append(
                hyd_id
            )

            if (
                len(found)
                >
                max_nodes
            ):

                raise RuntimeError(
                    "La reconstrucción "
                    "aguas arriba superó "
                    "el límite de seguridad."
                )

    return list(
        found.values()
    )


def main():

    print(
        "Consultando HydroBASINS..."
    )

    feature_collection = (
        query_bbox()
    )

    print(
        "Buscando candidato "
        "cercano a 28.9 km²..."
    )

    seed, ranking = (
        choose_candidate(
            feature_collection
        )
    )

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

    print(
        "Reconstruyendo "
        "cuenca aguas arriba..."
    )

    upstream = (
        collect_upstream(
            seed
        )
    )

    geometries = [

        shape(
            feature[
                "geometry"
            ]
        )

        for feature
        in upstream

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

    seed_props = (
        seed[
            "properties"
        ]
    )

    output_feature = {

        "type":
            "Feature",

        "properties": {

            "id":
                "san_ildefonso",

            "name":
                (
                    "Quebrada San "
                    "Ildefonso — "
                    "cuenca candidata "
                    "HydroBASINS L12"
                ),

            "dataset":
                (
                    "HydroBASINS "
                    "v1c level 12"
                ),

            "candidate_hybas_id":
                seed_props.get(
                    "HYBAS_ID"
                ),

            "candidate_up_area_km2":
                seed_props.get(
                    "UP_AREA"
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
                False

        },

        "geometry":
            mapping(
                basin
            )

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

        "selected_candidate":
            seed_props,

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
            output_feature,
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
        "VALIDACIÓN:"
    )

    print(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        )
    )

    return 0


if __name__ == "__main__":

    sys.exit(
        main()
    )
