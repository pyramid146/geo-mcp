#!/usr/bin/env bash
# Fetch HM Land Registry's Price Paid Data "complete" CSV.
# ~5.4 GB, every residential sale in England & Wales since 1995, OGLv3.
# The URL is stable; the file is refreshed monthly with the previous
# month's transactions.
#
# Idempotent on last-modified: re-runs skip when the local file matches
# the HEAD Last-Modified timestamp.
set -euo pipefail

readonly SRC_URL="http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-complete.csv"
readonly DEST_DIR="/data/ingest/ppd"
readonly CSV_PATH="${DEST_DIR}/pp-complete.csv"

mkdir -p "$DEST_DIR"

remote_modified=$(curl -sIL --max-time 30 "$SRC_URL" | awk -F': ' 'BEGIN{IGNORECASE=1} /^last-modified/ {gsub("\r",""); print $2}' | tail -1)
echo "[download] remote last-modified: ${remote_modified}"

if [[ -f "$CSV_PATH" ]]; then
    if [[ -f "${CSV_PATH}.mtime" ]] && [[ "$(cat "${CSV_PATH}.mtime")" == "$remote_modified" ]]; then
        echo "[download] local copy is current. Skipping."
        exit 0
    fi
    echo "[download] local copy stale; re-fetching."
fi

echo "[download] Fetching ${SRC_URL} (≈ 5.4 GB)"
curl --fail --location --progress-bar -o "${CSV_PATH}.part" "$SRC_URL"
mv "${CSV_PATH}.part" "$CSV_PATH"
echo "$remote_modified" > "${CSV_PATH}.mtime"

echo "[download] $(wc -l < "$CSV_PATH") rows, $(du -h "$CSV_PATH" | awk '{print $1}')"
