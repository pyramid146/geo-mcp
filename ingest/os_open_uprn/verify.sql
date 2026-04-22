-- Verify staging.os_open_uprn loaded sanely.
-- Expect ~40M rows across GB (~33M England, ~3M Wales, ~3M Scotland).

SELECT 'row_count' AS metric, COUNT(*)::text AS value FROM staging.os_open_uprn
UNION ALL
SELECT 'min_uprn',  MIN(uprn)::text FROM staging.os_open_uprn
UNION ALL
SELECT 'max_uprn',  MAX(uprn)::text FROM staging.os_open_uprn
UNION ALL
SELECT 'bbox_lat_range',
       round(MIN(lat)::numeric, 3)::text || ' to ' || round(MAX(lat)::numeric, 3)::text
  FROM staging.os_open_uprn
UNION ALL
SELECT 'bbox_lon_range',
       round(MIN(lon)::numeric, 3)::text || ' to ' || round(MAX(lon)::numeric, 3)::text
  FROM staging.os_open_uprn
UNION ALL
SELECT 'indexes',
       string_agg(indexname, ', ')
  FROM pg_indexes
 WHERE schemaname = 'staging' AND tablename = 'os_open_uprn';

-- Spot-check a well-known UPRN if one exists.
-- 10 Downing Street's UPRN is 10033544614 (publicly known landmark).
SELECT 'downing_street_10_uprn_10033544614' AS check,
       uprn, round(lat::numeric, 5) AS lat, round(lon::numeric, 5) AS lon
  FROM staging.os_open_uprn
 WHERE uprn = 10033544614;
