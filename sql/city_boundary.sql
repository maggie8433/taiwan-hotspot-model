SELECT
    "COUNTYNAME",
    "COUNTYENG",
    geom
FROM taiwan_ecology.city_boundary
WHERE geom IS NOT NULL;