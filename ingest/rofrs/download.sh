#!/usr/bin/env bash
# Fetch the "Risk of Flooding from Rivers and Sea — Postcodes in Areas at
# Risk" CSV from data.gov.uk. ~4.7 MB zipped; resolves the current
# resource URL via the CKAN API so the script needs no edits across
# releases (cadence is roughly annual).
set -euo pipefail

readonly CKAN_ID="risk-of-flooding-from-rivers-and-sea-postcodes-in-areas-at-risk2"
readonly CKAN_URL="https://ckan.publishing.service.gov.uk/api/3/action/package_show?id=${CKAN_ID}"

readonly DEST_DIR="/data/ingest/rofrs"
readonly ZIP_PATH="${DEST_DIR}/RoFRS_Postcodes_in_Areas_at_Risk.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

download_url=$(curl -sSL --max-time 30 "$CKAN_URL" | python3 -c "
import json, sys
resources = json.load(sys.stdin)['result']['resources']
zip_res = next(r for r in resources if r.get('name','').endswith('.zip'))
print(zip_res['url'])
")
echo "[download] Resolved URL: ${download_url}"

if [[ -f "$ZIP_PATH" ]]; then
    echo "[download] Zip already present. Skipping (rm to force)."
else
    echo "[download] Fetching ${download_url}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$download_url"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name '*.csv' -print -quit 2>/dev/null)" ]]; then
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

csv=$(find "$EXTRACT_DIR" -name '*.csv' | head -1)
echo "[download] CSV: ${csv}"
echo "[download] Rows: $(wc -l < "$csv")"
