#!/usr/bin/env bash
# Load watercourse_link from OS Open Rivers into staging.os_rivers.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly GPKG="/data/ingest/os_rivers/extracted/oprvrs_gb.gpkg"

set -a; source "${REPO_ROOT}/.env"; set +a
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=127.0.0.1 port=5432 dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

psql -h 127.0.0.1 -p 5432 -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS staging.os_rivers CASCADE;"

ogr2ogr \
    -f PostgreSQL "PG:${PG_CONN}" \
    "$GPKG" watercourse_link \
    -nln staging.os_rivers \
    -nlt PROMOTE_TO_MULTI \
    -lco GEOMETRY_NAME=geom_osgb \
    -lco SCHEMA=staging \
    -lco LAUNDER=YES \
    -lco SPATIAL_INDEX=GIST \
    -lco PRECISION=NO \
    -a_srs EPSG:27700 -t_srs EPSG:27700 \
    --config PG_USE_COPY YES

psql -h 127.0.0.1 -p 5432 -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
CREATE INDEX IF NOT EXISTS os_rivers_name_idx
    ON staging.os_rivers (watercourse_name);
ANALYZE staging.os_rivers;
SQL
echo "[load] Done."
