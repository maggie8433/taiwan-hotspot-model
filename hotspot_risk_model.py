import os
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
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

DB_SCHEMA = os.getenv(
    "DB_SCHEMA",
    "taiwan_ecology"
)

HOTSPOT_TABLE = os.getenv(
    "HOTSPOT_TABLE",
    "city_hotspot_scores"
)


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
        "Missing environment variables: "
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

# Min-Max normalization.
# Converts a numeric variable to a value between 0 and 1.
# Formula: normalized = (x - minimum)/ (maximum - minimum)
def normalize(series):

    numeric_series = pd.to_numeric(
        series,
        errors="coerce"
    )

    minimum = numeric_series.min()
    maximum = numeric_series.max()

    if pd.isna(minimum) or pd.isna(maximum):

        return pd.Series(
            np.nan,
            index=series.index
        )

    if maximum == minimum:

        return pd.Series(
            0.0,
            index=series.index
        )

    return (
        numeric_series - minimum
    ) / (
        maximum - minimum
    )

#  Convert the 0-100 hotspot score into a categorical risk level.
def get_risk_level(score):

    if pd.isna(score):
        return "Unknown"

    if score >= 80:
        return "Very High"

    elif score >= 60:
        return "High"

    elif score >= 40:
        return "Moderate"

    elif score >= 20:
        return "Low"

    else:
        return "Very Low"


