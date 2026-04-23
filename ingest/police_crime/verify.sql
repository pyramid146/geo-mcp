-- Sanity checks for staging.police_crimes.

SELECT 'row_count' AS metric, COUNT(*)::text AS value FROM staging.police_crimes
UNION ALL
SELECT 'date_range',
       MIN(month)::text || ' to ' || MAX(month)::text FROM staging.police_crimes
UNION ALL
SELECT 'distinct_crime_types',
       COUNT(DISTINCT crime_type)::text FROM staging.police_crimes
UNION ALL
SELECT 'distinct_forces',
       COUNT(DISTINCT reported_by)::text FROM staging.police_crimes;

-- Top 5 crime types.
SELECT crime_type, COUNT(*) AS n
  FROM staging.police_crimes
 GROUP BY 1
 ORDER BY 2 DESC
 LIMIT 5;

-- Spot-check: crimes within 500 m of central London (SW1A 1AA area).
SELECT COUNT(*) AS westminster_500m_crimes
  FROM staging.police_crimes p
 WHERE ST_DWithin(
     p.geom_osgb,
     ST_Transform(ST_SetSRID(ST_MakePoint(-0.1419, 51.5014), 4326), 27700),
     500
 );
