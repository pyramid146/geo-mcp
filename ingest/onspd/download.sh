#!/usr/bin/env bash
# Fetch the latest ONS Postcode Directory (ONSPD) release from the ONS
# Open Geography Portal, into /data/ingest/onspd/. Idempotent — if the
# zip already exists at the expected size, re-runs are a no-op.
#
# Release cadence is quarterly (Feb / May / Aug / Nov). To adopt a new
# release: find its ArcGIS item id on geoportal.statistics.gov.uk (the
# URL path after /datasets/) and update ONSPD_VERSION + ONSPD_ITEM_ID
# below. The old values stay in git history.
set -euo pipefail

readonly ONSPD_VERSION="FEB_2026"
readonly ONSPD_ITEM_ID="3080229224424c9cb53c0b48f5a64d27"
readonly ONSPD_URL="https://www.arcgis.com/sharing/rest/content/items/${ONSPD_ITEM_ID}/data"

readonly DEST_DIR="/data/ingest/onspd"
readonly ZIP_PATH="${DEST_DIR}/ONSPD_${ONSPD_VERSION}.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted_${ONSPD_VERSION}"

mkdir -p "$DEST_DIR"

remote_size=$(curl -sI -L --max-time 30 "$ONSPD_URL" \
    | awk -F': ' 'tolower($1)=="content-length" {gsub("\r",""); print $2}' \
    | tail -1)

if [[ -f "$ZIP_PATH" ]]; then
    local_size=$(stat -c %s "$ZIP_PATH")
    if [[ -n "$remote_size" && "$local_size" == "$remote_size" ]]; then
        echo "[download] ONSPD ${ONSPD_VERSION} already present (${local_size} bytes). Skipping download."
    else
        echo "[download] Local zip size (${local_size}) differs from remote (${remote_size:-unknown}). Re-fetching."
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${ONSPD_URL} (${remote_size:-?} bytes) → ${ZIP_PATH}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$ONSPD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name 'ONSPD_*.csv' -print -quit 2>/dev/null)" ]]; then
    echo "[download] Extracting to ${EXTRACT_DIR}"
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

csv_path=$(find "$EXTRACT_DIR" -path '*/Data/ONSPD_*_UK.csv' | head -1)
if [[ -z "$csv_path" ]]; then
    csv_path=$(find "$EXTRACT_DIR" -path '*/Data/ONSPD_*.csv' | head -1)
fi
if [[ -z "$csv_path" ]]; then
    echo "[download] ERROR: no ONSPD CSV found under ${EXTRACT_DIR}/**/Data/" >&2
    exit 1
fi

echo "[download] Ready: ${csv_path}"
echo "[download] Version: ${ONSPD_VERSION}"
