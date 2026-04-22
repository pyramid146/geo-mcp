#!/usr/bin/env bash
# Fetch the latest OS Boundary-Line (ESRI Shapefile / GB) from the OS
# Data Hub Downloads API. Idempotent — if the local zip matches the
# API-reported md5, re-runs are a no-op.
#
# Boundary-Line is released twice a year (May and October). The download
# API auto-serves the latest release, so this script never needs updating
# for a new release — just rerun it.
set -euo pipefail

readonly PRODUCT="BoundaryLine"
readonly FORMAT="ESRI%C2%AE+Shapefile"
readonly AREA="GB"
readonly LIST_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads"
readonly DOWNLOAD_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/boundary_line"
readonly ZIP_PATH="${DEST_DIR}/bdline_essh_gb.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

manifest=$(curl -sSL --max-time 30 "$LIST_URL")
expected_md5=$(echo "$manifest" | python3 -c "import json, sys; v = [d for d in json.load(sys.stdin) if d.get('format') == 'ESRI® Shapefile' and d.get('area') == '$AREA'][0]; print(v['md5'])")
expected_size=$(echo "$manifest" | python3 -c "import json, sys; v = [d for d in json.load(sys.stdin) if d.get('format') == 'ESRI® Shapefile' and d.get('area') == '$AREA'][0]; print(v['size'])")
echo "[download] OS API reports: md5=${expected_md5}, size=${expected_size}"

if [[ -f "$ZIP_PATH" ]]; then
    local_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$local_md5" == "$expected_md5" ]]; then
        echo "[download] Boundary-Line already present and md5 matches. Skipping."
    else
        echo "[download] Local md5 (${local_md5}) != API md5. Re-fetching."
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
    actual_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$actual_md5" != "$expected_md5" ]]; then
        echo "[download] ERROR: md5 mismatch after download (got ${actual_md5}, expected ${expected_md5})" >&2
        exit 1
    fi
fi

if [[ ! -d "$EXTRACT_DIR" ]] || [[ -z "$(find "$EXTRACT_DIR" -name 'country_region.shp' -print -quit 2>/dev/null)" ]]; then
    echo "[download] Extracting to ${EXTRACT_DIR}"
    rm -rf "$EXTRACT_DIR"
    mkdir -p "$EXTRACT_DIR"
    unzip -q -o "$ZIP_PATH" -d "$EXTRACT_DIR"
fi

data_dir=$(find "$EXTRACT_DIR" -name 'country_region.shp' -printf '%h\n' | head -1)
if [[ -z "$data_dir" ]]; then
    echo "[download] ERROR: country_region.shp not found after extraction" >&2
    exit 1
fi

echo "[download] Shapefiles in: ${data_dir}"
echo "[download] Present:"
find "$data_dir" -maxdepth 1 -name '*.shp' -printf '  %f\n' | sort
