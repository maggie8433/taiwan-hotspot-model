import os
from pathlib import Path
from datetime import datetime

import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine

from ecological_layers import (
    ECOLOGICAL_LAYERS,
    PROTECTED_LAYERS
)


# Project paths
BASE_DIR = Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"


# Load .env
load_dotenv(
    BASE_DIR / ".env"
)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# Check database configuration
required_variables = {
    "DB_HOST": DB_HOST,
    "DB_PORT": DB_PORT,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD
}

missing_variables = [
    name
    for name, value in required_variables.items()
    if not value
]

if missing_variables:
    raise ValueError(
        "Missing database environment variables: "
        + ", ".join(missing_variables)
    )


# Load SQL file from the sql folder.
def load_sql(filename):

    sql_file = SQL_DIR / filename

    if not sql_file.exists():
        raise FileNotFoundError(
            f"SQL file not found: {sql_file}"
        )

    with open(
        sql_file,
        "r",
        encoding="utf-8"
    ) as file:
        return file.read()


# Load the ecological layer SQL template and insert the ecological table name.
def load_ecological_layer_sql(table_name):

    sql_template = load_sql(
        "ecological_layer.sql"
    )

    return sql_template.format(
        table_name=table_name
    )


# Load the verification SQL template and insert the schema and table names.
def load_verification_sql(schema_name, table_name):

    sql_template = load_sql(
        "verification.sql"
    )

    return sql_template.format(
        schema_name=schema_name,
        table_name=table_name
    )


# Connect to PostgreSQL
engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# Load city boundarie
city_sql = load_sql(
    "city_boundary.sql"
)

cities = gpd.read_postgis(
    city_sql,
    engine,
    geom_col="geom"
)

if cities.crs is None:
    raise ValueError(
        "city_boundary has no CRS."
    )


# Project city boundaries
# EPSG:3826 = TWD97 / TM2 zone 121.
# This projected CRS allows area calculations in metres.
cities = cities.to_crs(
    epsg=3826
)


# Repair city geometry
cities["geom"] = (
    cities.geometry.make_valid()
)

cities = cities[
    cities.geometry.notna()
    & ~cities.geometry.is_empty
].copy()


# Calculate city area in km²
cities["city_area_km2"] = (
    cities.geometry.area
    / 1_000_000
)


# Create base result table
result = cities[
    [
        "COUNTYNAME",
        "COUNTYENG",
        "city_area_km2"
    ]
].copy()


