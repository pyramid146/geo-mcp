#!/usr/bin/env bash
# Load IMD 2019 into staging.imd_2019 (one row per LSOA 2011).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly CSV_PATH="/data/ingest/imd/imd2019.csv"

set -a; source "${REPO_ROOT}/.env"; set +a
export PGPASSWORD="$MCP_INGEST_PASSWORD"
psql() { command psql -h 127.0.0.1 -p 5432 -U mcp_ingest -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 "$@"; }

echo "[load] staging.imd_2019"
psql <<SQL
DROP TABLE IF EXISTS staging.imd_2019 CASCADE;
CREATE TABLE staging.imd_2019 (
    lsoa11_code  text PRIMARY KEY,
    lsoa11_name  text,
    lad19_code   text,
    lad19_name   text,
    imd_rank     integer NOT NULL,   -- 1 = most deprived of 32,844
    imd_decile   integer NOT NULL    -- 1 = most deprived 10%, 10 = least deprived 10%
);

\\copy staging.imd_2019 (lsoa11_code, lsoa11_name, lad19_code, lad19_name, imd_rank, imd_decile) FROM '$CSV_PATH' WITH (FORMAT csv, HEADER true);

CREATE INDEX imd_2019_decile_idx ON staging.imd_2019 (imd_decile);
ANALYZE staging.imd_2019;
SQL
echo "[load] Done."
