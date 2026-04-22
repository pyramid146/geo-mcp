#!/usr/bin/env bash
# Fetch the latest "Flood Map for Planning - Flood Zones" GeoPackage from
# the Defra Data Services Platform. Idempotent — skips the download when
# the local file matches the API-reported size.
#
# The dataset is a composite of Flood Zones 2 and 3 (Zone 1 is implicitly
# "everywhere else"). Replaces the retired Flood-Zone-2 and Flood-Zone-3
# datasets that were separate downloads pre-2025.
#
# Update cycle: quarterly-ish. The CKAN dataset id below is stable;
# resource URLs change with each release. download.sh queries the CKAN
# API so it always picks up the latest.
set -euo pipefail

readonly CKAN_ID="flood-map-for-planning-flood-zones1"
readonly CKAN_URL="https://ckan.publishing.service.gov.uk/api/3/action/package_show?id=${CKAN_ID}"

readonly DEST_DIR="/data/ingest/ea_flood"
readonly ZIP_PATH="${DEST_DIR}/Flood_Map_for_Planning_Flood_Zones.gpkg.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

download_url=$(curl -sSL --max-time 30 "$CKAN_URL" | python3 -c "
import json, sys
resources = json.load(sys.stdin)['result']['resources']
gpkg = next(r for r in resources if r.get('name','').endswith('.gpkg.zip'))
print(gpkg['url'])
")
echo "[download] Resolved URL: ${download_url}"

# Defra's download endpoint rejects HEAD and is flaky on Range requests, so
# skip size probing. Idempotency is based on the extracted .gpkg existing;
# to force a refresh, delete /data/ingest/ea_flood/ and rerun.
if [[ -f "$ZIP_PATH" ]]; then
    echo "[download] Zip already present at ${ZIP_PATH}. Skipping download."
else
    echo "[download] Fetching ${download_url} (expect ~1 GB)"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$download_url"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name '*.gpkg' -print -quit 2>/dev/null)" ]]; then
    echo "[download] Extracting to ${EXTRACT_DIR}"
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

gpkg_path=$(find "$EXTRACT_DIR" -name '*.gpkg' | head -1)
if [[ -z "$gpkg_path" ]]; then
    echo "[download] ERROR: no .gpkg file found after extraction" >&2
    exit 1
fi
echo "[download] GeoPackage: ${gpkg_path}"
