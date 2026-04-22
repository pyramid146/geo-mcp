#!/usr/bin/env bash
# Restore the most recent meta backup into a scratch database
# (geo_restore_drill), verify the tables came back with sensible row
# counts, then drop the scratch DB.
#
# Run periodically (say monthly) — if this fails, the real production
# restore would fail too, and you want to find out now rather than
# when you're actually trying to recover.
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly BACKUP_DIR="${GEO_MCP_BACKUP_DIR:-/data/backups}"

set -a
source "${REPO_ROOT}/.env"
set +a

mapfile -t files < <(ls -1t "${BACKUP_DIR}"/meta-*.sql.gz 2>/dev/null || true)
if [[ ${#files[@]} -eq 0 ]]; then
    echo "[restore-drill] ERROR: no backups under ${BACKUP_DIR}" >&2
    exit 1
fi
latest="${files[0]}"
echo "[restore-drill] latest backup: ${latest}"

export PGPASSWORD="$MCP_ADMIN_PASSWORD"
readonly SCRATCH_DB="geo_restore_drill"

psql_admin() {
    psql -h 127.0.0.1 -p 5432 -U mcp_admin -d "$POSTGRES_DB" -tA -v ON_ERROR_STOP=1 "$@"
}

psql_scratch() {
    psql -h 127.0.0.1 -p 5432 -U mcp_admin -d "$SCRATCH_DB" -tA -v ON_ERROR_STOP=1 "$@"
}

# Clean up a possibly-leftover scratch DB from a previous failed run.
echo "[restore-drill] recreating scratch DB: ${SCRATCH_DB}"
psql_admin -c "DROP DATABASE IF EXISTS ${SCRATCH_DB};" >/dev/null
psql_admin -c "CREATE DATABASE ${SCRATCH_DB};" >/dev/null

# meta schema needs to exist before a pg_dump with --clean --if-exists
# can drop-then-recreate its tables.
psql_scratch -c "CREATE SCHEMA IF NOT EXISTS meta;" >/dev/null

echo "[restore-drill] restoring ${latest} into ${SCRATCH_DB}"
gunzip -c "$latest" | psql -h 127.0.0.1 -p 5432 -U mcp_admin -d "$SCRATCH_DB" -v ON_ERROR_STOP=1 >/dev/null

echo "[restore-drill] verifying row counts (expect > 0 on all three core tables)"
fail=0
for table in customers api_keys usage_log; do
    n=$(psql_scratch -c "SELECT COUNT(*) FROM meta.${table};")
    echo "  meta.${table}: ${n}"
    if [[ "$n" == "0" ]] && [[ "$table" != "usage_log" ]]; then
        # usage_log might legitimately be empty on a very fresh system;
        # customers/api_keys being empty means the backup is suspicious.
        echo "  WARNING: meta.${table} restored empty — backup may be truncated"
        fail=1
    fi
done

echo "[restore-drill] dropping scratch DB"
psql_admin -c "DROP DATABASE ${SCRATCH_DB};" >/dev/null

if [[ $fail -ne 0 ]]; then
    echo "[restore-drill] FAIL — inspect the backup manually"
    exit 1
fi
echo "[restore-drill] OK"
