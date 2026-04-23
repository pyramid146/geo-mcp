#!/usr/bin/env bash
# Load only the `local_buildings` layer from OS Open Zoomstack into
# staging.os_zoomstack_buildings.
#
# ~15.1 M building polygons across GB, each with a stable OS uuid + a
# Polygon geometry in EPSG:27700. This layer is the property-level
# building-footprint dataset (as opposed to `district_buildings`, which
# is a coarse generalisation for lower zoom levels).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly GPKG="/data/ingest/os_zoomstack/extracted/OS_Open_Zoomstack.gpkg"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

if [[ ! -f "$GPKG" ]]; then
    echo "[load] ERROR: GPKG missing — run download.sh first" >&2
    exit 1
fi

echo "[load] local_buildings → staging.os_zoomstack_buildings"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS staging.os_zoomstack_buildings CASCADE;"

ogr2ogr \
    -f PostgreSQL \
    "PG:${PG_CONN}" \
    "$GPKG" \
    local_buildings \
    -nln "staging.os_zoomstack_buildings" \
    -nlt PROMOTE_TO_MULTI \
    -lco GEOMETRY_NAME=geom_osgb \
    -lco SCHEMA=staging \
    -lco LAUNDER=YES \
    -lco SPATIAL_INDEX=GIST \
    -lco PRECISION=NO \
    -a_srs EPSG:27700 \
    -t_srs EPSG:27700 \
    --config PG_USE_COPY YES

echo "[load] adding generated area_sqm column + analyzing"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
ALTER TABLE staging.os_zoomstack_buildings
    ADD COLUMN area_sqm double precision
    GENERATED ALWAYS AS (ST_Area(geom_osgb)) STORED;

CREATE INDEX IF NOT EXISTS os_zoomstack_buildings_uuid_idx
    ON staging.os_zoomstack_buildings (uuid);

ANALYZE staging.os_zoomstack_buildings;
SQL

echo "[load] Done."
