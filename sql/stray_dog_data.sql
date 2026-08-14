SELECT
    city_name_zh,
    estimated_stray_dogs,
    stray_dogs_per_100_people
FROM taiwan_ecology.stray_dog_estimates
WHERE city_name_zh NOT IN (
    '總計',
    '全國',
    '臺灣'
);