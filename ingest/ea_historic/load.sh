#!/usr/bin/env bash
# Load Recorded Flood Outlines into staging.ea_historic_floods.
# 31k polygon features in EPSG:27700 — SW England + London + the usual
# flood hot spots get hit most often.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEST_DIR="/data/ingest/ea_historic"

set -a
source "${REPO_ROOT}/.env"
set +a

gpkg=$(find "${DEST_DIR}/extracted" -name '*.gpkg' | head -1)
if [[ -z "$gpkg" ]]; then
    echo "[load] ERROR: no gpkg found. Run download.sh first." >&2
    exit 1
fi
echo "[load] Source: ${gpkg}"

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS staging.ea_historic_floods CASCADE;"

echo "[load] ogr2ogr gpkg → staging.ea_historic_floods"
ogr2ogr \
    -f PostgreSQL \
    "PG:${PG_CONN}" \
    "$gpkg" \
    Recorded_Flood_Outlines \
    -nln staging.ea_historic_floods \
    -nlt PROMOTE_TO_MULTI \
    -select name,start_date,end_date,flood_src,flood_caus,fluvial_f,coastal_f,tidal_f \
    -lco GEOMETRY_NAME=geom \
    -lco SCHEMA=staging \
    -lco LAUNDER=YES \
    -lco SPATIAL_INDEX=GIST \
    --config PG_USE_COPY YES

echo "[load] Post-load indexes + ANALYZE"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
CREATE INDEX IF NOT EXISTS ea_historic_floods_start_idx ON staging.ea_historic_floods (start_date);
CREATE INDEX IF NOT EXISTS ea_historic_floods_src_idx   ON staging.ea_historic_floods (flood_src);
ANALYZE staging.ea_historic_floods;
SQL

echo "[load] Done."
