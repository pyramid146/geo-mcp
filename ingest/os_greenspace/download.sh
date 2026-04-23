#!/usr/bin/env bash
# Fetch OS Open Greenspace (GeoPackage, GB) from the OS Downloads API.
# ~57 MB zipped, contains every park, sports field, allotment, play
# space, golf course, religious ground, and cemetery nationally.
set -euo pipefail

readonly PRODUCT="OpenGreenspace"
readonly FORMAT="GeoPackage"
readonly AREA="GB"
readonly LIST_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads"
readonly DOWNLOAD_URL="https://api.os.uk/downloads/v1/products/${PRODUCT}/downloads?area=${AREA}&format=${FORMAT}&redirect"

readonly DEST_DIR="/data/ingest/os_greenspace"
readonly ZIP_PATH="${DEST_DIR}/opgrsp_gpkg.zip"
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
        rm -f "$ZIP_PATH"
    fi
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "[download] Fetching ${DOWNLOAD_URL}"
    curl --fail --location --progress-bar -o "${ZIP_PATH}.part" "$DOWNLOAD_URL"
    mv "${ZIP_PATH}.part" "$ZIP_PATH"
fi

gpkg_name=$(unzip -l "$ZIP_PATH" | awk '/\.gpkg$/ {print $NF; exit}')
if [[ ! -f "${EXTRACT_DIR}/${gpkg_name}" ]]; then
    mkdir -p "$EXTRACT_DIR"
    unzip -o -j "$ZIP_PATH" "${gpkg_name}" -d "$EXTRACT_DIR"
fi
chmod 644 "${EXTRACT_DIR}/${gpkg_name}" 2>/dev/null || true

echo "[download] GPKG at: ${EXTRACT_DIR}/${gpkg_name}"
ogrinfo "${EXTRACT_DIR}/${gpkg_name}" 2>/dev/null | awk '/^[0-9]+:/ {print "  "$0}'
