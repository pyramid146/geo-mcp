-- Add a pre-materialised OSGB27700 geometry column to staging.onspd so
-- spatial joins against EA flood polygons (and any other 27700-native
-- dataset) don't pay a per-row ST_Transform. One-off migration; onspd is
-- append-only between ingests so a plain column stays in sync.
--
-- NOTE: apply as mcp_ingest (owner of staging.onspd), not mcp_admin.
--   PGPASSWORD=$MCP_INGEST_PASSWORD psql -U mcp_ingest -d geo -f 002_*.sql
-- migrate.sh still runs the schema-level changes under mcp_admin — for
-- table-level ALTERs you want the role that owns the table.

ALTER TABLE staging.onspd
    ADD COLUMN IF NOT EXISTS geom_osgb geometry(POINT, 27700);

UPDATE staging.onspd
   SET geom_osgb = ST_Transform(geom, 27700)
 WHERE geom IS NOT NULL AND geom_osgb IS NULL;

CREATE INDEX IF NOT EXISTS onspd_geom_osgb_idx
    ON staging.onspd USING GIST (geom_osgb);

ANALYZE staging.onspd;
