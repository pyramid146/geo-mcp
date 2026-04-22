\pset format aligned
\pset title 'EA Flood Zones verification'

\echo ''
\echo '== Row count per zone =='
SELECT flood_zone, COUNT(*) AS polygons
  FROM staging.ea_flood_zones
 GROUP BY flood_zone
 ORDER BY flood_zone;

\echo ''
\echo '== SRID (expect 27700) =='
SELECT DISTINCT ST_SRID(geom) FROM staging.ea_flood_zones LIMIT 1;

\echo ''
\echo '== Indexes =='
SELECT indexname, indexdef
  FROM pg_indexes
 WHERE schemaname = 'staging' AND tablename = 'ea_flood_zones'
 ORDER BY indexname;

\echo ''
\echo '== Spot checks =='

\echo ''
\echo 'Somerset Levels — Weston Zoyland TA7 0LZ (known flood-prone area)'
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-2.9167, 51.0783), 4326), 27700) AS g
)
SELECT z.flood_zone, COUNT(*) AS polygons_matched
  FROM staging.ea_flood_zones z, pt
 WHERE ST_Covers(z.geom, pt.g)
 GROUP BY z.flood_zone;

\echo ''
\echo 'Snowdon summit — should be in no flood zone'
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-4.0765, 53.0685), 4326), 27700) AS g
)
SELECT COUNT(*) AS matches FROM staging.ea_flood_zones z, pt
 WHERE ST_Covers(z.geom, pt.g);

\echo ''
\echo 'Central London (SW1A 1AA) — likely in no flood zone'
WITH pt AS (
    SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-0.1419, 51.5014), 4326), 27700) AS g
)
SELECT z.flood_zone, COUNT(*) FROM staging.ea_flood_zones z, pt
 WHERE ST_Covers(z.geom, pt.g)
 GROUP BY z.flood_zone;
