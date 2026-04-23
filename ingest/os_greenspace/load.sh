#!/usr/bin/env bash
# Load greenspace_site polygons from OS Open Greenspace into
# staging.os_greenspace. Skips access_point — the polygon footprint
# is what drives "parks near me" queries.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly GPKG="/data/ingest/os_greenspace/extracted/opgrsp_gb.gpkg"

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

echo "[load] greenspace_site → staging.os_greenspace"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS staging.os_greenspace CASCADE;"

ogr2ogr \
    -f PostgreSQL \
    "PG:${PG_CONN}" \
    "$GPKG" \
    greenspace_site \
    -nln "staging.os_greenspace" \
    -nlt PROMOTE_TO_MULTI \
    -lco GEOMETRY_NAME=geom_osgb \
    -lco SCHEMA=staging \
    -lco LAUNDER=YES \
    -lco SPATIAL_INDEX=GIST \
    -lco PRECISION=NO \
    -a_srs EPSG:27700 \
    -t_srs EPSG:27700 \
    --config PG_USE_COPY YES

psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
ALTER TABLE staging.os_greenspace
    ADD COLUMN area_sqm double precision
    GENERATED ALWAYS AS (ST_Area(geom_osgb)) STORED;

CREATE INDEX IF NOT EXISTS os_greenspace_function_idx
    ON staging.os_greenspace (function);

ANALYZE staging.os_greenspace;
SQL

echo "[load] Done."
