#!/usr/bin/env bash
# Load the RoFRS postcodes CSV into staging.rofrs_postcodes.
#
# Two flavours of row live in the CSV:
#   * unit-level postcodes ("SW1A 1AA") — normal, joinable to ONSPD
#   * sector-level anonymised rows ("NE70 7P*") — EA's disclosure-control
#     aggregates for sparse sectors. We keep them (75k of them carry real
#     risk counts) but they won't join to ONSPD (which holds only
#     unit-level postcodes), so per-point and area tools naturally ignore
#     them. They're preserved for any future sector-fallback lookup.
#
# The source file has a UTF-8 BOM on the first byte; strip it on the way in.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly DEST_DIR="/data/ingest/rofrs"

set -a
source "${REPO_ROOT}/.env"
set +a

csv=$(find "${DEST_DIR}/extracted" -name '*AtRisk*.csv' -o -name '*Postcodes*.csv' | head -1)
if [[ -z "$csv" ]]; then
    echo "[load] ERROR: no CSV under ${DEST_DIR}/extracted. Run download.sh first." >&2
    exit 1
fi
echo "[load] Source: ${csv}"

bom_stripped="${DEST_DIR}/rofrs_postcodes.nobom.csv"
sed '1s/^\xef\xbb\xbf//' "$csv" > "$bom_stripped"

readonly PGHOST=127.0.0.1
readonly PGPORT=5432
export PGPASSWORD="$MCP_INGEST_PASSWORD"

echo "[load] Creating staging.rofrs_postcodes + bulk COPY"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
DROP TABLE IF EXISTS staging.rofrs_postcodes CASCADE;
CREATE TABLE staging.rofrs_postcodes (
    pcds             text PRIMARY KEY,  -- the CSV's PC column, single-space form
    cntpc            int,               -- total properties in postcode
    res_cntpc        int,               -- residential property count
    nrp_cntpc        int,               -- non-residential property count
    unc_cntpc        int,               -- unclassified property count
    res_cnt_verylow  int, nrp_cnt_verylow int, unc_cnt_verylow int, tot_cnt_verylow int,
    res_cnt_low      int, nrp_cnt_low     int, unc_cnt_low     int, tot_cnt_low     int,
    res_cnt_medium   int, nrp_cnt_medium  int, unc_cnt_medium  int, tot_cnt_medium  int,
    res_cnt_high     int, nrp_cnt_high    int, unc_cnt_high    int, tot_cnt_high    int,
    sortoff          text,
    district         text,
    sector           text,
    unit             text
);

\copy staging.rofrs_postcodes FROM '${bom_stripped}' WITH (FORMAT csv, HEADER)

CREATE INDEX IF NOT EXISTS rofrs_postcodes_district_idx ON staging.rofrs_postcodes (district);
CREATE INDEX IF NOT EXISTS rofrs_postcodes_sortoff_idx  ON staging.rofrs_postcodes (sortoff);

ANALYZE staging.rofrs_postcodes;
SQL

rm -f "$bom_stripped"
echo "[load] Done."
