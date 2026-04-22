#!/usr/bin/env bash
# Load the most-recently-extracted ONSPD CSV into staging.onspd via
# ogr2ogr. Overwrites any existing staging.onspd. Runs as mcp_ingest,
# which owns tables it creates in the staging schema; default
# privileges auto-grant SELECT to mcp_readonly.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEST_DIR="/data/ingest/onspd"

set -a
source "${REPO_ROOT}/.env"
set +a

csv_path=$(ls -t "${DEST_DIR}"/extracted_*/Data/ONSPD_*_UK.csv 2>/dev/null | head -1)
if [[ -z "$csv_path" ]]; then
    csv_path=$(ls -t "${DEST_DIR}"/extracted_*/Data/ONSPD_*.csv 2>/dev/null | head -1)
fi
if [[ -z "$csv_path" ]]; then
    echo "[load] ERROR: no extracted ONSPD CSV under ${DEST_DIR}. Run download.sh first." >&2
    exit 1
fi
echo "[load] Source: ${csv_path}"

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PG_CONN="host=${PGHOST} port=${PGPORT} dbname=${POSTGRES_DB} user=mcp_ingest password=${MCP_INGEST_PASSWORD}"

psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
    "DROP TABLE IF EXISTS staging.onspd CASCADE;"

echo "[load] ogr2ogr CSV → staging.onspd (this can take a few minutes) ..."
ogr2ogr \
    -f PostgreSQL \
    "PG:${PG_CONN}" \
    "$csv_path" \
    -nln staging.onspd \
    -oo X_POSSIBLE_NAMES=long \
    -oo Y_POSSIBLE_NAMES=lat \
    -oo KEEP_GEOM_COLUMNS=YES \
    -oo HEADERS=YES \
    -oo AUTODETECT_TYPE=YES \
    -a_srs EPSG:4326 \
    -lco GEOMETRY_NAME=geom \
    -lco SCHEMA=staging \
    -lco LAUNDER=YES \
    -lco SPATIAL_INDEX=GIST \
    --config PG_USE_COPY YES \
    -progress

echo "[load] Post-load: null out invalid geometries, add B-tree indexes, ANALYZE"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
-- ONSPD encodes "no coordinates known" as long=0, lat=99.999999 (mostly
-- legacy / non-geographic postcodes). Null the geom so spatial queries
-- ignore them cleanly while the row-level metadata remains queryable.
UPDATE staging.onspd
   SET geom = NULL
 WHERE geom IS NOT NULL
   AND (ST_X(geom) = 0.0 OR ST_Y(geom) > 70 OR ST_Y(geom) < 40);

CREATE INDEX IF NOT EXISTS onspd_pcds_idx ON staging.onspd (pcds);
CREATE INDEX IF NOT EXISTS onspd_pcd7_idx ON staging.onspd (pcd7);

ANALYZE staging.onspd;
SQL

echo "[load] Done."