# Connect to PostgreSQL
engine = create_engine(
    f"postgresql+psycopg2://"
    f"{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


print("\nDatabase connection created.")

# Calculate ecological sensitivity score
ecology = pd.read_sql(
    load_sql(
        "ecological_indicators.sql"
    ),
    engine
)


print(
    "Ecological records loaded:",
    len(ecology)
)

required_ecological_columns = [

    "city_name_zh",
    "city_name_en",

    "protected_area_coverage_pct",

    "ecological_conservation_corridors_unique_coverage_pct",

    "state_forest_management_areas_unique_coverage_pct",

    "forest_wildlife_distribution_per_100km2"
]


for column in required_ecological_columns:

    if column not in ecology.columns:

        raise ValueError(
            f"Missing ecological column: {column}"
        )

#  Normalize ecological indicators
ecology["protected_score"] = normalize(
    ecology[
        "protected_area_coverage_pct"
    ]
)


ecology["corridor_score"] = normalize(
    ecology[
        "ecological_conservation_corridors_unique_coverage_pct"
    ]
)


ecology["forest_score"] = normalize(
    ecology[
        "state_forest_management_areas_unique_coverage_pct"
    ]
)


ecology["wildlife_density_score"] = normalize(
    ecology[
        "forest_wildlife_distribution_per_100km2"
    ]
)

# Protected areas       = 25%
# Ecological corridors  = 25%
# State forest          = 25%
# Wildlife distribution = 25%
# This avoids claiming that one ecological indicator is inherently more important without empirical justification.

ECO_Protected_Weight = 0.25
ECO_Corridor_Weight = 0.25
ECO_Forest_Weight = 0.25
ECO_Wildlife_Weight = 0.25


eco_weight_total = (
    ECO_Protected_Weight
    + ECO_Corridor_Weight
    + ECO_Forest_Weight
    + ECO_Wildlife_Weight
)


if not np.isclose(
    eco_weight_total,
    1.0
):
    raise ValueError(
        "Ecological weights must add up to 1."
    )


ecology["ecological_score"] = (

    ECO_Protected_Weight
    * ecology["protected_score"]

    + ECO_Corridor_Weight
    * ecology["corridor_score"]

    + ECO_Forest_Weight
    * ecology["forest_score"]

    + ECO_Wildlife_Weight
    * ecology["wildlife_density_score"]
)


print("\nEcological scores calculated.")

# Calculate stray pressure scores
stray = pd.read_sql(
    load_sql(
        "stray_dog_data.sql"
    ),
    engine
)


print(
    "Stray dog records loaded:",
    len(stray)
)

required_stray_columns = [

    "city_name_zh",
    "estimated_stray_dogs",
    "stray_dogs_per_100_people"

]


for column in required_stray_columns:

    if column not in stray.columns:

        raise ValueError(
            f"Missing stray dog column: {column}"
        )


stray["stray_score"] = normalize(
    stray[
        "stray_dogs_per_100_people"
    ]
)


print("\nStray pressure scores calculated.")

# Calculate Shelter pressure score
shelter = pd.read_sql(
    load_sql(
        "latest_shelter_statistics.sql"
    ),
    engine
)


print(
    "Shelter records loaded:",
    len(shelter)
)

required_shelter_columns = [

    "city_name_zh",
    "close_ym",
    "dog_occupancy_percent"

]


for column in required_shelter_columns:

    if column not in shelter.columns:

        raise ValueError(
            f"Missing shelter column: {column}"
        )


shelter["shelter_score"] = normalize(
    shelter[
        "dog_occupancy_percent"
    ]
)


print("\nShelter pressure scores calculated.")

# Merge Ecological, stray data, shelter data
risk = ecology.merge(

    stray[
        [
            "city_name_zh",

            "estimated_stray_dogs",

            "stray_dogs_per_100_people",

            "stray_score"
        ]
    ],

    on="city_name_zh",

    how="left"
)

risk = risk.merge(

    shelter[
        [
            "city_name_zh",

            "close_ym",

            "dog_occupancy_percent",

            "shelter_score"
        ]
    ],

    on="city_name_zh",

    how="left"
)


print(
    "Combined city records:",
    len(risk)
)

# Check for missing data
score_columns = [

    "stray_score",
    "ecological_score",
    "shelter_score"

]


for column in score_columns:

    missing = risk[
        risk[column].isna()
    ]

    if len(missing) > 0:

        print(
            f"\nWARNING: Missing {column}:"
        )

        print(
            missing[
                [
                    "city_name_zh",
                    "city_name_en"
                ]
            ].to_string(
                index=False
            )
        )

# Equal weighting is the baseline because we currently do not have empirical evidence that one of the three components should receive greater importance.
# Alternative scenarios are used for sensitivity analysis.
WEIGHT_SCENARIOS = {

    # Baseline
    "equal": {

        "stray": 1 / 3,

        "ecology": 1 / 3,

        "shelter": 1 / 3
    },

    # Balanced_focused
    "balanced_focus": {

        "stray": 0.40,

        "ecology": 0.40,

        "shelter": 0.20
    },


    # Stray-focused
    "stray_focus": {

        "stray": 0.50,

        "ecology": 0.30,

        "shelter": 0.20
    },

    # Ecology-focused
    "ecology_focus": {

        "stray": 0.30,

        "ecology": 0.50,

        "shelter": 0.20
    },


    # Shelter-focused
    "shelter_focus": {

        "stray": 0.30,

        "ecology": 0.30,

        "shelter": 0.40
    }
}

for scenario_name, weights in WEIGHT_SCENARIOS.items():

    total = (

        weights["stray"]

        + weights["ecology"]

        + weights["shelter"]
    )


    if not np.isclose(
        total,
        1.0
    ):

        raise ValueError(
            f"Weights for '{scenario_name}' "
            f"do not add up to 1."
        )

# Calculate all hotspot scenarios
for scenario_name, weights in WEIGHT_SCENARIOS.items():

    score_column = (
        f"{scenario_name}_hotspot_score"
    )


    risk[score_column] = (

        weights["stray"]
        * risk["stray_score"]

        + weights["ecology"]
        * risk["ecological_score"]

        + weights["shelter"]
        * risk["shelter_score"]

    ) * 100


    risk[score_column] = (
        risk[score_column]
        .round(2)
    )

    rank_column = (
        f"{scenario_name}_rank"
    )


    risk[rank_column] = (

        risk[score_column]

        .rank(
            ascending=False,
            method="min"
        )

        .astype("Int64")
    )

# The equal-weight scenario is the baseline.
risk["hotspot_score"] = (
    risk[
        "equal_hotspot_score"
    ]
)


risk["risk_rank"] = (
    risk[
        "equal_rank"
    ]
)

risk["risk_level"] = (

    risk[
        "hotspot_score"
    ]

    .apply(
        get_risk_level
    )
)

scenario_rank_columns = [

    "equal_rank",

    "balanced_focus_rank",

    "stray_focus_rank",

    "ecology_focus_rank",

    "shelter_focus_rank"

]


risk["best_rank"] = (

    risk[
        scenario_rank_columns
    ]

    .min(
        axis=1
    )
)


risk["worst_rank"] = (

    risk[
        scenario_rank_columns
    ]

    .max(
        axis=1
    )
)


risk["rank_range"] = (

    risk["worst_rank"]

    - risk["best_rank"]
)

scenario_score_columns = [

    "equal_hotspot_score",

    "balanced_focus_hotspot_score",

    "stray_focus_hotspot_score",

    "ecology_focus_hotspot_score",

    "shelter_focus_hotspot_score"

]


risk["minimum_scenario_score"] = (

    risk[
        scenario_score_columns
    ]

    .min(
        axis=1
    )
)


risk["maximum_scenario_score"] = (

    risk[
        scenario_score_columns
    ]

    .max(
        axis=1
    )
)


risk["score_range"] = (

    risk["maximum_scenario_score"]

    - risk["minimum_scenario_score"]
)


risk["score_range"] = (
    risk["score_range"]
    .round(2)
)

risk = risk.sort_values(
    "risk_rank",
    ascending=True
)

# Add calculated time
calculated_time = datetime.now().replace(
    microsecond=0
)

risk[
    "calculated_time"
] = calculated_time

# Save to CSV
output_file = (
    BASE_DIR
    / "hotspot_risk_sensitivity_analysis.csv"
)


risk.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)


print("\nCSV results saved to:")
print(
    output_file
)


# Preparing PostgreSQL
db_result = risk.copy()


# Write Result to PostgreSQL
db_result.to_sql(

    name=HOTSPOT_TABLE,

    con=engine,

    schema=DB_SCHEMA,

    if_exists="replace",

    index=False,

    method="multi"
)


print(
    "Created:",
    f"{DB_SCHEMA}.{HOTSPOT_TABLE}"
)

print(
    "Rows written:",
    len(db_result)
)


# Close database connection
engine.dispose()


print(
    "\nDatabase connection closed."
)