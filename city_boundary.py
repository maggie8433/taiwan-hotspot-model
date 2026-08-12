import os
from pathlib import Path

import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Project paths
BASE_DIR = Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"


# Load .env
load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


# Load SQL file 
def load_sql(filename):
    """
    Read an SQL file from the sql folder.
    """

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

# Connect to PostgreSQL
engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Read city boundaries
city_sql = load_sql(
    "city_boundary.sql"
)

cities = gpd.read_postgis(
    city_sql,
    engine,
    geom_col="geom"
)

print("City CRS:", cities.crs)


# Read important wildlife habitats
habitat_sql = load_sql(
    "important_wildlife_habitats.sql"
)

habitats = gpd.read_postgis(
    habitat_sql,
    engine,
    geom_col="geom"
)

print("\nHabitat CRS:", habitats.crs)

# Check CRS
if cities.crs is None:
    raise ValueError(
        "city_boundary CRS is missing"
    )

if habitats.crs is None:
    raise ValueError(
        "important_wildlife_habitats CRS is missing"
    )


# Convert both to EPSG:3826
cities = cities.to_crs(
    epsg=3826
)

habitats = habitats.to_crs(
    epsg=3826
)

# Repair invalid geometry
cities["geom"] = (
    cities.geometry.make_valid()
)

habitats["geom"] = (
    habitats.geometry.make_valid()
)

# Calculate city area
cities["city_area_km2"] = (
    cities.geometry.area
    / 1_000_000
)

# Remove overlap inside habitat layer
# Union habitat polygons first so the same habitat area is not counted twice.
unique_habitat_geometry = (
    habitats.geometry.union_all()
)

unique_habitats = gpd.GeoDataFrame(
    {
        "habitat_id": [1]
    },
    geometry=[
        unique_habitat_geometry
    ],
    crs="EPSG:3826"
)

unique_habitats = (
    unique_habitats.rename_geometry(
        "geom"
    )
)

# Intersect habitats with cities
overlap = gpd.overlay(
    cities[
        [
            "COUNTYNAME",
            "COUNTYENG",
            "geom"
        ]
    ],
    unique_habitats,
    how="intersection",
    keep_geom_type=False
)

print(
    "\nOverlap records:",
    len(overlap)
)

# Calculate overlap area
overlap["habitat_area_km2"] = (
    overlap.geometry.area
    / 1_000_000
)

# Sum habitat area by city
city_habitat = (
    overlap
    .groupby(
        [
            "COUNTYNAME",
            "COUNTYENG"
        ],
        as_index=False
    )[
        "habitat_area_km2"
    ]
    .sum()
)

# Add total city area
city_area = cities[
    [
        "COUNTYNAME",
        "COUNTYENG",
        "city_area_km2"
    ]
]


result = city_area.merge(
    city_habitat,
    on=[
        "COUNTYNAME",
        "COUNTYENG"
    ],
    how="left"
)


result["habitat_area_km2"] = (
    result["habitat_area_km2"]
    .fillna(0)
)

# Calculate habitat coverage %
result[
    "habitat_coverage_percent"
] = (
    result["habitat_area_km2"]
    / result["city_area_km2"]
    * 100
)

# Sort result
result = result.sort_values(
    "habitat_coverage_percent",
    ascending=False
)

print(
    "\nImportant Wildlife Habitat Coverage:"
)

print(
    result[
        [
            "COUNTYNAME",
            "COUNTYENG",
            "city_area_km2",
            "habitat_area_km2",
            "habitat_coverage_percent"
        ]
    ].to_string(
        index=False
    )
)

# Close database connection
engine.dispose()

print(
    "\nDatabase connection closed."
)