# Process ecological_layers
for table_name in ECOLOGICAL_LAYERS:

    print("\n")
    print("========================================")
    print(
        "Processing:",
        table_name
    )
    print("========================================")

    sql = load_ecological_layer_sql(
        table_name
    )

    try:

        # Load ecological layer
        layer = gpd.read_postgis(
            sql,
            engine,
            geom_col="geom"
        )

        print(
            "Rows:",
            len(layer)
        )

        print(
            "Original CRS:",
            layer.crs
        )

        print(
            "Geometry types:"
        )

        print(
            layer.geom_type.value_counts()
        )


        # Check CRS
        if layer.crs is None:

            print(
                "SKIPPED: CRS missing for",
                table_name
            )

            continue


        # Project to EPSG:3826
        layer = layer.to_crs(
            epsg=3826
        )


        # Repair geometry
        layer["geom"] = (
            layer.geometry.make_valid()
        )

        layer = layer[
            layer.geometry.notna()
            & ~layer.geometry.is_empty
        ].copy()


        geometry_types = (
            layer.geom_type.unique()
        )

        print(
            "Detected geometry types:",
            geometry_types
        )


        # layer / MultiPoint layers
        if all(
            geometry_type in [
                "Point",
                "MultiPoint"
            ]
            for geometry_type in geometry_types
        ):

            print(
                "Point layer detected "
                "-> using spatial join"
            )


            # Assign each point to a city
            joined = gpd.sjoin(
                layer,
                cities[
                    [
                        "COUNTYNAME",
                        "COUNTYENG",
                        "geom"
                    ]
                ],
                how="left",
                predicate="within"
            )


            # Count points that did not match a city
            unmatched_points = (
                joined["COUNTYNAME"]
                .isna()
                .sum()
            )

            print(
                "Points outside/unmatched with city:",
                unmatched_points
            )


            # Create count column name
            count_column = (
                table_name
                + "_count"
            )


            # Count points per city
            point_count = (
                joined
                .dropna(
                    subset=[
                        "COUNTYNAME"
                    ]
                )
                .groupby(
                    [
                        "COUNTYNAME",
                        "COUNTYENG"
                    ]
                )
                .size()
                .reset_index(
                    name=count_column
                )
            )


            # Merge point counts into result
            result = result.merge(
                point_count,
                on=[
                    "COUNTYNAME",
                    "COUNTYENG"
                ],
                how="left"
            )

            result[
                count_column
            ] = (
                result[
                    count_column
                ]
                .fillna(0)
                .astype(int)
            )


            # Calculate point density per 100 km²
            density_column = (
                table_name
                + "_per_100km2"
            )

            result[
                density_column
            ] = (
                result[
                    count_column
                ]
                / result[
                    "city_area_km2"
                ]
                * 100
            )

            continue


        # Polygon / MultiPolygon layers
        elif all(
            geometry_type in [
                "Polygon",
                "MultiPolygon"
            ]
            for geometry_type in geometry_types
        ):

            print(
                "Unioning polygons "
                "to remove overlap..."
            )


            # Union polygons within the same layer so that overlapping polygons are not counted twice.
            unique_geometry = (
                layer.geometry.union_all()
            )


            unique_layer = (
                gpd.GeoDataFrame(
                    {
                        "layer_id": [1]
                    },
                    geometry=[
                        unique_geometry
                    ],
                    crs="EPSG:3826"
                )
            )

            unique_layer = (
                unique_layer.rename_geometry(
                    "geom"
                )
            )


            # Intersect with city boundaries
            overlap = gpd.overlay(
                cities[
                    [
                        "COUNTYNAME",
                        "COUNTYENG",
                        "geom"
                    ]
                ],
                unique_layer,
                how="intersection",
                keep_geom_type=False
            )

            print(
                "Overlap records:",
                len(overlap)
            )


            if len(overlap) == 0:

                print(
                    "No overlap found for",
                    table_name
                )

                continue


            # Calculate unique area
            overlap[
                "unique_area_km2"
            ] = (
                overlap.geometry.area
                / 1_000_000
            )


            # Sum area by city
            city_overlap = (
                overlap
                .groupby(
                    [
                        "COUNTYNAME",
                        "COUNTYENG"
                    ],
                    as_index=False
                )[
                    "unique_area_km2"
                ]
                .sum()
            )


            # Generate result column names
            area_column = (
                table_name
                + "_unique_area_km2"
            )

            coverage_column = (
                table_name
                + "_unique_coverage_pct"
            )


            city_overlap = (
                city_overlap.rename(
                    columns={
                        "unique_area_km2":
                        area_column
                    }
                )
            )


            # Merge with result
            result = result.merge(
                city_overlap,
                on=[
                    "COUNTYNAME",
                    "COUNTYENG"
                ],
                how="left"
            )

            result[
                area_column
            ] = (
                result[
                    area_column
                ]
                .fillna(0)
            )


            # Calculate coverage percentage
            result[
                coverage_column
            ] = (
                result[
                    area_column
                ]
                / result[
                    "city_area_km2"
                ]
                * 100
            )

            result[
                coverage_column
            ] = (
                result[
                    coverage_column
                ]
                .clip(
                    lower=0,
                    upper=100
                )
            )


        # Unsupported geometry
        else:

            print(
                "Unsupported or mixed geometry type:",
                geometry_types
            )


    except Exception as error:

        print(
            "FAILED:",
            table_name
        )

        print(
            error
        )


# Create protected-area indicator
print("\n")
print("========================================")
print("Creating protected-area indicator")
print("========================================")


protected_geometries = []


for table_name in PROTECTED_LAYERS:

    print(
        "Loading protected layer:",
        table_name
    )

    sql = load_ecological_layer_sql(
        table_name
    )

    try:

        layer = gpd.read_postgis(
            sql,
            engine,
            geom_col="geom"
        )


        # Skip missing CRS
        if layer.crs is None:

            print(
                "SKIPPED:",
                table_name,
                "- missing CRS"
            )

            continue


        # Project to EPSG:3826
        layer = layer.to_crs(
            epsg=3826
        )


        # Repair geometry
        layer["geom"] = (
            layer.geometry.make_valid()
        )

        layer = layer[
            layer.geometry.notna()
            & ~layer.geometry.is_empty
        ].copy()


        # Only polygon geometry belongs in protected area
        layer = layer[
            layer.geom_type.isin(
                [
                    "Polygon",
                    "MultiPolygon"
                ]
            )
        ].copy()


        if len(layer) == 0:

            print(
                "SKIPPED:",
                table_name,
                "- no polygon geometry"
            )

            continue


        protected_geometries.append(
            layer[
                ["geom"]
            ]
        )


    except Exception as error:

        print(
            "FAILED protected layer:",
            table_name
        )

        print(
            error
        )


