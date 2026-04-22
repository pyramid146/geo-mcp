#!/usr/bin/env bash
# Load extracted EPC certificates CSVs into staging.epc_* tables.
#
# Strategy: create a TEXT-typed staging table per EPC product with
# columns derived from the first file's header — no column-list drift
# across source refreshes. The tool layer casts to date / numeric
# as needed.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly BASE="/data/ingest/epc"

set -a
source "${REPO_ROOT}/.env"
set +a

export PGPASSWORD="$MCP_INGEST_PASSWORD"
readonly PGHOST=127.0.0.1
readonly PGPORT=5432

load_kind() {
    local kind="$1" table="$2"
    local extract_dir="${BASE}/${kind}"

    # The new gov.uk EPC service ships per-year files (certificates-YYYY.csv)
    # at the top of each zip; the old opendatacommunities service shipped
    # per-LA folders (<la>/certificates.csv). Match both.
    mapfile -t certs < <(find "$extract_dir" \( -name 'certificates-*.csv' -o -name 'certificates.csv' \) | sort)
    if [[ ${#certs[@]} -eq 0 ]]; then
        echo "[load] ${kind}: no certificates CSV found, skipping."
        return
    fi
    echo "[load] ${kind}: ${#certs[@]} source files"

    # Build CREATE TABLE from the first file's header row.
    local cols
    cols=$(head -1 "${certs[0]}" | python3 -c "
import csv, sys
header = next(csv.reader(sys.stdin))
print(',\n    '.join(f'\"{c.lower()}\" text' for c in header))
")

    psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
DROP TABLE IF EXISTS staging.${table} CASCADE;
CREATE TABLE staging.${table} (
    ${cols}
);
SQL

    # Stream the concatenated rows through a FIFO — header kept from the
    # first file only, so \copy WITH HEADER skips exactly one line.
    local fifo
    fifo=$(mktemp -u)
    mkfifo "$fifo"
    (
        first=1
        for f in "${certs[@]}"; do
            if [[ $first -eq 1 ]]; then
                cat "$f"
                first=0
            else
                tail -n +2 "$f"
            fi
        done
    ) > "$fifo" &
    local reader=$!

    psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
        "\\copy staging.${table} FROM '${fifo}' WITH (FORMAT csv, HEADER true)"
    wait $reader
    rm -f "$fifo"

    # Indexes for the hot-path queries. Kept columns as TEXT to tolerate
    # source quirks; tool layer casts `lodgement_date::date` etc. at
    # query time. An index on lodgement_date (text) is enough since EPC
    # dates are lexicographically orderable in ISO form. Some columns
    # only exist on certain product variants (construction_age_band is
    # domestic-only); skip when absent.
    psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<SQL
CREATE INDEX IF NOT EXISTS ${table}_postcode_idx   ON staging.${table} (postcode);
CREATE INDEX IF NOT EXISTS ${table}_uprn_idx       ON staging.${table} (uprn) WHERE uprn IS NOT NULL AND uprn <> '';
CREATE INDEX IF NOT EXISTS ${table}_lodgement_idx  ON staging.${table} (lodgement_date);

DO \$\$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='staging' AND table_name='${table}'
           AND column_name='construction_age_band'
    ) THEN
        CREATE INDEX IF NOT EXISTS ${table}_age_band_idx ON staging.${table} (construction_age_band);
    END IF;
END \$\$;

ANALYZE staging.${table};
SQL

    local n
    n=$(psql -h "$PGHOST" -p "$PGPORT" -U mcp_ingest -d "$POSTGRES_DB" -tA -c "SELECT COUNT(*) FROM staging.${table}")
    echo "[load] ${kind}: ${n} rows loaded"
}

for k in "$@"; do
    case "$k" in
        domestic)     load_kind domestic     epc_domestic ;;
        non-domestic) load_kind non-domestic epc_non_domestic ;;
        display)      load_kind display      epc_display ;;
        *) echo "[load] unknown kind: $k" >&2; exit 1 ;;
    esac
done
if [[ $# -eq 0 ]]; then
    load_kind domestic     epc_domestic
    load_kind non-domestic epc_non_domestic
    load_kind display      epc_display
fi

echo "[load] Done."
