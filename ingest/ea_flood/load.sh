#!/usr/bin/env bash
# Load the EA Flood Map for Planning - Flood Zones GeoPackage into
# staging.ea_flood_zones. One table, two zone values ('FZ2', 'FZ3') —
# zone 1 is implicit ("everywhere else") and is not stored.
#
# 3.5 M polygon features — the load is the slow part (tens of minutes)
# and the GIST index takes several minutes more. PG_USE_COPY keeps it
# as fast as it reasonably can be.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEST_DIR="/data/ingest/ea_flood"

set -a
source "${REPO_ROOT}/.env"
set +a

gpkg_path=$(find "${DEST_DIR}/extracted" -name '*.gpkg' | head -1)
if [[ -z "$gpkg_path" ]]; then
    echo "[load] ERROR: no GeoPackage under ${DEST_DIR}. Run download.sh first." >&2
    exit 1
fi
echo "[load] Source: ${gpkg_path}"

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS staging.ea_flood_zones CASCADE;"

echo "[load] ogr2ogr gpkg → staging.ea_flood_zones (slow — 3.5 M polygons)..."
ogr2ogr \
    -f PostgreSQL \
    "PG:${PG_CONN}" \
    "$gpkg_path" \
    Flood_Zones_2_3_Rivers_and_Sea \
    -nln staging.ea_flood_zones \
    -nlt PROMOTE_TO_MULTI \
    -select origin,flood_zone,flood_source \
    -lco GEOMETRY_NAME=geom \
    -lco SCHEMA=staging \
    -lco LAUNDER=YES \
    -lco SPATIAL_INDEX=GIST \
    --config PG_USE_COPY YES

echo "[load] Post-load indexes + ANALYZE"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
CREATE INDEX IF NOT EXISTS ea_flood_zones_zone_idx ON staging.ea_flood_zones (flood_zone);
ANALYZE staging.ea_flood_zones;
SQL

echo "[load] Done."
