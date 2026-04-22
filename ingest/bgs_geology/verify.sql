\pset format aligned
\pset title 'BGS Geology 625k verification'

\echo ''
\echo '== Row counts =='
SELECT 'bgs_bedrock'     AS tbl, COUNT(*) FROM staging.bgs_bedrock
UNION ALL SELECT 'bgs_superficial', COUNT(*) FROM staging.bgs_superficial
UNION ALL SELECT 'bgs_dykes',       COUNT(*) FROM staging.bgs_dykes
UNION ALL SELECT 'bgs_faults',      COUNT(*) FROM staging.bgs_faults
ORDER BY tbl;

\echo ''
\echo '== SRID (expect 27700) =='
SELECT DISTINCT ST_SRID(geom) FROM staging.bgs_bedrock LIMIT 1;

\echo ''
\echo '== Spot-check: SW1A 1AA (central London) — expect London Clay =='
WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-0.1419, 51.5014), 4326), 27700) AS g)
SELECT b.lex_d AS formation, b.rcs_d AS rock_type, b.max_time_d AS age
  FROM staging.bgs_bedrock b, pt
 WHERE ST_Covers(b.geom, pt.g)
 LIMIT 3;

\echo ''
\echo '== Spot-check: GL20 5BY (Tewkesbury) bedrock + superficial =='
WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-2.1723, 51.9890), 4326), 27700) AS g)
SELECT 'bedrock'     AS layer, b.lex_d AS name, b.rcs_d AS rock_type FROM staging.bgs_bedrock b, pt
 WHERE ST_Covers(b.geom, pt.g)
UNION ALL
SELECT 'superficial', s.lex_d,             s.rcs_d            FROM staging.bgs_superficial s, pt
 WHERE ST_Covers(s.geom, pt.g);

\echo ''
\echo '== Spot-check: Snowdon summit (Welsh volcanics expected) =='
WITH pt AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-4.0765, 53.0685), 4326), 27700) AS g)
SELECT b.lex_d, b.rcs_d, b.max_time_d
  FROM staging.bgs_bedrock b, pt
 WHERE ST_Covers(b.geom, pt.g)
 LIMIT 3;