# Union protected area layers
if len(protected_geometries) > 0:

    # Combine all protected polygons
    protected = pd.concat(
        protected_geometries,
        ignore_index=True
    )

    protected = gpd.GeoDataFrame(
        protected,
        geometry="geom",
        crs="EPSG:3826"
    )

    print(
        "Protected polygons before union:",
        len(protected)
    )


    # Union all protected layers so overlapping protected areas are counted only once.
    protected_union = (
        protected.geometry.union_all()
    )


    protected_union_gdf = (
        gpd.GeoDataFrame(
            {
                "protected_id": [1]
            },
            geometry=[
                protected_union
            ],
            crs="EPSG:3826"
        )
    )

    protected_union_gdf = (
        protected_union_gdf
        .rename_geometry(
            "geom"
        )
    )


    # Intersect protected areas with city boundaries
    protected_overlap = gpd.overlay(
        cities[
            [
                "COUNTYNAME",
                "COUNTYENG",
                "geom"
            ]
        ],
        protected_union_gdf,
        how="intersection",
        keep_geom_type=False
    )

    print(
        "Protected-area city overlaps:",
        len(protected_overlap)
    )


    # Calculate protected area in km²
    protected_overlap[
        "protected_area_km2"
    ] = (
        protected_overlap.geometry.area
        / 1_000_000
    )


    # Sum protected area by city
    protected_city = (
        protected_overlap
        .groupby(
            [
                "COUNTYNAME",
                "COUNTYENG"
            ],
            as_index=False
        )[
            "protected_area_km2"
        ]
        .sum()
    )


    # Merge protected area into result
    result = result.merge(
        protected_city,
        on=[
            "COUNTYNAME",
            "COUNTYENG"
        ],
        how="left"
    )

    result[
        "protected_area_km2"
    ] = (
        result[
            "protected_area_km2"
        ]
        .fillna(0)
    )


    # Calculate protected-area coverage percentage
    result[
        "protected_area_coverage_pct"
    ] = (
        result[
            "protected_area_km2"
        ]
        / result[
            "city_area_km2"
        ]
        * 100
    )

    result[
        "protected_area_coverage_pct"
    ] = (
        result[
            "protected_area_coverage_pct"
        ]
        .clip(
            lower=0,
            upper=100
        )
    )

else:

    print(
        "WARNING: No protected-area "
        "geometries were available."
    )


# Sort by protected_area_coverage
if (
    "protected_area_coverage_pct"
    in result.columns
):

    result = result.sort_values(
        "protected_area_coverage_pct",
        ascending=False
    )

# Add calculated time
calculated_time = datetime.now()

result[
    "calculated_time"
] = calculated_time

# Save to CSV
output_file = (
    BASE_DIR
    / "ecological_indicators_by_city.csv"
)


result.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)


print("\nCSV results saved to:")
print(
    output_file
)


# Preparing PostgreSQL
print("\n")
print("========================================")
print("Preparing PostgreSQL output")
print("========================================")


db_result = result.copy()


# Rename city columns
db_result = db_result.rename(
    columns={
        "COUNTYNAME":
        "city_name_zh",

        "COUNTYENG":
        "city_name_en"
    }
)


# Add numeric ID
db_result.insert(
    0,
    "id",
    range(
        1,
        len(db_result) + 1
    )
)


# Write Result to PostgreSQL
TABLE_NAME = (
    "city_ecological_indicators"
)

SCHEMA_NAME = (
    "taiwan_ecology"
)


print(
    f"Writing results to "
    f"{SCHEMA_NAME}.{TABLE_NAME}..."
)


db_result.to_sql(
    name=TABLE_NAME,
    con=engine,
    schema=SCHEMA_NAME,
    if_exists="replace",
    index=False,
    method="multi"
)


print(
    f"Successfully created "
    f"{SCHEMA_NAME}.{TABLE_NAME}"
)


# Verify data from PostgreSQL
verification_sql = load_verification_sql(
    SCHEMA_NAME,
    TABLE_NAME
)


verification_result = (
    pd.read_sql(
        verification_sql,
        engine
    )
)


print("\n")
print("========================================")
print("PostgreSQL Import Complete")
print("========================================")


print(
    "Rows imported:",
    len(
        verification_result
    )
)


print(
    "Table:",
    f"{SCHEMA_NAME}.{TABLE_NAME}"
)


print(
    "Calculated time:",
    calculated_time
)


# Close database connection
engine.dispose()


print(
    "\nDatabase connection closed."
)