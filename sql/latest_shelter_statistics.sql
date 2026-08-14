SELECT DISTINCT ON (city_name_zh)
    city_name_zh,
    close_ym,
    dog_occupancy_percent
FROM taiwan_ecology.shelter_statistics
WHERE city_name_zh NOT IN (
    '總計',
    '全國',
    '臺灣'
)
ORDER BY
    city_name_zh,
    close_ym DESC;