#!/usr/bin/env bash
# Load the downloaded NHLE GeoPackages into staging tables.
# One staging table per designation type; ListDate is converted from
# unix-epoch-ms to a proper DATE for query ergonomics.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEST_DIR="/data/ingest/nhle"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

load_gpkg() {
    local gpkg="$1" layer="$2" table="$3"
    local extra="${4:-}"
    if [[ ! -f "$gpkg" ]]; then
        echo "[load] missing ${gpkg}, skipping." >&2
        return
    fi
    echo "[load] $gpkg → staging.${table}"
    psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
        "DROP TABLE IF EXISTS staging.${table} CASCADE;"
    ogr2ogr \
        -f PostgreSQL \
        "PG:${PG_CONN}" \
        "$gpkg" \
        "$layer" \
        -nln "staging.${table}" \
        -nlt PROMOTE_TO_MULTI \
        -lco GEOMETRY_NAME=geom \
        -lco SCHEMA=staging \
        -lco LAUNDER=YES \
        -lco SPATIAL_INDEX=GIST \
        -lco PRECISION=NO \
        -t_srs EPSG:27700 \
        --config PG_USE_COPY YES \
        ${extra}
}

load_gpkg "${DEST_DIR}/listed_buildings_points.gpkg"   listed_buildings_points   nhle_listed_points
load_gpkg "${DEST_DIR}/listed_buildings_polygons.gpkg" listed_buildings_polygons nhle_listed_polygons
load_gpkg "${DEST_DIR}/scheduled_monuments.gpkg"       scheduled_monuments       nhle_scheduled_monuments
load_gpkg "${DEST_DIR}/parks_and_gardens.gpkg"         parks_and_gardens         nhle_parks_and_gardens
load_gpkg "${DEST_DIR}/battlefields.gpkg"              battlefields              nhle_battlefields
load_gpkg "${DEST_DIR}/protected_wreck_sites.gpkg"     protected_wreck_sites     nhle_protected_wrecks
load_gpkg "${DEST_DIR}/world_heritage_sites.gpkg"      world_heritage_sites      nhle_world_heritage_sites

echo "[load] Post-load: normalise designation_date, add indexes, ANALYZE"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
-- Each NHLE layer uses a different column name for its designation-date
-- (listdate / regdate / scheddate / desigdate / inscrdate). Add a uniform
-- `designation_date` column and populate it from the source, converting
-- epoch-ms to date.
DO $$
DECLARE
    mapping record;
BEGIN
    FOR mapping IN
        SELECT * FROM (VALUES
            ('nhle_listed_points',        'listdate'),
            ('nhle_listed_polygons',      'listdate'),
            ('nhle_scheduled_monuments',  'scheddate'),
            ('nhle_parks_and_gardens',    'regdate'),
            ('nhle_battlefields',         'regdate'),
            ('nhle_protected_wrecks',     'desigdate'),
            ('nhle_world_heritage_sites', 'inscrdate')
        ) AS t(table_name, source_col)
    LOOP
        EXECUTE format('ALTER TABLE staging.%I ADD COLUMN IF NOT EXISTS designation_date date', mapping.table_name);
        EXECUTE format($fmt$
            UPDATE staging.%I
               SET designation_date = CASE
                   WHEN %I IS NULL THEN NULL
                   ELSE (to_timestamp(%I::bigint / 1000.0) AT TIME ZONE 'UTC')::date
               END
            WHERE designation_date IS NULL
        $fmt$, mapping.table_name, mapping.source_col, mapping.source_col);
    END LOOP;
END $$;

-- B-tree indexes that the tool layer will actually use
CREATE INDEX IF NOT EXISTS nhle_listed_points_entry_idx   ON staging.nhle_listed_points   (listentry);
CREATE INDEX IF NOT EXISTS nhle_listed_points_grade_idx   ON staging.nhle_listed_points   (grade);
CREATE INDEX IF NOT EXISTS nhle_listed_polygons_entry_idx ON staging.nhle_listed_polygons (listentry);
CREATE INDEX IF NOT EXISTS nhle_listed_polygons_grade_idx ON staging.nhle_listed_polygons (grade);

ANALYZE staging.nhle_listed_points;
ANALYZE staging.nhle_listed_polygons;
ANALYZE staging.nhle_scheduled_monuments;
ANALYZE staging.nhle_parks_and_gardens;
ANALYZE staging.nhle_battlefields;
ANALYZE staging.nhle_protected_wrecks;
ANALYZE staging.nhle_world_heritage_sites;
SQL

echo "[load] Done."
