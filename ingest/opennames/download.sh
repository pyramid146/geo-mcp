#!/usr/bin/env bash
# Fetch OS OpenNames (CSV bundle, GB) from the OS Downloads API.
# ~103 MB zipped; extracts to many per-100km-square CSVs.
set -euo pipefail

readonly PRODUCT="OpenNames"
readonly FORMAT="CSV"
readonly AREA="GB"
readonly LIST_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads"
readonly DOWNLOAD_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/opennames"
readonly ZIP_PATH="${DEST_DIR}/opname_csv_gb.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

manifest=$(curl -sSL --max-time 30 "$LIST_URL")
expected_md5=$(echo "$manifest" | python3 -c "
import json, sys
items = json.load(sys.stdin)
m = next(d for d in items if d.get('format')=='CSV' and d.get('area')=='$AREA')
print(m['md5'])
")
echo "[download] OS API reports md5=${expected_md5}"

if [[ -f "$ZIP_PATH" ]]; then
    local_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$local_md5" == "$expected_md5" ]]; then
        echo "[download] Zip already present and md5 matches. Skipping."
    else
        echo "[download] md5 mismatch — re-fetching"
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name '*.csv' -print -quit 2>/dev/null)" ]]; then
    echo "[download] Extracting"
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

csv_count=$(find "$EXTRACT_DIR" -name '*.csv' | wc -l)
echo "[download] CSV files: ${csv_count}"
