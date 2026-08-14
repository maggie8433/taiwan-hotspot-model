# ============================================================
# ECOLOGICAL LAYER CONFIGURATION
# ============================================================
#
# This file contains the ecological layer configuration used
# by test_ecological_overlap.py.
#
# Add or remove layers here instead of modifying the main
# processing script.
# ============================================================


# ============================================================
# ALL ECOLOGICAL LAYERS
# ============================================================

ECOLOGICAL_LAYERS = [
    "ecological_conservation_corridors",
    "forest_wildlife_distribution",
    "important_wildlife_habitats",
    "national_green_network_zones",
    "natural_reserve_areas",
    "nature_reserves",
    "state_forest_management_areas",
    "terrestrial_wildlife_protected_areas"
]


# ============================================================
# PROTECTED-AREA LAYERS
# ============================================================
#
# These layers are unioned together to calculate:
#
#   protected_area_km2
#   protected_area_coverage_pct
#
# A layer listed here should normally also exist in
# ECOLOGICAL_LAYERS.
# ============================================================

PROTECTED_LAYERS = [
    "important_wildlife_habitats",
    "natural_reserve_areas",
    "nature_reserves",
    "terrestrial_wildlife_protected_areas"
]