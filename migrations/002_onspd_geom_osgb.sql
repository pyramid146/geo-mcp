-- ROLE: mcp_ingest
-- Add a pre-materialised OSGB27700 geometry column to staging.onspd so
-- spatial joins against EA flood polygons (and any other 27700-native
-- dataset) don't pay a per-row ST_Transform. One-off migration; onspd is
-- append-only between ingests so a plain column stays in sync.
--
-- Runs as mcp_ingest (owner of staging.onspd) — migrate.sh reads the
-- ROLE: header above and dispatches to the right password in .env.

ALTER TABLE staging.onspd
    ADD COLUMN IF NOT EXISTS geom_osgb geometry(POINT, 27700);

UPDATE staging.onspd
   SET geom_osgb = ST_Transform(geom, 27700)
 WHERE geom IS NOT NULL AND geom_osgb IS NULL;

CREATE INDEX IF NOT EXISTS onspd_geom_osgb_idx
    ON staging.onspd USING GIST (geom_osgb);

ANALYZE staging.onspd;
