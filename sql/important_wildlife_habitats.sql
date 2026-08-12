SELECT
    id,
    "Name",
    name_en,
    geom
FROM taiwan_ecology.important_wildlife_habitats
WHERE geom IS NOT NULL;