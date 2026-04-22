\pset format aligned
\pset title 'OpenNames verification'

\echo ''
\echo '== Row count =='
SELECT COUNT(*) AS total FROM staging.opennames;

\echo ''
\echo '== Type distribution =='
SELECT type, COUNT(*) FROM staging.opennames GROUP BY type ORDER BY COUNT(*) DESC;

\echo ''
\echo '== Populated-place local_type distribution =='
SELECT local_type, COUNT(*) FROM staging.opennames
 WHERE type = 'populatedPlace'
 GROUP BY local_type ORDER BY COUNT(*) DESC;

\echo ''
\echo '== Spot-check: Manchester =='
SELECT name1, local_type, county_unitary, region, country, postcode_district,
       ST_AsText(ST_Transform(geom, 4326)) AS wgs84
  FROM staging.opennames
 WHERE lower(name1) = 'manchester' AND type = 'populatedPlace';

\echo ''
\echo '== Spot-check: Trafalgar Square =='
SELECT name1, local_type, county_unitary, ST_AsText(ST_Transform(geom, 4326)) AS wgs84
  FROM staging.opennames WHERE lower(name1) = 'trafalgar square' LIMIT 5;
