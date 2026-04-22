-- Sanity checks for staging.onspd after load. Run as any role with SELECT
-- on staging.onspd (mcp_ingest, mcp_admin, mcp_readonly all work).
\pset format aligned
\pset title 'ONSPD staging.onspd verification'

\echo ''
\echo '== Row count =='
SELECT COUNT(*) AS total_rows FROM staging.onspd;

\echo ''
\echo '== Row count check (expect PASS: > 2.5M UK postcodes) =='
SELECT CASE WHEN COUNT(*) > 2500000 THEN 'PASS' ELSE 'FAIL' END AS row_count_check,
       COUNT(*) AS actual
  FROM staging.onspd;

\echo ''
\echo '== Geometry SRID (expect 4326) =='
SELECT DISTINCT ST_SRID(geom) AS srid
  FROM staging.onspd
 WHERE geom IS NOT NULL
 LIMIT 5;

\echo ''
\echo '== UK bounding box (expect roughly long -8.7..1.8, lat 49.7..60.9) =='
SELECT ROUND(MIN(ST_X(geom))::numeric, 3) AS min_long,
       ROUND(MIN(ST_Y(geom))::numeric, 3) AS min_lat,
       ROUND(MAX(ST_X(geom))::numeric, 3) AS max_long,
       ROUND(MAX(ST_Y(geom))::numeric, 3) AS max_lat
  FROM staging.onspd
 WHERE geom IS NOT NULL;

\echo ''
\echo '== Geometry population =='
SELECT COUNT(*) FILTER (WHERE geom IS NOT NULL) AS with_geom,
       COUNT(*) FILTER (WHERE geom IS NULL)     AS without_geom
  FROM staging.onspd;

\echo ''
\echo '== Live vs terminated postcodes =='
SELECT COUNT(*) FILTER (WHERE doterm IS NULL) AS live,
       COUNT(*) FILTER (WHERE doterm IS NOT NULL) AS terminated
  FROM staging.onspd;

\echo ''
\echo '== Indexes on staging.onspd =='
SELECT indexname, indexdef
  FROM pg_indexes
 WHERE schemaname = 'staging' AND tablename = 'onspd'
 ORDER BY indexname;

\echo ''
\echo '== Spot-check: SW1A 1AA (Buckingham Palace area) =='
SELECT pcds, ctry25cd, rgn25cd, ST_AsText(geom) AS geom_wkt
  FROM staging.onspd
 WHERE pcds = 'SW1A 1AA';
