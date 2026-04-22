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
    echo "[migrate] applying $(basename "$f")"
    psql -h 127.0.0.1 -p 5432 -U mcp_admin -d "$POSTGRES_DB" \
         -v ON_ERROR_STOP=1 -f "$f"
done

echo "[migrate] Done."
