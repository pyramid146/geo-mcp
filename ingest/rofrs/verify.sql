\pset format aligned
\pset title 'RoFRS verification'

\echo ''
\echo '== Row count =='
SELECT COUNT(*) AS total_postcodes FROM staging.rofrs_postcodes;

\echo ''
\echo '== Postcodes with ≥1 residential property in each category =='
SELECT
    COUNT(*) FILTER (WHERE res_cnt_high    > 0) AS postcodes_high,
    COUNT(*) FILTER (WHERE res_cnt_medium  > 0) AS postcodes_medium,
    COUNT(*) FILTER (WHERE res_cnt_low     > 0) AS postcodes_low,
    COUNT(*) FILTER (WHERE res_cnt_verylow > 0) AS postcodes_verylow
  FROM staging.rofrs_postcodes;

\echo ''
\echo '== Total residential properties by risk band =='
SELECT
    SUM(res_cnt_verylow) AS very_low,
    SUM(res_cnt_low)     AS low,
    SUM(res_cnt_medium)  AS medium,
    SUM(res_cnt_high)    AS high
  FROM staging.rofrs_postcodes;

\echo ''
\echo '== Spot-check: Tewkesbury area (GL20) =='
SELECT pcds, res_cntpc, res_cnt_high, res_cnt_medium, res_cnt_low, res_cnt_verylow
  FROM staging.rofrs_postcodes
 WHERE pcds LIKE 'GL20 %' AND res_cnt_high > 0
 ORDER BY res_cnt_high DESC
 LIMIT 5;

\echo ''
\echo '== Coverage vs ONSPD live postcodes =='
SELECT
    (SELECT COUNT(*) FROM staging.onspd WHERE doterm IS NULL) AS onspd_live,
    (SELECT COUNT(*) FROM staging.rofrs_postcodes)            AS rofrs_rows,
    (SELECT COUNT(*) FROM staging.rofrs_postcodes r
       JOIN staging.onspd o ON o.pcds = r.pcds
      WHERE o.doterm IS NULL)                                 AS joinable_live;
