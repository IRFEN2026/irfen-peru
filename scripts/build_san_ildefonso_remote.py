#!/usr/bin/env python3

import json
import math
import sys
import tempfile
import zipfile
from pathlib import Path

import requests
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
from pyproj import Geod


URL = (
    "https://data.hydrosheds.org/file/"
    "hydrobasins/standard/"
    "hybas_sa_lev01-12_v1c.zip"
)

TARGET_AREA = 28.9

BBOX = (
    -79.08,
    -8.13,
    -78.91,
    -7.97
)

DOWNSTREAM_REF = Point(
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


def download_zip(url, destination):

    print(
        "Descargando HydroBASINS oficial..."
    )

    with requests.get(
        url,
        stream=True,
        timeout=120
    ) as response:

        response.raise_for_status()

        total = 0

        with open(
            destination,
            "wb"
        ) as output:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if chunk:

                    output.write(
                        chunk
                    )

                    total += len(
                        chunk
                    )

                    print(
                        f"{total / 1024 / 1024:.1f} MB",
                        end="\r"
                    )

    print()
    print(
        "Descarga terminada."
    )


def find_level12(
    folder
):

    candidates = list(
        folder.rglob(
            "*lev12*.shp"
        )
    )

    if not candidates:

        raise RuntimeError(
            "No se encontró "
            "el shapefile level 12."
        )

    # preferir Sudamérica estándar
    candidates.sort(
        key=lambda p:
        (
            "hybas_sa" not in p.name.lower(),
            len(
                str(p)
            )
        )
    )

    return candidates[0]


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
    subset
):

    candidates = []

    for _, row in subset.iterrows():

        up_area = (
            row.get(
                "UP_AREA"
            )
        )

        if up_area is None:
            continue

        try:

            up_area = float(
                up_area
            )

        except Exception:

            continue

        if not (
            5
            <= up_area
            <=
            100
        ):

            continue

        geom = (
            row.geometry
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

        spatial_score = (
            center.distance(
                DOWNSTREAM_REF
            )
            *
            1.5
        )

        score = (
            area_score
            +
            spatial_score
        )

        candidates.append(
            (
                score,
                row
            )
        )

    if not candidates:

        raise RuntimeError(
            "No se encontraron "
            "candidatos de área compatible."
        )

    candidates.sort(
        key=lambda x:
        x[0]
    )

    selected = (
        candidates[0][1]
    )

    ranking = []

    for score, row in (
        candidates[:10]
    ):

        ranking.append({

            "HYBAS_ID":
                int(
                    row[
                        "HYBAS_ID"
                    ]
                ),

            "UP_AREA":
                float(
                    row[
                        "UP_AREA"
                    ]
                ),

            "SUB_AREA":
                float(
                    row[
                        "SUB_AREA"
                    ]
                ),

            "score":
                round(
                    float(
                        score
                    ),
                    5
                )

        })

    return (
        selected,
        ranking
    )


def collect_upstream(
    gdf,
    seed_id
):

    by_downstream = {}

    for _, row in gdf.iterrows():

        try:

            next_down = int(
                row[
                    "NEXT_DOWN"
                ]
            )

        except Exception:

            continue

        by_downstream.setdefault(
            next_down,
            []
        ).append(
            row
        )

    found = {}
    frontier = [
        int(
            seed_id
        )
    ]

    while frontier:

        current = (
            frontier.pop(
                0
            )
        )

        if current in found:
            continue

        row_match = gdf[
            gdf[
                "HYBAS_ID"
            ]
            ==
            current
        ]

        if len(
            row_match
        ):

            found[
                current
            ] = (
                row_match
                .iloc[0]
            )

        children = (
            by_downstream
            .get(
                current,
                []
            )
        )

        for child in children:

            child_id = int(
                child[
                    "HYBAS_ID"
                ]
            )

            if child_id not in found:

                frontier.append(
                    child_id
                )

        if len(
            found
        ) > 500:

            raise RuntimeError(
                "Demasiadas subcuencas "
                "aguas arriba. "
                "Revisar candidato."
            )

    return list(
        found.values()
    )


def main():

    with tempfile.TemporaryDirectory() as tmp:

        tmp = Path(
            tmp
        )

        zip_path = (
            tmp
            /
            "hydrobasins.zip"
        )

        download_zip(
            URL,
            zip_path
        )

        print(
            "Extrayendo archivo..."
        )

        with zipfile.ZipFile(
            zip_path,
            "r"
        ) as z:

            z.extractall(
                tmp
                /
                "hydrobasins"
            )

        shp = find_level12(
            tmp
            /
            "hydrobasins"
        )

        print(
            "Shapefile encontrado:"
        )

        print(
            shp
        )

        print(
            "Leyendo HydroBASINS level 12..."
        )

        gdf = gpd.read_file(
            shp
        )

        if (
            gdf.crs
            is None
        ):

            gdf = (
                gdf.set_crs(
                    4326
                )
            )

        else:

            gdf = (
                gdf.to_crs(
                    4326
                )
            )

        xmin, ymin, xmax, ymax = BBOX

        subset = gdf.cx[
            xmin:xmax,
            ymin:ymax
        ]

        print(
            "Subcuencas en área de búsqueda:",
            len(
                subset
            )
        )

        selected, ranking = (
            choose_candidate(
                subset
            )
        )

        selected_id = int(
            selected[
                "HYBAS_ID"
            ]
        )

        print(
            "Candidato seleccionado:"
        )

        print(
            "HYBAS_ID:",
            selected_id
        )

        print(
            "UP_AREA:",
            selected[
                "UP_AREA"
            ]
        )

        print(
            "SUB_AREA:",
            selected[
                "SUB_AREA"
            ]
        )

        print(
            "Reconstruyendo "
            "cuenca aguas arriba..."
        )

        upstream_rows = (
            collect_upstream(
                gdf,
                selected_id
            )
        )

        geometries = [

            row.geometry

            for row
            in upstream_rows

        ]

        basin = (
            unary_union(
                geometries
            )
            .buffer(0)
        )

        delineated_area = (
            geodesic_area_km2(
                basin
            )
        )

        relative_error = (

            abs(
                delineated_area
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

        feature = {

            "type":
                "Feature",

            "properties": {

                "id":
                    "san_ildefonso",

                "name":
                    (
                        "Quebrada "
                        "San Ildefonso "
                        "— candidato "
                        "HydroBASINS L12"
                    ),

                "dataset":
                    (
                        "HydroBASINS "
                        "v1c level 12"
                    ),

                "source":
                    (
                        "HydroSHEDS "
                        "official download"
                    ),

                "candidate_hybas_id":
                    selected_id,

                "candidate_up_area_km2":
                    float(
                        selected[
                            "UP_AREA"
                        ]
                    ),

                "reference_area_km2":
                    TARGET_AREA,

                "delineated_area_km2":
                    round(
                        delineated_area,
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
                        upstream_rows
                    ),

                "production_ready":
                    False

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
                    delineated_area,
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
                    selected_id,

                "UP_AREA":
                    float(
                        selected[
                            "UP_AREA"
                        ]
                    ),

                "SUB_AREA":
                    float(
                        selected[
                            "SUB_AREA"
                        ]
                    )

            },

            "n_upstream_subbasins":
                len(
                    upstream_rows
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
            "RESULTADO FINAL"
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
