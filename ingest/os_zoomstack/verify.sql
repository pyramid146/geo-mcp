-- Verify staging.os_zoomstack_buildings is sane.

SELECT 'row_count' AS metric, COUNT(*)::text AS value FROM staging.os_zoomstack_buildings
UNION ALL
SELECT 'bbox_e',
       round(ST_XMin(ST_Extent(geom_osgb))::numeric, 0)::text || ' to '
    || round(ST_XMax(ST_Extent(geom_osgb))::numeric, 0)::text
  FROM staging.os_zoomstack_buildings
UNION ALL
SELECT 'area_stats',
       'min=' || round(MIN(area_sqm)::numeric, 1)::text
    || ' med=' || round(percentile_cont(0.5) WITHIN GROUP (ORDER BY area_sqm)::numeric, 1)::text
    || ' max=' || round(MAX(area_sqm)::numeric, 0)::text
  FROM staging.os_zoomstack_buildings;

-- Spot check: buildings within 100m of 10 Downing Street.
SELECT COUNT(*) AS buildings_near_downing_st
  FROM staging.os_zoomstack_buildings b
 WHERE ST_DWithin(
     b.geom_osgb,
     ST_Transform(ST_SetSRID(ST_MakePoint(-0.1276, 51.5034), 4326), 27700),
     100
 );
