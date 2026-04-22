#!/usr/bin/env bash
# Concatenate the per-100km-grid CSVs into one, then bulk-COPY into
# staging.opennames. CSVs carry no header row — the schema is
# positional per the OS OpenNames technical specification.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEST_DIR="/data/ingest/opennames"
readonly CSV_DIR="${DEST_DIR}/extracted/Data"
readonly MERGED_CSV="${DEST_DIR}/opennames_merged.csv"

set -a
source "${REPO_ROOT}/.env"
set +a

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"

csv_count=$(find "$CSV_DIR" -name '*.csv' | wc -l)
if [[ "$csv_count" -lt 100 ]]; then
    echo "[load] ERROR: expected >100 CSVs under ${CSV_DIR}, found ${csv_count}. Run download.sh first." >&2
    exit 1
fi

echo "[load] Merging ${csv_count} per-tile CSVs → ${MERGED_CSV}"
# Strip UTF-8 BOM from each file as it's concatenated — the first CSV's
# first byte is EF BB BF, which otherwise winds up in the middle of the
# merged stream.
if [[ ! -s "$MERGED_CSV" ]]; then
    find "$CSV_DIR" -name '*.csv' -print0 \
        | xargs -0 sed 's/^\xef\xbb\xbf//' \
        > "$MERGED_CSV"
fi
echo "[load] Merged size: $(stat -c %s "$MERGED_CSV") bytes"

echo "[load] Creating staging.opennames + bulk COPY"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
DROP TABLE IF EXISTS staging.opennames CASCADE;
CREATE TABLE staging.opennames (
    id                    TEXT PRIMARY KEY,
    names_uri             TEXT,
    name1                 TEXT,
    name1_lang            TEXT,
    name2                 TEXT,
    name2_lang            TEXT,
    type                  TEXT,
    local_type            TEXT,
    geometry_x            INTEGER,
    geometry_y            INTEGER,
    most_detail_view_res  INTEGER,
    least_detail_view_res INTEGER,
    mbr_xmin              INTEGER,
    mbr_ymin              INTEGER,
    mbr_xmax              INTEGER,
    mbr_ymax              INTEGER,
    postcode_district     TEXT,
    postcode_district_uri TEXT,
    populated_place       TEXT,
    populated_place_uri   TEXT,
    populated_place_type  TEXT,
    district_borough      TEXT,
    district_borough_uri  TEXT,
    district_borough_type TEXT,
    county_unitary        TEXT,
    county_unitary_uri    TEXT,
    county_unitary_type   TEXT,
    region                TEXT,
    region_uri            TEXT,
    country               TEXT,
    country_uri           TEXT,
    related_spatial_object TEXT,
    same_as_dbpedia        TEXT,
    same_as_geonames       TEXT
);

\copy staging.opennames FROM '${MERGED_CSV}' WITH (FORMAT csv)

ALTER TABLE staging.opennames
    ADD COLUMN geom GEOMETRY(POINT, 27700)
    GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(geometry_x, geometry_y), 27700)) STORED;

CREATE INDEX opennames_geom_idx         ON staging.opennames USING GIST (geom);
CREATE INDEX opennames_name1_lower_idx  ON staging.opennames (lower(name1));
CREATE INDEX opennames_name2_lower_idx  ON staging.opennames (lower(name2));
CREATE INDEX opennames_type_idx         ON staging.opennames (type);
CREATE INDEX opennames_local_type_idx   ON staging.opennames (local_type);
CREATE INDEX opennames_postcode_idx     ON staging.opennames (postcode_district);

ANALYZE staging.opennames;
SQL

echo "[load] Done."
