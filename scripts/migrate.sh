#!/usr/bin/env bash
# Apply every SQL file in migrations/ in filename order, as mcp_admin.
# Migrations must be idempotent (CREATE TABLE IF NOT EXISTS, etc).
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

set -a
source "${REPO_ROOT}/.env"
set +a

export PGPASSWORD="$MCP_ADMIN_PASSWORD"
shopt -s nullglob

for f in "${REPO_ROOT}"/migrations/*.sql; do
    # Optional role override via a "-- ROLE: mcp_ingest" header line.
    # Table-owning migrations (e.g. 002_onspd_geom_osgb.sql) must run as
    # the table owner, not mcp_admin.
    role=$(awk 'NR<=5 && $1=="--" && $2=="ROLE:" { print $3; exit }' "$f")
    role=${role:-mcp_admin}
    case "$role" in
        mcp_admin)   pw="$MCP_ADMIN_PASSWORD"   ;;
        mcp_ingest)  pw="$MCP_INGEST_PASSWORD"  ;;
        *)           echo "[migrate] unknown ROLE $role in $(basename "$f")" >&2; exit 1 ;;
    esac
    echo "[migrate] applying $(basename "$f") as $role"
    PGPASSWORD="$pw" psql -h 127.0.0.1 -p 5432 -U "$role" -d "$POSTGRES_DB" \
         -v ON_ERROR_STOP=1 -f "$f"
done

echo "[migrate] Done."
