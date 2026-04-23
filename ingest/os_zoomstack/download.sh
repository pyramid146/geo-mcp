#!/usr/bin/env bash
# Fetch OS Open Zoomstack (GeoPackage, GB) from the OS Data Hub
# Downloads API. Idempotent on md5 match. Full zip is ~4.3 GB.
#
# Zoomstack ships many layers (roads, railways, woodland, foreshore,
# contours, etc.). We deliberately load only the `building` layer in
# load.sh — it's the one that unlocks meaningful property-level tools.
# Other layers stay in the extracted GeoPackage for future ingests
# without re-downloading.
set -euo pipefail

readonly PRODUCT="OpenZoomstack"
readonly FORMAT="GeoPackage"
readonly AREA="GB"
readonly LIST_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads"
readonly DOWNLOAD_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/os_zoomstack"
readonly ZIP_PATH="${DEST_DIR}/os_open_zoomstack.zip"
readonly EXTRACT_DIR="${DEST_DIR}/extracted"

mkdir -p "$DEST_DIR"

manifest=$(curl -sSL --max-time 30 "$LIST_URL")
expected_md5=$(echo "$manifest" | python3 -c "import json, sys; v = [d for d in json.load(sys.stdin) if d.get('format') == '$FORMAT' and d.get('area') == '$AREA'][0]; print(v['md5'])")
expected_size=$(echo "$manifest" | python3 -c "import json, sys; v = [d for d in json.load(sys.stdin) if d.get('format') == '$FORMAT' and d.get('area') == '$AREA'][0]; print(v['size'])")
echo "[download] OS API reports: md5=${expected_md5}, size=${expected_size}"

if [[ -f "$ZIP_PATH" ]]; then
    local_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$local_md5" == "$expected_md5" ]]; then
        echo "[download] already present and md5 matches. Skipping."
    else
        echo "[download] md5 mismatch (${local_md5} vs ${expected_md5}). Re-fetching."
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
    actual_md5=$(md5sum "$ZIP_PATH" | awk '{print $1}')
    if [[ "$actual_md5" != "$expected_md5" ]]; then
        echo "[download] ERROR: md5 mismatch after download" >&2
        exit 1
    fi
fi

# Extract the GeoPackage. It's a single .gpkg file inside the zip.
gpkg_name=$(unzip -l "$ZIP_PATH" | awk '/\.gpkg$/ {print $NF; exit}')
if [[ -z "$gpkg_name" ]]; then
    echo "[download] ERROR: no .gpkg inside zip" >&2
    exit 1
fi
if [[ ! -f "${EXTRACT_DIR}/${gpkg_name}" ]]; then
    echo "[download] Extracting ${gpkg_name}"
    mkdir -p "$EXTRACT_DIR"
    unzip -o -j "$ZIP_PATH" "${gpkg_name}" -d "$EXTRACT_DIR"
fi
chmod 644 "${EXTRACT_DIR}/${gpkg_name}" 2>/dev/null || true

echo "[download] GPKG at: ${EXTRACT_DIR}/${gpkg_name}"
echo "[download] Layers in the GPKG:"
ogrinfo "${EXTRACT_DIR}/${gpkg_name}" 2>/dev/null | awk '/^[0-9]+:/ {print "  "$0}' | head -20
