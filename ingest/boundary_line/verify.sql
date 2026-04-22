\pset format aligned
\pset title 'Boundary-Line verification'

\echo ''
\echo '== Row counts per shapefile =='
SELECT 'bl_country'        AS tbl, COUNT(*) FROM staging.bl_country
UNION ALL
SELECT 'bl_english_region' AS tbl, COUNT(*) FROM staging.bl_english_region
UNION ALL
SELECT 'bl_lad'            AS tbl, COUNT(*) FROM staging.bl_lad
UNION ALL
SELECT 'bl_ward'           AS tbl, COUNT(*) FROM staging.bl_ward
UNION ALL
SELECT 'admin_names'       AS tbl, COUNT(*) FROM staging.admin_names
ORDER BY tbl;

\echo ''
\echo '== SRID (expect 27700 everywhere) =='
SELECT 'bl_country'        AS tbl, ST_SRID(geom) FROM staging.bl_country        LIMIT 1;
SELECT 'bl_english_region' AS tbl, ST_SRID(geom) FROM staging.bl_english_region LIMIT 1;
SELECT 'bl_lad'            AS tbl, ST_SRID(geom) FROM staging.bl_lad            LIMIT 1;
SELECT 'bl_ward'           AS tbl, ST_SRID(geom) FROM staging.bl_ward           LIMIT 1;

\echo ''
\echo '== admin_names by level =='
SELECT level, COUNT(*) FROM staging.admin_names GROUP BY level ORDER BY level;

\echo ''
\echo '== Coverage check: ONSPD codes that have / lack a name in admin_names =='
SELECT 'country' AS level,
       COUNT(DISTINCT o.ctry25cd) FILTER (WHERE a.code IS NOT NULL) AS with_name,
       COUNT(DISTINCT o.ctry25cd) FILTER (WHERE a.code IS NULL)     AS without_name
  FROM staging.onspd o
  LEFT JOIN staging.admin_names a ON a.code = o.ctry25cd AND a.level = 'country'
 WHERE o.ctry25cd IS NOT NULL
UNION ALL
SELECT 'region',
       COUNT(DISTINCT o.rgn25cd) FILTER (WHERE a.code IS NOT NULL),
       COUNT(DISTINCT o.rgn25cd) FILTER (WHERE a.code IS NULL)
  FROM staging.onspd o
  LEFT JOIN staging.admin_names a ON a.code = o.rgn25cd AND a.level = 'region'
 WHERE o.rgn25cd IS NOT NULL
UNION ALL
SELECT 'lad',
       COUNT(DISTINCT o.lad25cd) FILTER (WHERE a.code IS NOT NULL),
       COUNT(DISTINCT o.lad25cd) FILTER (WHERE a.code IS NULL)
  FROM staging.onspd o
  LEFT JOIN staging.admin_names a ON a.code = o.lad25cd AND a.level = 'lad'
 WHERE o.lad25cd IS NOT NULL
UNION ALL
SELECT 'ward',
       COUNT(DISTINCT o.wd25cd) FILTER (WHERE a.code IS NOT NULL),
       COUNT(DISTINCT o.wd25cd) FILTER (WHERE a.code IS NULL)
  FROM staging.onspd o
  LEFT JOIN staging.admin_names a ON a.code = o.wd25cd AND a.level = 'ward'
 WHERE o.wd25cd IS NOT NULL;

\echo ''
\echo '== Spot-check: SW1A 1AA admin chain =='
SELECT
    o.pcds,
    (SELECT name FROM staging.admin_names WHERE code = o.ctry25cd AND level='country') AS country,
    (SELECT name FROM staging.admin_names WHERE code = o.rgn25cd  AND level='region')  AS region,
    (SELECT name FROM staging.admin_names WHERE code = o.lad25cd  AND level='lad')     AS local_authority,
    (SELECT name FROM staging.admin_names WHERE code = o.wd25cd   AND level='ward')    AS ward
  FROM staging.onspd o
 WHERE o.pcds = 'SW1A 1AA';
