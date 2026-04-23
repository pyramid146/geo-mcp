#!/usr/bin/env bash
# Fetch the current GIAS (Get Information About Schools) all-data CSV
# from DfE. URL contains the file's generation date; we try today,
# yesterday, and progressively older dates until we hit a 200.
#
# GIAS's Azure-hosted API refuses requests without a User-Agent header,
# hence -A.
set -euo pipefail

readonly DEST_DIR="/data/ingest/gias_schools"
readonly CSV_PATH="${DEST_DIR}/edubasealldata.csv"

mkdir -p "$DEST_DIR"

tmp="${CSV_PATH}.part"
for i in 0 1 2 3 4 5 6 7 8 9 10; do
    d=$(date -d "${i} days ago" +%Y%m%d)
    url="https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata${d}.csv"
    status=$(curl -sSL --max-time 30 -A "Mozilla/5.0" -o "$tmp" -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [[ "$status" == "200" ]] && [[ $(stat -c '%s' "$tmp" 2>/dev/null || echo 0) -gt 1000000 ]]; then
        echo "[download] got ${d}: $(stat -c '%s' "$tmp") bytes"
        mv "$tmp" "$CSV_PATH"
        break
    fi
done

if [[ ! -f "$CSV_PATH" ]]; then
    echo "[download] ERROR: could not fetch GIAS CSV within last 10 days" >&2
    exit 1
fi

echo "[download] CSV at $CSV_PATH"
wc -l "$CSV_PATH"
