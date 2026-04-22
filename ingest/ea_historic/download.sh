#!/usr/bin/env bash
# Fetch the EA "Recorded Flood Outlines" GeoPackage from data.gov.uk.
# This is the per-event product (31k named flood events with dates,
# sources, causes since 1946). The related "Historic Flood Map" is
# just the binary composite — we prefer the event-level detail here.
# ~80 MB zipped; CKAN API resolves the current release URL.
set -euo pipefail

readonly CKAN_ID="recorded-flood-outlines1"
readonly CKAN_URL="https://ckan.publishing.service.gov.uk/api/3/action/package_show?id=${CKAN_ID}"

readonly DEST_DIR="/data/ingest/ea_historic"
readonly ZIP_PATH="${DEST_DIR}/Recorded_Flood_Outlines.gpkg.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

download_url=$(curl -sSL --max-time 30 "$CKAN_URL" | python3 -c "
import json, sys
resources = json.load(sys.stdin)['result']['resources']
gpkg = next(r for r in resources if r.get('name','').endswith('.gpkg.zip'))
print(gpkg['url'])
")
echo "[download] Resolved URL: ${download_url}"

if [[ -f "$ZIP_PATH" ]]; then
    echo "[download] Zip already present. Skipping (rm to force)."
else
    echo "[download] Fetching"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$download_url"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name '*.gpkg' -print -quit 2>/dev/null)" ]]; then
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

gpkg=$(find "$EXTRACT_DIR" -name '*.gpkg' | head -1)
echo "[download] GeoPackage: ${gpkg}"
