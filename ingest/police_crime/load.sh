#!/usr/bin/env bash
# Load police.uk street-level crime CSVs into staging.police_crimes.
#
# CSV columns (as of 2025 schema):
#   "Crime ID","Month","Reported by","Falls within","Longitude","Latitude",
#   "Location","LSOA code","LSOA name","Crime type","Last outcome category","Context"
#
# Table stores one row per recorded crime, with a generated geom +
# generated OSGB geom for spatial indexing. Month stored as DATE
# (first-of-month).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly EXTRACT_DIR="/data/ingest/police_crime/extracted"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"

psql() { command psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

echo "[load] (re)creating staging.police_crimes"
psql <<'SQL'
DROP TABLE IF EXISTS staging.police_crimes CASCADE;
CREATE TABLE staging.police_crimes (
    id            bigserial PRIMARY KEY,
    crime_id      text,
    month         date NOT NULL,
    reported_by   text,
    falls_within  text,
    lon           double precision,
    lat           double precision,
    location      text,
    lsoa_code     text,
    lsoa_name     text,
    crime_type    text NOT NULL,
    last_outcome  text,
    context       text
);

-- Unlogged staging table for faster raw loads; we'll repopulate the
-- final table in one pass after COPY.
CREATE UNLOGGED TABLE staging._police_crimes_raw (
    crime_id      text,
    month_str     text,
    reported_by   text,
    falls_within  text,
    lon           text,
    lat           text,
    location      text,
    lsoa_code     text,
    lsoa_name     text,
    crime_type    text,
    last_outcome  text,
    context       text
);
SQL

echo "[load] bulk-copying CSVs into raw staging"
for f in "$EXTRACT_DIR"/*/*-street.csv; do
    psql -c "\\copy staging._police_crimes_raw FROM '$f' WITH (FORMAT csv, HEADER true)"
done

echo "[load] projecting raw → typed table; filtering rows with no coords"
psql <<'SQL'
INSERT INTO staging.police_crimes (
    crime_id, month, reported_by, falls_within, lon, lat,
    location, lsoa_code, lsoa_name, crime_type, last_outcome, context
)
SELECT
    NULLIF(crime_id, ''),
    to_date(month_str, 'YYYY-MM'),
    NULLIF(reported_by, ''),
    NULLIF(falls_within, ''),
    NULLIF(lon, '')::double precision,
    NULLIF(lat, '')::double precision,
    NULLIF(location, ''),
    NULLIF(lsoa_code, ''),
    NULLIF(lsoa_name, ''),
    crime_type,
    NULLIF(last_outcome, ''),
    NULLIF(context, '')
  FROM staging._police_crimes_raw
 WHERE crime_type IS NOT NULL AND crime_type <> ''
   AND NULLIF(lon, '') IS NOT NULL
   AND NULLIF(lat, '') IS NOT NULL;

DROP TABLE staging._police_crimes_raw;

ALTER TABLE staging.police_crimes
    ADD COLUMN geom_osgb geometry(POINT, 27700)
    GENERATED ALWAYS AS (ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 27700)) STORED;

CREATE INDEX police_crimes_geom_osgb_idx ON staging.police_crimes USING GIST (geom_osgb);
CREATE INDEX police_crimes_month_idx     ON staging.police_crimes (month);
CREATE INDEX police_crimes_crime_type_idx ON staging.police_crimes (crime_type);

ANALYZE staging.police_crimes;
SQL

echo "[load] Done."
