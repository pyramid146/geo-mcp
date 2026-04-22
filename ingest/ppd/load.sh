#!/usr/bin/env bash
# Load HMLR Price Paid Data into staging.price_paid.
# ~30 M rows; COPY takes a few minutes, index builds take a few more.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly CSV_PATH="/data/ingest/ppd/pp-complete.csv"

set -a
source "${REPO_ROOT}/.env"
set +a

if [[ ! -f "$CSV_PATH" ]]; then
    echo "[load] ERROR: $CSV_PATH missing. Run download.sh first." >&2
    exit 1
fi

export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PGHOST=127.0.0.1
readonly PGPORT=5432

echo "[load] Recreating staging.price_paid and bulk-COPY from ${CSV_PATH}"
psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
DROP TABLE IF EXISTS staging.price_paid CASCADE;

-- Column order and types are per HMLR's published Price Paid Data
-- specification. The source CSV has no header — columns are positional.
CREATE TABLE staging.price_paid (
    transaction_id       text PRIMARY KEY,    -- {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}
    price                integer NOT NULL,
    -- HMLR serialises transfers as "YYYY-MM-DD 00:00" with a trailing
    -- zero time component, so store as timestamp and cast to date at
    -- query time.
    date_of_transfer     timestamp NOT NULL,
    postcode             text,                -- nullable (~5% blank)
    property_type        char(1),             -- D/S/T/F/O (Detached/Semi/Terraced/Flat/Other)
    old_new              char(1),             -- Y/N (new build)
    duration             char(1),             -- F/L/U (Freehold/Leasehold/Unknown)
    paon                 text,                -- primary addressable object name
    saon                 text,                -- secondary addressable object name
    street               text,
    locality             text,
    town_city            text,
    district             text,
    county               text,
    ppd_category_type    char(1),             -- A (standard) / B (additional)
    record_status        char(1)              -- A/C/D (added/changed/deleted)
);

\copy staging.price_paid FROM '${CSV_PATH}' WITH (FORMAT csv, HEADER false, QUOTE '"')

CREATE INDEX IF NOT EXISTS price_paid_postcode_date_idx ON staging.price_paid (postcode, date_of_transfer);
CREATE INDEX IF NOT EXISTS price_paid_date_idx          ON staging.price_paid (date_of_transfer);
CREATE INDEX IF NOT EXISTS price_paid_district_idx      ON staging.price_paid (district);

ANALYZE staging.price_paid;
SQL

echo "[load] Done."
