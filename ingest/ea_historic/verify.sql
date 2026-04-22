\pset format aligned
\pset title 'EA Historic Floods (Recorded Flood Outlines) verification'

\echo ''
\echo '== Row count =='
SELECT COUNT(*) FROM staging.ea_historic_floods;

\echo ''
\echo '== SRID (expect 27700) =='
SELECT DISTINCT ST_SRID(geom) FROM staging.ea_historic_floods LIMIT 1;

\echo ''
\echo '== Date range =='
SELECT
    MIN(start_date) AS earliest,
    MAX(start_date) AS latest,
    COUNT(*) FILTER (WHERE start_date IS NULL) AS undated
  FROM staging.ea_historic_floods;

\echo ''
\echo '== Source distribution =='
SELECT flood_src, COUNT(*) AS n
  FROM staging.ea_historic_floods
 GROUP BY flood_src
 ORDER BY n DESC
 LIMIT 10;

\echo ''
\echo '== Spot-check: Tewkesbury (fluvial flood hot spot) =='
WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-2.1554, 51.9929), 4326), 27700) AS g)
SELECT COUNT(*)                                  AS floods_covering_tewkesbury,
       MIN(start_date)::date                     AS earliest,
       MAX(start_date)::date                     AS most_recent
  FROM staging.ea_historic_floods, pt
 WHERE ST_Covers(geom, pt.g);

\echo ''
\echo '== Spot-check: central London SW1A 1AA — should be 0 or tiny =='
WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-0.1419, 51.5014), 4326), 27700) AS g)
SELECT COUNT(*) AS floods_covering_point FROM staging.ea_historic_floods, pt
 WHERE ST_Covers(geom, pt.g);
