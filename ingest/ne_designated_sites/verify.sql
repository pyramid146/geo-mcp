-- Verify staging.ne_designated_sites is sane.

SELECT 'row_count' AS metric, COUNT(*)::text AS value
  FROM staging.ne_designated_sites
UNION ALL
SELECT 'distinct_types',
       string_agg(DISTINCT designation_type, ', ')
  FROM staging.ne_designated_sites;

-- Per-type counts.
SELECT designation_type, COUNT(*) AS n
  FROM staging.ne_designated_sites
 GROUP BY 1
 ORDER BY 2 DESC;

-- Spot check: what designations contain / are near Kew Gardens
-- (51.4787, -0.2956)? Kew is a World Heritage Site (Historic
-- England's territory) but also sits within several NE designations.
SELECT designation_type, name
  FROM staging.ne_designated_sites d
 WHERE ST_DWithin(
     d.geom_osgb,
     ST_Transform(ST_SetSRID(ST_MakePoint(-0.2956, 51.4787), 4326), 27700),
     500
 )
 LIMIT 10;
