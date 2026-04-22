#!/usr/bin/env bash
# Load OS Open UPRN CSV into staging.os_open_uprn.
#
# Source columns (OS Open UPRN data dictionary):
#   UPRN          bigint  — the Unique Property Reference Number
#   X_COORDINATE  double  — OSGB36 easting, metres (EPSG:27700)
#   Y_COORDINATE  double  — OSGB36 northing, metres (EPSG:27700)
#   LATITUDE      double  — WGS84 (EPSG:4326)
#   LONGITUDE     double  — WGS84 (EPSG:4326)
#
# No addresses, no postcodes — OS Open UPRN is purely a coordinate anchor
# per UPRN. Address-level lookups require AddressBase, which is a
# commercially-licensed product and out of scope for this MVP.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly EXTRACT_DIR="/data/ingest/os_open_uprn/extracted"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"

csv_path=$(find "$EXTRACT_DIR" -maxdepth 1 -name 'osopenuprn_*.csv' -print -quit)
if [[ -z "$csv_path" ]]; then
    echo "[load] ERROR: no osopenuprn_*.csv under ${EXTRACT_DIR} — run download.sh first" >&2
    exit 1
fi
echo "[load] csv: $csv_path"

psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
DROP TABLE IF EXISTS staging.os_open_uprn CASCADE;

CREATE TABLE staging.os_open_uprn (
    uprn       bigint  PRIMARY KEY,
    easting    double precision NOT NULL,
    northing   double precision NOT NULL,
    lat        double precision NOT NULL,
    lon        double precision NOT NULL
);

-- OS emits CSV with an UPRN,X_COORDINATE,Y_COORDINATE,LATITUDE,LONGITUDE
-- header row. COPY with HEADER skips it.
\\copy staging.os_open_uprn (uprn, easting, northing, lat, lon) FROM '$csv_path' WITH (FORMAT csv, HEADER true);

-- Materialised OSGB27700 POINT — the main spatial index backing any
-- future "UPRN near X" or "all UPRNs in polygon Y" query. Cheap because
-- we already have the OSGB coords natively.
ALTER TABLE staging.os_open_uprn
    ADD COLUMN geom_osgb geometry(POINT, 27700)
    GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(easting, northing), 27700)) STORED;

CREATE INDEX os_open_uprn_geom_osgb_idx
    ON staging.os_open_uprn USING GIST (geom_osgb);

ANALYZE staging.os_open_uprn;
SQL

echo "[load] Done."
