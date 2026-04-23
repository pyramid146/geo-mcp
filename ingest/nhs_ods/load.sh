#!/usr/bin/env bash
# Load NHS ODS GP practices + branches into staging.nhs_gp_practices,
# geocoded via ONSPD postcode join.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
set -a; source "${REPO_ROOT}/.env"; set +a
export PGPASSWORD="$MCP_INGEST_PASSWORD"
psql() { command psql -h 127.0.0.1 -p 5432 -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

# epraccur CSV columns (no header), subset to the first 15 we need:
#   1 org_code, 2 name, 3 national_grouping, 4 hlhg, 5 addr1, 6 addr2,
#   7 addr3, 8 addr4, 9 addr5, 10 postcode, 11 open_date, 12 close_date,
#   13 status, 14 sub_type, 15 commissioner, ...
psql <<'SQL'
DROP TABLE IF EXISTS staging.nhs_gp_practices CASCADE;
CREATE UNLOGGED TABLE staging._nhs_raw (
    org_code     text,
    name         text,
    reg1         text,  -- national grouping
    reg2         text,  -- high level health geography
    addr1        text,
    addr2        text,
    addr3        text,
    addr4        text,
    addr5        text,
    postcode     text,
    open_date    text,
    close_date   text,
    status_code  text,
    sub_type     text,
    commissioner text,
    -- ignore remaining columns by NULL-padding with dummy names:
    col16 text, col17 text, col18 text, col19 text, col20 text,
    col21 text, col22 text, col23 text, col24 text, col25 text,
    col26 text, col27 text
);
SQL

psql -c "\\copy staging._nhs_raw FROM '/data/ingest/nhs_ods/epraccur.csv' WITH (FORMAT csv)"
# branches (ebranchs) has the same shape.
psql -c "\\copy staging._nhs_raw FROM '/data/ingest/nhs_ods/ebranchs.csv' WITH (FORMAT csv)"

psql <<'SQL'
CREATE TABLE staging.nhs_gp_practices AS
SELECT
    r.org_code,
    r.name,
    NULLIF(r.addr1, '') AS addr1,
    NULLIF(r.addr2, '') AS addr2,
    NULLIF(r.addr3, '') AS town,
    NULLIF(r.postcode, '') AS postcode,
    r.status_code,
    CASE
      WHEN r.open_date ~ '^\d{8}$' THEN to_date(r.open_date, 'YYYYMMDD') ELSE NULL
    END AS open_date,
    CASE
      WHEN r.close_date ~ '^\d{8}$' THEN to_date(r.close_date, 'YYYYMMDD') ELSE NULL
    END AS close_date,
    o.lat AS lat,
    o.long AS lon,
    o.geom AS geom_wgs84,
    ST_Transform(o.geom, 27700) AS geom_osgb
  FROM staging._nhs_raw r
  LEFT JOIN staging.onspd o ON o.pcds = r.postcode
 WHERE r.org_code IS NOT NULL;

DROP TABLE staging._nhs_raw;

CREATE INDEX nhs_gp_geom_osgb_idx ON staging.nhs_gp_practices USING GIST (geom_osgb);
CREATE INDEX nhs_gp_status_idx    ON staging.nhs_gp_practices (status_code);
CREATE INDEX nhs_gp_org_code_idx  ON staging.nhs_gp_practices (org_code);
ANALYZE staging.nhs_gp_practices;
SQL

echo "[load] Done."
