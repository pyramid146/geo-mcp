#!/usr/bin/env bash
# Fetch the most-recent street-level crime archive from police.uk.
# The archive is the full 36-month rolling dataset; we selectively
# extract only the last $GEO_MCP_CRIME_MONTHS months of *-street.csv
# files (default 24) to keep on-disk footprint manageable.
#
# Licence: Open Government Licence v3.0 (data.police.uk).
# Refresh cadence: monthly (typically ~6-8 weeks after the reporting period).
set -euo pipefail

readonly MONTHS="${GEO_MCP_CRIME_MONTHS:-24}"
readonly DEST_DIR="/data/ingest/police_crime"
readonly ZIP_PATH="${DEST_DIR}/archive.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

# 1. Resolve the latest archive date via the dates API.
latest_date=$(curl -sSL --max-time 30 'https://data.police.uk/api/crimes-street-dates' \
    | python3 -c "import json, sys; print(json.load(sys.stdin)[0]['date'])")
archive_url="https://policeuk-data.s3.amazonaws.com/archive/${latest_date}.zip"
echo "[download] latest archive: ${latest_date} → ${archive_url}"

# 2. Fetch (size-aware; no explicit md5 — police.uk publishes one, but via
#    a response header not a manifest). Compare Content-Length first.
expected_size=$(curl -sSLI --max-time 30 "$archive_url" | awk '/^[Cc]ontent-[Ll]ength:/ {print $2}' | tr -d '\r')
echo "[download] remote size: ${expected_size} bytes"

needs_download=true
if [[ -f "$ZIP_PATH" ]]; then
    local_size=$(stat -c '%s' "$ZIP_PATH")
    if [[ "$local_size" == "$expected_size" ]]; then
        echo "[download] local archive matches size. Skipping fetch."
        needs_download=false
    fi
fi

if $needs_download; then
    echo "[download] fetching ${archive_url}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$archive_url"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

# 3. Compute which YYYY-MM folders to extract. python3 for date arithmetic.
months_to_extract=$(python3 - <<PY
from datetime import date
latest = "${latest_date}"
y, m = map(int, latest.split("-"))
months = []
for i in range(${MONTHS}):
    months.append(f"{y:04d}-{m:02d}")
    m -= 1
    if m == 0:
        m = 12
        y -= 1
print(" ".join(months))
PY
)
echo "[download] will extract months: ${months_to_extract}"

# 4. Extract only -street.csv files for the target months.
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
patterns=()
for m in $months_to_extract; do
    patterns+=("${m}/*-street.csv")
done
unzip -q -o "$ZIP_PATH" "${patterns[@]}" -d "$EXTRACT_DIR" || true

n_files=$(find "$EXTRACT_DIR" -name '*-street.csv' | wc -l)
echo "[download] extracted ${n_files} street-level CSV files"
if [[ "$n_files" -eq 0 ]]; then
    echo "[download] ERROR: no CSVs extracted — archive structure may have changed" >&2
    exit 1
fi
